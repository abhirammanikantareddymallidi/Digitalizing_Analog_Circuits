"""
Technology Constraint Engine.

Given a technology node name + device type, validates circuit/device parameters
against the actual values loaded from the PTM model files.

Key rules:
  - Only enforces constraints for which data is present in the PTM file.
  - Does NOT invent missing values.
  - Returns structured check results (same schema as physical_constraints.py).
  - ML predictions that violate technology constraints are REJECTED, not silently clamped.
"""

from __future__ import annotations
import math
from typing import List, Dict, Any, Optional

from technology.tech_database import TechDatabase, TechnologyNodeInfo


class TechConstraintEngine:
    """
    Validate device/circuit parameters against technology-node constraints.

    Usage:
        engine = TechConstraintEngine()
        checks = engine.validate(
            params={"VDD": 1.8, "VTH": 0.68, "Cox": 8.5, "mu_n": 280.0},
            node_name="16nm",
            device_type="NMOS"
        )
        # Each check: {name, condition, satisfied, severity, rule, tech_source}
    """

    def __init__(self):
        self._db = TechDatabase.get_instance()

    # ── Main entry point ──────────────────────────────────────────
    def validate(
        self,
        params: Dict[str, Any],
        node_name: Optional[str],
        device_type: str = "NMOS",
        ml_predictions: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Validate params (and optionally ml_predictions) against the selected technology.

        Args:
            params:         dict of circuit/device parameters in lab units
            node_name:      technology node string, e.g. "16nm"
            device_type:    "NMOS", "PMOS", or "CMOS"
            ml_predictions: optional dict of ML-predicted outputs to check

        Returns:
            List of constraint-check dicts, each with:
              {name, condition, satisfied, severity, rule, tech_source,
               original_ml_value (if applicable), tech_limit}
        """
        checks: List[Dict[str, Any]] = []

        if not node_name:
            checks.append(self._no_tech_selected_check())
            return checks

        node = self._db.get_node(node_name)
        if node is None:
            checks.append(self._unknown_node_check(node_name))
            return checks

        if not node.is_valid:
            checks.append(self._no_model_file_check(node))
            return checks

        # Determine effective device types to validate against
        dev_types = (
            ["NMOS", "PMOS"] if device_type.upper() == "CMOS"
            else [device_type.upper()]
        )

        for dt in dev_types:
            ranges = node.get_constraint_ranges(dt)
            if not ranges:
                continue

            # Validate each parameter that exists in both params and ranges
            for param_name, rng in ranges.items():
                # Prefer user-provided params; skip if not supplied
                if param_name not in params:
                    continue

                val = params[param_name]
                check = self._check_param_in_range(
                    param_name=param_name,
                    value=val,
                    rng=rng,
                    device_type=dt,
                    node_name=node_name,
                )
                checks.append(check)

        # Validate ML-predicted values separately (show original ML values)
        if ml_predictions:
            ml_checks = self._validate_ml_predictions(
                ml_predictions, node, dev_types, node_name
            )
            checks.extend(ml_checks)

        # Technology compatibility summary
        checks.append(self._node_summary_check(node, device_type))

        return checks

    def get_tech_defaults(
        self, node_name: str, device_type: str = "NMOS"
    ) -> Dict[str, Any]:
        """
        Return recommended default parameter values for the selected technology node.

        Only values that exist in the PTM file are returned.
        Never invents values.
        """
        node = self._db.get_node(node_name)
        if node is None or not node.is_valid:
            return {}

        dt = device_type.upper()
        if dt == "CMOS":
            nmos_defaults = self.get_tech_defaults(node_name, "NMOS")
            pmos_defaults = self.get_tech_defaults(node_name, "PMOS")
            defaults = {
                "VDD": nmos_defaults.get("VDD", pmos_defaults.get("VDD")),
                "VTH_n": nmos_defaults.get("VTH"),
                "VTH_p": pmos_defaults.get("VTH"),
                "mu_n": nmos_defaults.get("mu_n"),
                "mu_p": pmos_defaults.get("mu_p"),
                "Cox": nmos_defaults.get("Cox", pmos_defaults.get("Cox")),
                "L_n": nmos_defaults.get("L"),
                "L_p": pmos_defaults.get("L"),
                "lambda_n": nmos_defaults.get("lambda_n"),
                "lambda_p": pmos_defaults.get("lambda_p"),
            }
            return {key: value for key, value in defaults.items() if value is not None}

        dev = node.nmos if dt == "NMOS" else node.pmos
        if dev is None:
            return {}

        defaults = {}

        if node.nominal_vdd is not None:
            defaults["VDD"] = node.nominal_vdd

        if dev.vth0 is not None:
            vth_key = "VTH" if dt == "NMOS" else "VTH"
            defaults[vth_key] = round(dev.vth0, 5)

        if dev.Cox_fF_um2 is not None:
            defaults["Cox"] = round(dev.Cox_fF_um2, 4)

        if dev.mu_cm2Vs is not None:
            mu_key = "mu_n" if dt == "NMOS" else "mu_p"
            defaults[mu_key] = round(dev.mu_cm2Vs, 2)

        if dev.pclm is not None:
            lambda_key = "lambda_n" if dt == "NMOS" else "lambda_p"
            defaults[lambda_key] = dev.pclm

        if node.node_nm is not None:
            defaults["L"] = round(node.node_nm / 1000.0, 5)  # nm → µm

        return defaults

    def check_circuit_technology_compatibility(
        self, circuit_type: str, node_name: str
    ) -> Dict[str, Any]:
        """
        Check whether the circuit type is compatible with the technology node.

        Returns a dict: {compatible: bool, reason: str}
        """
        node = self._db.get_node(node_name)
        if node is None:
            return {
                "compatible": False,
                "reason": f"Unknown technology node: {node_name!r}",
            }

        # All standard circuits are supported for nodes with model files
        if not node.has_model_file:
            return {
                "compatible": False,
                "reason": (
                    f"Technology node '{node_name}' has no parameter file. "
                    "Analysis cannot proceed without technology-specific data."
                ),
            }

        return {
            "compatible": True,
                "reason": f"Circuit '{circuit_type}' is compatible with {node_name}.",
        }

    # ── Private helpers ───────────────────────────────────────────
    def _check_param_in_range(
        self,
        param_name: str,
        value: float,
        rng: Dict[str, Any],
        device_type: str,
        node_name: str,
    ) -> Dict[str, Any]:
        """Build a single constraint-check result for a parameter vs. range."""
        lo, hi = rng["min"], rng["max"]
        nom     = rng.get("nominal", None)
        unit    = rng.get("unit", "")
        source  = rng.get("source", "PTM model file")

        try:
            val_f = float(value)
        except (TypeError, ValueError):
            return {
                "name":        f"Tech [{node_name}] {device_type} {param_name}",
                "condition":   f"{param_name} = {value!r} (not a number)",
                "satisfied":   False,
                "severity":    "WARNING",
                "rule":        f"Parameter must be numeric ({unit})",
                "tech_source": source,
            }

        satisfied = lo <= val_f <= hi
        cond_str = (
            f"{param_name} = {val_f:.5g} {unit}  ∈  "
            f"[{lo:.5g}, {hi:.5g}] {unit}"
            + (f"  (nominal: {nom:.5g} {unit})" if nom is not None else "")
        )

        return {
            "name":        f"Tech [{node_name}] {device_type}: {param_name}",
            "condition":   cond_str,
            "satisfied":   satisfied,
            "severity":    "CRITICAL" if not satisfied else "OK",
            "rule": (
                f"{param_name} must be within [{lo:.5g}, {hi:.5g}] {unit} "
                f"for {node_name} technology node."
            ),
            "tech_source":  source,
            "tech_min":     lo,
            "tech_max":     hi,
            "tech_nominal": nom,
            "tech_unit":    unit,
        }

    def _validate_ml_predictions(
        self,
        ml_predictions: Dict[str, Any],
        node: TechnologyNodeInfo,
        dev_types: List[str],
        node_name: str,
    ) -> List[Dict[str, Any]]:
        """Check ML-predicted output parameters against technology constraints."""
        checks = []
        for dt in dev_types:
            ranges = node.get_constraint_ranges(dt)
            for param_name, rng in ranges.items():
                if param_name not in ml_predictions:
                    continue
                ml_val = ml_predictions[param_name]
                try:
                    ml_f = float(ml_val)
                except (TypeError, ValueError):
                    continue

                lo, hi = rng["min"], rng["max"]
                unit   = rng.get("unit", "")
                source = rng.get("source", "PTM model file")
                satisfied = lo <= ml_f <= hi

                checks.append({
                    "name":              f"ML Prediction [{node_name}] {dt}: {param_name}",
                    "condition": (
                        f"ML predicted {param_name} = {ml_f:.5g} {unit}  |  "
                        f"Tech limit: [{lo:.5g}, {hi:.5g}] {unit}"
                    ),
                    "satisfied":         satisfied,
                    "severity":          "CRITICAL" if not satisfied else "OK",
                    "rule": (
                        f"ML-predicted {param_name} must satisfy the {node_name} "
                        "technology constraint. Prediction REJECTED if violated."
                    ),
                    "tech_source":       source,
                    "original_ml_value": ml_f,
                    "tech_min":          lo,
                    "tech_max":          hi,
                    "tech_unit":         unit,
                    "is_ml_check":       True,
                })

        return checks

    @staticmethod
    def _no_tech_selected_check() -> Dict[str, Any]:
        return {
            "name":      "Technology Node Selection",
            "condition": "No technology node selected",
            "satisfied": True,
            "severity":  "WARNING",
            "rule":      "Select a technology node to enable technology-specific constraint checks.",
        }

    @staticmethod
    def _unknown_node_check(node_name: str) -> Dict[str, Any]:
        return {
            "name":      f"Technology Node: {node_name}",
            "condition": f"Unknown technology node: {node_name!r}",
            "satisfied": False,
            "severity":  "WARNING",
            "rule":      "Selected technology node is not in the database.",
        }

    @staticmethod
    def _no_model_file_check(node: TechnologyNodeInfo) -> Dict[str, Any]:
        return {
            "name":      f"Technology Node: {node.node_name}",
            "condition": (
                f"Node {node.node_name!r} has no valid PTM parameter file. "
                "Technology-specific constraint check skipped."
            ),
            "satisfied": False,
            "severity":  "WARNING",
            "rule": (
                "A .pm model file is required to enforce technology-specific constraints. "
                "Add the file to the Technology nodes folder."
            ),
        }

    @staticmethod
    def _node_summary_check(node: TechnologyNodeInfo, device_type: str) -> Dict[str, Any]:
        return {
            "name":      f"Technology Compatibility",
            "condition": (
                f"Node: {node.node_name}  |  VDD nominal: "
                + (f"{node.nominal_vdd:.2f} V" if node.nominal_vdd is not None else "N/A")
                + f"  |  Device: {device_type}"
            ),
            "satisfied": True,
            "severity":  "OK",
            "rule":      "Technology node recognised and model parameters loaded from PTM file.",
        }
