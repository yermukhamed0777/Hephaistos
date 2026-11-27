"""Evaluate every material/thickness pair and select the lightest feasible one."""

from __future__ import annotations

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


def evaluate_case(case: Case) -> Evaluation:
    """Evaluate all pairs and choose the lightest that satisfies both limits.

    A candidate passes a limit when it is equal to it (inclusive boundary).
    No value is rounded before comparison or selection.
    """
    beam = case.beam
    limits = case.constraints
    candidates: list[CandidateResult] = []

    for material in case.materials:
        for thickness_m in case.stock_thicknesses_m:
            inertia = second_moment_of_area(beam.width_m, thickness_m)
            stress = maximum_bending_stress(
                beam.tip_force_n,
                beam.length_m,
                beam.width_m,
                thickness_m,
            )
            deflection = tip_deflection(
                beam.tip_force_n,
                beam.length_m,
                beam.width_m,
                thickness_m,
                material.elastic_modulus_pa,
            )
            mass = beam_mass(
                material.density_kg_m3,
                beam.width_m,
                thickness_m,
                beam.length_m,
            )
            safety = yield_safety_factor(material.yield_strength_pa, stress)

            deflection_passes = deflection <= limits.max_tip_deflection_m
            yield_passes = safety >= limits.min_yield_safety_factor
            rejection_codes: list[str] = []
            if not deflection_passes:
                rejection_codes.append(DEFLECTION_REJECTION)
            if not yield_passes:
                rejection_codes.append(STRENGTH_REJECTION)

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
