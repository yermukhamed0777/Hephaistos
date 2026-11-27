"""Selection, rejection, tie-break and boundary tests."""

from __future__ import annotations

import json
import subprocess
import unittest
from dataclasses import replace
from pathlib import Path

from metron.case import Constraints, Material, load_case_file
from metron.solver import (
    DEFLECTION_REJECTION,
    STATUS_FEASIBLE,
    STATUS_NO_FEASIBLE_CANDIDATE,
    NumericalRangeError,
    evaluate_case,
)

ROOT = Path(__file__).resolve().parents[1]
REFERENCE_CASE = ROOT / "cases" / "support_arm_reference.json"
MATERIAL_CASE = ROOT / "cases" / "support_arm_material_choice.json"
TEST_CATALOG = ROOT / "metron" / "data" / "test_catalog.json"


def candidate_at(evaluation, thickness_mm: float):
    matches = [
        candidate
        for candidate in evaluation.candidates
        if abs(candidate.thickness_m - thickness_mm / 1000.0) < 1e-15
    ]
    if len(matches) != 1:
        raise AssertionError(f"Expected one candidate at {thickness_mm} mm; got {len(matches)}")
    return matches[0]


class ReferenceSelectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.evaluation = evaluate_case(load_case_file(REFERENCE_CASE))

    def test_reference_case_selects_4mm(self) -> None:
        self.assertEqual(self.evaluation.status, STATUS_FEASIBLE)
        selected = self.evaluation.selected
        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected.thickness_m, 0.004)
        self.assertAlmostEqual(selected.mass_kg, 0.0216, places=15)
        self.assertEqual(selected.material.material_id, "SYN-AL-01")

    def test_3mm_fails_only_the_deflection_limit(self) -> None:
        candidate = candidate_at(self.evaluation, 3.0)
        self.assertTrue(candidate.yield_passes)
        self.assertFalse(candidate.deflection_passes)
        self.assertEqual(candidate.rejection_codes, (DEFLECTION_REJECTION,))
        self.assertAlmostEqual(candidate.max_bending_stress_pa, 33333333.333333336)
        self.assertAlmostEqual(candidate.tip_deflection_m, 0.0010582010582010585)
        self.assertAlmostEqual(candidate.mass_kg, 0.0162)

    def test_5mm_passes_both_but_is_heavier_than_4mm(self) -> None:
        candidate = candidate_at(self.evaluation, 5.0)
        self.assertTrue(candidate.meets_all_constraints)
        self.assertAlmostEqual(candidate.mass_kg, 0.027)
        selected = self.evaluation.selected
        assert selected is not None
        self.assertLess(selected.mass_kg, candidate.mass_kg)
        self.assertGreater(candidate.yield_safety_factor, selected.yield_safety_factor)

    def test_all_six_pairs_are_evaluated_in_the_two_material_case(self) -> None:
        evaluation = evaluate_case(load_case_file(MATERIAL_CASE))
        self.assertEqual(len(evaluation.candidates), 6)

    def test_two_material_case_selects_b5_at_18_grams(self) -> None:
        evaluation = evaluate_case(load_case_file(MATERIAL_CASE))
        self.assertEqual(evaluation.status, STATUS_FEASIBLE)
        selected = evaluation.selected
        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected.material.material_id, "SYN-LD-02")
        self.assertEqual(selected.thickness_m, 0.005)
        self.assertAlmostEqual(selected.mass_kg, 0.018, places=15)


class BoundaryAndTieTests(unittest.TestCase):
    def test_equality_at_safety_factor_boundary_passes(self) -> None:
        case = load_case_file(REFERENCE_CASE)
        # The 4 mm reference candidate has SF = 150 MPa / 18.75 MPa = 8 exactly.
        case = replace(
            case,
            stock_thicknesses_m=(0.004,),
            constraints=Constraints(max_tip_deflection_m=0.001, min_yield_safety_factor=8.0),
        )
        evaluation = evaluate_case(case)
        self.assertEqual(evaluation.status, STATUS_FEASIBLE)
        self.assertIsNotNone(evaluation.selected)
        assert evaluation.selected is not None
        self.assertEqual(evaluation.selected.yield_safety_factor, 8.0)
        self.assertTrue(evaluation.selected.yield_passes)

    def test_exact_mass_tie_is_broken_by_material_id(self) -> None:
        case = load_case_file(REFERENCE_CASE)
        base = case.materials[0]
        material_b = Material(
            material_id="SYN-TIE-B",
            name="Synthetic tie fixture B",
            provenance="Synthetic test-only fixture.",
            elastic_modulus_pa=base.elastic_modulus_pa,
            density_kg_m3=base.density_kg_m3,
            yield_strength_pa=base.yield_strength_pa,
        )
        material_a = replace(material_b, material_id="SYN-TIE-A")
        case = replace(
            case,
            materials=(material_b, material_a),
            stock_thicknesses_m=(0.004,),
        )
        evaluation = evaluate_case(case)
        self.assertIsNotNone(evaluation.selected)
        assert evaluation.selected is not None
        self.assertEqual(evaluation.selected.material.material_id, "SYN-TIE-A")
        self.assertAlmostEqual(evaluation.selected.mass_kg, 0.0216, places=15)


class NumericalRangeTests(unittest.TestCase):
    def test_extreme_length_raises_a_controlled_numeric_error(self) -> None:
        case = load_case_file(REFERENCE_CASE)
        case = replace(case, beam=replace(case.beam, length_m=1.0e300))
        with self.assertRaises(NumericalRangeError):
            evaluate_case(case)

    def test_underflowing_thickness_raises_a_controlled_numeric_error(self) -> None:
        case = load_case_file(REFERENCE_CASE)
        case = replace(case, stock_thicknesses_m=(1.0e-120,))
        with self.assertRaises(NumericalRangeError):
            evaluate_case(case)


class NoFeasibleCandidateTests(unittest.TestCase):
    def test_none_qualifies_is_a_valid_engineering_result(self) -> None:
        case = load_case_file(REFERENCE_CASE)
        case = replace(
            case,
            constraints=Constraints(
                max_tip_deflection_m=0.0001,
                min_yield_safety_factor=20.0,
            ),
        )
        evaluation = evaluate_case(case)
        self.assertEqual(evaluation.status, STATUS_NO_FEASIBLE_CANDIDATE)
        self.assertIsNone(evaluation.selected)
        self.assertEqual(evaluation.feasible_candidates, ())
        for candidate in evaluation.candidates:
            self.assertFalse(candidate.meets_all_constraints)
            self.assertTrue(candidate.rejection_codes)


class CatalogApplicabilityTests(unittest.TestCase):
    """End-to-end tests for catalog-backed material selection."""

    def setUp(self) -> None:
        # ROOT is the project root, same as other test classes
        self.catalog = json.load(open(str(TEST_CATALOG)))

    def test_3mm_selectable_with_catalog(self) -> None:
        """3 mm is within (0, 3] interval; candidate must be selected."""
        import json, tempfile, os
        from pathlib import Path

        case_dict = {
            'schema_version': '1.0',
            'case_id': 'catalog-test-3mm',
            'title': 'Catalog test: 3 mm',
            'description': 'Test catalog interval applicability at 3 mm',
            'beam': {'length_mm': 1000.0, 'width_mm': 20.0, 'tip_force_n': 10.0},
            'constraints': {
                'max_tip_deflection_mm': 1.0,
                'min_yield_safety_factor': 2.0,
            },
            'stock_thicknesses_mm': [3.0],
            'materials': [
                {
                    'id': 'TEST-5052-H32',
                    'name': 'Aluminum 5052-H32',
                    'provenance': 'H32 temper',
                    'elastic_modulus_gpa': 70.3,
                    'density_kg_m3': 2680.0,
                    'yield_strength_mpa': 193.0,
                    'catalog_id': 'TEST-5052-H32',
                }
            ],
        }
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(case_dict, f)
            tmppath = f.name
        try:
            completed = subprocess.run(
                ['python', '-m', 'metron', tmppath, '--catalog', str(TEST_CATALOG)],
                cwd=str(ROOT),
                capture_output=True, text=True, encoding='utf-8',
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            result = json.loads(completed.stdout)
            self.assertEqual(result['status'], 'feasible')
            selected = result['selection']['selected']
            self.assertIsNotNone(selected)
            self.assertEqual(selected['thickness_mm_display'], '3')
            # Heavier candidates at 3.001 and 5 mm must be excluded for lacking applicable evidence
            outcomes = {c['thickness_mm_display']: c['outcome_category'] for c in result['candidates']}
            self.assertEqual(outcomes.get('3', ''), 'passes under the stated assumptions')
            self.assertEqual(outcomes.get('3.001', ''), 'lacks applicable evidence')
            self.assertEqual(outcomes.get('5', ''), 'lacks applicable evidence')
        finally:
            os.unlink(tmppath)

    def test_3mm001_and_5mm_excluded_for_missing_evidence(self) -> None:
        """At 3.001 mm and 5 mm, catalog interval not applicable → lacks applicable evidence."""
        import json, tempfile, os
        from pathlib import Path

        case_dict = {
            'schema_version': '1.0',
            'case_id': 'catalog-test-out-of-range',
            'title': 'Catalog test: out of range',
            'description': 'Test catalog interval not applicable outside (0, 3]',
            'beam': {'length_mm': 1000.0, 'width_mm': 20.0, 'tip_force_n': 10.0},
            'constraints': {
                'max_tip_deflection_mm': 1.0,
                'min_yield_safety_factor': 2.0,
            },
            'stock_thicknesses_mm': [3.0, 3.001, 5.0],
            'materials': [
                {
                    'id': 'TEST-5052-H32',
                    'name': 'Aluminum 5052-H32',
                    'provenance': 'H32 temper',
                    'elastic_modulus_gpa': 70.3,
                    'density_kg_m3': 2680.0,
                    'yield_strength_mpa': 193.0,
                    'catalog_id': 'TEST-5052-H32',
                }
            ],
        }
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(case_dict, f)
            tmppath = f.name
        try:
            completed = subprocess.run(
                ['python', '-m', 'metron', tmppath, '--catalog', str(TEST_CATALOG)],
                cwd=str(ROOT),
                capture_output=True, text=True, encoding='utf-8',
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            result = json.loads(completed.stdout)
            self.assertEqual(result['status'], 'no_feasible_candidate')
            # Verify each candidate's outcome
            for c in result['candidates']:
                t = c['thickness_mm_display']
                if t == '3':
                    # 3 mm should pass (interval applies)
                    self.assertEqual(c['outcome_category'], 'passes under the stated assumptions')
                elif t in ('3.001', '5'):
                    # Out of range → lacks applicable evidence
                    self.assertEqual(c['outcome_category'], 'lacks applicable evidence')
                    self.assertFalse(c['meets_all_constraints'])
        finally:
            os.unlink(tmppath)


if __name__ == "__main__":
    unittest.main()
