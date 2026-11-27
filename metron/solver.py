"""Evaluate every material/thickness pair and select the lightest feasible one."""

from __future__ import annotations

import math
from dataclasses import dataclass

from .beam import (
    beam_mass,
    maximum_bending_stress,
    second_moment_of_area,
    tip_deflection,
    yield_safety_factor,
)
from .case import Case, Material

STATUS_FEASIBLE = "feasible"
STATUS_NO_FEASIBLE_CANDIDATE = "no_feasible_candidate"

DEFLECTION_REJECTION = "tip_deflection_exceeds_limit"
STRENGTH_REJECTION = "yield_safety_below_minimum"

TIE_BREAK_RULE = (
    "Lowest mass_kg. Exact ties are resolved by material_id in ascending "
    "Unicode code-point order, then thickness_m in ascending order."
)


def _parse_interval(ti: str) -> tuple[float, float, bool, bool] | None:
    """Parse thickness interval notation (a-b], [a-b], (a-b), [a-b].

    Returns (lo, hi, left_inclusive, right_inclusive) or None if unparseable.
    """
    try:
        inner = ti.strip("()[]")
        lo_str, hi_str = inner.split(",")
        lo = float(lo_str.strip())
        hi = float(hi_str.strip().rstrip("]"))
        left_incl = ti.startswith("[")
        right_incl = ti.endswith("]")
        return lo, hi, left_incl, right_incl
    except (ValueError, IndexError):
        return None


def _is_within_interval(
    lo: float, hi: float, left_incl: bool, right_incl: bool,
    thickness_m: float,
) -> bool:
    """Check if thickness_m falls within [lo, hi] with given inclusivity."""
    if left_incl and right_incl:
        return lo <= thickness_m <= hi
    elif left_incl and not right_incl:
        return lo <= thickness_m < hi
    elif not left_incl and right_incl:
        return lo < thickness_m <= hi
    else:  # not left_incl and not right_incl
        return lo < thickness_m < hi


class NumericalRangeError(ValueError):
    """Finite inputs produced a result outside the representable float range."""


def _resolve_yield_from_catalog(
    material: Material,
    thickness_m: float,
    catalog: dict | None,
) -> tuple[float, str, str | None, bool]:
    """Resolve the yield strength for a given thickness using the material catalog.

    Returns (yield_pa, typical_or_minimum, source_note, interval_applies).
    interval_applies is True only when thickness_m (in metres) falls within the
    documented thickness interval (in millimetres) for the yield value. If outside
    the interval, the nominal yield is returned with interval_applies=False,
    indicating the value is extrapolated beyond its validated range.

    If no catalog or no thickness-dependent data, returns the material's
    nominal yield_strength_pa with label 'typical' and None source_note,
    and interval_applies=False.
    """
    typical_or_minimum = "typical"
    yield_pa = material.yield_strength_pa
    source_note = None
    interval_applies = False

    catalog_id = None
    sp = getattr(material, "_source_property", None) or {}
    if sp and isinstance(sp, dict):
        catalog_id = sp.get("catalog_id")

    if not catalog_id or catalog is None:
        return yield_pa, typical_or_minimum, source_note, interval_applies

    # Convert thickness from metres to millimetres for interval comparison
    thickness_mm = thickness_m * 1e3

    # Look up the material record in the catalog
    mat_record = catalog.get("materials", [])
    selected_mat = None
    for m in mat_record:
        if m.get("id") == catalog_id:
            selected_mat = m
            break

    if selected_mat is None:
        # Catalog ID not found; use nominal value, mark as typical
        return yield_pa, typical_or_minimum, source_note, interval_applies

    # Resolve yield from catalog properties
    for prop in selected_mat.get("properties", []):
        if prop.get("property") == "yield_strength_mpa":
            ti = prop.get("thickness_interval_mm")
            if ti is not None:
                parsed = _parse_interval(ti)
                if parsed is not None:
                    lo, hi, left_incl, right_incl = parsed
                    if _is_within_interval(lo, hi, left_incl, right_incl, thickness_mm):
                        # Thickness within documented interval (both in mm)
                        resolved_mpa = prop.get("value_mpa")
                        if resolved_mpa is not None:
                            yield_pa = resolved_mpa * 1e6
                        else:
                            typical_or_minimum = prop.get(
                                "typical_or_minimum", "typical"
                            )
                        source_note = prop.get("source_applicability", None)
                        interval_applies = True
                else:
                    # Unparseable interval; treat as applying broadly
                    resolved_mpa = prop.get("value_mpa")
                    if resolved_mpa is not None:
                        yield_pa = resolved_mpa * 1e6
                    typical_or_minimum = prop.get("typical_or_minimum", "typical")
                    source_note = prop.get("source_applicability", None)
                    interval_applies = True
            else:
                # No thickness interval specified; value applies broadly
                resolved_mpa = prop.get("value_mpa")
                if resolved_mpa is not None:
                    yield_pa = resolved_mpa * 1e6
                typical_or_minimum = prop.get("typical_or_minimum", "typical")
                source_note = prop.get("source_applicability", None)
                interval_applies = True

    # If interval does not apply, use the material's nominal yield strength
    if not interval_applies:
        yield_pa = material.yield_strength_pa
        typical_or_minimum = "typical"
        source_note = None

    return yield_pa, typical_or_minimum, source_note, interval_applies


def _resolve_property_from_catalog(
    material: Material,
    thickness_m: float,
    catalog: dict | None,
    property_name: str,
    default_value: float,
) -> float:
    """Resolve a material property (density, modulus, or yield) from the catalog.

    If the material has a catalog_id and the catalog contains the requested
    property with a thickness interval, the catalog value is used if thickness
    falls within the interval. Otherwise, the material's default value is used.

    Parameters
    ----------
    material : Material
        The material instance with optional catalog_id.
    thickness_m : float
        Thickness in metres for interval checking.
    catalog : dict or None
        Material catalog dict as loaded from materials_catalog.json.
    property_name : str
        Name of the property to resolve: "yield_strength_mpa", "elastic_modulus_gpa",
        or "density_kg_m3".
    default_value : float
        The material's default value to use if catalog is not applicable.

    Returns
    -------
    float
        The resolved property value in SI units.
    """
    catalog_id = None
    sp = getattr(material, "_source_property", None) or {}
    if sp and isinstance(sp, dict):
        catalog_id = sp.get("catalog_id")

    if not catalog_id or catalog is None:
        return default_value

    # Convert thickness from metres to millimetres for interval comparison
    thickness_mm = thickness_m * 1e3

    # Look up the material record in the catalog
    mat_record = catalog.get("materials", [])
    selected_mat = None
    for m in mat_record:
        if m.get("id") == catalog_id:
            selected_mat = m
            break

    if selected_mat is None:
        # Catalog ID not found; use default value
        return default_value

    # Resolve the requested property from catalog
    for prop in selected_mat.get("properties", []):
        if prop.get("property") == property_name:
            ti = prop.get("thickness_interval_mm")
            if ti is not None:
                parsed = _parse_interval(ti)
                if parsed is not None:
                    lo, hi, left_incl, right_incl = parsed
                    if _is_within_interval(lo, hi, left_incl, right_incl, thickness_mm):
                        # Thickness within documented interval
                        resolved = prop.get("value_mpa") if property_name == "yield_strength_mpa" else \
                                   prop.get("value_gpa") if property_name == "elastic_modulus_gpa" else \
                                   prop.get("value_kg_m3")
                        if resolved is not None:
                            if property_name == "yield_strength_mpa":
                                return resolved * 1e6
                            elif property_name == "elastic_modulus_gpa":
                                return resolved * 1e9
                            elif property_name == "density_kg_m3":
                                return resolved
                # If interval doesn't apply, fall through to default
            else:
                # No thickness interval; catalog value applies broadly
                resolved = prop.get("value_mpa") if property_name == "yield_strength_mpa" else \
                           prop.get("value_gpa") if property_name == "elastic_modulus_gpa" else \
                           prop.get("value_kg_m3")
                if resolved is not None:
                    if property_name == "yield_strength_mpa":
                        return resolved * 1e6
                    elif property_name == "elastic_modulus_gpa":
                        return resolved * 1e9
                    elif property_name == "density_kg_m3":
                        return resolved
                # If no resolved value in property, fall through to default

    # Catalog record found but property not found or interval not applicable;
    # use the material's default value
    return default_value


def _require_representable(
    values: dict[str, float],
    material_id: str,
    thickness_m: float,
) -> None:
    for name, value in values.items():
        if not math.isfinite(value) or value <= 0.0:
            raise NumericalRangeError(
                f"Calculation of {name} for material {material_id!r} at "
                f"thickness {thickness_m * 1.0e3:g} mm produced a non-finite "
                "or non-positive value. The inputs are outside the numeric "
                "range supported by this model."
            )


@dataclass(frozen=True)
class CandidateResult:
    """One material and one stock thickness, evaluated in SI."""

    material: Material
    thickness_m: float
    second_moment_m4: float
    max_bending_stress_pa: float
    tip_deflection_m: float
    mass_kg: float
    yield_safety_factor: float
    deflection_passes: bool
    yield_passes: bool
    rejection_codes: tuple[str, ...]
    outcome_category: str
    governing_property: str | None
    governing_source: str | None
    uses_typical: bool
    reference_note: str | None

    @property
    def meets_all_constraints(self) -> bool:
        return not self.rejection_codes

    @property
    def selection_key(self) -> tuple[float, str, float]:
        """Deterministic ordering used only to pick among feasible candidates."""
        return (self.mass_kg, self.material.material_id, self.thickness_m)


@dataclass(frozen=True)
class Evaluation:
    """The complete candidate set and the deterministic selection outcome."""

    case: Case
    candidates: tuple[CandidateResult, ...]
    selected: CandidateResult | None
    status: str

    @property
    def feasible_candidates(self) -> tuple[CandidateResult, ...]:
        return tuple(c for c in self.candidates if c.meets_all_constraints)


def evaluate_case(
    case: Case,
    *,
    catalog: dict | None = None,
) -> Evaluation:
    """Evaluate all pairs and choose the lightest that satisfies both limits.

    A candidate passes a limit when it is equal to it (inclusive boundary).
    No value is rounded before comparison or selection.

    Parameters
    ----------
    case : Case
        The validated case with geometry, constraints, and materials.
    catalog : dict or None
        Optional material catalog dict as loaded from materials_catalog.json.
        When provided, thickness-dependent yield resolution and source
        citations are activated for materials that reference the catalog.

    Returns
    -------
    Evaluation
        The complete candidate set and the deterministic selection outcome.
    """
    beam = case.beam
    limits = case.constraints
    candidates: list[CandidateResult] = []

    for material in case.materials:
        sp = getattr(material, "_source_property", None) or {}
        has_catalog_ref = sp.get("catalog_id") is not None
        for thickness_m in case.stock_thicknesses_m:
            try:
                inertia = second_moment_of_area(beam.width_m, thickness_m)
                stress = maximum_bending_stress(
                    beam.tip_force_n,
                    beam.length_m,
                    beam.width_m,
                    thickness_m,
                )
                # Resolve density and modulus from catalog if material references it
                modulus_pa = _resolve_property_from_catalog(
                    material, thickness_m, catalog, "elastic_modulus_gpa", material.elastic_modulus_pa
                )
                density_kg_m3 = _resolve_property_from_catalog(
                    material, thickness_m, catalog, "density_kg_m3", material.density_kg_m3
                )
                deflection = tip_deflection(
                    beam.tip_force_n,
                    beam.length_m,
                    beam.width_m,
                    thickness_m,
                    modulus_pa,
                )
                mass = beam_mass(
                    density_kg_m3,
                    beam.width_m,
                    thickness_m,
                    beam.length_m,
                )
                # Resolve yield considering thickness and catalog
                yield_pa, typical_or_minimum, source_note, interval_applies = (
                    _resolve_yield_from_catalog(material, thickness_m, catalog)
                )
                safety = yield_safety_factor(yield_pa, stress)
            except (ArithmeticError, ValueError) as exc:
                raise NumericalRangeError(
                    f"Calculation for material {material.material_id!r} at "
                    f"thickness {thickness_m * 1.0e3:g} mm failed in the "
                    f"representable numeric range: {exc}"
                ) from exc

            _require_representable(
                {
                    "second_moment_of_area": inertia,
                    "maximum_bending_stress": stress,
                    "tip_deflection": deflection,
                    "mass": mass,
                    "yield_safety_factor": safety,
                },
                material.material_id,
                thickness_m,
            )

            deflection_passes = deflection <= limits.max_tip_deflection_m
            yield_passes = safety >= limits.min_yield_safety_factor

            # Determine outcome category and governing property/source
            outcome_category: str
            governing_property: str | None = None
            governing_source: str | None = None
            uses_typical = False

            if not deflection_passes:
                outcome_category = "fails an engineering constraint"
                governing_property = "tip_deflection"
            elif not yield_passes:
                outcome_category = "fails an engineering constraint"
                governing_property = "yield_safety_factor"
                # Note whether we used typical or minimum yield
                uses_typical = typical_or_minimum == "typical"
            elif has_catalog_ref and interval_applies and source_note is not None:
                # Passes and uses catalog-referenced data within applicability
                outcome_category = "passes under the stated assumptions"
                governing_property = "yield_safety_factor (from catalog)"
                governing_source = source_note
                uses_typical = typical_or_minimum == "typical"
            elif has_catalog_ref and not interval_applies:
                # Passes but uses catalog yield outside its documented thickness range
                outcome_category = "lacks applicable evidence"
                governing_property = "yield_safety_factor (extrapolated)"
                governing_source = (
                    f"yield from catalog interval not applicable at "
                    f"{thickness_m * 1.0e3:g} mm"
                )
                uses_typical = typical_or_minimum == "typical"
            else:
                outcome_category = "passes under the stated assumptions"

            rejection_codes: list[str] = []
            if not deflection_passes:
                rejection_codes.append(DEFLECTION_REJECTION)
            if not yield_passes:
                rejection_codes.append(STRENGTH_REJECTION)
            # A catalog-backed candidate with thickness outside its documented
            # interval is ineligible, even if the nominal yield would pass.
            if has_catalog_ref and not interval_applies:
                rejection_codes.append("lacks_applicable_evidence")

            # Build a reference note for the output
            reference_note: str | None = None
            if source_note is not None:
                reference_note = f"governed by {source_note}"
            elif typical_or_minimum == "minimum" and has_catalog_ref:
                reference_note = (
                    f"using minimum yield ({typical_or_minimum}) for thickness "
                    f"{thickness_m * 1.0e3:g} mm"
                )
            elif has_catalog_ref and interval_applies:
                reference_note = (
                    f"using typical yield ({typical_or_minimum}) from catalog, "
                    "interval applies"
                )
            elif has_catalog_ref and not interval_applies:
                reference_note = (
                    f"using typical yield ({typical_or_minimum}) from catalog, "
                    "interval not applicable at %s mm"
                    % (thickness_m * 1.0e3)
                )
            else:
                reference_note = None

            candidates.append(
                CandidateResult(
                    material=material,
                    thickness_m=thickness_m,
                    second_moment_m4=inertia,
                    max_bending_stress_pa=stress,
                    tip_deflection_m=deflection,
                    mass_kg=mass,
                    yield_safety_factor=safety,
                    deflection_passes=deflection_passes,
                    yield_passes=yield_passes,
                    rejection_codes=tuple(rejection_codes),
                    # Additional metadata for the worked comparison
                    outcome_category=outcome_category,
                    governing_property=governing_property,
                    governing_source=governing_source,
                    uses_typical=uses_typical,
                    reference_note=reference_note,
                )
            )

    feasible = [candidate for candidate in candidates if candidate.meets_all_constraints]
    selected = min(feasible, key=lambda candidate: candidate.selection_key, default=None)
    status = STATUS_FEASIBLE if selected is not None else STATUS_NO_FEASIBLE_CANDIDATE
    return Evaluation(
        case=case,
        candidates=tuple(candidates),
        selected=selected,
        status=status,
    )
