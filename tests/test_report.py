"""JSON contract and display-value tests."""

from __future__ import annotations

import unittest
from dataclasses import replace
from pathlib import Path

from metron.case import Constraints, load_case_file
from metron.report import report_dict
from metron.solver import evaluate_case

ROOT = Path(__file__).resolve().parents[1]
REFERENCE_CASE = ROOT / "cases" / "support_arm_reference.json"


class ReportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.evaluation = evaluate_case(load_case_file(REFERENCE_CASE))
        self.report = report_dict(self.evaluation)

    def test_contract_contains_inputs_units_and_candidate_reasons(self) -> None:
        for key in (
            "schema_version",
            "status",
            "case_id",
            "assumptions",
            "units",
            "inputs",
            "materials",
            "candidates",
            "selection",
        ):
            self.assertIn(key, self.report)

        self.assertEqual(self.report["status"], "feasible")
        self.assertEqual(self.report["materials"][0]["id"], "SYN-AL-01")
        self.assertIn("load_convention", self.report["assumptions"])
        self.assertEqual(
            self.report["units"]["case_file"]["elastic_modulus_gpa"], "gigapascal"
        )

    def test_candidate_rejection_is_structured_and_display_is_rounded(self) -> None:
        three_mm = next(
            candidate
            for candidate in self.report["candidates"]
            if candidate["thickness_m"] == 0.003
        )
        self.assertFalse(three_mm["meets_all_constraints"])
        self.assertEqual(
            [reason["code"] for reason in three_mm["rejection_reasons"]],
            ["tip_deflection_exceeds_limit"],
        )
        self.assertEqual(three_mm["max_bending_stress_pa"], 33333333.333333336)
        self.assertEqual(three_mm["max_bending_stress_mpa_display"], "33.3333")
        self.assertEqual(three_mm["tip_deflection_mm_display"], "1.0582")

    def test_selection_uses_unrounded_mass_and_reports_display(self) -> None:
        selected = self.report["selection"]["selected"]
        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["material_id"], "SYN-AL-01")
        self.assertEqual(selected["thickness_m"], 0.004)
        self.assertEqual(selected["mass_kg"], 0.0216)
        self.assertEqual(selected["mass_g_display"], "21.6")
        self.assertEqual(self.report["selection"]["feasible_count"], 2)

    def test_no_feasible_report_identifies_failed_constraints(self) -> None:
        case = replace(
            self.evaluation.case,
            constraints=Constraints(
                max_tip_deflection_m=0.0001,
                min_yield_safety_factor=20.0,
            ),
        )
        report = report_dict(evaluate_case(case))
        self.assertEqual(report["status"], "no_feasible_candidate")
        self.assertIsNone(report["selection"]["selected"])
        self.assertEqual(
            report["selection"]["failed_constraints"],
            ["tip_deflection", "yield_safety"],
        )
        self.assertEqual(report["selection"]["failure_counts"]["either_constraint"], 3)
        self.assertIsNotNone(report["selection"]["reason"])


if __name__ == "__main__":
    unittest.main()
