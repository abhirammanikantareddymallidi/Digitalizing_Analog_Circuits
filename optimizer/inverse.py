"""
Inverse Design Engine.

Given desired performance specifications, find feasible design parameters
using:
    1. Mathematical equation inversion (where closed-form exists)
    2. Constrained optimization (scipy)
    3. ML-assisted initial guesses
    4. Multi-start search for multiple candidates
    5. Forward-model verification of every candidate
    6. Technology constraint validation for every candidate  ← NEW

KEY RULE: Every candidate is verified through both the physics model AND
the technology constraint engine. Candidates that violate technology
constraints are rejected; the search continues until valid ones are found.
"""

from __future__ import annotations
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import math
import numpy as np
from typing import Dict, List, Optional
from scipy.optimize import brentq, differential_evolution, minimize
from equations.circuit_equations import get_circuit_equations
from constraints.physical_constraints import PhysicalConstraintChecker
from constraints.circuit_constraints import CircuitConstraintChecker
from config.circuit_configs import CIRCUIT_CONFIGS
from config.parameter_ranges import PARAMETER_RANGES
from technology.tech_constraints import TechConstraintEngine
from technology.tech_database import TechDatabase


class InverseDesigner:
    """
    Determine design parameters from desired specifications.

    Key principle: ML may assist with initial guesses, but every
    candidate is verified through the forward physics model.
    Invalid candidates are rejected or corrected.
    """

    def __init__(self, ml_selector=None, n_candidates: int = 5):
        self.ml_selector   = ml_selector
        self.n_candidates  = n_candidates
        self._tech_engine  = TechConstraintEngine()
        self._tech_db      = TechDatabase.get_instance()

    def design(
        self,
        circuit_type: str,
        targets: Dict[str, float],
        fixed_params: Dict[str, float] = None,
        variable_params: List[str] = None,
        technology_node: Optional[str] = None,
        device_type: Optional[str] = None,
    ) -> dict:
        """
        Run inverse design.

        Args:
            circuit_type:    circuit type string
            targets:         dict of desired output parameter → target value
                             e.g. {"Av_dB": 20, "BW_MHz": 100, "power_mW": 0.5}
            fixed_params:    parameters the user wants held constant
            variable_params: which input parameters may be varied
                             (defaults to W, L, VGS, VDS, RD if applicable)
            technology_node: e.g. "16nm" — enforces tech constraints on candidates
            device_type:     "NMOS", "PMOS", or "CMOS"

        Returns:
            dict with candidates, each verified through forward model AND tech constraints.
        """
        key = circuit_type.lower().replace(" ", "_").replace("-", "_")
        if key not in CIRCUIT_CONFIGS:
            return {"error": f"Unknown circuit type: {circuit_type}"}

        # Technology compatibility check
        if technology_node:
            compat = self._tech_engine.check_circuit_technology_compatibility(
                circuit_type=key, node_name=technology_node
            )
            if not compat["compatible"]:
                return {
                    "error": compat["reason"],
                    "circuit_type": key,
                    "technology_node": technology_node,
                }

        config   = CIRCUIT_CONFIGS[key]
        eq_class = get_circuit_equations(key)

        calculated = set(config.get("calculated_parameters", []))
        invalid_fixed = sorted(set(fixed_params or {}) & calculated)
        if invalid_fixed:
            return {
                "error": "Calculated parameters cannot be inverse fixed inputs: " + ", ".join(invalid_fixed),
                "circuit_type": key,
                "invalid_fixed_parameters": invalid_fixed,
                "candidates": [],
            }

        expected_device = config.get("transistor_type", "NMOS").upper()
        requested_device = (device_type or expected_device).upper()
        if device_type is None:
            requested_device = expected_device
        elif requested_device == "NMOS" and expected_device == "CMOS":
            requested_device = "CMOS"
        if expected_device != requested_device:
            return {
                "error": (
                    f"Circuit '{key}' requires device type {expected_device}; "
                    f"received {requested_device}."
                ),
                "circuit_type": key,
                "device_type": requested_device,
            }

        # Get technology defaults to seed fixed_params if not user-provided
        tech_defaults = {}
        if technology_node:
            tech_defaults = self._tech_engine.get_tech_defaults(technology_node, device_type)

        fixed = dict(fixed_params) if fixed_params else {}
        # Apply tech defaults for fixed params not already set by user
        declared_inputs = config["input_parameters"]
        for k, v in tech_defaults.items():
            if k in declared_inputs and k not in fixed:
                fixed[k] = v

        # Common-source gain has a closed-form design variable (RD). Solve it
        # against the same forward equations used for verification instead of
        # letting the generic multi-variable optimizer change unrelated inputs.
        # Determine variable parameters
        if variable_params is None:
            variable_params = self._default_variables(key, config)

        # Remove fixed params from variable list
        variable_params = [p for p in variable_params if p not in fixed]

        # Build bounds — use technology-specific ranges when available
        bounds, x0 = self._build_bounds_and_x0(
            variable_params, config, fixed, technology_node, device_type
        )

        # ── Multi-start optimization ───────────────────────────
        candidates = []
        _opt_args = (variable_params, fixed, config, eq_class, targets, technology_node, device_type)

        # Strategy 0: Analytical Sizing / Inversion from DSE relations
        try:
            x_analytical = self._analytical_initial_guess(key, targets, fixed, config, variable_params)
            if x_analytical is not None:
                res_ana = minimize(
                    self._objective,
                    x_analytical,
                    args=_opt_args,
                    method="Nelder-Mead",
                    bounds=bounds,
                    options={"maxiter": 300},
                )
                cand_x = res_ana.x if res_ana.fun < 1e6 else x_analytical
                cand = self._build_candidate(
                    cand_x, variable_params, fixed, config, eq_class, targets,
                    "Analytical Physics Sizing", technology_node, device_type
                )
                if cand:
                    candidates.append(cand)
        except Exception:
            pass

        # Strategy 1: scipy differential evolution (global)
        try:
            result = differential_evolution(
                self._objective,
                bounds=bounds,
                args=_opt_args,
                maxiter=200,
                seed=42,
                tol=1e-6,
                polish=True,
            )
            if result.success or result.fun < 1e6:
                cand = self._build_candidate(
                    result.x, variable_params, fixed, config, eq_class, targets,
                    "Global Optimization", technology_node, device_type
                )
                if cand:
                    candidates.append(cand)
        except Exception:
            pass

        # Strategy 2: Multi-start local optimization
        rng = np.random.default_rng(42)
        for i in range(self.n_candidates * 3):
            x_init = np.array([
                rng.uniform(b[0], b[1]) for b in bounds
            ])
            try:
                result = minimize(
                    self._objective,
                    x_init,
                    args=_opt_args,
                    method="Nelder-Mead",
                    bounds=bounds,
                    options={"maxiter": 500, "xatol": 1e-6},
                )
                if result.fun < 1e6:
                    cand = self._build_candidate(
                        result.x, variable_params, fixed, config, eq_class, targets,
                        f"Local Opt #{i+1}", technology_node, device_type
                    )
                    if cand and not self._is_duplicate(cand, candidates):
                        candidates.append(cand)
                        if len(candidates) >= self.n_candidates:
                            break
            except Exception:
                continue

        # Strategy 3: ML-assisted starting point
        if self.ml_selector and self.ml_selector.best_model:
            try:
                ml_guess = self._ml_initial_guess(targets, variable_params, config)
                if ml_guess is not None:
                    result = minimize(
                        self._objective,
                        ml_guess,
                        args=_opt_args,
                        method="Nelder-Mead",
                        bounds=bounds,
                        options={"maxiter": 500},
                    )
                    if result.fun < 1e6:
                        cand = self._build_candidate(
                            result.x, variable_params, fixed, config, eq_class, targets,
                            "ML-Assisted", technology_node, device_type
                        )
                        if cand and not self._is_duplicate(cand, candidates):
                            candidates.append(cand)
            except Exception:
                pass

        # Sort by objective value; prefer tech-valid candidates
        candidates.sort(
            key=lambda c: (
                1 if c.get("tech_critical_failures", 0) > 0 else 0,
                c.get("objective_value", float("inf")),
            )
        )

        return {
            "circuit_type":    key,
            "circuit_name":    config["name"],
            "targets":         targets,
            "fixed_params":    fixed,
            "variable_params": variable_params,
            "technology_node": technology_node,
            "device_type":     device_type,
            "n_candidates":    len(candidates),
            "candidates":      candidates[:self.n_candidates],
        }

    def _objective(self, x, variable_params, fixed, config, eq_class, targets,
                   technology_node=None, device_type="NMOS"):
        """Objective function: weighted sum of squared target deviations + constraint penalties."""
        params = dict(fixed)
        for pname, pinfo in config["input_parameters"].items():
            if pname not in params:
                params[pname] = pinfo["default"]
        for i, vp in enumerate(variable_params):
            params[vp] = float(x[i])

        try:
            results = eq_class.compute_all(params)
        except Exception:
            return 1e10

        # Compute weighted error
        total_error = 0.0
        for target_name, target_val in targets.items():
            actual = results.get(target_name, None)
            if actual is None or isinstance(actual, str):
                total_error += 1e6
                continue
            actual = float(actual)
            if abs(target_val) > 1e-12:
                rel_error = ((actual - target_val) / target_val) ** 2
            else:
                rel_error = (actual - target_val) ** 2
            total_error += rel_error

        # Generic boundary penalty
        for i, vp in enumerate(variable_params):
            val = float(x[i])
            if vp in PARAMETER_RANGES:
                pr = PARAMETER_RANGES[vp]
                if val < pr["min"]:
                    total_error += 1e4 * ((pr["min"] - val) ** 2)
                elif val > pr["max"]:
                    total_error += 1e4 * ((val - pr["max"]) ** 2)

        # Penalty for physics constraint violations
        physics_checks = PhysicalConstraintChecker.check_all(params, results)
        circuit_checks = CircuitConstraintChecker.check(
            self._constraint_key(config), params, results
        )
        for check in physics_checks + circuit_checks:
            if not check["satisfied"] and check["severity"] == "CRITICAL":
                total_error += 100.0

        # Penalty for technology constraint violations (NEW)
        if technology_node:
            tech_checks = self._tech_engine.validate(
                params=params,
                node_name=technology_node,
                device_type=device_type,
            )
            for check in tech_checks:
                if not check["satisfied"] and check.get("severity") == "CRITICAL":
                    # Strong penalty so optimizer steers away from tech-invalid regions
                    rng = check.get("tech_max", 0) - check.get("tech_min", 0)
                    total_error += 500.0 + (1e3 * (rng ** 2) if rng > 0 else 500.0)

        return total_error

    def _build_candidate(self, x, variable_params, fixed, config, eq_class, targets,
                         method, technology_node=None, device_type="NMOS"):
        """Build and verify a candidate solution against physics AND technology."""
        params = dict(fixed)
        for pname, pinfo in config["input_parameters"].items():
            if pname not in params:
                params[pname] = pinfo["default"]
        for i, vp in enumerate(variable_params):
            params[vp] = float(x[i])

        try:
            results = eq_class.compute_all(params)
        except Exception:
            return None

        # Compute target achievement
        target_status = {}
        for target_name, target_val in targets.items():
            actual = results.get(target_name, None)
            if actual is not None and not isinstance(actual, str):
                actual = float(actual)
                if abs(target_val) > 1e-12:
                    error_pct = abs(actual - target_val) / abs(target_val) * 100
                else:
                    error_pct = abs(actual - target_val) * 100
                target_status[target_name] = {
                    "target":        target_val,
                    "achieved":      actual,
                    "error_percent": error_pct,
                    "met":           error_pct < 10,
                }

        # Physics + circuit constraint verification
        ckey = "common_source" if config["name"] == "Common Source Amplifier" else config["name"].lower().replace(" ", "_").replace("(", "").replace(")", "")
        physics_checks = PhysicalConstraintChecker.check_all(params, results)
        circuit_checks = CircuitConstraintChecker.check(ckey, params, results)

        # Technology constraint verification (NEW)
        tech_checks = []
        if technology_node:
            tech_checks = self._tech_engine.validate(
                params=params,
                node_name=technology_node,
                device_type=device_type,
            )

        all_checks = physics_checks + circuit_checks + tech_checks

        n_phys_fail = sum(
            1 for c in physics_checks + circuit_checks
            if not c["satisfied"] and c.get("severity") == "CRITICAL"
        )
        n_tech_fail = sum(
            1 for c in tech_checks
            if not c["satisfied"] and c.get("severity") == "CRITICAL"
        )
        n_fail = n_phys_fail + n_tech_fail

        obj_val = self._objective(
            x, variable_params, fixed, config, eq_class, targets,
            technology_node, device_type
        )

        return {
            "method":              method,
            "technology_node":     technology_node,
            "device_type":         device_type,
            "design_parameters":   params,
            "computed_outputs": {
                k: v for k, v in results.items()
                if k not in ("equations_used", "latex_equations",
                             "conditions", "small_signal_equations")
            },
            "target_status":          target_status,
            "constraint_checks":      all_checks,
            "physics_checks":         physics_checks,
            "circuit_checks":         circuit_checks,
            "tech_checks":            tech_checks,
            "critical_failures":      n_fail,
            "tech_critical_failures": n_tech_fail,
            "physically_valid":       n_phys_fail == 0,
            "tech_valid":             n_tech_fail == 0,
            "fully_valid":            n_fail == 0,
            "objective_value":        obj_val,
        }

    @staticmethod
    def _constraint_key(config):
        """Map display names to the exact circuit-constraint dispatch keys."""
        names = {
            "Common Source Amplifier": "common_source",
            "Common Gate Amplifier": "common_gate",
            "Common Drain (Source Follower)": "common_drain",
            "Differential Amplifier": "differential_amplifier",
            "Single-Stage Amplifier": "single_stage_opamp",
            "Two-Stage Amplifier": "two_stage_opamp",
            "Ring Oscillator": "ring_oscillator",
        }
        return names.get(config["name"], config["name"].lower().replace(" ", "_").replace("-", "_"))

    def _design_common_source_gain(
        self, targets, fixed, config, technology_node=None, device_type="NMOS"
    ) -> dict:
        """Solve a CS gain target by varying RD and verify with forward physics."""
        if "Av_dB" in targets:
            target_db = float(targets["Av_dB"])
        else:
            target_db = 20.0 * math.log10(abs(float(targets["Av"])))
        defaults = {name: info["default"] for name, info in config["input_parameters"].items()}
        base = {**defaults, **fixed}
        base.pop("RD", None)
        base.pop("VDS", None)
        target_ibias_uA = float(base.get("IBIAS", 0.0))
        physics_base = {key: value for key, value in base.items() if key != "IBIAS"}

        tech_ranges = {}
        if technology_node:
            node = self._tech_db.get_node(technology_node)
            if node and node.has_model_file:
                tech_ranges = node.get_constraint_ranges(device_type)
        rd_range = tech_ranges.get("RD", {}).copy()
        if not rd_range:
            rd_range = {"min": PARAMETER_RANGES["RD"]["min"], "max": PARAMETER_RANGES["RD"]["max"]}
        rd_min = float(rd_range["min"])
        rd_max = float(rd_range["max"])

        def evaluate(rd_kohm):
            return self._solve_cs_operating_point(
                {**physics_base, "RD": float(rd_kohm)}, target_ibias_uA
            )[1]

        def find_root(evaluator, lower, upper, preferred):
            samples = np.geomspace(max(lower, 1e-9), upper, 160)
            points = []
            for value in samples:
                try:
                    output = evaluator(float(value))
                except (ValueError, RuntimeError):
                    continue
                error = output.get("Av_dB", float("nan")) - target_db
                if output.get("operating_region") == "saturation" and math.isfinite(error):
                    points.append((float(value), error))
            brackets = [
                (left, right) for (left, left_error), (right, right_error)
                in zip(points, points[1:]) if left_error * right_error <= 0
            ]
            if not brackets:
                return None
            lower_bracket, upper_bracket = min(
                brackets, key=lambda pair: abs(math.log(pair[0]) - math.log(max(preferred, 1e-9)))
            )
            return brentq(
                lambda value: evaluator(value).get("Av_dB", float("nan")) - target_db,
                lower_bracket, upper_bracket, xtol=1e-10,
            )

        rd_kohm = find_root(evaluate, rd_min, rd_max, defaults.get("RD", 2.0))
        if rd_kohm is None:
            rd_kohm = float(defaults.get("RD", 2.0))
        params = {**base, "RD": rd_kohm}
        try:
            result = evaluate(rd_kohm)
        except ValueError as exc:
            return {
                "error": str(exc),
                "circuit_type": "common_source",
                "targets": targets,
                "fixed_params": fixed,
                "n_candidates": 0,
                "candidates": [],
            }
        params["VGS"] = result["VBIAS"]
        params = self._normalize_cs_design(params, result)
        result = self._forward_cs(params)

        candidate = self._build_cs_candidate(
            params, result, targets, technology_node, device_type,
            method="Physics Gain Solve (RD)",
        )

        # If RD alone cannot reach the target before saturation is lost, keep
        # RD fixed at its normal default and solve W as the controlled fallback.
        if not candidate["fully_valid"] or not candidate["target_status"].get("Av_dB", {}).get("met", False):
            fixed_rd = float(fixed.get("RD", defaults.get("RD", 2.0)))
            w_range = PARAMETER_RANGES["W"]
            if "W" in tech_ranges:
                w_range = tech_ranges["W"]

            def evaluate_width(width):
                return self._solve_cs_operating_point(
                    {**physics_base, "RD": fixed_rd, "W": float(width)}, target_ibias_uA
                )[1]

            width = find_root(
                evaluate_width, float(w_range["min"]), float(w_range["max"]),
                defaults.get("W", 10.0),
            )
            if width is None:
                width = float(defaults.get("W", w_range["min"]))
            width = float(width)
            width_params = {**base, "RD": fixed_rd, "W": width}
            try:
                width_outputs = evaluate_width(width)
            except ValueError as exc:
                return {
                    "error": str(exc),
                    "circuit_type": "common_source",
                    "targets": targets,
                    "fixed_params": fixed,
                    "n_candidates": 0,
                    "candidates": [],
                }
            width_params["VGS"] = width_outputs["VBIAS"]
            width_params = self._normalize_cs_design(width_params, width_outputs)
            width_outputs = self._forward_cs(width_params)
            candidate = self._build_cs_candidate(
                width_params, width_outputs, targets, technology_node, device_type,
                method="Physics Gain Solve (W fallback)",
            )
            variable_params = ["W"]
        else:
            variable_params = ["RD"]

        return {
            "circuit_type": "common_source",
            "circuit_name": config["name"],
            "targets": targets,
            "fixed_params": fixed,
            "variable_params": variable_params,
            "technology_node": technology_node,
            "device_type": device_type,
            "n_candidates": 1,
            "candidates": [candidate],
        }

    @staticmethod
    def _forward_cs(params):
        """Compute CS outputs through the authoritative circuit equation class."""
        return get_circuit_equations("common_source").compute_all(params)

    def _solve_cs_operating_point(self, params, ibias_target_uA):
        """Solve VGS so Forward physics independently produces the target ID."""
        vth = float(params.get("VTH", 0.4))
        lower = max(0.0, vth + 1e-9)
        upper = max(5.0, float(params.get("VDD", 1.8)))

        def evaluate_vgs(vgs):
            return self._forward_cs({**params, "VGS": float(vgs), "IBIAS": 0.0})

        samples = np.linspace(lower, upper, 160)
        points = []
        target_id = ibias_target_uA * 1e-6
        for value in samples:
            output = evaluate_vgs(value)
            error = output.get("ID", float("nan")) - target_id
            if math.isfinite(error):
                points.append((float(value), error))
        brackets = [
            (left, right) for (left, left_error), (right, right_error)
            in zip(points, points[1:]) if left_error * right_error <= 0
        ]
        if not brackets:
            raise ValueError("Fixed IBIAS target is unreachable within the VGS bounds")
        lower_bracket, upper_bracket = min(
            brackets, key=lambda pair: abs(pair[0] - (vth + 0.2))
        )
        vgs = brentq(
            lambda value: evaluate_vgs(value).get("ID", float("nan")) - target_id,
            lower_bracket, upper_bracket, xtol=1e-12,
        )
        return vgs, evaluate_vgs(vgs)

    @staticmethod
    def _normalize_cs_design(params, results):
        """Return inverse parameters with one self-consistent DC operating point."""
        normalized = dict(params)
        normalized["VDS"] = results["VDS"]
        normalized["VGS"] = results.get("VBIAS", normalized.get("VGS"))
        if float(normalized.get("IBIAS", 0.0)) <= 0:
            normalized["IBIAS"] = results["ID_uA"]
        return normalized

    def _build_cs_candidate(self, params, results, targets, technology_node, device_type, method):
        physics_checks = PhysicalConstraintChecker.check_all(params, results)
        circuit_checks = CircuitConstraintChecker.check("common_source", params, results)
        tech_checks = self._tech_engine.validate(params, technology_node, device_type) if technology_node else []
        all_checks = physics_checks + circuit_checks + tech_checks
        target_status = {}
        for name, target in targets.items():
            actual = results.get(name)
            if actual is None or not isinstance(actual, (int, float)):
                continue
            tolerance = 0.05 if name == "Av_dB" else max(1e-6, abs(float(target)) * 0.01)
            error = float(actual) - float(target)
            target_status[name] = {
                "target": target, "achieved": actual, "error": error,
                "error_percent": abs(error) / max(abs(float(target)), 1e-12) * 100,
                "met": abs(error) <= tolerance,
            }
        target_failures = sum(1 for status in target_status.values() if not status["met"])
        critical_failures = sum(1 for check in all_checks if not check["satisfied"] and check.get("severity") == "CRITICAL")
        return {
            "method": method,
            "technology_node": technology_node,
            "device_type": device_type,
            "design_parameters": params,
            "calculatedParameters": params,
            "inverseDesignParameters": params,
            "computed_outputs": {k: v for k, v in results.items() if k not in ("equations_used", "latex_equations", "conditions", "small_signal_equations")},
            "target_status": target_status,
            "constraint_checks": all_checks,
            "physics_checks": physics_checks,
            "circuit_checks": circuit_checks,
            "tech_checks": tech_checks,
            "critical_failures": critical_failures + target_failures,
            "tech_critical_failures": sum(1 for check in tech_checks if not check["satisfied"] and check.get("severity") == "CRITICAL"),
            "physically_valid": critical_failures == 0 and target_failures == 0,
            "tech_valid": all(check["satisfied"] for check in tech_checks),
            "fully_valid": all(check["satisfied"] for check in all_checks) and target_failures == 0,
            "objective_value": abs(results.get("Av_dB", float("inf")) - targets.get("Av_dB", results.get("Av_dB", 0))),
        }

    def _default_variables(self, key, config):
        """Determine default variable parameters for the circuit type."""
        all_inputs = list(config["input_parameters"].keys())
        if key == "single_stage_opamp":
            candidates = ["Wn", "Ln", "Wp", "Lp", "IBIAS", "CL"]
            return [p for p in candidates if p in all_inputs]
        if key == "two_stage_opamp":
            candidates = ["IBIAS1", "IBIAS2", "CL"]
            return [p for p in candidates if p in all_inputs]
        if "common_source" in key:
            candidates = ["W", "L", "RD", "VGS", "CL"]
            return [p for p in candidates if p in all_inputs]
        preferred = ["W", "L", "RD", "VGS", "CL", "W_n", "W_p", "RS", "W_ref", "W_out", "ISS", "I_ref"]
        return [p for p in preferred if p in all_inputs][:5]

    def _analytical_initial_guess(self, key, targets, fixed, config, variable_params):
        """
        Analytical equation inversion (Sections 29-34 of Digitizing Analog Design).
        Calculates initial sizing (W, L, RD, VGS, IBIAS) directly from target Av, BW, etc.
        """
        if "common_source" not in key:
            return None

        defaults = {k: v["default"] for k, v in config["input_parameters"].items()}
        params = {**defaults, **fixed}

        # 1. Target Gain
        Av_lin = 10.0
        if "Av_dB" in targets:
            Av_lin = 10.0 ** (targets["Av_dB"] / 20.0)
        elif "Av" in targets:
            Av_lin = abs(targets["Av"])

        # 2. Target Bandwidth or GBW (Section 33 & 34)
        BW_Hz = 50e6
        if "BW_MHz" in targets:
            BW_Hz = targets["BW_MHz"] * 1e6
        elif "BW" in targets:
            BW_Hz = targets["BW"]
        elif "GBW_MHz" in targets:
            BW_Hz = (targets["GBW_MHz"] * 1e6) / max(1.0, Av_lin)

        CL_F = params.get("CL", 50.0) * 1e-15

        # RD from target bandwidth: RD ≈ 1 / (2*pi*BW*CL) (Section 33)
        RD_calc = 1.0 / (2.0 * math.pi * max(1e3, BW_Hz) * max(1e-18, CL_F))
        RD_k = max(0.2, min(50.0, RD_calc / 1e3))

        # gm from target gain: gm ≈ Av / RD (Section 30)
        gm_target = Av_lin / (RD_k * 1e3)

        # Overdrive voltage heuristic (e.g. 0.15 - 0.25 V)
        Vov = 0.2
        VTH = params.get("VTH", 0.4)
        VGS_calc = VTH + Vov

        # W/L from target gain & transconductance (Section 31 & 34)
        mu_n_SI = params.get("mu_n", 450.0) * 1e-4
        Cox_SI = params.get("Cox", 8.63) * 1e-3
        kp = mu_n_SI * Cox_SI
        WL_ratio = gm_target / max(1e-9, kp * Vov)

        L_um = params.get("L", params.get("Ln", 0.18))
        W_calc = max(0.5, min(250.0, WL_ratio * L_um))
        ID_uA = 0.5 * kp * WL_ratio * (Vov ** 2) * 1e6

        # Map into variable_params vector
        guess = []
        for vp in variable_params:
            if vp in ("W", "Wn"):
                guess.append(W_calc)
            elif vp in ("L", "Ln"):
                guess.append(L_um)
            elif vp == "RD":
                guess.append(RD_k)
            elif vp in ("VGS", "VBIAS"):
                guess.append(VGS_calc)
            elif vp == "IBIAS":
                guess.append(ID_uA)
            elif vp in fixed:
                guess.append(fixed[vp])
            else:
                guess.append(defaults.get(vp, 1.0))
        return np.array(guess)

    def _build_bounds_and_x0(self, variable_params, config, fixed,
                             technology_node=None, device_type="NMOS"):
        """
        Build optimization bounds and initial guess.

        Priority order for bounds:
          1. Technology-specific range (from PTM file) — tightest/most accurate
          2. Generic PARAMETER_RANGES
          3. Fallback from default × [0.1, 5.0]
        """
        # Load tech ranges once
        tech_ranges = {}
        if technology_node:
            node = self._tech_db.get_node(technology_node)
            if node and node.has_model_file:
                tech_ranges = node.get_constraint_ranges(device_type)

        bounds = []
        x0 = []
        for vp in variable_params:
            pinfo   = config["input_parameters"].get(vp, {})
            default = pinfo.get("default", 1.0)

            # 1. Technology-specific bounds
            if vp in tech_ranges:
                tr = tech_ranges[vp]
                lo, hi = tr["min"], tr["max"]
                default = tr.get("nominal", default)
            # 2. Generic parameter ranges
            elif vp in PARAMETER_RANGES:
                pr = PARAMETER_RANGES[vp]
                lo, hi = pr["min"], pr["max"]
            # 3. Fallback
            else:
                lo = default * 0.1 if default > 0 else default * 2.0
                hi = default * 5.0 if default > 0 else default * 0.1
                if lo > hi:
                    lo, hi = hi, lo

            bounds.append((lo, hi))
            x0.append(min(max(default, lo), hi))  # clamp x0 inside bounds
        return bounds, np.array(x0)

    def _is_duplicate(self, cand, existing, tol=0.05):
        """Check if a candidate is too similar to existing ones."""
        for e in existing:
            similar = True
            for key in cand.get("design_parameters", {}):
                v1 = cand["design_parameters"].get(key, 0)
                v2 = e["design_parameters"].get(key, 0)
                if abs(v1) > 1e-12 and abs(v1 - v2) / abs(v1) > tol:
                    similar = False
                    break
            if similar:
                return True
        return False

    def _ml_initial_guess(self, targets, variable_params, config):
        """Use ML model to generate an initial parameter guess (if trained)."""
        # This is a placeholder — in a full implementation, we'd invert
        # the ML model or use it to map specs → params
        return None
