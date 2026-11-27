"""Parse and validate unit-explicit JSON case files, converting to SI once."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from .units import GPA_TO_PA, MM_TO_M, MPA_TO_PA

SCHEMA_VERSION = "1.0"

_TOP_REQUIRED = (
    "schema_version",
    "case_id",
    "beam",
    "constraints",
    "stock_thicknesses_mm",
    "materials",
)
_TOP_OPTIONAL = ("title", "description")
_BEAM_REQUIRED = ("length_mm", "width_mm", "tip_force_n")
_CONSTRAINT_REQUIRED = ("max_tip_deflection_mm", "min_yield_safety_factor")
_MATERIAL_REQUIRED = (
    "id",
    "name",
    "provenance",
    "elastic_modulus_gpa",
    "density_kg_m3",
    "yield_strength_mpa",
)
_MATERIAL_OPTIONAL = ("catalog_id",)
_UNIT_HINT = (
    "Use an explicit unit suffix such as _mm, _gpa, _mpa or _kg_m3. "
    "A generic units field is not accepted."
)


@dataclass(frozen=True)
class ValidationIssue:
    """One machine-readable problem with a supplied case."""

    path: str
    code: str
    message: str

    def as_dict(self) -> dict[str, str]:
        return {"path": self.path, "code": self.code, "message": self.message}


class CaseValidationError(ValueError):
    """Raised when a case is structurally valid JSON but not a valid case."""

    def __init__(self, issues: Sequence[ValidationIssue]) -> None:
        self.issues = tuple(issues)
        summary = "; ".join(f"{issue.path}: {issue.message}" for issue in self.issues)
        super().__init__(summary)


@dataclass(frozen=True)
class Beam:
    """Beam geometry and load, normalized to SI."""

    length_m: float
    width_m: float
    tip_force_n: float


@dataclass(frozen=True)
class Constraints:
    """Acceptance limits, normalized to SI where applicable."""

    max_tip_deflection_m: float
    min_yield_safety_factor: float


@dataclass(frozen=True)
class Material:
    """One synthetic or datasheet-backed material record, normalized to SI."""

    material_id: str
    name: str
    provenance: str
    elastic_modulus_pa: float
    density_kg_m3: float
    yield_strength_pa: float
    catalog_id: str | None = None
    _source_property: dict[str, Any] | None = None


@dataclass(frozen=True)
class Case:
    """A fully validated case with every physical quantity in SI units."""

    schema_version: str
    case_id: str
    title: str
    description: str
    beam: Beam
    constraints: Constraints
    stock_thicknesses_m: tuple[float, ...]
    materials: tuple[Material, ...]


def _issue(
    issues: list[ValidationIssue],
    path: str,
    code: str,
    message: str,
) -> None:
    issues.append(ValidationIssue(path=path, code=code, message=message))


def _require_object(value: Any, path: str, issues: list[ValidationIssue]) -> Mapping[str, Any] | None:
    if not isinstance(value, dict):
        _issue(issues, path, "wrong_type", "Expected a JSON object.")
        return None
    return value


def _check_keys(
    obj: Mapping[str, Any],
    path: str,
    required: Sequence[str],
    optional: Sequence[str],
    issues: list[ValidationIssue],
) -> None:
    allowed = set(required) | set(optional)
    for key in required:
        if key not in obj:
            _issue(
                issues,
                f"{path}.{key}",
                "missing_field",
                "Required field is missing.",
            )
    for key in obj:
        if key not in allowed:
            _issue(
                issues,
                f"{path}.{key}",
                "unknown_field",
                f"Unknown field {key!r}. {_UNIT_HINT}",
            )


def _string(
    value: Any,
    path: str,
    issues: list[ValidationIssue],
    *,
    allow_empty: bool,
) -> str:
    if not isinstance(value, str):
        _issue(issues, path, "wrong_type", "Expected a string.")
        return ""
    text = value.strip()
    if not allow_empty and not text:
        _issue(issues, path, "empty_value", "Must not be empty.")
    return text


def _number(value: Any, path: str, issues: list[ValidationIssue]) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _issue(
            issues,
            path,
            "wrong_type",
            "Expected a finite JSON number (not a string or boolean).",
        )
        return None
    try:
        number = float(value)
    except (OverflowError, ValueError):
        _issue(
            issues,
            path,
            "non_finite",
            "Number is outside the finite binary64 range.",
        )
        return None
    if not math.isfinite(number):
        _issue(issues, path, "non_finite", "Number must be finite.")
        return None
    return number


def _positive_number(value: Any, path: str, issues: list[ValidationIssue]) -> float | None:
    number = _number(value, path, issues)
    if number is None:
        return None
    if number <= 0.0:
        _issue(issues, path, "not_positive", "Number must be greater than zero.")
        return None
    return number


def _converted_si(
    value: float | None,
    multiplier: float,
    path: str,
    issues: list[ValidationIssue],
) -> float | None:
    """Convert at the input boundary and require a finite, positive SI value."""
    if value is None:
        return None
    try:
        converted = value * multiplier
    except OverflowError:
        converted = math.inf
    if not math.isfinite(converted) or converted <= 0.0:
        _issue(
            issues,
            path,
            "out_of_range",
            "Converted SI value must be finite and greater than zero.",
        )
        return None
    return converted


def parse_case_document(document: Any) -> Case:
    """Validate a parsed JSON document and return a Case normalized to SI.

    Conversions happen here and nowhere else:

    * mm -> m
    * GPa -> Pa
    * MPa -> Pa

    Density is already requested in kg/m^3 and force in N.
    """
    issues: list[ValidationIssue] = []

    if not isinstance(document, dict):
        raise CaseValidationError(
            [ValidationIssue("$", "wrong_type", "The case root must be a JSON object.")]
        )

    _check_keys(document, "$", _TOP_REQUIRED, _TOP_OPTIONAL, issues)

    schema_version = _string(
        document.get("schema_version", ""),
        "$.schema_version",
        issues,
        allow_empty=False,
    )
    if schema_version and schema_version != SCHEMA_VERSION:
        _issue(
            issues,
            "$.schema_version",
            "unsupported_schema",
            f"Expected {SCHEMA_VERSION!r}; got {schema_version!r}.",
        )

    case_id = _string(
        document.get("case_id", ""),
        "$.case_id",
        issues,
        allow_empty=False,
    )
    title = _string(document.get("title", ""), "$.title", issues, allow_empty=True)
    description = _string(
        document.get("description", ""),
        "$.description",
        issues,
        allow_empty=True,
    )

    beam_obj = _require_object(document.get("beam"), "$.beam", issues)
    length_m: float | None = None
    width_m: float | None = None
    tip_force_n: float | None = None
    if beam_obj is not None:
        _check_keys(beam_obj, "$.beam", _BEAM_REQUIRED, (), issues)
        length_mm = _positive_number(beam_obj.get("length_mm"), "$.beam.length_mm", issues)
        width_mm = _positive_number(beam_obj.get("width_mm"), "$.beam.width_mm", issues)
        tip_force_n = _positive_number(
            beam_obj.get("tip_force_n"), "$.beam.tip_force_n", issues
        )
        length_m = _converted_si(length_mm, MM_TO_M, "$.beam.length_mm", issues)
        width_m = _converted_si(width_mm, MM_TO_M, "$.beam.width_mm", issues)

    constraints_obj = _require_object(
        document.get("constraints"), "$.constraints", issues
    )
    max_tip_deflection_m: float | None = None
    min_yield_safety_factor: float | None = None
    if constraints_obj is not None:
        _check_keys(
            constraints_obj, "$.constraints", _CONSTRAINT_REQUIRED, (), issues
        )
        max_deflection_mm = _positive_number(
            constraints_obj.get("max_tip_deflection_mm"),
            "$.constraints.max_tip_deflection_mm",
            issues,
        )
        min_yield_safety_factor = _positive_number(
            constraints_obj.get("min_yield_safety_factor"),
            "$.constraints.min_yield_safety_factor",
            issues,
        )
        max_tip_deflection_m = _converted_si(
            max_deflection_mm,
            MM_TO_M,
            "$.constraints.max_tip_deflection_mm",
            issues,
        )

    stock_thicknesses_m: list[float] = []
    raw_thicknesses = document.get("stock_thicknesses_mm")
    if not isinstance(raw_thicknesses, list):
        _issue(
            issues,
            "$.stock_thicknesses_mm",
            "wrong_type",
            "Expected a non-empty JSON array of thicknesses in millimetres.",
        )
    elif not raw_thicknesses:
        _issue(
            issues,
            "$.stock_thicknesses_mm",
            "empty_value",
            "At least one stock thickness is required.",
        )
    else:
        seen_thicknesses: set[float] = set()
        for index, value in enumerate(raw_thicknesses):
            path = f"$.stock_thicknesses_mm[{index}]"
            thickness_mm = _positive_number(value, path, issues)
            if thickness_mm is None:
                continue
            thickness_m = _converted_si(thickness_mm, MM_TO_M, path, issues)
            if thickness_m is None:
                continue
            if thickness_m in seen_thicknesses:
                _issue(
                    issues,
                    path,
                    "duplicate_value",
                    "Duplicate stock thickness; each option must be unique.",
                )
                continue
            seen_thicknesses.add(thickness_m)
            stock_thicknesses_m.append(thickness_m)

    materials: list[Material] = []
    raw_materials = document.get("materials")
    if not isinstance(raw_materials, list):
        _issue(
            issues,
            "$.materials",
            "wrong_type",
            "Expected a non-empty JSON array of material records.",
        )
    elif not raw_materials:
        _issue(
            issues,
            "$.materials",
            "empty_value",
            "At least one material is required.",
        )
    else:
        seen_ids: set[str] = set()
        for index, raw_material in enumerate(raw_materials):
            base_path = f"$.materials[{index}]"
            material_obj = _require_object(raw_material, base_path, issues)
            if material_obj is None:
                continue
            _check_keys(
                material_obj,
                base_path,
                _MATERIAL_REQUIRED,
                _MATERIAL_OPTIONAL,
                issues,
            )
            material_id = _string(
                material_obj.get("id", ""),
                f"{base_path}.id",
                issues,
                allow_empty=False,
            )
            name = _string(
                material_obj.get("name", ""),
                f"{base_path}.name",
                issues,
                allow_empty=False,
            )
            provenance = _string(
                material_obj.get("provenance", ""),
                f"{base_path}.provenance",
                issues,
                allow_empty=False,
            )
            modulus_gpa = _positive_number(
                material_obj.get("elastic_modulus_gpa"),
                f"{base_path}.elastic_modulus_gpa",
                issues,
            )
            density = _positive_number(
                material_obj.get("density_kg_m3"),
                f"{base_path}.density_kg_m3",
                issues,
            )
            yield_mpa = _positive_number(
                material_obj.get("yield_strength_mpa"),
                f"{base_path}.yield_strength_mpa",
                issues,
            )

            if material_id:
                if material_id in seen_ids:
                    _issue(
                        issues,
                        f"{base_path}.id",
                        "duplicate_value",
                        f"Duplicate material id {material_id!r}; ids must be unique.",
                    )
                else:
                    seen_ids.add(material_id)

            modulus_pa = _converted_si(
                modulus_gpa,
                GPA_TO_PA,
                f"{base_path}.elastic_modulus_gpa",
                issues,
            )
            yield_pa = _converted_si(
                yield_mpa,
                MPA_TO_PA,
                f"{base_path}.yield_strength_mpa",
                issues,
            )
            catalog_id = _string(
                material_obj.get("catalog_id", ""),
                f"{base_path}.catalog_id",
                issues,
                allow_empty=True,
            )

            if None not in (modulus_pa, density, yield_pa):
                materials.append(
                    Material(
                        material_id=material_id,
                        name=name,
                        provenance=provenance,
                        elastic_modulus_pa=modulus_pa,
                        density_kg_m3=density,
                        yield_strength_pa=yield_pa,
                        catalog_id=catalog_id if catalog_id else None,
                        _source_property={"catalog_id": catalog_id} if catalog_id else None,
                    )
                )

    if issues:
        raise CaseValidationError(issues)

    # All fields are present and valid at this point.
    assert length_m is not None
    assert width_m is not None
    assert tip_force_n is not None
    assert max_tip_deflection_m is not None
    assert min_yield_safety_factor is not None
    assert materials and stock_thicknesses_m

    return Case(
        schema_version=SCHEMA_VERSION,
        case_id=case_id,
        title=title,
        description=description,
        beam=Beam(
            length_m=length_m,
            width_m=width_m,
            tip_force_n=tip_force_n,
        ),
        constraints=Constraints(
            max_tip_deflection_m=max_tip_deflection_m,
            min_yield_safety_factor=min_yield_safety_factor,
        ),
        stock_thicknesses_m=tuple(stock_thicknesses_m),
        materials=tuple(materials),
    )


def load_case_file(path: str | Path) -> Case:
    """Load a UTF-8/BOM JSON case file and validate it.

    Malformed JSON is reported as a CaseValidationError with code
    ``invalid_json``. File-system errors propagate as OSError.
    """
    # utf-8-sig accepts both plain UTF-8 and the BOM emitted by Windows PowerShell.
    text = Path(path).read_text(encoding="utf-8-sig")
    try:
        document = json.loads(text)
    except json.JSONDecodeError as exc:
        raise CaseValidationError(
            [
                ValidationIssue(
                    path="$",
                    code="invalid_json",
                    message=(
                        f"Invalid JSON at line {exc.lineno}, column {exc.colno}: "
                        f"{exc.msg}."
                    ),
                )
            ]
        ) from exc
    except (ValueError, OverflowError) as exc:
        raise CaseValidationError(
            [
                ValidationIssue(
                    path="$",
                    code="invalid_json",
                    message=f"Invalid JSON value: {exc}.",
                )
            ]
        ) from exc
    return parse_case_document(document)
