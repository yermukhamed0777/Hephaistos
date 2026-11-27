"""End-to-end tests through the documented ``python -m metron`` entry point."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REFERENCE_CASE = ROOT / "cases" / "support_arm_reference.json"


def run_cli(*arguments: str) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["PYTHONUTF8"] = "1"
    return subprocess.run(
        [sys.executable, "-m", "metron", *arguments],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=environment,
        check=False,
    )


def temporary_case(document: dict) -> Path:
    handle = tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".json",
        delete=False,
        encoding="utf-8",
    )
    with handle:
        json.dump(document, handle, indent=2)
    return Path(handle.name)


class CommandLineTests(unittest.TestCase):
    def test_reference_command_exits_zero_and_emits_json(self) -> None:
        completed = run_cli(str(REFERENCE_CASE))
        self.assertEqual(completed.returncode, 0, completed.stderr)
        result = json.loads(completed.stdout)
        self.assertEqual(result["status"], "feasible")
        self.assertEqual(result["selection"]["selected"]["thickness_m"], 0.004)
        self.assertEqual(completed.stderr, "")

    def test_no_feasible_candidate_exits_one(self) -> None:
        document = json.loads(REFERENCE_CASE.read_text(encoding="utf-8"))
        document["constraints"] = {
            "max_tip_deflection_mm": 0.1,
            "min_yield_safety_factor": 20.0,
        }
        path = temporary_case(document)
        try:
            completed = run_cli(str(path))
        finally:
            path.unlink(missing_ok=True)
        self.assertEqual(completed.returncode, 1, completed.stderr)
        result = json.loads(completed.stdout)
        self.assertEqual(result["status"], "no_feasible_candidate")
        self.assertIsNone(result["selection"]["selected"])
        self.assertEqual(
            result["selection"]["failed_constraints"],
            ["tip_deflection", "yield_safety"],
        )

    def test_invalid_case_exits_two_with_structured_errors(self) -> None:
        path = temporary_case({})
        try:
            completed = run_cli(str(path))
        finally:
            path.unlink(missing_ok=True)
        self.assertEqual(completed.returncode, 2, completed.stderr)
        result = json.loads(completed.stdout)
        self.assertEqual(result["status"], "invalid_input")
        self.assertTrue(result["errors"])
        self.assertEqual(completed.stderr, "")

    def test_malformed_json_exits_two(self) -> None:
        handle = tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".json",
            delete=False,
            encoding="utf-8",
        )
        with handle:
            handle.write("{not json")
        path = Path(handle.name)
        try:
            completed = run_cli(str(path))
        finally:
            path.unlink(missing_ok=True)
        self.assertEqual(completed.returncode, 2, completed.stderr)
        result = json.loads(completed.stdout)
        self.assertEqual(result["errors"][0]["code"], "invalid_json")

    def test_missing_file_exits_two(self) -> None:
        completed = run_cli(str(ROOT / "cases" / "does_not_exist.json"))
        self.assertEqual(completed.returncode, 2)
        result = json.loads(completed.stdout)
        self.assertEqual(result["errors"][0]["code"], "file_not_found")


if __name__ == "__main__":
    unittest.main()
