# Circuit Input-Output Analyzer

A Flask web application for physics-based analog circuit analysis and design-space exploration. It accepts circuit inputs, calculates electrical performance, checks physical and technology constraints, and can search for circuit parameters that meet user-defined targets.

## What the project does

The application supports two main workflows:

1. **Forward analysis**: provide circuit parameters and receive calculated outputs such as gain, bandwidth, bias current, power, noise, area, swing, and operating region.
2. **Inverse design**: provide desired performance targets and fixed parameters; the optimizer searches for feasible design parameters and verifies every candidate.

The system combines:

- Circuit equations and transistor physics
- Physical and circuit-level constraint checks
- PTM technology-model parsing and technology-specific limits
- Optional machine-learning predictions for comparison
- A browser UI and JSON REST API

## Supported circuits

- `common_source`: NMOS common-source amplifier
- `common_gate`: NMOS common-gate amplifier
- `common_drain`: NMOS source follower
- `differential_amplifier`: NMOS differential pair
- `ring_oscillator`: CMOS ring oscillator

## Project structure

```text
app.py                         Flask application and API routes
config/                        Circuit definitions and parameter ranges
equations/                     Circuit and transistor equations
physics/                       Device physics, constants, and unit conversion
constraints/                   Physical and circuit validation rules
technology/                    PTM parser, technology database, and limits
Technology nodes/              PTM model files: 16nm, 22nm, 32nm, 45nm
optimizer/                     Forward analysis and inverse design
models/                        Optional ML models and model selection
simulator/                     Simulation and verification helpers
validation/                    Consistency validation utilities
data/                          Data generation helpers
ui/index.html                  Browser interface
ui/static/                     CSS and JavaScript frontend
test_full_audit.py              Full physics, API, and technology audit
test_dse.py                    Forward and inverse design smoke test
```

## End-to-end workflow

### 1. Application startup

1. Python starts `app.py`.
2. Flask creates the web application using `ui/` as the template directory and `ui/static/` for frontend assets.
3. `ModelSelector`, `ForwardAnalyzer`, and `InverseDesigner` are initialized.
4. `TechDatabase` scans `Technology nodes/` and loads the available `.pm` files.
5. The technology constraint engine becomes available for API requests.

### 2. Browser initialization

When the browser opens `/`:

1. Flask returns `ui/index.html`.
2. `ui/static/js/main.js` requests `/api/circuits`.
3. The frontend builds the selected circuit's input form from its configuration.
4. The frontend requests `/api/technologies`.
5. Valid technology nodes are added to the technology selector.
6. The user chooses forward analysis or inverse design.

### 3. Circuit configuration

Each circuit is defined in `config/circuit_configs.py`. A configuration owns:

- Circuit name and transistor type
- User input parameters and defaults
- Technology-controlled parameters
- Calculated outputs that must not be supplied as inputs
- Output metrics
- Equation names
- Circuit-specific constraints

The configuration is the source used by both the API and the UI, so the form and analysis use the same parameter contract.

### 4. Technology selection

Technology files in `Technology nodes/` are parsed by `technology/ptm_parser.py` and stored by `technology/tech_database.py`.

For a selected node, the system can provide:

- NMOS and PMOS model values
- Nominal supply voltage
- Threshold voltage
- Mobility
- Oxide capacitance
- Technology-specific parameter ranges
- Parse errors and warnings

Technology values are used as defaults where appropriate. User values are still validated against the selected technology limits.

## Forward-analysis workflow

The forward path is:

```text
User inputs
    -> API validation
    -> Circuit and device-type validation
    -> Technology compatibility check
    -> Technology defaults and parameter aliases
    -> Circuit equation evaluation
    -> Optional ML prediction
    -> Physics constraint checks
    -> Circuit constraint checks
    -> Technology constraint checks
    -> Verification summary and result JSON
```

Detailed behavior:

1. Normalize the circuit name, for example `common source` becomes `common_source`.
2. Confirm that the circuit exists and that the requested device type matches it.
3. Reject unknown inputs, calculated outputs, non-numeric values, negative dimensions, and other invalid domains.
4. Check whether the selected technology node is compatible with the circuit.
5. Fill missing values using technology defaults first, then circuit defaults.
6. Resolve supported aliases such as `Wn` to `W`, `Ln` to `L`, and `VBIAS` to `VGS`.
7. Select the equation class through `equations.circuit_equations.get_circuit_equations()`.
8. Compute the operating point and performance metrics.
9. If enabled and a trained model is available, calculate ML predictions and compare them with physics results.
10. Run physical, circuit, and technology checks.
11. Return calculated outputs, equations used, constraint details, technology information, ML comparison, and an overall `PASS`, `WARNING`, or `FAIL` status.

### Forward API example

```powershell
curl -X POST http://127.0.0.1:5000/api/forward `
  -H "Content-Type: application/json" `
  -d '{
    "circuit_type": "common_source",
    "params": {
      "VDD": 1.8,
      "VGS": 0.6,
      "W": 10.0,
      "L": 0.18,
      "RD": 2.0,
      "CL": 50.0
    },
    "include_ml": false,
    "technology_node": "16nm",
    "device_type": "NMOS"
  }'
```

Important response sections include:

- `physics_results`
- `equations_used`
- `constraint_checks`
- `physics_checks`
- `circuit_checks`
- `tech_checks`
- `verification_summary`
- `ml_prediction`
- `ml_vs_physics`

## Inverse-design workflow

The inverse path is:

```text
Target metrics and fixed parameters
    -> Circuit and technology validation
    -> Select variable parameters and bounds
    -> Apply technology defaults
    -> Analytical initial guess when available
    -> Global differential-evolution search
    -> Multi-start local optimization
    -> Optional ML-assisted starting point
    -> Forward-equation evaluation for each candidate
    -> Physics, circuit, and technology verification
    -> Rank and return candidates
```

Detailed behavior:

1. Normalize and validate the circuit type.
2. Validate device type and technology compatibility.
3. Reject calculated parameters used as fixed or variable design inputs.
4. Apply technology defaults to unspecified fixed parameters.
5. Select default variable parameters unless the caller provides a list.
6. Build parameter bounds from `config/parameter_ranges.py` and technology data.
7. Try analytical sizing where a closed-form relationship is available.
8. Run SciPy differential evolution for global exploration.
9. Run multiple seeded local searches to find additional candidates.
10. Use an ML prediction as an optional starting point when a trained model exists.
11. Recompute every candidate with the circuit equations.
12. Reject candidates that fail critical physics, circuit, or technology constraints.
13. Calculate target achievement and rank candidates by validity and objective error.

### Inverse API example

```powershell
curl -X POST http://127.0.0.1:5000/api/inverse `
  -H "Content-Type: application/json" `
  -d '{
    "circuit_type": "common_source",
    "targets": {
      "Av_dB": 20.0,
      "BW_MHz": 80.0
    },
    "fixed_params": {
      "VDD": 1.8
    },
    "technology_node": "16nm",
    "device_type": "NMOS"
  }'
```

Each candidate may include:

- `design_parameters`
- `target_status`
- `objective_value`
- `method`
- `physically_valid`
- `fully_valid`
- Physics and technology failure counts
- A forward-verification result

## API routes

| Method | Route | Purpose |
|---|---|---|
| `GET` | `/` | Serve the browser interface |
| `GET` | `/api/circuits` | List circuits, inputs, outputs, and dependencies |
| `GET` | `/api/technologies` | List discovered technology nodes |
| `GET` | `/api/technology/<node>` | Return complete node details |
| `GET` | `/api/tech-defaults/<node>` | Return recommended defaults for a device type |
| `POST` | `/api/forward` | Run physics-based forward analysis |
| `POST` | `/api/inverse` | Run inverse design and candidate search |

## Installation and startup

Use Python 3.10 or newer.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install flask numpy scipy scikit-learn
```

`xgboost` is optional. The ML layer falls back to scikit-learn Gradient Boosting when XGBoost is unavailable.

Start the application from the project root:

```powershell
python app.py
```

Open:

```text
http://127.0.0.1:5000
```

## Validation and testing

Run the full audit:

```powershell
python test_full_audit.py
```

The audit checks:

- All supported circuit types
- Default forward calculations
- Invalid input rejection
- Unit conversions
- Technology-node loading
- Inverse-design target achievement
- Forward verification of inverse candidates
- Core API routes

Run the design-space smoke test:

```powershell
python test_dse.py
```

## Design rules and important behavior

- Physics results are the authoritative calculated outputs.
- ML predictions are supplementary and are compared against physics results.
- ML values are not silently clamped to technology limits.
- Critical constraint failures make a result invalid.
- Calculated outputs cannot be passed back as user inputs.
- Technology-node values can override generic defaults for technology-owned parameters.
- The inverse designer never trusts an optimizer result without forward verification.
- Non-finite values are sanitized before JSON serialization.

## Typical usage summary

```text
1. Start app.py.
2. Open the web UI.
3. Select a circuit.
4. Select a device type and technology node when required.
5. Choose Forward Analysis or Inverse Design.
6. Enter circuit inputs or target metrics.
7. Run the analysis.
8. Review physics outputs and equations.
9. Review PASS, WARNING, or FAIL checks.
10. For inverse design, inspect candidates and their verification status.
```
