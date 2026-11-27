# Metron JSON contract, version 1.0

This document defines the input case format and the stable result envelope used by Metron Milestone 1. The contract is intentionally independent of any LLM or UI: a shell command reads a JSON file, writes JSON to stdout, and sets an exit code.

## 1. Input case

A case file is one UTF-8 JSON object with this shape:

```json
{
  "schema_version": "1.0",
  "case_id": "support-arm-reference",
  "title": "Robocon support arm: stock-thickness check",
  "description": "Illustrative synthetic-fixture teaching case.",
  "beam": {
    "length_mm": 100.0,
    "width_mm": 20.0,
    "tip_force_n": 10.0
  },
  "constraints": {
    "max_tip_deflection_mm": 0.50,
    "min_yield_safety_factor": 2.0
  },
  "stock_thicknesses_mm": [3.0, 4.0, 5.0],
  "materials": [
    {
      "id": "SYN-AL-01",
      "name": "Synthetic aluminium-like teaching material 01",
      "provenance": "Synthetic fixture; not a real alloy and not design data.",
      "elastic_modulus_gpa": 70.0,
      "density_kg_m3": 2700.0,
      "yield_strength_mpa": 150.0
    }
  ]
}
```

### Required top-level fields

| Field | Type | Rule |
|---|---|---|
| `schema_version` | string | Must be exactly `"1.0"`. |
| `case_id` | string | Non-empty. Echoed in the result. |
| `beam` | object | See beam fields. |
| `constraints` | object | See constraint fields. |
| `stock_thicknesses_mm` | array of numbers | At least one unique positive value, in mm. |
| `materials` | array of objects | At least one material; IDs must be unique. |

Optional: `title`, `description` (strings, may be empty).

### `beam`

| Field | Unit | Rule |
|---|---|---|
| `length_mm` | mm | Finite and > 0. |
| `width_mm` | mm | Finite and > 0; perpendicular to the load. |
| `tip_force_n` | N | Finite and > 0; downward load at the free end. |

Thickness is not a beam field; it comes from each `stock_thicknesses_mm` entry. Thickness is the dimension parallel to the load (the bending direction).

### `constraints`

| Field | Unit | Rule |
|---|---|---|
| `max_tip_deflection_mm` | mm | Finite and > 0. Equality passes. |
| `min_yield_safety_factor` | dimensionless | Finite and > 0. Equality passes. |

### `materials[]`

Every material needs all six fields.

| Field | Unit | Rule |
|---|---|---|
| `id` | string | Non-empty and unique in the case. Appears in every result. |
| `name` | string | Non-empty human label. |
| `provenance` | string | Non-empty source/limitations label. Required so invented properties cannot masquerade as datasheet data. |
| `elastic_modulus_gpa` | GPa | Finite and > 0. |
| `density_kg_m3` | kg/m³ | Finite and > 0. |
| `yield_strength_mpa` | MPa | Finite and > 0. |

There is no generic `units` field, no unit-bearing string such as `"10 N"`, and no inferred unit. Unknown fields are rejected. Use explicit suffixes exactly as listed. This prevents an ambiguous or silently mixed-unit case.

### Validation and SI conversion

At the input boundary only:

- mm → m
- GPa → Pa
- MPa → Pa
- N and kg/m³ are unchanged

The solver receives SI values. All result values whose field name ends in `_m`, `_pa`, `_m4`, `_kg`, `_n` or `_kg_m3` are in SI units. Display strings are explicitly named and are not inputs to any decision.

Malformed JSON, unreadable files and any validation issue produce `status = "invalid_input"`. Nothing is evaluated in that case. Validation reports all detected issues it can collect in one pass, each with a JSON path, stable code and message.

## 2. Physics contract

A candidate is a material/thickness pair. For each pair:

```text
I  = b t^3 / 12
σ  = F L (t/2) / I
δ  = F L^3 / (3 E I)
m  = ρ b t L
SF = S_y / σ

pass_deflection = δ <= max_tip_deflection_m
pass_strength   = SF >= min_yield_safety_factor
feasible        = pass_deflection and pass_strength
```

Selection: minimum unrounded `mass_kg` over feasible candidates. Exact mass ties: `material_id` ascending by Unicode code point, then `thickness_m` ascending.

Supported mechanical model: Euler–Bernoulli bending of a straight, slender, homogeneous, isotropic, linearly elastic prismatic beam, ideal clamp, static transverse point load at the free end, small deflections. The full assumptions are echoed in the result.

## 3. Result envelope

Every CLI invocation prints one JSON object.

```json
{
  "schema_version": "1.0",
  "tool": "metron",
  "tool_version": "0.1.0",
  "status": "feasible",
  "case_id": "support-arm-reference",
  "title": "...",
  "description": "...",
  "assumptions": {
    "model": "...",
    "bending_orientation": "...",
    "load_convention": "...",
    "constraint_rule": "...",
    "mass_definition": "...",
    "selection_rule": "...",
    "numerical_precision": "..."
  },
  "units": {
    "case_file": {"length_mm": "millimetre", "...": "..."},
    "raw_output": {"mass_kg": "kilogram", "...": "..."},
    "display_fields": "..."
  },
  "inputs": {
    "beam": {"length_m": 0.1, "width_m": 0.02, "tip_force_n": 10.0},
    "constraints": {
      "max_tip_deflection_m": 0.0005,
      "min_yield_safety_factor": 2.0
    },
    "stock_thicknesses_m": [0.003, 0.004, 0.005]
  },
  "materials": [
    {
      "id": "SYN-AL-01",
      "name": "...",
      "provenance": "...",
      "elastic_modulus_pa": 70000000000.0,
      "elastic_modulus_gpa_display": "70",
      "density_kg_m3": 2700.0,
      "yield_strength_pa": 150000000.0,
      "yield_strength_mpa_display": "150"
    }
  ],
  "candidates": [
    {
      "material_id": "SYN-AL-01",
      "material_name": "...",
      "provenance": "...",
      "thickness_m": 0.004,
      "thickness_mm_display": "4",
      "second_moment_m4": 1.0666666666666667e-10,
      "max_bending_stress_pa": 18750000.0,
      "max_bending_stress_mpa_display": "18.75",
      "tip_deflection_m": 0.00044642857142857147,
      "tip_deflection_mm_display": "0.446429",
      "mass_kg": 0.0216,
      "mass_g_display": "21.6",
      "yield_safety_factor": 8.0,
      "yield_safety_factor_display": "8",
      "checks": {
        "tip_deflection": {
          "value_m": 0.00044642857142857147,
          "limit_m": 0.0005,
          "passes": true
        },
        "yield_safety": {
          "value": 8.0,
          "minimum": 2.0,
          "passes": true
        }
      },
      "meets_all_constraints": true,
      "rejection_reasons": []
    }
  ],
  "selection": {
    "selected": {
      "material_id": "SYN-AL-01",
      "material_name": "...",
      "thickness_m": 0.004,
      "thickness_mm_display": "4",
      "mass_kg": 0.0216,
      "mass_g_display": "21.6"
    },
    "rule": "Lowest mass_kg. Exact ties are resolved by ...",
    "evaluated_count": 3,
    "feasible_count": 2,
    "failure_counts": {
      "tip_deflection": 1,
      "yield_safety": 0,
      "either_constraint": 1
    },
    "failed_constraints": [],
    "reason": null
  }
}
```

### Statuses

| `status` | Meaning | Exit code | `selection.selected` |
|---|---|---:|---|
| `feasible` | At least one pair passes both constraints. | 0 | object |
| `no_feasible_candidate` | No pair passes both. This is a valid engineering result. | 1 | `null` |
| `invalid_input` | Case file missing, unreadable, malformed or invalid. No physics evaluated. | 2 | absent |

### Candidate fields

Every candidate, feasible or rejected, includes:

- the material ID, name and provenance;
- `thickness_m` and SI results for `I`, stress, deflection, mass and safety factor;
- full-precision raw values plus `_display` strings;
- explicit `checks.tip_deflection` and `checks.yield_safety` objects with the raw value, limit and boolean;
- `meets_all_constraints`;
- `rejection_reasons`, a list of `{"code", "message"}`.

Stable rejection codes:

- `tip_deflection_exceeds_limit`
- `yield_safety_below_minimum`

Both may appear for one candidate, in that order.

### No-feasible selection fields

For `no_feasible_candidate`:

- `selection.selected` is `null`.
- `selection.failed_constraints` lists each constraint that at least one candidate failed, in the order `tip_deflection`, `yield_safety`.
- `selection.failure_counts` counts candidates failing each constraint and at least one constraint.
- `selection.reason` is a human-readable summary.

For a feasible selection, `failed_constraints` is an empty list and `reason` is `null`.

### Invalid input envelope

```json
{
  "schema_version": "1.0",
  "tool": "metron",
  "tool_version": "0.1.0",
  "status": "invalid_input",
  "case_file": "path/as/given.json",
  "errors": [
    {
      "path": "$.beam.length_mm",
      "code": "not_positive",
      "message": "Number must be greater than zero."
    }
  ]
}
```

Error codes are stable strings such as `missing_field`, `unknown_field`, `wrong_type`, `non_finite`, `not_positive`, `duplicate_value`, `empty_value`, `unsupported_schema`, `invalid_json`, `file_not_found` and `file_unreadable`.

## 4. API surface

The same calculation is available as ordinary Python functions:

```python
from metron import load_case_file, evaluate_case, report_dict

case = load_case_file("cases/support_arm_reference.json")
evaluation = evaluate_case(case)
result = report_dict(evaluation)
```

Individual SI functions are `second_moment_of_area`, `maximum_bending_stress`, `tip_deflection`, `beam_mass` and `yield_safety_factor` in `metron.beam`.

This contract is versioned by `schema_version`. Breaking changes require a new schema version and updated tests.
