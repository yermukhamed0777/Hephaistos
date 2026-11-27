"""Validation tests for the explicit-unit JSON input boundary."""

from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from metron.case import CaseValidationError, load_case_file, parse_case_document

ROOT = Path(__file__).resolve().parents[1]
REFERENCE_CASE = ROOT / "cases" / "support_arm_reference.json"


def valid_document() -> dict:
    return json.loads(REFERENCE_CASE.read_text(encoding="utf-8"))


class ValidationTests(unittest.TestCase):
    def assert_invalid(self, document: object, expected_code: str, path_fragment: str) -> None:
        with self.assertRaises(CaseValidationError) as context:
            parse_case_document(document)
        codes = {issue.code for issue in context.exception.issues}
        paths = {issue.path for issue in context.exception.issues}
        self.assertIn(expected_code, codes)
        self.assertTrue(
            any(path_fragment in path for path in paths),
            f"Expected a path containing {path_fragment!r}; got {sorted(paths)}",
        )

    def test_case_is_converted_to_si_once(self) -> None:
        case = load_case_file(REFERENCE_CASE)
        self.assertEqual(case.beam.length_m, 0.100)
        self.assertEqual(case.beam.width_m, 0.020)
        self.assertEqual(case.beam.tip_force_n, 10.0)
        self.assertEqual(case.constraints.max_tip_deflection_m, 0.0005)
        self.assertEqual(case.stock_thicknesses_m, (0.003, 0.004, 0.005))
        self.assertEqual(case.materials[0].elastic_modulus_pa, 70.0e9)
        self.assertEqual(case.materials[0].yield_strength_pa, 150.0e6)
        self.assertEqual(case.materials[0].density_kg_m3, 2700.0)

    def test_missing_material_property_is_rejected(self) -> None:
        document = valid_document()
        del document["materials"][0]["yield_strength_mpa"]
        self.assert_invalid(document, "missing_field", "yield_strength_mpa")

    def test_missing_dimension_is_rejected(self) -> None:
        document = valid_document()
        del document["beam"]["width_mm"]
        self.assert_invalid(document, "missing_field", "width_mm")

    def test_ambiguous_units_field_is_rejected(self) -> None:
        document = valid_document()
        document["beam"]["length"] = 100.0
        document["units"] = "mm"
        self.assert_invalid(document, "unknown_field", "$.units")
        self.assert_invalid(document, "unknown_field", "length")

    def test_numeric_string_is_rejected(self) -> None:
        document = valid_document()
        document["beam"]["tip_force_n"] = "10 N"
        self.assert_invalid(document, "wrong_type", "tip_force_n")

    def test_boolean_is_not_a_number(self) -> None:
        document = valid_document()
        document["beam"]["tip_force_n"] = True
        self.assert_invalid(document, "wrong_type", "tip_force_n")

    def test_zero_dimension_is_rejected(self) -> None:
        document = valid_document()
        document["beam"]["length_mm"] = 0.0
        self.assert_invalid(document, "not_positive", "length_mm")

    def test_negative_modulus_is_rejected(self) -> None:
        document = valid_document()
        document["materials"][0]["elastic_modulus_gpa"] = -70.0
        self.assert_invalid(document, "not_positive", "elastic_modulus_gpa")

    def test_non_finite_number_is_rejected(self) -> None:
        document = valid_document()
        document["beam"]["width_mm"] = float("inf")
        self.assert_invalid(document, "non_finite", "width_mm")

    def test_huge_integer_is_rejected_without_overflowing(self) -> None:
        document = valid_document()
        document["beam"]["length_mm"] = 10**400
        self.assert_invalid(document, "non_finite", "length_mm")

    def test_conversion_overflow_is_rejected(self) -> None:
        document = valid_document()
        document["materials"][0]["elastic_modulus_gpa"] = 1.0e300
        self.assert_invalid(document, "out_of_range", "elastic_modulus_gpa")

    def test_conversion_underflow_is_rejected(self) -> None:
        document = valid_document()
        document["stock_thicknesses_mm"] = [5.0e-324]
        self.assert_invalid(document, "out_of_range", "stock_thicknesses_mm[0]")

    def test_utf8_bom_case_file_is_accepted(self) -> None:
        handle = tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".json",
            delete=False,
            encoding="utf-8-sig",
        )
        with handle:
            json.dump(valid_document(), handle)
        path = Path(handle.name)
        try:
            case = load_case_file(path)
        finally:
            path.unlink(missing_ok=True)
        self.assertEqual(case.case_id, "support-arm-reference")

    def test_non_positive_stock_is_rejected(self) -> None:
        document = valid_document()
        document["stock_thicknesses_mm"] = [3.0, 0.0, 5.0]
        self.assert_invalid(document, "not_positive", "stock_thicknesses_mm[1]")

    def test_duplicate_stock_is_rejected(self) -> None:
        document = valid_document()
        document["stock_thicknesses_mm"] = [3.0, 3.0, 4.0]
        self.assert_invalid(document, "duplicate_value", "stock_thicknesses_mm[1]")

    def test_duplicate_material_id_is_rejected(self) -> None:
        document = valid_document()
        duplicate = copy.deepcopy(document["materials"][0])
        document["materials"].append(duplicate)
        self.assert_invalid(document, "duplicate_value", "materials[1].id")

    def test_empty_materials_is_rejected(self) -> None:
        document = valid_document()
        document["materials"] = []
        self.assert_invalid(document, "empty_value", "materials")

    def test_wrong_schema_version_is_rejected(self) -> None:
        document = valid_document()
        document["schema_version"] = "2.0"
        self.assert_invalid(document, "unsupported_schema", "schema_version")

    def test_invalid_json_reports_a_validation_error(self) -> None:
        handle = tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".json",
            delete=False,
            encoding="utf-8",
        )
        with handle:
            handle.write('{"schema_version": "1.0",')
        path = Path(handle.name)
        try:
            with self.assertRaises(CaseValidationError) as context:
                load_case_file(path)
        finally:
            path.unlink(missing_ok=True)
        self.assertEqual(context.exception.issues[0].code, "invalid_json")

    def test_root_must_be_an_object(self) -> None:
        with self.assertRaises(CaseValidationError) as context:
            parse_case_document([])
        self.assertEqual(context.exception.issues[0].code, "wrong_type")


if __name__ == "__main__":
    unittest.main()
