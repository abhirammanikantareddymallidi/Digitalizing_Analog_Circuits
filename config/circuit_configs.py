"""
Circuit configuration definitions for all supported circuit types.

Each configuration specifies:
  - input_parameters: parameters the user provides
  - output_parameters: computed results
  - equations: named equation references
  - constraints: physical/operating constraints
  - description: human-readable circuit description
"""

CIRCUIT_CONFIGS = {
    # ─────────────────────────────────────────────────────────────
    # Common Source Amplifier
    # ─────────────────────────────────────────────────────────────
    "common_source": {
        "name": "Common Source Amplifier",
        "abbreviation": "CS",
        "transistor_type": "NMOS",
        "description": (
            "Single-stage NMOS amplifier with the source terminal grounded. "
            "Provides voltage gain with 180° phase inversion."
        ),
        "input_parameters": {
            "VDD":     {"unit": "V",     "default": 1.8,    "description": "Supply voltage"},
            "VGS":     {"unit": "V",     "default": 0.6,    "description": "Gate-source voltage (VBIAS)"},
            "VTH":     {"unit": "V",     "default": 0.4,    "description": "Threshold voltage"},
            "W":       {"unit": "um",    "default": 10.0,   "description": "Channel width (Wn)"},
            "L":       {"unit": "um",    "default": 0.18,   "description": "Channel length (Ln)"},
            "mu_n":    {"unit": "cm2/Vs","default": 450.0,  "description": "Electron mobility"},
            "Cox":     {"unit": "fF/um2","default": 8.63,   "description": "Oxide capacitance per unit area"},
            "lambda_n":{"unit": "1/V",   "default": 0.1,    "description": "Channel-length modulation parameter"},
            "RD":      {"unit": "kΩ",    "default": 2.0,    "description": "Drain resistance"},
            "CL":      {"unit": "fF",    "default": 50.0,   "description": "Load capacitance"},
        },
        "technology_parameters": ["VTH", "mu_n", "Cox", "lambda_n"],
        "calculated_parameters": ["VOV", "ID", "ID_uA", "IBIAS", "VDS", "operating_region", "gm", "ro", "Rout", "Av", "Av_dB", "power_dissipation"],
        "output_parameters": [
            "operating_region", "ID", "ID_uA", "VDS", "VOV", "VDS_sat", "gm", "ro",
            "Av", "Av_dB", "Rin", "Rout", "BW", "BW_MHz", "GBW", "GBW_MHz",
            "phase_margin_deg", "power_dissipation", "power_mW",
            "thermal_noise_nV", "flicker_noise_nV", "total_noise_nV", "integrated_noise_uV",
            "output_swing_V", "output_swing_pp", "transistor_area_um2", "total_area_um2",
            "IIP3_V", "IIP3_dBm", "PSRR", "PSRR_dB",
        ],
        "equations": [
            "ID_saturation", "ID_triode", "gm_saturation",
            "ro_saturation", "Av_cs", "Rout_cs", "BW_cs", "GBW_cs",
            "phase_margin_cs", "power_cs", "thermal_noise_cs", "flicker_noise_cs",
            "output_swing_cs", "area_cs", "linearity_iip3_cs", "psrr_cs",
        ],
        "constraints": [
            "region_detection", "VDS_saturation", "current_positive",
            "power_budget", "voltage_headroom", "output_swing_headroom", "phase_margin_stability",
        ],
    },

    # ─────────────────────────────────────────────────────────────
    # Common Gate Amplifier
    # ─────────────────────────────────────────────────────────────
    "common_gate": {
        "name": "Common Gate Amplifier",
        "abbreviation": "CG",
        "transistor_type": "NMOS",
        "description": (
            "Single-stage NMOS amplifier with the gate terminal at AC ground. "
            "Provides voltage gain without phase inversion and low input impedance."
        ),
        "input_parameters": {
            "VDD":     {"unit": "V",     "default": 1.8,    "description": "Supply voltage"},
            "VGS":     {"unit": "V",     "default": 0.8,    "description": "Gate-source voltage"},
            "VTH":     {"unit": "V",     "default": 0.4,    "description": "Threshold voltage"},
            "W":       {"unit": "um",    "default": 10.0,   "description": "Channel width"},
            "L":       {"unit": "um",    "default": 0.18,   "description": "Channel length"},
            "mu_n":    {"unit": "cm2/Vs","default": 450.0,  "description": "Electron mobility"},
            "Cox":     {"unit": "fF/um2","default": 8.63,   "description": "Oxide capacitance per unit area"},
            "lambda_n":{"unit": "1/V",   "default": 0.1,    "description": "Channel-length modulation parameter"},
            "RD":      {"unit": "kΩ",    "default": 5.0,    "description": "Drain resistance"},
            "RS":      {"unit": "kΩ",    "default": 1.0,    "description": "Source resistance (signal source)"},
            "CL":      {"unit": "fF",    "default": 50.0,   "description": "Load capacitance"},
        },
        "technology_parameters": ["VTH", "mu_n", "Cox", "lambda_n"],
        "calculated_parameters": ["VOV", "ID", "VDS", "operating_region", "gm", "ro", "Rout", "Av", "Av_dB", "power_dissipation"],
        "output_parameters": [
            "operating_region", "ID", "gm", "ro", "VOV",
            "Av", "Av_dB", "Rin", "Rout", "BW", "GBW",
            "power_dissipation",
        ],
        "equations": [
            "ID_saturation", "ID_triode", "gm_saturation",
            "ro_saturation", "Av_cg", "Rin_cg", "Rout_cg", "BW_cg",
        ],
        "constraints": [
            "region_detection", "VDS_saturation", "current_positive",
            "power_budget", "voltage_headroom",
        ],
    },

    # ─────────────────────────────────────────────────────────────
    # Common Drain (Source Follower)
    # ─────────────────────────────────────────────────────────────
    "common_drain": {
        "name": "Common Drain (Source Follower)",
        "abbreviation": "CD",
        "transistor_type": "NMOS",
        "description": (
            "Voltage buffer with near-unity gain, high input impedance, "
            "and low output impedance. Output taken from the source terminal."
        ),
        "input_parameters": {
            "VDD":     {"unit": "V",     "default": 1.8,    "description": "Supply voltage"},
            "VGS":     {"unit": "V",     "default": 0.8,    "description": "Gate-source voltage"},
            "VTH":     {"unit": "V",     "default": 0.4,    "description": "Threshold voltage"},
            "W":       {"unit": "um",    "default": 10.0,   "description": "Channel width"},
            "L":       {"unit": "um",    "default": 0.18,   "description": "Channel length"},
            "mu_n":    {"unit": "cm2/Vs","default": 450.0,  "description": "Electron mobility"},
            "Cox":     {"unit": "fF/um2","default": 8.63,   "description": "Oxide capacitance per unit area"},
            "lambda_n":{"unit": "1/V",   "default": 0.1,    "description": "Channel-length modulation parameter"},
            "RS":      {"unit": "kΩ",    "default": 2.0,    "description": "Source resistance / load"},
            "CL":      {"unit": "fF",    "default": 50.0,   "description": "Load capacitance"},
        },
        "technology_parameters": ["VTH", "mu_n", "Cox", "lambda_n"],
        "calculated_parameters": ["VOV", "ID", "VDS", "operating_region", "gm", "ro", "Rout", "Av", "Av_dB", "power_dissipation"],
        "output_parameters": [
            "operating_region", "ID", "gm", "ro", "VOV",
            "Av", "Av_dB", "Rin", "Rout", "BW",
            "power_dissipation",
        ],
        "equations": [
            "ID_saturation", "ID_triode", "gm_saturation",
            "ro_saturation", "Av_cd", "Rin_cd", "Rout_cd", "BW_cd",
        ],
        "constraints": [
            "region_detection", "VDS_saturation", "current_positive",
            "power_budget",
        ],
    },

    # ─────────────────────────────────────────────────────────────
    # Differential Amplifier
    # ─────────────────────────────────────────────────────────────
    "differential_amplifier": {
        "name": "Differential Amplifier",
        "abbreviation": "DiffAmp",
        "transistor_type": "NMOS",
        "description": (
            "NMOS differential pair with resistive loads and tail current source. "
            "Amplifies the difference between two input signals while rejecting common-mode."
        ),
        "input_parameters": {
            "VDD":      {"unit": "V",     "default": 1.8,   "description": "Supply voltage"},
            "VCM":      {"unit": "V",     "default": 0.9,   "description": "Common-mode input voltage"},
            "Vdiff":    {"unit": "mV",    "default": 10.0,  "description": "Differential input voltage"},
            "VTH":      {"unit": "V",     "default": 0.4,   "description": "Threshold voltage"},
            "W":        {"unit": "um",    "default": 20.0,  "description": "Differential pair W (each)"},
            "L":        {"unit": "um",    "default": 0.18,  "description": "Differential pair L (each)"},
            "mu_n":     {"unit": "cm2/Vs","default": 450.0, "description": "Electron mobility"},
            "Cox":      {"unit": "fF/um2","default": 8.63,  "description": "Oxide capacitance per unit area"},
            "lambda_n": {"unit": "1/V",   "default": 0.1,   "description": "Channel-length modulation parameter"},
            "RD":       {"unit": "kΩ",    "default": 5.0,   "description": "Drain load resistance (each)"},
            "ISS":      {"unit": "uA",    "default": 200.0, "description": "Tail current source"},
            "RSS":      {"unit": "kΩ",    "default": 50.0,  "description": "Tail current source output resistance"},
            "CL":       {"unit": "fF",    "default": 50.0,  "description": "Load capacitance (each output)"},
        },
        "technology_parameters": ["VTH", "mu_n", "Cox", "lambda_n"],
        "calculated_parameters": ["ID_each", "VGS", "VDS", "VOV", "operating_region", "gm", "ro", "Ad", "Ad_dB", "Acm", "CMRR", "Rout", "power_dissipation"],
        "output_parameters": [
            "operating_region", "ID_each", "gm", "ro", "VOV",
            "Ad", "Ad_dB", "Acm", "Acm_dB", "CMRR", "CMRR_dB",
            "Rin_diff", "Rout",
            "BW", "BW_MHz", "GBW", "GBW_MHz",
            "phase_margin_deg", "power_dissipation", "power_mW",
            "thermal_noise_nV", "total_noise_nV",
            "output_swing_V", "output_swing_pp",
            "transistor_area_um2", "total_area_um2",
            "IIP3_V", "IIP3_dBm", "PSRR_dB",
            "VICM_max", "VICM_min",
        ],
        "equations": [
            "ID_diff_pair", "gm_diff", "Ad_diff", "Acm_diff",
            "CMRR_eq", "BW_diff", "VICM_range",
            "phase_margin_diff", "noise_diff", "output_swing_diff",
            "area_diff", "linearity_iip3_diff", "psrr_diff",
        ],
        "constraints": [
            "region_detection", "VICM_range_check",
            "tail_current_balance", "current_positive",
            "power_budget", "voltage_headroom",
        ],
    },

    # ─────────────────────────────────────────────────────────────
    # Single-Stage Amplifier
    # ─────────────────────────────────────────────────────────────
    "single_stage_opamp": {
        "name": "Single-Stage Amplifier",
        "abbreviation": "SSA",
        "transistor_type": "CMOS",
        "description": (
            "CMOS single-stage operational amplifier with a differential input stage "
            "and a current-source load. Provides high gain and moderate bandwidth."
        ),
        "input_parameters": {
            "VDD":     {"unit": "V",     "default": 1.8,    "description": "Supply voltage"},
            "VSS":     {"unit": "V",     "default": 0.0,    "description": "Negative supply / ground reference"},
            "Wn":      {"unit": "um",    "default": 10.0,   "description": "NMOS width"},
            "Ln":      {"unit": "um",    "default": 0.18,   "description": "NMOS length"},
            "Wp":      {"unit": "um",    "default": 20.0,   "description": "PMOS width"},
            "Lp":      {"unit": "um",    "default": 0.18,   "description": "PMOS length"},
            "IBIAS":   {"unit": "uA",    "default": 50.0,   "description": "Bias current"},
            "CL":      {"unit": "fF",    "default": 25.0,   "description": "Load capacitance"},
            "VTH_n":   {"unit": "V",     "default": 0.4,    "description": "NMOS threshold voltage"},
            "VTH_p":   {"unit": "V",     "default": -0.4,   "description": "PMOS threshold voltage"},
            "mu_n":    {"unit": "cm2/Vs","default": 450.0,  "description": "NMOS mobility"},
            "mu_p":    {"unit": "cm2/Vs","default": 120.0,  "description": "PMOS mobility"},
            "Cox":     {"unit": "fF/um2","default": 8.63,   "description": "Oxide capacitance per unit area"},
            "lambda_n":{"unit": "1/V",   "default": 0.1,    "description": "NMOS channel-length modulation"},
            "lambda_p":{"unit": "1/V",   "default": 0.1,    "description": "PMOS channel-length modulation"},
        },
        "technology_parameters": ["VTH_n", "VTH_p", "mu_n", "mu_p", "Cox", "lambda_n", "lambda_p"],
        "calculated_parameters": ["VOV", "ID", "ID_uA", "VDS", "operating_region", "gm", "ro", "Rout", "Av", "Av_dB", "power_dissipation"],
        "output_parameters": [
            "operating_region", "ID", "ID_uA", "VOV", "gm", "gm_mS", "ro", "ro_kOhm",
            "Rout", "Rout_kOhm", "Av", "Av_magnitude", "Av_dB", "pole_frequency",
            "pole_frequency_MHz", "GBW", "GBW_MHz", "CMRR_dB", "output_swing_V",
            "output_swing_pp", "power_dissipation", "power_mW",
        ],
        "equations": [
            "single_stage_opamp_dc", "single_stage_opamp_gain", "single_stage_opamp_bandwidth",
            "single_stage_opamp_output_swing", "single_stage_opamp_power",
        ],
        "constraints": [
            "region_detection", "saturation_required", "gain_positive", "output_swing_feasible",
        ],
    },

    # ─────────────────────────────────────────────────────────────
    # Two-Stage Amplifier
    # ─────────────────────────────────────────────────────────────
    "two_stage_opamp": {
        "name": "Two-Stage Amplifier",
        "abbreviation": "TSA",
        "transistor_type": "CMOS",
        "description": (
            "Two-stage CMOS op-amp with a differential first stage and a gain stage. "
            "Designed for higher gain and moderate output drive capability."
        ),
        "input_parameters": {
            "VDD":     {"unit": "V",     "default": 1.8,    "description": "Supply voltage"},
            "VSS":     {"unit": "V",     "default": 0.0,    "description": "Negative supply / ground reference"},
            "Wn1":     {"unit": "um",    "default": 10.0,   "description": "First-stage NMOS width"},
            "Ln1":     {"unit": "um",    "default": 0.18,   "description": "First-stage NMOS length"},
            "Wp1":     {"unit": "um",    "default": 20.0,   "description": "First-stage PMOS width"},
            "Lp1":     {"unit": "um",    "default": 0.18,   "description": "First-stage PMOS length"},
            "Wn2":     {"unit": "um",    "default": 12.0,   "description": "Second-stage NMOS width"},
            "Ln2":     {"unit": "um",    "default": 0.18,   "description": "Second-stage NMOS length"},
            "Wp2":     {"unit": "um",    "default": 24.0,   "description": "Second-stage PMOS width"},
            "Lp2":     {"unit": "um",    "default": 0.18,   "description": "Second-stage PMOS length"},
            "IBIAS1":  {"unit": "uA",    "default": 20.0,   "description": "First-stage bias current"},
            "IBIAS2":  {"unit": "uA",    "default": 30.0,   "description": "Second-stage bias current"},
            "CC":      {"unit": "fF",    "default": 0.5,    "description": "Miller compensation capacitor"},
            "CL":      {"unit": "fF",    "default": 100.0,  "description": "Load capacitance"},
            "VTH_n":   {"unit": "V",     "default": 0.4,    "description": "NMOS threshold voltage"},
            "VTH_p":   {"unit": "V",     "default": -0.4,   "description": "PMOS threshold voltage"},
            "mu_n":    {"unit": "cm2/Vs","default": 450.0,  "description": "NMOS mobility"},
            "mu_p":    {"unit": "cm2/Vs","default": 120.0,  "description": "PMOS mobility"},
            "Cox":     {"unit": "fF/um2","default": 8.63,   "description": "Oxide capacitance per unit area"},
            "lambda_n":{"unit": "1/V",   "default": 0.1,    "description": "NMOS channel-length modulation"},
            "lambda_p":{"unit": "1/V",   "default": 0.1,    "description": "PMOS channel-length modulation"},
        },
        "technology_parameters": ["VTH_n", "VTH_p", "mu_n", "mu_p", "Cox", "lambda_n", "lambda_p"],
        "calculated_parameters": ["ID1", "ID1_uA", "ID2", "ID2_uA", "VOV1", "VOV2", "gm1", "gm2", "ro1", "ro2", "A1", "A2", "Av", "Av_dB", "Ceq", "fu", "GBW", "dominant_pole", "non_dominant_pole", "SR", "CMRR_dB", "phase_margin_deg", "output_swing_V", "Rout", "power_dissipation"],
        "output_parameters": [
            "operating_region", "ID1", "ID1_uA", "ID2", "ID2_uA", "VOV1", "VOV2",
            "gm1", "gm1_mS", "gm2", "gm2_mS", "ro1", "ro1_kOhm", "ro2", "ro2_kOhm",
            "A1", "A2", "Av", "Av_magnitude", "Av_dB", "Ceq", "Ceq_fF", "fu", "fu_MHz",
            "GBW", "GBW_MHz", "dominant_pole", "dominant_pole_MHz", "non_dominant_pole",
            "non_dominant_pole_MHz", "SR", "SR_V_per_us", "CMRR_dB", "phase_margin_deg",
            "output_swing_V", "output_swing_pp", "Rout", "Rout_kOhm", "power_dissipation", "power_mW",
        ],
        "equations": [
            "two_stage_dc", "two_stage_gain", "two_stage_compensation", "two_stage_slew", "two_stage_power",
        ],
        "constraints": [
            "region_detection", "saturation_required", "phase_margin_stability", "slew_rate_feasible",
        ],
    },

    # ─────────────────────────────────────────────────────────────
    # Ring Oscillator
    # ─────────────────────────────────────────────────────────────
    "ring_oscillator": {
        "name": "Ring Oscillator",
        "abbreviation": "RO",
        "transistor_type": "CMOS",
        "description": (
            "Ring of an odd number of CMOS inverter stages connected in a loop. "
            "Oscillation frequency is determined by the total propagation delay."
        ),
        "input_parameters": {
            "VDD":      {"unit": "V",     "default": 1.8,   "description": "Supply voltage"},
            "N_stages": {"unit": "",      "default": 5,     "description": "Number of inverter stages (must be odd)"},
            "VTH_n":    {"unit": "V",     "default": 0.4,   "description": "NMOS threshold voltage"},
            "VTH_p":    {"unit": "V",     "default": -0.4,  "description": "PMOS threshold voltage (negative)"},
            "W_n":      {"unit": "um",    "default": 2.0,   "description": "NMOS channel width per stage"},
            "L_n":      {"unit": "um",    "default": 0.18,  "description": "NMOS channel length"},
            "W_p":      {"unit": "um",    "default": 4.0,   "description": "PMOS channel width per stage"},
            "L_p":      {"unit": "um",    "default": 0.18,  "description": "PMOS channel length"},
            "mu_n":     {"unit": "cm2/Vs","default": 450.0, "description": "NMOS mobility"},
            "mu_p":     {"unit": "cm2/Vs","default": 120.0, "description": "PMOS mobility"},
            "Cox":      {"unit": "fF/um2","default": 8.63,  "description": "Oxide capacitance per unit area"},
            "CL":       {"unit": "fF",    "default": 5.0,   "description": "Load capacitance per stage"},
        },
        "technology_parameters": ["VTH_n", "VTH_p", "mu_n", "mu_p", "Cox"],
        "calculated_parameters": ["kn", "kp", "td_per_stage", "total_delay", "f_osc", "T_period", "P_total", "operating_region"],
        "output_parameters": [
            "f_osc", "T_period",
            "td_per_stage", "total_delay",
            "kn_stage", "kp_stage",
            "P_dynamic_per_stage", "P_total",
        ],
        "equations": [
            "inverter_delay", "ring_osc_frequency",
            "dynamic_power_ring",
        ],
        "constraints": [
            "odd_stages", "oscillation_condition",
            "power_budget", "frequency_feasibility",
        ],
    },
}


def get_circuit_config(circuit_type: str) -> dict:
    """Return the configuration dictionary for the specified circuit type."""
    key = circuit_type.lower().replace(" ", "_").replace("-", "_")
    if key not in CIRCUIT_CONFIGS:
        available = ", ".join(CIRCUIT_CONFIGS.keys())
        raise ValueError(
            f"Unknown circuit type '{circuit_type}'. Available types: {available}"
        )
    return CIRCUIT_CONFIGS[key]


def list_circuit_types() -> list:
    """Return a list of all supported circuit type keys."""
    return list(CIRCUIT_CONFIGS.keys())


def get_parameter_classification(circuit_type: str) -> dict:
    """Return the single owning category for every declared circuit parameter."""
    config = get_circuit_config(circuit_type)
    classification = {
        name: "USER_INPUT" for name in config["input_parameters"]
    }
    for name in config.get("technology_parameters", []):
        if name in classification:
            classification[name] = "TECHNOLOGY_PARAMETER"
    for name in config.get("calculated_parameters", []):
        classification[name] = "CALCULATED_OUTPUT"
    for name in config.get("output_parameters", []):
        classification.setdefault(name, "CALCULATED_OUTPUT")
    return classification


def get_dependency_map(circuit_type: str) -> dict:
    """Return forward ownership and inverse target ownership for every parameter."""
    config = get_circuit_config(circuit_type)
    classification = get_parameter_classification(circuit_type)
    dependency_map = {}
    for name, category in classification.items():
        inverse_category = category
        if name in config.get("output_parameters", []):
            inverse_category = "TARGET_SPECIFICATION"
        dependency_map[name] = {
            "forward": category,
            "inverse": inverse_category,
        }
    return dependency_map


def get_ui_input_parameters(circuit_type: str) -> dict:
    """Return only editable design inputs; technology and calculated values are excluded."""
    config = get_circuit_config(circuit_type)
    technology = set(config.get("technology_parameters", []))
    calculated = set(config.get("calculated_parameters", []))
    return {
        name: info for name, info in config["input_parameters"].items()
        if name not in technology and name not in calculated
    }
