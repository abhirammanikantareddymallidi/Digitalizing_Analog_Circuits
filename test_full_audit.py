"""Executable application audit for core physics, API, and validation contracts."""

import math

from app import app
from config.circuit_configs import CIRCUIT_CONFIGS, get_parameter_classification, get_ui_input_parameters
from optimizer.forward import ForwardAnalyzer
from optimizer.inverse import InverseDesigner
from physics.transistor import (
    _cm2Vs_to_m2Vs,
    _fF_to_F,
    _fF_um2_to_F_m2,
    _kOhm_to_Ohm,
    _uA_to_A,
    _um_to_m,
)
from technology.tech_database import TechDatabase


def assert_finite_outputs(result):
    values = result.get("physics_results", result.get("computed_outputs", {}))
    allowed_infinite = {"Rin", "ro", "ro_kOhm", "Rout", "Rout_kOhm", "CMRR", "CMRR_dB"}
    for name, value in values.items():
        if isinstance(value, float) and math.isnan(value):
            raise AssertionError(f"{name} is NaN")
        if isinstance(value, float) and math.isinf(value) and name not in allowed_infinite:
            raise AssertionError(f"{name} is unexpectedly infinite")


def run_audit():
    forward = ForwardAnalyzer()
    inverse = InverseDesigner(n_candidates=2)
    circuits = list(CIRCUIT_CONFIGS)
    assert circuits == [
        "common_source", "common_gate", "common_drain",
        "differential_amplifier", "single_stage_opamp",
        "two_stage_opamp", "ring_oscillator",
    ]

    for circuit, config in CIRCUIT_CONFIGS.items():
        params = {name: info["default"] for name, info in config["input_parameters"].items()}
        result = forward.analyze(
            circuit,
            params,
            include_ml=False,
            device_type=config["transistor_type"],
        )
        assert "error" not in result, (circuit, result)
        assert_finite_outputs(result)
        classification = get_parameter_classification(circuit)
        ui_inputs = get_ui_input_parameters(circuit)
        assert not set(config.get("calculated_parameters", [])) & set(ui_inputs)
        assert all(category in {
            "USER_INPUT", "TECHNOLOGY_PARAMETER", "CALCULATED_OUTPUT"
        } for category in classification.values())

        calculated = config.get("calculated_parameters", [])
        if calculated:
            rejected = forward.analyze(
                circuit,
                {**params, calculated[0]: 1.0},
                include_ml=False,
                device_type=config["transistor_type"],
            )
            assert rejected["error"] == "Invalid input parameters"

    single_stage = forward.analyze(
        "single_stage_opamp",
        {
            "VDD": 1.8,
            "VSS": 0.0,
            "Wn": 10.0,
            "Ln": 0.18,
            "Wp": 20.0,
            "Lp": 0.18,
            "IBIAS": 50.0,
            "CL": 25.0,
            "VTH_n": 0.4,
            "VTH_p": -0.4,
            "mu_n": 450.0,
            "mu_p": 120.0,
            "Cox": 8.63,
            "lambda_n": 0.1,
            "lambda_p": 0.1,
        },
        include_ml=False,
        device_type="CMOS",
    )
    assert "error" not in single_stage, single_stage
    assert_finite_outputs(single_stage)

    two_stage = forward.analyze(
        "two_stage_opamp",
        {
            "VDD": 1.8,
            "VSS": 0.0,
            "Wn1": 10.0,
            "Ln1": 0.18,
            "Wp1": 20.0,
            "Lp1": 0.18,
            "Wn2": 12.0,
            "Ln2": 0.18,
            "Wp2": 24.0,
            "Lp2": 0.18,
            "IBIAS1": 20.0,
            "IBIAS2": 30.0,
            "CC": 0.5,
            "CL": 100.0,
            "VTH_n": 0.4,
            "VTH_p": -0.4,
            "mu_n": 450.0,
            "mu_p": 120.0,
            "Cox": 8.63,
            "lambda_n": 0.1,
            "lambda_p": 0.1,
        },
        include_ml=False,
        device_type="CMOS",
    )
    assert "error" not in two_stage, two_stage
    assert_finite_outputs(two_stage)

    inverse_single = inverse.design("single_stage_opamp", {"Av_dB": 20.0}, fixed_params={"VDD": 1.8, "VSS": 0.0})
    assert inverse_single["candidates"] and inverse_single["candidates"][0]["fully_valid"]

    invalid = {name: info["default"] for name, info in CIRCUIT_CONFIGS["common_source"]["input_parameters"].items()}
    invalid["W"] = -1.0
    rejected = forward.analyze("common_source", invalid, include_ml=False)
    assert rejected["error"] == "Invalid input parameters"

    expected_conversions = {
        "um": (_um_to_m(1), 1e-6),
        "mobility": (_cm2Vs_to_m2Vs(1), 1e-4),
        "Cox": (_fF_um2_to_F_m2(1), 1e-3),
        "uA": (_uA_to_A(1), 1e-6),
        "kOhm": (_kOhm_to_Ohm(1), 1e3),
        "fF": (_fF_to_F(1), 1e-15),
    }
    for name, (actual, expected) in expected_conversions.items():
        assert actual == expected, (name, actual, expected)

    database = TechDatabase.get_instance()
    assert database.loaded_count == 4
    for node_name in ("45nm", "32nm", "22nm", "16nm"):
        node = database.get_node(node_name)
        assert node is not None and node.has_model_file
        assert node.nmos is not None and node.pmos is not None

    inverse_result = inverse.design("common_source", {"Av_dB": 20.0}, fixed_params={"VDD": 1.8})
    candidate = inverse_result["candidates"][0]
    assert candidate["fully_valid"]
    design = candidate["design_parameters"]
    assert "VDS" not in design and "IBIAS" not in design
    verified = forward.analyze("common_source", design, include_ml=False)
    verified_outputs = verified["physics_results"]
    assert math.isclose(verified_outputs["Av_dB"], 20.0, rel_tol=0, abs_tol=0.05)
    assert verified_outputs["operating_region"] == "saturation"
    assert verified["verification_summary"]["overall_status"] == "PASS"

    with app.test_client() as client:
        assert client.get("/api/circuits").status_code == 200
        assert client.get("/api/technologies").status_code == 200
        response = client.post(
            "/api/inverse",
            json={
                "circuit_type": "common_source",
                "targets": {"Av_dB": 20.0},
                "fixed_params": {"VDD": 1.8},
            },
        )
        assert response.status_code == 200
        assert response.get_json()["candidates"][0]["fully_valid"]

    print("FULL AUDIT PASSED")


if __name__ == "__main__":
    run_audit()