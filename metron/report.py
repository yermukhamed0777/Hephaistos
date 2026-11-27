"""Serialize an evaluation to the stable, machine-readable Metron JSON contract."""

from __future__ import annotations

from ._version import __version__
from .case import Case, Material
from .solver import (
    CandidateResult,
    DEFLECTION_REJECTION,
    Evaluation,
    STRENGTH_REJECTION,
    TIE_BREAK_RULE,
)
from .units import KG_TO_G, M_TO_MM, PA_TO_MPA

RESULT_SCHEMA_VERSION = "1.0"

ASSUMPTIONS = {
    "model": (
        "Euler-Bernoulli beam theory: a straight, slender, homogeneous, "
        "isotropic, linearly elastic beam with an ideal clamp, loaded by a "
        "single static transverse point load at its free end. Small "
        "deflections; no shear deformation, self-weight, stress "
        "concentration, buckling, fatigue or plastic redistribution."
    ),
    "bending_orientation": (
        "The beam axis is x, from the clamp at x=0 to the free end at x=L. "
        "Thickness t is the cross-section dimension parallel to the applied "
        "load (the bending direction). Width b is perpendicular to the load."
    ),
    "load_convention": (
        "A positive tip_force_n acts downward at the free end and is "
        "transverse to the beam axis. Tip deflection is the downward "
        "magnitude. Maximum nominal bending stress is reported at the fixed "
        "end, at the outer fibres y = +/- t/2."
    ),
    "constraint_rule": (
        "A candidate is feasible only when tip deflection <= the maximum "
        "deflection limit AND yield safety factor >= the minimum safety "
        "factor. Equality at either boundary passes."
    ),
    "mass_definition": (
        "Mass is the prismatic structural beam only: m = density * b * t * L. "
        "Clamp hardware, fasteners, finish and non-structural material are "
        "excluded."
    ),
    "selection_rule": TIE_BREAK_RULE,
    "numerical_precision": (
        "All checks and the selection use unrounded IEEE-754 binary64 "
        "values. Fields ending in _display are six-significant-digit strings "
        "for human display only and are never used for a decision."
    ),
}

UNITS = {
    "case_file": {
        "length_mm": "millimetre",
        "width_mm": "millimetre",
        "tip_force_n": "newton",
        "max_tip_deflection_mm": "millimetre",
        "min_yield_safety_factor": "dimensionless",
        "stock_thicknesses_mm": "millimetre",
        "elastic_modulus_gpa": "gigapascal",
        "density_kg_m3": "kilogram per cubic metre",
        "yield_strength_mpa": "megapascal",
    },
    "raw_output": {
        "length_m": "metre",
        "width_m": "metre",
        "tip_force_n": "newton",
        "max_tip_deflection_m": "metre",
        "thickness_m": "metre",
        "second_moment_m4": "metre^4",
        "max_bending_stress_pa": "pascal",
        "tip_deflection_m": "metre",
        "mass_kg": "kilogram",
        "yield_safety_factor": "dimensionless",
        "elastic_modulus_pa": "pascal",
        "density_kg_m3": "kilogram per cubic metre",
        "yield_strength_pa": "pascal",
    },
    "display_fields": (
        "Six-significant-digit display strings: lengths in mm, stress in "
        "MPa, mass in g, modulus in GPa, yield strength in MPa."
    ),
}


def _display(value: float) -> str:
    return format(value, ".6g")


def _material_dict(material: Material) -> dict[str, object]:
    return {
        "id": material.material_id,
        "name": material.name,
        "provenance": material.provenance,
        "elastic_modulus_pa": material.elastic_modulus_pa,
        "elastic_modulus_gpa_display": _display(
            material.elastic_modulus_pa * PA_TO_MPA / 1000.0
        ),
        "density_kg_m3": material.density_kg_m3,
        "yield_strength_pa": material.yield_strength_pa,
        "yield_strength_mpa_display": _display(
            material.yield_strength_pa * PA_TO_MPA
        ),
    }


def _rejection_dicts(
    candidate: CandidateResult,
    case: Case,
) -> list[dict[str, str]]:
    reasons: list[dict[str, str]] = []
    if DEFLECTION_REJECTION in candidate.rejection_codes:
        reasons.append(
            {
                "code": DEFLECTION_REJECTION,
                "message": (
                    f"Tip deflection "
                    f"{_display(candidate.tip_deflection_m * M_TO_MM)} mm "
                    f"exceeds the limit "
                    f"{_display(case.constraints.max_tip_deflection_m * M_TO_MM)} mm."
                ),
            }
        )
    if STRENGTH_REJECTION in candidate.rejection_codes:
        reasons.append(
            {
                "code": STRENGTH_REJECTION,
                "message": (
                    f"Yield safety factor "
                    f"{_display(candidate.yield_safety_factor)} is below the "
                    f"minimum {_display(case.constraints.min_yield_safety_factor)}."
                ),
            }
        )
    return reasons


def _candidate_dict(candidate: CandidateResult, case: Case) -> dict[str, object]:
    return {
        "material_id": candidate.material.material_id,
        "material_name": candidate.material.name,
        "provenance": candidate.material.provenance,
        "thickness_m": candidate.thickness_m,
        "thickness_mm_display": _display(candidate.thickness_m * M_TO_MM),
        "second_moment_m4": candidate.second_moment_m4,
        "max_bending_stress_pa": candidate.max_bending_stress_pa,
        "max_bending_stress_mpa_display": _display(
            candidate.max_bending_stress_pa * PA_TO_MPA
        ),
        "tip_deflection_m": candidate.tip_deflection_m,
        "tip_deflection_mm_display": _display(candidate.tip_deflection_m * M_TO_MM),
        "mass_kg": candidate.mass_kg,
        "mass_g_display": _display(candidate.mass_kg * KG_TO_G),
        "yield_safety_factor": candidate.yield_safety_factor,
        "yield_safety_factor_display": _display(candidate.yield_safety_factor),
        "checks": {
            "tip_deflection": {
                "value_m": candidate.tip_deflection_m,
                "limit_m": case.constraints.max_tip_deflection_m,
                "passes": candidate.deflection_passes,
            },
            "yield_safety": {
                "value": candidate.yield_safety_factor,
                "minimum": case.constraints.min_yield_safety_factor,
                "passes": candidate.yield_passes,
            },
        },
        "meets_all_constraints": candidate.meets_all_constraints,
        "rejection_reasons": _rejection_dicts(candidate, case),
    }


def report_dict(evaluation: Evaluation) -> dict[str, object]:
    """Return the complete JSON-ready result. Display values are never used for decisions."""
    case = evaluation.case
    selected = evaluation.selected

    deflection_failures = sum(
        1 for candidate in evaluation.candidates if not candidate.deflection_passes
    )
    yield_failures = sum(
        1 for candidate in evaluation.candidates if not candidate.yield_passes
    )
    any_failure = sum(
        1 for candidate in evaluation.candidates if not candidate.meets_all_constraints
    )
    failed_constraints: list[str] = []
    if selected is None:
        if deflection_failures:
            failed_constraints.append("tip_deflection")
        if yield_failures:
            failed_constraints.append("yield_safety")

    if selected is None:
        selected_dict: dict[str, object] | None = None
        no_selection_reason = (
            "No supplied material/thickness pair satisfies both constraints."
        )
    else:
        selected_dict = {
            "material_id": selected.material.material_id,
            "material_name": selected.material.name,
            "thickness_m": selected.thickness_m,
            "thickness_mm_display": _display(selected.thickness_m * M_TO_MM),
            "mass_kg": selected.mass_kg,
            "mass_g_display": _display(selected.mass_kg * KG_TO_G),
        }
        no_selection_reason = None

    return {
        "schema_version": RESULT_SCHEMA_VERSION,
        "tool": "metron",
        "tool_version": __version__,
        "status": evaluation.status,
        "case_id": case.case_id,
        "title": case.title,
        "description": case.description,
        "assumptions": ASSUMPTIONS,
        "units": UNITS,
        "inputs": {
            "beam": {
                "length_m": case.beam.length_m,
                "width_m": case.beam.width_m,
                "tip_force_n": case.beam.tip_force_n,
            },
            "constraints": {
                "max_tip_deflection_m": case.constraints.max_tip_deflection_m,
                "min_yield_safety_factor": case.constraints.min_yield_safety_factor,
            },
            "stock_thicknesses_m": list(case.stock_thicknesses_m),
        },
        "materials": [_material_dict(material) for material in case.materials],
        "candidates": [
            _candidate_dict(candidate, case) for candidate in evaluation.candidates
        ],
        "selection": {
            "selected": selected_dict,
            "rule": TIE_BREAK_RULE,
            "evaluated_count": len(evaluation.candidates),
            "feasible_count": len(evaluation.feasible_candidates),
            "failure_counts": {
                "tip_deflection": deflection_failures,
                "yield_safety": yield_failures,
                "either_constraint": any_failure,
            },
            "failed_constraints": failed_constraints,
            "reason": no_selection_reason,
        },
    }
