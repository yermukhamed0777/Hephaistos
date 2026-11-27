"""Metron: a transparent cantilever material and thickness selector.

All public calculation functions take SI units: metres, newtons, pascals,
kilograms per cubic metre and kilograms. Case files use unit-suffixed fields
and are converted to SI once by :func:`metron.case.load_case_file`.
"""

from __future__ import annotations

from ._version import __version__
from .beam import (
    beam_mass,
    maximum_bending_stress,
    second_moment_of_area,
    tip_deflection,
    yield_safety_factor,
)
from .case import Case, CaseValidationError, load_case_file, parse_case_document
from .report import report_dict
from .solver import CandidateResult, Evaluation, NumericalRangeError, evaluate_case

__all__ = [
    "CandidateResult",
    "Case",
    "CaseValidationError",
    "Evaluation",
    "NumericalRangeError",
    "beam_mass",
    "evaluate_case",
    "load_case_file",
    "maximum_bending_stress",
    "parse_case_document",
    "report_dict",
    "second_moment_of_area",
    "tip_deflection",
    "yield_safety_factor",
]
