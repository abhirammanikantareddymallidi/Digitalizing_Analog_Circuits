"""
Physical constraint checker — operating region conditions, current/voltage validity,
and parameter boundary enforcement.

Every check returns a structured dict with:
    name, condition_str, satisfied (bool), severity, rule
"""

from __future__ import annotations
from typing import List


class PhysicalConstraintChecker:
    """
    Evaluate physics-level constraints for a transistor operating point.

    These constraints are independent of the specific circuit topology.
    """

    @staticmethod
    def check_all(params: dict, results: dict) -> List[dict]:
        """Run all physical-level checks and return a list of constraint results."""
        checks = []
        if results.get("region") == "digital":
            # CMOS inverter validation is handled by its NMOS/PMOS-specific
            # circuit checks; generic single-transistor checks would inspect
            # missing VGS/VDS/ID fields and create misleading PASS results.
            checks.extend(PhysicalConstraintChecker.check_parameter_bounds(params))
            return checks
        checks.append(PhysicalConstraintChecker.check_region_consistency(params, results))
        checks.append(PhysicalConstraintChecker.check_current_positive(results))
        checks.append(PhysicalConstraintChecker.check_voltage_headroom(params, results))
        checks.append(PhysicalConstraintChecker.check_power_budget(params, results))
        checks.append(PhysicalConstraintChecker.check_overdrive_positive(results))
        checks.extend(PhysicalConstraintChecker.check_parameter_bounds(params))
        return checks

    @staticmethod
    def check_input_consistency(params: dict, results: dict) -> List[dict]:
        """Compatibility hook retained for callers of the former input audit."""
        checks = []
        calculated_vds = results.get("VDS_calculated")
        input_vds = results.get("VDS_input")
        if calculated_vds is not None and input_vds is not None:
            vdd = float(params.get("VDD", 1.8))
            tolerance = max(1e-3, 0.01 * vdd)
            error = abs(float(input_vds) - float(calculated_vds))
            checks.append({
                "name": "DC Operating Point Consistency: VDS",
                "condition": (
                    f"VDS input = {float(input_vds):.4f} V; "
                    f"VDD - ID×RD = {float(calculated_vds):.4f} V"
                ),
                "satisfied": error <= tolerance,
                "severity": "CRITICAL" if error > tolerance else "OK",
                "rule": "VDS must equal VDD - ID×RD at the DC operating point",
            })

        input_ibias = results.get("IBIAS_input_uA")
        calculated_id = results.get("ID_uA")
        if input_ibias is not None and calculated_id is not None:
            if float(input_ibias) > 0:
                tolerance = max(0.01, 0.01 * abs(float(calculated_id)))
                error = abs(float(input_ibias) - float(calculated_id))
                checks.append({
                    "name": "DC Operating Point Consistency: IBIAS",
                    "condition": (
                        f"IBIAS input = {float(input_ibias):.4f} µA; "
                        f"calculated ID = {float(calculated_id):.4f} µA"
                    ),
                    "satisfied": error <= tolerance,
                    "severity": "CRITICAL" if error > tolerance else "OK",
                    "rule": "An explicit IBIAS target must match the calculated drain current",
                })
            else:
                checks.append({
                    "name": "Bias Current Mode",
                    "condition": f"IBIAS = 0; calculated ID = {float(calculated_id):.4f} µA",
                    "satisfied": True,
                    "severity": "OK",
                    "rule": "IBIAS=0 means derive the bias current from the transistor operating point",
                })
        return checks

    # ── Region consistency ──────────────────────────────────────
    @staticmethod
    def check_region_consistency(params: dict, results: dict) -> dict:
        """Verify that detected region is consistent with VGS, VDS, VTH."""
        region = results.get("region", "unknown")
        VGS = params.get("VGS", params.get("VBIAS", results.get("VGS", 0)))
        VDS = results.get("VDS", 0)
        VTH = params.get("VTH", params.get("VTH_n", 0.4))
        VOV = results.get("VOV", VGS - VTH)

        if region == "cutoff":
            satisfied = VGS <= VTH
            cond_str = f"Cutoff requires VGS ({VGS:.4f}) ≤ VTH ({VTH:.4f})"
        elif region == "triode":
            satisfied = VGS > VTH and VDS < VOV
            cond_str = f"Triode requires VGS > VTH AND VDS ({VDS:.4f}) < VOV ({VOV:.4f})"
        elif region == "saturation":
            satisfied = VGS > VTH and VDS >= VOV
            cond_str = f"Saturation requires VGS > VTH AND VDS ({VDS:.4f}) ≥ VOV ({VOV:.4f})"
        else:
            satisfied = True
            cond_str = f"Region '{region}' — no voltage-based check"

        return {
            "name": "Region Consistency",
            "condition": cond_str,
            "satisfied": satisfied,
            "severity": "CRITICAL" if not satisfied else "OK",
            "rule": "Operating region must be consistent with terminal voltages",
        }

    # ── Current positive ────────────────────────────────────────
    @staticmethod
    def check_current_positive(results: dict) -> dict:
        """Drain current must be non-negative for an enhancement-mode device."""
        ID = results.get("ID", results.get("ID_each", 0))
        satisfied = ID >= 0
        return {
            "name": "Current Positivity",
            "condition": f"ID = {ID:.6e} A ≥ 0",
            "satisfied": satisfied,
            "severity": "CRITICAL" if not satisfied else "OK",
            "rule": "Drain current must be non-negative",
        }

    # ── Voltage headroom ────────────────────────────────────────
    @staticmethod
    def check_voltage_headroom(params: dict, results: dict) -> dict:
        """VDS should not exceed VDD."""
        VDD = params.get("VDD", 1.8)
        VDS = results.get("VDS", 0)
        satisfied = 0 <= VDS <= VDD
        return {
            "name": "Voltage Headroom",
            "condition": f"0 ≤ VDS ({VDS:.4f}) ≤ VDD ({VDD:.4f})",
            "satisfied": satisfied,
            "severity": "WARNING" if not satisfied else "OK",
            "rule": "Drain-source voltage must be within supply rails",
        }

    # ── Power budget ────────────────────────────────────────────
    @staticmethod
    def check_power_budget(params: dict, results: dict, max_power_W=0.1) -> dict:
        """Total power should be within a reasonable budget."""
        power = results.get("power_dissipation", results.get("P_total", 0))
        satisfied = power <= max_power_W
        return {
            "name": "Power Budget",
            "condition": f"Power = {power*1e3:.4f} mW ≤ {max_power_W*1e3:.1f} mW",
            "satisfied": satisfied,
            "severity": "WARNING" if not satisfied else "OK",
            "rule": "Power dissipation within budget",
        }

    # ── Overdrive positive (for non-cutoff) ─────────────────────
    @staticmethod
    def check_overdrive_positive(results: dict) -> dict:
        """VOV must be positive for triode/saturation."""
        region = results.get("region", "unknown")
        VOV = results.get("VOV", 0)
        if region in ("triode", "saturation"):
            satisfied = VOV > 0
        else:
            satisfied = True
        return {
            "name": "Overdrive Voltage",
            "condition": f"VOV = {VOV:.4f} V > 0  (region={region})",
            "satisfied": satisfied,
            "severity": "CRITICAL" if not satisfied else "OK",
            "rule": "Overdrive voltage must be positive in active regions",
        }

    # ── Parameter bounds ────────────────────────────────────────
    @staticmethod
    def check_parameter_bounds(params: dict) -> List[dict]:
        """Check that key parameters are in physically reasonable ranges."""
        checks = []
        bound_rules = {
            "W":   (0.01, 10000, "um", "Channel width"),
            "L":   (0.01, 100,   "um", "Channel length"),
            "Wn":  (0.01, 10000, "um", "NMOS width (Wn)"),
            "Ln":  (0.01, 100,   "um", "NMOS length (Ln)"),
            "VBIAS":(0.0, 5.0,   "V",  "Gate bias voltage"),
            "IBIAS":(0.0, 50000, "uA", "Quiescent bias current"),
            "W_n": (0.01, 10000, "um", "NMOS width"),
            "L_n": (0.01, 100,   "um", "NMOS length"),
            "W_p": (0.01, 10000, "um", "PMOS width"),
            "L_p": (0.01, 100,   "um", "PMOS length"),
            "mu_n":(10,   1000,  "cm2/Vs", "Electron mobility"),
            "mu_p":(5,    500,   "cm2/Vs", "Hole mobility"),
            "Cox": (0.1,  50,    "fF/um2", "Oxide capacitance"),
        }
        for pname, (lo, hi, unit, desc) in bound_rules.items():
            if pname in params:
                val = params[pname]
                satisfied = lo <= val <= hi
                checks.append({
                    "name": f"Bounds: {desc}",
                    "condition": f"{lo} ≤ {pname}={val} ≤ {hi} {unit}",
                    "satisfied": satisfied,
                    "severity": "WARNING" if not satisfied else "OK",
                    "rule": f"{desc} should be within [{lo}, {hi}] {unit}",
                })
        return checks
