# Hephaistos: Metron

**Milestone 1 — a transparent material and stock-thickness selector for a static cantilever.**

Metron answers one engineering question:

> For a rectangular cantilever under a static tip load, which supplied material and stock thickness meet both a tip-deflection limit and a yield safety factor at the lowest mass?

It is a small, offline Python tool. It opens a unit-explicit JSON case, evaluates every supplied material/thickness pair, reports every rejection reason, and returns the lightest feasible option. The decision is reproducible and can be checked by hand.

> **Fixture warning.** Every material in the bundled cases is a **synthetic teaching fixture**. The IDs, names and provenance labels say so explicitly. They are not alloy grades, not manufacturer data, and must not be used for design.

---

## Quick start (Windows PowerShell)

Supported Python: **3.10 or newer**. There are no runtime dependencies and no install step is required for a fresh checkout.

Run these commands in **one PowerShell tab and stay in that tab**. The working directory is the repository root.

```powershell
Set-Location 'C:\Users\erm1h\Documents\Projects\Hephaistos'
python --version
python -m metron .\cases\support_arm_reference.json
```

The first command is the one to run first. It prints JSON and exits with code `0`; the selected result is the 4 mm stock at 21.6 g.

Run the independent tests:

```powershell
python -m unittest discover -s tests -t . -v
```

Run the two-material example:

```powershell
python -m metron .\cases\support_arm_material_choice.json
```

Optional console-script installation:

```powershell
python -m pip install -e .
metron .\cases\support_arm_reference.json
```

The checked-in source checkout does not need that installation. The JSON output is the integration point for a later Hermes/OpenCode/Ollama tool; no model, database, credentials or network access is involved here.

---

## The support-arm question

This is an illustrative teaching example, not a real Robocon part.

- A straight support arm of length **L = 100 mm** and width **b = 20 mm**.
- One end is an ideal clamp; a **F = 10 N** downward point load acts at the free end.
- Stock thickness **t** is available in **3, 4 and 5 mm**.
- The tip may deflect at most **0.50 mm**.
- The yield safety factor must be at least **2.0**.

The synthetic reference fixture is `SYN-AL-01`: **E = 70 GPa**, **density = 2700 kg/m³**, **illustrative yield strength = 150 MPa**. These values make the first check match a hand calculation. They are not the properties of a named alloy.

### Bending orientation

`t` is the cross-section dimension **in the bending direction** — the direction the tip moves. `b` is perpendicular to the load. The arm is loaded on its narrow edge as drawn.

```text
SIDE VIEW (x-y bending plane)

  clamp
   ||====================================> x
   ||   L = 100 mm                   F = 10 N
   ||                                  |
   ||                                  v  (downward at the free end)

CROSS-SECTION (looking along the arm)

  +----------------------+  ^
  |                      |  |  t = 3, 4 or 5 mm
  |                      |  |  (bending direction)
  +----------------------+  v
  <------ b = 20 mm ------>

  into the page: width b; vertical: thickness t
```

The load convention, sign conventions and supported model are also emitted in every JSON result under `assumptions`.

---

## Result for the 3 / 4 / 5 mm case

Bundled case: [`cases/support_arm_reference.json`](cases/support_arm_reference.json).

| Material | t (mm) | Mass (g) | Max stress (MPa) | Yield SF | Tip deflection (mm) | Strength | Deflection | Decision |
|---|---:|---:|---:|---:|---:|:---:|:---:|---|
| SYN-AL-01 | 3 | 16.2 | 33.3333 | 4.5 | 1.0582 | pass | **fail** | rejected — too flexible |
| SYN-AL-01 | 4 | **21.6** | **18.75** | **8.0** | **0.446429** | pass | pass | **selected** |
| SYN-AL-01 | 5 | 27.0 | 12.0 | 12.5 | 0.228571 | pass | pass | feasible, but 5.4 g heavier |

**Why 3 mm loses despite passing strength.** Its stress is 33.3333 MPa and its safety factor is 4.5, comfortably above the required 2.0. But deflection scales as `1/t³`: the 3 mm tip moves 1.0582 mm, which is more than twice the 0.50 mm permitted. Strength alone is not the governing constraint.

**Why 5 mm loses despite passing both constraints.** It deflects only 0.228571 mm and has a safety factor of 12.5, so it is genuinely feasible. It simply weighs 27.0 g, versus 21.6 g for the 4 mm option. The selection is driven by mass among feasible candidates.

The 4 mm option is feasible and is the lightest feasible pair. That is the whole decision.

### Selection across two materials

Bundled case: [`cases/support_arm_material_choice.json`](cases/support_arm_material_choice.json). The second fixture, `SYN-LD-02`, is synthetic and has **E = 40 GPa**, **density = 1800 kg/m³** and **illustrative yield strength = 120 MPa**.

| Material | t (mm) | Mass (g) | Max stress (MPa) | Yield SF | Tip deflection (mm) | Constraints | Decision |
|---|---:|---:|---:|---:|---:|:---:|---|
| SYN-AL-01 | 3 | 16.2 | 33.3333 | 4.5 | 1.0582 | deflection fails | rejected |
| SYN-AL-01 | 4 | 21.6 | 18.75 | 8.0 | 0.446429 | pass | feasible |
| SYN-AL-01 | 5 | 27.0 | 12.0 | 12.5 | 0.228571 | pass | feasible |
| SYN-LD-02 | 3 | 10.8 | 33.3333 | 3.6 | 1.85185 | deflection fails | rejected |
| SYN-LD-02 | 4 | 14.4 | 18.75 | 6.4 | 0.78125 | deflection fails | rejected |
| **SYN-LD-02** | **5** | **18.0** | **12.0** | **10.0** | **0.4** | **pass** | **selected** |

The lighter 3 mm and 4 mm versions of the low-density material are rejected on deflection. Its 5 mm version is still the lightest feasible option at **18.0 g**, 3.6 g lighter than the reference material at 4 mm. This is a material-and-thickness interaction, not a material-only ranking.

---

## Derivation

For a straight, slender, homogeneous, isotropic, linearly elastic beam with an ideal clamp and a transverse point load at the free end, Euler–Bernoulli beam theory gives:

```text
Second moment of area:        I  = b t^3 / 12
Maximum bending stress:       σ  = F L (t/2) / I  = 6 F L / (b t^2)
Tip deflection:               δ  = F L^3 / (3 E I) = 4 F L^3 / (E b t^3)
Mass:                         m  = ρ b t L
Yield safety factor:          SF = S_y / σ
```

`σ` is the nominal maximum bending stress at the fixed end, at the outer fibres (`y = ±t/2`). `δ` is the downward tip displacement. The model assumes small deflections; it does not include shear deformation, self-weight, stress concentrations, buckling, fatigue or plastic redistribution.

### Hand check of the 4 mm reference case

```text
L = 0.100 m, b = 0.020 m, t = 0.004 m, F = 10 N
E = 70e9 Pa, rho = 2700 kg/m^3, Sy = 150e6 Pa

I  = 0.020 * 0.004^3 / 12            = 1.0666667e-10 m^4
σ  = 10 * 0.100 * 0.002 / I           = 18.75e6 Pa   = 18.75 MPa
δ  = 10 * 0.100^3 / (3 * 70e9 * I)    = 4.4642857e-4 m = 0.446429 mm
m  = 2700 * 0.020 * 0.004 * 0.100     = 0.0216 kg     = 21.6 g
SF = 150e6 / 18.75e6                  = 8.0
```

Those are the values printed in `max_bending_stress_pa`, `tip_deflection_m`, `mass_kg` and `yield_safety_factor`. The `_display` fields are six-significant-digit strings for humans. All comparisons and the selection use the unrounded binary64 values; display rounding never changes a decision.

### Why thickness can matter more than a higher-yield-strength material

Two different constraints are in play:

- **Stiffness:** `δ ∝ 1/t³` and `δ ∝ 1/E`. Yield strength does not appear. A higher `S_y` cannot rescue a deflection failure.
- **Strength:** `σ ∝ 1/t²`, so `SF ∝ S_y t²`. Thickness is very effective here as well, but it also adds mass linearly, `m ∝ t`.

Going from 3 mm to 4 mm reduces deflection by a factor of `(4/3)³ = 2.37` and stress by `(4/3)² = 1.78`, while adding only 33% mass. A higher-yield-strength material can avoid a strength failure, but if deflection governs, increasing `E`, increasing `t`, shortening `L`, or reducing `F` is what matters. In the two-material case, the low-density material has a lower modulus and needs 5 mm to meet stiffness, but it still wins on total mass.

### Selection and ties

Every supplied material × stock-thickness pair is evaluated. A candidate is feasible when **both** checks pass. Boundary equality passes (`δ <= limit`, `SF >= minimum`). The selected candidate is the one with the lowest unrounded `mass_kg`.

Exact mass ties are resolved deterministically by `material_id` in ascending Unicode code-point order, then `thickness_m` ascending. The rule is included in the JSON output.

If no candidate qualifies, Metron still returns a valid JSON engineering result with `status = "no_feasible_candidate"`, every candidate's rejection reasons and a `failed_constraints` summary. That is different from invalid input, which returns `status = "invalid_input"` and structured validation errors.

---

## Input and output

A case is one JSON object. **Units live in the field names; there is no generic `units` setting.** Supported input fields:

| Field | Unit | Meaning |
|---|---|---|
| `beam.length_mm` | mm | Cantilever length `L` |
| `beam.width_mm` | mm | Width `b`, perpendicular to the load |
| `beam.tip_force_n` | N | Downward static point load at the free end |
| `constraints.max_tip_deflection_mm` | mm | Maximum permitted tip deflection |
| `constraints.min_yield_safety_factor` | — | Minimum permitted yield safety factor |
| `stock_thicknesses_mm` | mm | Unique positive stock thicknesses to evaluate |
| `materials[].id` | — | Unique material identifier included in the output |
| `materials[].name` | — | Human-readable label |
| `materials[].provenance` | — | Source/limitations label; required |
| `materials[].elastic_modulus_gpa` | GPa | Young's modulus `E` |
| `materials[].density_kg_m3` | kg/m³ | Density `ρ` |
| `materials[].yield_strength_mpa` | MPa | Yield strength `S_y` |

The parser rejects unknown fields (including ambiguous `length` or `units`), numeric strings, booleans, non-finite values, non-positive dimensions and duplicate IDs/thicknesses. All conversions to SI happen at this one input boundary. See [`docs/json-contract.md`](docs/json-contract.md) for the full schema and output fields.

The CLI is one entry point:

```text
python -m metron CASE_FILE [--compact]
```

Exit codes:

| Code | Meaning |
|---:|---|
| `0` | `status = "feasible"`; a selected candidate is present |
| `1` | `status = "no_feasible_candidate"`; valid result, no qualifying pair |
| `2` | `status = "invalid_input"`; malformed JSON, missing file or validation failure |

The CLI prints JSON to stdout in both success and validation-failure cases. For a Hermes/Ollama integration, call `python -m metron <case>` (or the installed `metron`) and parse stdout. No LLM is needed for the calculation.

---

## Verification

The suite uses only Python's standard library and does not call the solver to derive its expected physics values.

```powershell
python -m unittest discover -s tests -t . -v
```

Coverage includes:

- the reference values `I = 1.0666667e-10 m⁴`, `σ = 18.75 MPa`, `δ = 0.446429 mm`, `m = 21.6 g`, `SF = 8`;
- doubling force doubles both stress and deflection;
- doubling thickness reduces stress by four and deflection by eight;
- inclusive equality at the safety-factor boundary;
- missing properties, invalid dimensions, ambiguous units, non-finite values and booleans;
- selection across materials, exact-mass tie-breaking and no-feasible-candidate outcomes;
- the normal CLI entry point, all three exit codes and machine-readable validation errors.

The local result and exact commands are recorded in [`docs/verification.md`](docs/verification.md). GitHub Actions runs the same tests on push and pull request via [`.github/workflows/ci.yml`](.github/workflows/ci.yml).

**What the checks establish:** agreement between the implementation and the stated Euler–Bernoulli beam model. They do **not** establish that a physical arm behaves this way. Physical validation would require measured dimensions, measured material properties, a characterized clamp, controlled loading and deflection/strain measurements. The synthetic fixtures are not a substitute for any of that.

---

## Assumptions and limitations

- Static, uniaxial, small-deflection Euler–Bernoulli bending only; no shear deformation or large-displacement effects.
- Ideal rigid clamp at one end; a single transverse point load at the free end.
- Straight, prismatic, rectangular section; constant homogeneous isotropic properties.
- Nominal stress only. No stress concentration at the clamp, surface finish, holes, welds, threads or contact effects.
- No self-weight, dynamic load, vibration, fatigue, creep, buckling, local crippling or plastic redistribution.
- Material fixtures are synthetic and not design data; density and modulus are treated as deterministic constants.
- Stock thickness is exact; no mill tolerance, corrosion allowance, coating or surface treatment.
- The mass is the beam only, excluding clamp hardware, fasteners and non-structural material.
- A yield safety factor is not a complete design code check.

Deferred beyond this milestone: real material databases, model adapters, Hermes/Ollama integration code, persistence and any frontend.

---

## Repository map

```text
Hephaistos/
├── cases/
│   ├── support_arm_reference.json       # 3/4/5 mm reference case
│   └── support_arm_material_choice.json # two-material comparison
├── docs/
│   ├── json-contract.md
│   └── verification.md
├── metron/
│   ├── beam.py                          # closed-form SI calculations
│   ├── case.py                          # validation and one-time SI conversion
│   ├── solver.py                        # pair evaluation and selection
│   ├── report.py                        # stable JSON result contract
│   ├── cli.py                           # command-line entry point
│   └── __main__.py
├── tests/
├── .github/workflows/ci.yml
├── pyproject.toml
└── README.md
```

## Next milestone

Replace the synthetic fixtures with a small, curated collection of **grade-, temper-, and product-form-specific material records**, each backed by a manufacturer datasheet or recognized handbook and carrying a traceable source citation, product form, thickness range, and the conditions under which `E`, `ρ` and `S_y` apply. Add provenance tests and a reviewable source table; keep the existing calculation contract stable.
