"""
Valid parameter ranges and default values for all circuit/device parameters.

Ranges are used for:
  - Input validation
  - Constraint boundary checking
  - Training-data generation bounds
  - Inverse-design search space
"""

PARAMETER_RANGES = {
    # ── Supply / bias voltages ──────────────────────────────────
    "VDD":      {"min": 0.6,   "max": 5.0,    "unit": "V",      "description": "Supply voltage"},
    "VGS":      {"min": 0.0,   "max": 5.0,    "unit": "V",      "description": "Gate-source voltage"},
    "VDS":      {"min": 0.0,   "max": 5.0,    "unit": "V",      "description": "Drain-source voltage"},
    "VTH":      {"min": 0.1,   "max": 1.2,    "unit": "V",      "description": "Threshold voltage (magnitude)"},
    "VTH_n":    {"min": 0.1,   "max": 1.2,    "unit": "V",      "description": "NMOS threshold voltage"},
    "VTH_p":    {"min": -1.2,  "max": -0.1,   "unit": "V",      "description": "PMOS threshold voltage"},
    "VCM":      {"min": 0.0,   "max": 5.0,    "unit": "V",      "description": "Common-mode voltage"},
    "Vdiff":    {"min": -500.0,"max": 500.0,   "unit": "mV",     "description": "Differential input voltage"},

    # ── Transistor dimensions ───────────────────────────────────
    "W":        {"min": 0.1,   "max": 1000.0, "unit": "um",     "description": "Channel width"},
    "L":        {"min": 0.018, "max": 10.0,   "unit": "um",     "description": "Channel length"},
    "W_n":      {"min": 0.1,   "max": 1000.0, "unit": "um",     "description": "NMOS width"},
    "L_n":      {"min": 0.018, "max": 10.0,   "unit": "um",     "description": "NMOS length"},
    "W_p":      {"min": 0.1,   "max": 1000.0, "unit": "um",     "description": "PMOS width"},
    "L_p":      {"min": 0.018, "max": 10.0,   "unit": "um",     "description": "PMOS length"},
    "W_ref":    {"min": 0.1,   "max": 1000.0, "unit": "um",     "description": "Reference transistor width"},
    "L_ref":    {"min": 0.018, "max": 10.0,   "unit": "um",     "description": "Reference transistor length"},
    "W_out":    {"min": 0.1,   "max": 1000.0, "unit": "um",     "description": "Output transistor width"},
    "L_out":    {"min": 0.018, "max": 10.0,   "unit": "um",     "description": "Output transistor length"},

    # ── Process parameters ──────────────────────────────────────
    "mu_n":     {"min": 100.0, "max": 800.0,  "unit": "cm2/Vs", "description": "Electron mobility"},
    "mu_p":     {"min": 50.0,  "max": 400.0,  "unit": "cm2/Vs", "description": "Hole mobility"},
    "Cox":      {"min": 1.0,   "max": 30.0,   "unit": "fF/um2", "description": "Oxide capacitance / area"},
    "lambda_n": {"min": 0.001, "max": 0.5,    "unit": "1/V",    "description": "NMOS CLM parameter"},
    "lambda_p": {"min": 0.001, "max": 0.5,    "unit": "1/V",    "description": "PMOS CLM parameter"},

    # ── Passive components ──────────────────────────────────────
    "RD":       {"min": 0.01,  "max": 1000.0, "unit": "kΩ",     "description": "Drain resistance"},
    "RS":       {"min": 0.01,  "max": 1000.0, "unit": "kΩ",     "description": "Source resistance"},
    "RSS":      {"min": 1.0,   "max": 10000.0,"unit": "kΩ",     "description": "Tail current source resistance"},
    "CL":       {"min": 0.1,   "max": 10000.0,"unit": "fF",     "description": "Load capacitance"},

    # ── Currents & Biasing ──────────────────────────────────────
    "IBIAS":    {"min": 0.0,   "max": 50000.0,"unit": "uA",     "description": "Quiescent bias current"},
    "VBIAS":    {"min": 0.0,   "max": 5.0,    "unit": "V",      "description": "Gate bias voltage"},
    "I_ref":    {"min": 0.1,   "max": 10000.0,"unit": "uA",     "description": "Reference current"},
    "ISS":      {"min": 1.0,   "max": 10000.0,"unit": "uA",     "description": "Tail current"},
    "VDS_out":  {"min": 0.0,   "max": 5.0,    "unit": "V",      "description": "Output VDS"},

    # ── Measurable objectives & Metrics ────────────────────────
    "Av_dB":              {"min": -40.0, "max": 120.0,   "unit": "dB",     "description": "Voltage gain in dB"},
    "BW_MHz":             {"min": 0.001, "max": 100000.0,"unit": "MHz",    "description": "Bandwidth in MHz"},
    "GBW_MHz":            {"min": 0.001, "max": 100000.0,"unit": "MHz",    "description": "Gain-bandwidth product in MHz"},
    "phase_margin_deg":   {"min": 0.0,   "max": 180.0,   "unit": "deg",    "description": "Phase margin in degrees"},
    "power_mW":           {"min": 0.001, "max": 500.0,   "unit": "mW",     "description": "DC power dissipation in mW"},
    "total_noise_nV":     {"min": 0.01,  "max": 10000.0, "unit": "nV/√Hz", "description": "Input-referred noise density at 1kHz"},
    "output_swing_V":     {"min": 0.0,   "max": 5.0,     "unit": "V",      "description": "Single-ended output swing"},
    "output_swing_pp":    {"min": 0.0,   "max": 10.0,    "unit": "V",      "description": "Peak-to-peak output swing"},
    "total_area_um2":     {"min": 0.001, "max": 100000.0,"unit": "um2",    "description": "Total estimated circuit area"},
    "transistor_area_um2":{"min": 0.001, "max": 10000.0, "unit": "um2",    "description": "Transistor active area"},
    "IIP3_V":             {"min": 0.001, "max": 10.0,    "unit": "V",      "description": "Third-order input intercept voltage"},
    "PSRR_dB":            {"min": -20.0, "max": 120.0,   "unit": "dB",     "description": "Power supply rejection ratio in dB"},
    "CMRR_dB":            {"min": -20.0, "max": 140.0,   "unit": "dB",     "description": "Common-mode rejection ratio in dB"},

    # ── Ring oscillator ─────────────────────────────────────────
    "N_stages": {"min": 3,     "max": 101,    "unit": "",       "description": "Number of stages (odd)"},
    "f_clk":    {"min": 0.001, "max": 10000.0,"unit": "MHz",    "description": "Clock frequency"},
}


def get_parameter_range(param_name: str) -> dict:
    """Return the min/max/unit for a named parameter."""
    if param_name not in PARAMETER_RANGES:
        raise ValueError(f"Unknown parameter '{param_name}'")
    return PARAMETER_RANGES[param_name]


def validate_parameter(param_name: str, value: float) -> dict:
    """
    Validate a parameter value against its allowed range.

    Returns:
        dict with keys: valid (bool), message (str), clipped_value (float)
    """
    if param_name not in PARAMETER_RANGES:
        return {"valid": True, "message": "No range defined", "clipped_value": value}

    pr = PARAMETER_RANGES[param_name]
    if value < pr["min"]:
        return {
            "valid": False,
            "message": f"{param_name} = {value} {pr['unit']} is below minimum {pr['min']} {pr['unit']}",
            "clipped_value": pr["min"],
        }
    if value > pr["max"]:
        return {
            "valid": False,
            "message": f"{param_name} = {value} {pr['unit']} is above maximum {pr['max']} {pr['unit']}",
            "clipped_value": pr["max"],
        }
    return {"valid": True, "message": "Within range", "clipped_value": value}
