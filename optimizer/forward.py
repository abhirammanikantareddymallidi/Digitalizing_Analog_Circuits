"""
Forward Analysis Engine.

Pipeline:
    1. Accept circuit type + parameters + technology node
    2. Check technology compatibility
    3. Determine operating region from physics
    4. Compute all outputs using circuit equations
    5. Optionally generate ML prediction
    6. Run constraint/physics verification
    7. Run technology constraint verification (NEW)
    8. If technology constraints fail: mark INVALID, show ML vs. tech limits
    9. Produce final result with full explainability

IMPORTANT:
  - ML predictions that violate technology constraints are REJECTED.
  - Original ML values are always shown alongside the technology limit.
  - Values are never silently clamped.
"""

from __future__ import annotations
import os
import sys
import math
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from typing import Dict, Optional, Any

from equations.circuit_equations import get_circuit_equations
from constraints.physical_constraints import PhysicalConstraintChecker
from constraints.circuit_constraints import CircuitConstraintChecker
from config.circuit_configs import CIRCUIT_CONFIGS
from technology.tech_constraints import TechConstraintEngine
from technology.tech_database import TechDatabase


class ForwardAnalyzer:
    """
    Run forward analysis: circuit type + parameters → performance metrics.

    Every result includes:
        - Physics-computed outputs
        - Operating region determination
        - Equation audit trail
        - Constraint PASS/FAIL status  (physics + circuit + technology)
        - Technology constraint checks per PTM file
        - Optionally, ML prediction for comparison
    """

    def __init__(self, ml_selector=None):
        self.ml_selector  = ml_selector
        self._tech_engine = TechConstraintEngine()
        self._tech_db     = TechDatabase.get_instance()

    def analyze(
        self,
        circuit_type: str,
        params: dict,
        include_ml: bool = True,
        technology_node: Optional[str] = None,
        device_type: str = "NMOS",
    ) -> dict:
        """
        Perform full forward analysis.

        Args:
            circuit_type:     one of the supported circuit types
            params:           dict of input parameters in lab units
            include_ml:       whether to run ML comparison
            technology_node:  e.g. "16nm" — used for tech constraint checks
            device_type:      "NMOS", "PMOS", or "CMOS"

        Returns:
            Comprehensive result dict with physics, ML, technology and validation.
        """
        key = circuit_type.lower().replace(" ", "_").replace("-", "_")
        if key not in CIRCUIT_CONFIGS:
            return {"error": f"Unknown circuit type: {circuit_type}"}

        config = CIRCUIT_CONFIGS[key]
        expected_device = config.get("transistor_type", "NMOS").upper()
        requested_device = device_type.upper()
        if expected_device != requested_device:
            return {
                "error": (
                    f"Circuit '{key}' requires device type {expected_device}; "
                    f"received {requested_device}."
                ),
                "circuit_type": key,
                "device_type": requested_device,
            }

        if key == "cmos_inverter":
            calculated_inputs = set(config.get("calculated_parameters", [])) & set(params)
            if calculated_inputs:
                blocked = self._blocked_verification_result(
                    key,
                    device_type,
                    "Input validation failed: calculated outputs cannot be forward inputs: "
                    + ", ".join(sorted(calculated_inputs)),
                )
                blocked["error"] = "Invalid input parameters"
                blocked["validation_errors"] = [
                    f"{name} is a calculated output and cannot be a forward input"
                    for name in sorted(calculated_inputs)
                ]
                return blocked

        if key == "cmos_inverter" and not technology_node:
            return self._blocked_verification_result(
                key,
                device_type,
                "Technology Node must be selected before physics verification can be performed.",
            )

        input_errors = self._validate_input_parameters(params, config)
        if key == "cmos_inverter":
            required_inputs = {"CL", "L_n", "L_p", "VDD", "W_n", "W_p", "f_clk"}
            input_errors.extend(
                f"{name} is required for CMOS inverter analysis"
                for name in sorted(required_inputs - set(params))
            )
        if input_errors:
            if key == "cmos_inverter":
                blocked = self._blocked_verification_result(
                    key, device_type, "Input validation failed: " + "; ".join(input_errors)
                )
                blocked["error"] = "Invalid input parameters"
                blocked["validation_errors"] = input_errors
                return blocked
            return {
                "error": "Invalid input parameters",
                "validation_errors": input_errors,
                "params": params,
            }

        # ── Step 0: Technology compatibility check ──────────────────
        tech_compat = None
        node_info   = None
        if technology_node:
            tech_compat = self._tech_engine.check_circuit_technology_compatibility(
                circuit_type=key, node_name=technology_node
            )
            node_info = self._tech_db.get_node(technology_node)
            if not tech_compat["compatible"]:
                if key == "cmos_inverter":
                    return self._blocked_verification_result(
                        key, device_type, tech_compat["reason"]
                    )
                return {
                    "error": tech_compat["reason"],
                    "circuit_type": key,
                    "technology_node": technology_node,
                    "device_type": device_type,
                    "tech_compatible": tech_compat,
                }

        # ── Step 1: Fill defaults ──────────────────────────────────
        # Auto-fill from technology defaults first, then use circuit defaults
        tech_defaults = {}
        if technology_node:
            tech_defaults = self._tech_engine.get_tech_defaults(technology_node, device_type)

        aliases = {
            "W": ["Wn"], "Wn": ["W"],
            "L": ["Ln"], "Ln": ["L"],
            "VGS": ["VBIAS"], "VBIAS": ["VGS"],
        }
        filled_params = {}
        for pname, pinfo in config["input_parameters"].items():
            technology_owned = {
                "VTH", "VTH_n", "VTH_p", "mu_n", "mu_p", "Cox",
                "lambda_n", "lambda_p",
            }
            if technology_node and pname in technology_owned and pname in tech_defaults:
                filled_params[pname] = tech_defaults[pname]
            elif pname in params:
                filled_params[pname] = params[pname]
            else:
                # Check aliases
                found = False
                for alt in aliases.get(pname, []):
                    if alt in params:
                        filled_params[pname] = params[alt]
                        found = True
                        break
                if not found:
                    # Prefer technology defaults over circuit defaults
                    if pname in tech_defaults:
                        filled_params[pname] = tech_defaults[pname]
                    else:
                        filled_params[pname] = pinfo["default"]
        params = filled_params

        # ── Step 2: Physics computation ─────────────────────────────
        eq_class = get_circuit_equations(key)
        try:
            physics_results = eq_class.compute_all(params)
        except Exception as e:
            if key == "cmos_inverter":
                return self._blocked_verification_result(
                    key, device_type, f"Physics calculation failed: {str(e)}"
                )
            return {
                "error": f"Physics computation failed: {str(e)}",
                "params": params,
            }

        calculation_errors = []
        if key == "cmos_inverter":
            nonfinite = [
                name for name, value in physics_results.items()
                if isinstance(value, (int, float)) and not math.isfinite(float(value))
            ]
            if nonfinite:
                calculation_errors.append(
                    "Physics calculation returned non-finite values: " + ", ".join(nonfinite)
                )
                for name in nonfinite:
                    value = physics_results[name]
                    physics_results[name] = "Infinity" if value > 0 else "-Infinity"

        # ── Step 3: ML prediction (optional) ─────────────────────────
        ml_prediction    = None
        ml_vs_physics    = None
        ml_tech_checks   = []
        if include_ml and self.ml_selector and self.ml_selector.best_model:
            try:
                ml_raw       = self.ml_selector.predict(params)
                ml_prediction = ml_raw["prediction"]

                # Compare ML vs physics
                ml_vs_physics = {}
                for output_name in config["output_parameters"]:
                    phys_val = physics_results.get(output_name)
                    ml_val   = ml_prediction.get(output_name)
                    if phys_val is not None and ml_val is not None:
                        try:
                            phys_f = float(phys_val) if not isinstance(phys_val, str) else 0
                            ml_f   = float(ml_val)
                            error_pct = (
                                abs(ml_f - phys_f) / abs(phys_f) * 100
                                if abs(phys_f) > 1e-12
                                else abs(ml_f - phys_f) * 100
                            )
                            ml_vs_physics[output_name] = {
                                "physics":       phys_f,
                                "ml":            ml_f,
                                "error_percent": error_pct,
                                "match":         error_pct < 10,
                            }
                        except (TypeError, ValueError):
                            pass

                # Validate ML outputs against technology
                if technology_node and ml_prediction:
                    ml_tech_checks = self._tech_engine.validate(
                        params=ml_prediction,
                        node_name=technology_node,
                        device_type=device_type,
                        ml_predictions=ml_prediction,
                    )
            except Exception:
                ml_prediction = None

        # ── Step 4: Physics constraint verification ──────────────────
        physics_checks = PhysicalConstraintChecker.check_all(params, physics_results)
        circuit_checks = CircuitConstraintChecker.check(key, params, physics_results)
        for error in calculation_errors:
            physics_checks.append({
                "name": "Finite Physics Outputs",
                "condition": error,
                "satisfied": False,
                "severity": "CRITICAL",
                "rule": "All calculated physics outputs must be finite before verification can pass.",
            })

        # ── Step 5: Technology constraint verification ───────────────
        tech_checks = self._tech_engine.validate(
            params=params,
            node_name=technology_node,
            device_type=device_type,
        )

        # Combine all checks
        all_checks = physics_checks + circuit_checks + tech_checks

        n_pass     = sum(1 for c in all_checks if c["satisfied"])
        n_fail     = sum(1 for c in all_checks if not c["satisfied"])
        n_critical = sum(
            1 for c in all_checks
            if c.get("severity") == "CRITICAL" and not c["satisfied"]
        )

        # Count tech-specific critical failures
        n_tech_critical = sum(
            1 for c in tech_checks
            if c.get("severity") == "CRITICAL" and not c["satisfied"]
        )

        if key == "cmos_inverter":
            overall_status = "PASS" if n_fail == 0 else "FAIL"
        else:
            overall_status = "PASS" if n_critical == 0 else "FAIL"
            if n_fail > 0 and n_critical == 0:
                overall_status = "WARNING"

        # ── Step 6: Build technology info block ─────────────────────
        tech_info = self._build_tech_info(technology_node, node_info)

        # ── Step 7: Assemble final result ────────────────────────────
        result = {
            "circuit_type":   key,
            "circuit_name":   config["name"],
            "input_parameters": params,

            # Technology context (NEW)
            "technology_node": technology_node,
            "device_type":     device_type,
            "technology_info": tech_info,
            "tech_compatible": tech_compat,

            # Physics results
            "physics_results": {
                k: v for k, v in physics_results.items()
                if k not in ("equations_used", "latex_equations",
                             "conditions", "small_signal_equations")
            },

            # Equations used
            "equations_used":         physics_results.get("equations_used", []),
            "latex_equations":        physics_results.get("latex_equations", []),
            "small_signal_equations": physics_results.get("small_signal_equations", []),

            # Region conditions
            "region_conditions": physics_results.get("conditions", []),

            # ML comparison
            "ml_prediction":    ml_prediction,
            "ml_vs_physics":    ml_vs_physics,
            "ml_tech_checks":   ml_tech_checks,

            # Constraint verification
            "constraint_checks":    all_checks,
            "physics_checks":       physics_checks,
            "circuit_checks":       circuit_checks,
            "tech_checks":          tech_checks,

            "verification_summary": {
                "overall_status":         overall_status,
                "total_checks":           len(all_checks),
                "passed":                 n_pass,
                "failed":                 n_fail,
                "critical_failures":      n_critical,
                "tech_critical_failures": n_tech_critical,
                "technology_selected":    bool(technology_node),
                "technology_file_loaded": bool(node_info and node_info.has_model_file),
                "pmos_model_valid":       bool(node_info and node_info.pmos),
                "nmos_model_valid":       bool(node_info and node_info.nmos),
                "required_parameters_valid": bool(node_info and node_info.is_valid),
                "physics_checks_passed":  all(check["satisfied"] for check in physics_checks + circuit_checks),
            },
        }

        return result

    @staticmethod
    def _blocked_verification_result(
        circuit_type: str, device_type: str, reason: str
    ) -> dict:
        """Return a visible failed verification without running unsafe physics calculations."""
        check = {
            "name": "Technology Model Validation",
            "condition": reason,
            "satisfied": False,
            "severity": "CRITICAL",
            "rule": reason,
        }
        return {
            "circuit_type": circuit_type,
            "circuit_name": CIRCUIT_CONFIGS[circuit_type]["name"],
            "device_type": device_type,
            "technology_node": None,
            "physics_results": {},
            "equations_used": [],
            "latex_equations": [],
            "small_signal_equations": [],
            "region_conditions": [],
            "constraint_checks": [check],
            "physics_checks": [],
            "circuit_checks": [],
            "tech_checks": [check],
            "verification_summary": {
                "overall_status": "FAIL",
                "total_checks": 1,
                "passed": 0,
                "failed": 1,
                "critical_failures": 1,
                "technology_required": True,
                    "technology_selected": False,
                    "technology_file_loaded": False,
                    "pmos_model_valid": False,
                    "nmos_model_valid": False,
                    "required_parameters_valid": False,
                    "physics_checks_passed": False,
            },
        }

    @staticmethod
    def _validate_input_parameters(params: dict, config: dict) -> list:
        """Reject non-finite and impossible domains before equation evaluation."""
        errors = []
        declared = set(config["input_parameters"])
        calculated = set(config.get("calculated_parameters", []))
        for name in params:
            if name in calculated:
                errors.append(f"{name} is a calculated output and cannot be a forward input")
            elif name not in declared and name not in {"Wn", "Ln", "VBIAS"}:
                errors.append(f"{name} is not a declared input for this circuit")
        positive_parameters = {
            "W", "L", "W_n", "L_n", "W_p", "L_p", "W_ref", "L_ref",
            "W_out", "L_out", "RD", "RS", "RSS", "CL", "I_ref", "ISS", "VDD",
        }
        nonnegative_parameters = {"f_clk", "N_stages"}
        for name, value in params.items():
            if not isinstance(value, (int, float)) or not math.isfinite(float(value)):
                errors.append(f"{name} must be a finite numeric value")
                continue
            numeric_value = float(value)
            if name in positive_parameters and numeric_value <= 0:
                errors.append(f"{name} must be greater than zero")
            elif name in nonnegative_parameters and numeric_value < 0:
                errors.append(f"{name} must not be negative")
        if "N_stages" in params and float(params["N_stages"]).is_integer() is False:
            errors.append("N_stages must be an integer")
        return errors

    def quick_compute(self, circuit_type: str, params: dict) -> dict:
        """Compute physics-only results without ML or full verification."""
        key      = circuit_type.lower().replace(" ", "_").replace("-", "_")
        eq_class = get_circuit_equations(key)
        config   = CIRCUIT_CONFIGS[key]

        filled = {}
        for pname, pinfo in config["input_parameters"].items():
            filled[pname] = params.get(pname, pinfo["default"])

        return eq_class.compute_all(filled)

    def _build_tech_info(
        self,
        technology_node: Optional[str],
        node_info: Any,
    ) -> Optional[dict]:
        """Build a compact technology information block for the result."""
        if not technology_node:
            return None
        if node_info is None:
            return {"node": technology_node, "status": "unknown"}

        info: dict = {
            "node_name":       node_info.node_name,
            "has_model_file":  node_info.has_model_file,
            "valid":           node_info.is_valid,
            "nominal_vdd":     node_info.nominal_vdd,
            "parse_errors":    node_info.parse_errors,
        }
        if node_info.nmos:
            info["nmos"] = {
                "vth0":       node_info.nmos.vth0,
                "Cox_fF_um2": node_info.nmos.Cox_fF_um2,
                "mu_cm2Vs":   node_info.nmos.mu_cm2Vs,
            }
        if node_info.pmos:
            info["pmos"] = {
                "vth0":       node_info.pmos.vth0,
                "Cox_fF_um2": node_info.pmos.Cox_fF_um2,
                "mu_cm2Vs":   node_info.pmos.mu_cm2Vs,
            }
        return info
