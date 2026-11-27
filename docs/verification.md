# Verification record

**Milestone:** 1 — Metron
**Recorded:** 2026-11-27 (Asia/Shanghai)
**Local platform:** Windows, PowerShell, Python 3.14.6, Git 2.55.0
**Dependencies installed for verification:** none beyond the Python standard library

## Clean-tree export

A fresh-tree check was performed from the committed tree only, not from the working directory. The DSH sandbox blocked `git clone` because Git's helper process could not create a named pipe, so the tree was exported with `git archive` and unpacked into an ignored `.verify` directory:

```powershell
git archive --format=zip --output=.\.verify\milestone.zip HEAD
Expand-Archive -LiteralPath .\.verify\milestone.zip -DestinationPath .\.verify\fresh-tree
Set-Location .\.verify\fresh-tree
```

The export contained only tracked files (no `__pycache__`, test cache or local result files). The commands below were then run from that directory with no installation step.

## Unit tests

```powershell
python -m unittest discover -s tests -t . -v
```

Observed final line:

```text
Ran 52 tests

OK
```

Exit code: `0`.

This covers the reference values, force scaling, thickness scaling, boundary equality, input validation, cross-material selection, tie-breaking, no-feasible-candidate output, numeric-range handling, BOM input and the normal CLI entry point.

## Reference case through the CLI

```powershell
python -m metron .\cases\support_arm_reference.json
```

Exit code: `0`. Observed decision data from the JSON:

| Material | t (mm) | Mass (g) | Stress (MPa) | SF | Deflection (mm) | Feasible | Rejection |
|---|---:|---:|---:|---:|---:|:---:|---|
| SYN-AL-01 | 3 | 16.2 | 33.3333 | 4.5 | 1.0582 | no | `tip_deflection_exceeds_limit` |
| SYN-AL-01 | 4 | 21.6 | 18.75 | 8 | 0.446429 | yes | — |
| SYN-AL-01 | 5 | 27 | 12 | 12.5 | 0.228571 | yes | — |

Selected: `SYN-AL-01`, 4 mm, `mass_kg = 0.0216` (21.6 g).

The reference decision therefore reproduces the independent hand check in the milestone brief. The 3 mm option passes the strength check but fails deflection; the 5 mm option passes both but is heavier than 4 mm.

## Two-material case through the CLI

```powershell
python -m metron .\cases\support_arm_material_choice.json
```

Exit code: `0`. Three of six candidates are feasible. Selected: `SYN-LD-02`, 5 mm, 18 g. The two lighter `SYN-LD-02` options fail only the deflection limit. This exercises selection across materials rather than selection only across thicknesses for one material.

## Edge-case follow-up

An external review identified that extreme finite inputs could escape validation and crash, and that Windows PowerShell BOM-prefixed JSON could be rejected. Both were fixed and are covered by regression tests. The repaired CLI behaviour was rechecked through the normal entry point:

| Input variation | Exit | Status | Error code |
|---|---:|---|---|
| 401-digit integer for `length_mm` | 2 | `invalid_input` | `non_finite` |
| `length_mm = 1e300` | 2 | `invalid_input` | `numerical_range` |
| `stock_thicknesses_mm = [1e-120]` | 2 | `invalid_input` | `numerical_range` |
| `elastic_modulus_gpa = 1e300` | 2 | `invalid_input` | `out_of_range` |
| Reference case with a UTF-8 BOM | 0 | `feasible` | — (selected 4 mm) |

No traceback was written to stderr for any of these cases.

## Interpretation of the checks

These checks establish agreement between the implementation and the stated Euler–Bernoulli beam model, plus agreement with the independent reference arithmetic. They are **not** physical validation. Validating a real support arm would require measured dimensions and material properties, a characterized clamp, controlled static loading, measured deflection and strain, and ideally a yield/failure test. The bundled fixtures are synthetic and are not design data.

## GitHub Actions

The workflow at `.github/workflows/ci.yml` runs the same standard-library test suite and a CLI smoke test on Python 3.10 and 3.13 for pushes and pull requests.

Remote CI state observed during this milestone (2026-11-27, Asia/Shanghai):

- Draft pull request [#1 — Milestone 1: Metron cantilever material and stock selector](https://github.com/yermukhamed0777/Hephaistos/pull/1) (branch `milestone-1-metron`, base `main`).
- Workflow run `45961792407` (pull_request event, head commit `5489a1c`): **success** on Python 3.10 and Python 3.13; the third check in the run (`Gitar`) also **success**.
- Workflow run `45961788370` (push event, same branch/head): **success** on Python 3.10 and Python 3.13.
- Draft PR merge state: `CLEAN`.

This file records the local pass above and the remote CI state observed in this session; the status was also confirmed from the pull-request check rollup.

## Status of the three checks

| Check | Result |
|---|---|
| Local test run (this session, working tree and fresh-tree export) | **pass** — 52 tests, OK, exit 0 |
| Remote GitHub Actions run on the draft PR head | **pass** — both matrix legs SUCCESS |
| External review check ("Gitar") on the fixed head | **pass** |

No check could not be run from this environment: the full suite, the CLI entry point and the numeric fuzz set were all executed locally, and the same suite plus a CLI smoke test run remotely via GitHub Actions.

## Unresolved issues

None at the close of this milestone. Extreme finite inputs, BOM-prefixed case files and numeric-range failures were all handled and regression-tested before this milestone was closed.
