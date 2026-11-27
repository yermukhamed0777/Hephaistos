"""Command-line entry point: evaluate one JSON case file and print JSON."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from ._version import __version__
from .case import CaseValidationError, ValidationIssue, load_case_file
from .report import RESULT_SCHEMA_VERSION, report_dict
from .solver import STATUS_FEASIBLE, evaluate_case

EXIT_FEASIBLE = 0
EXIT_NO_FEASIBLE = 1
EXIT_INVALID_INPUT = 2


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="metron",
        description=(
            "Select the lightest supplied material and stock thickness for a "
            "rectangular cantilever under a static tip load."
        ),
    )
    parser.add_argument("case_file", help="path to a Metron JSON case file")
    parser.add_argument(
        "--compact",
        action="store_true",
        help="emit compact JSON instead of two-space-indented JSON",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    return parser


def _emit(payload: dict[str, object], compact: bool) -> None:
    indent = None if compact else 2
    print(json.dumps(payload, indent=indent, ensure_ascii=True, allow_nan=False))


def _invalid_payload(
    case_file: str,
    issues: Sequence[ValidationIssue],
) -> dict[str, object]:
    return {
        "schema_version": RESULT_SCHEMA_VERSION,
        "tool": "metron",
        "tool_version": __version__,
        "status": "invalid_input",
        "case_file": case_file,
        "errors": [issue.as_dict() for issue in issues],
    }


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)

    try:
        case = load_case_file(args.case_file)
    except CaseValidationError as exc:
        _emit(_invalid_payload(args.case_file, exc.issues), args.compact)
        return EXIT_INVALID_INPUT
    except FileNotFoundError:
        _emit(
            _invalid_payload(
                args.case_file,
                [
                    ValidationIssue(
                        path="$",
                        code="file_not_found",
                        message=f"Case file not found: {args.case_file}",
                    )
                ],
            ),
            args.compact,
        )
        return EXIT_INVALID_INPUT
    except (OSError, UnicodeError) as exc:
        _emit(
            _invalid_payload(
                args.case_file,
                [
                    ValidationIssue(
                        path="$",
                        code="file_unreadable",
                        message=f"Could not read the case file: {exc}",
                    )
                ],
            ),
            args.compact,
        )
        return EXIT_INVALID_INPUT

    result = report_dict(evaluate_case(case))
    _emit(result, args.compact)
    return EXIT_FEASIBLE if result["status"] == STATUS_FEASIBLE else EXIT_NO_FEASIBLE


if __name__ == "__main__":
    sys.exit(main())
