"""
Circuit-level constraint checker — topology-specific validity rules.

Each circuit type has its own set of constraints beyond the basic
physical checks (e.g., noise-margin positivity for an inverter,
odd-stage count for a ring oscillator).
"""

from __future__ import annotations
from typing import List
from physics.transistor import NMOS, PMOS


class CircuitConstraintChecker:
    """Run circuit-specific constraint checks."""

    @staticmethod
    def check(circuit_type: str, params: dict, results: dict) -> List[dict]:
        """Dispatch to the circuit-specific checker."""
        key = circuit_type.lower().replace(" ", "_").replace("-", "_")
        method = getattr(CircuitConstraintChecker, f"_check_{key}", None)
        if method is None:
            return [{"name": "Circuit Check", "condition": "No circuit-specific checks defined",
                      "satisfied": True, "severity": "INFO", "rule": "N/A"}]
        return method(params, results)

    # ── Common Source ───────────────────────────────────────────
    @staticmethod
    def _check_common_source(params, results) -> List[dict]:
        checks = []
        # Gain should be negative (inverting)
        Av = results.get("Av", 0)
        checks.append({
            "name": "CS Gain Polarity",
            "condition": f"Av = {Av:.4f} should be negative (inverting)",
            "satisfied": Av < 0,
            "severity": "WARNING" if Av >= 0 else "OK",
            "rule": "Common-source gain is inverting",
        })
        # Saturation required for amplification
        region = results.get("region", "unknown")
        checks.append({
            "name": "CS Saturation Required",
            "condition": f"Region = {region} should be saturation for amplification",
            "satisfied": region == "saturation",
            "severity": "CRITICAL" if region != "saturation" else "OK",
            "rule": "Transistor must be in saturation for linear amplification",
        })
        # Saturation headroom constraint: VDD - ID*RD >= VOV (from DSE section 3 & 4)
        VDD = params.get("VDD", 1.8)
        RD_k = params.get("RD", 5.0)
        ID = results.get("ID", 0.0)
        VOV = results.get("VOV", 0.0)
        VD = VDD - ID * (RD_k * 1e3)
        headroom_ok = VD >= (VOV - 1e-6)
        checks.append({
            "name": "CS Output Saturation Headroom",
            "condition": f"VD ({VD:.3f} V) ≥ VOV ({VOV:.3f} V)  [VDD - ID·RD ≥ VGS - VTH]",
            "satisfied": headroom_ok,
            "severity": "CRITICAL" if not headroom_ok else "OK",
            "rule": "Transistor drain voltage must stay above overdrive to avoid entering triode",
        })
        # Phase margin stability
        pm = results.get("phase_margin_deg", 90.0)
        checks.append({
            "name": "Phase Margin Stability",
            "condition": f"PM = {pm:.1f}° ≥ 45.0°",
            "satisfied": pm >= 45.0,
            "severity": "WARNING" if pm < 45.0 else "OK",
            "rule": "Phase margin ≥ 45° ensures closed-loop stability without excessive ringing",
        })
        return checks

    # ── Common Gate ─────────────────────────────────────────────
    @staticmethod
    def _check_common_gate(params, results) -> List[dict]:
        checks = []
        Av = results.get("Av", 0)
        checks.append({
            "name": "CG Gain Polarity",
            "condition": f"Av = {Av:.4f} should be positive (non-inverting)",
            "satisfied": Av > 0,
            "severity": "WARNING" if Av <= 0 else "OK",
            "rule": "Common-gate gain is non-inverting",
        })
        region = results.get("region", "unknown")
        checks.append({
            "name": "CG Saturation Required",
            "condition": f"Region = {region} should be saturation",
            "satisfied": region == "saturation",
            "severity": "CRITICAL" if region != "saturation" else "OK",
            "rule": "Transistor must be in saturation for amplification",
        })
        return checks

    # ── Common Drain ────────────────────────────────────────────
    @staticmethod
    def _check_common_drain(params, results) -> List[dict]:
        checks = []
        Av = results.get("Av", 0)
        checks.append({
            "name": "CD Gain Range",
            "condition": f"Av = {Av:.4f} should be 0 < Av < 1",
            "satisfied": 0 < Av < 1,
            "severity": "WARNING" if not (0 < Av < 1) else "OK",
            "rule": "Source follower gain is slightly below unity",
        })
        return checks

    # ── CMOS Inverter ───────────────────────────────────────────
    @staticmethod
    def _check_cmos_inverter(params, results) -> List[dict]:
        checks = []
        VDD = float(params.get("VDD", 0.0))
        VTH_n = float(params.get("VTH_n", 0.0))
        VTH_p = float(params.get("VTH_p", 0.0))
        VM = float(results.get("VM", 0.0))
        VOUT = float(results.get("VOUT_at_VM", VDD / 2.0))
        nmos = NMOS(
            W=params["W_n"], L=params["L_n"], mu=params["mu_n"],
            Cox=params["Cox"], VTH=VTH_n, lambda_=params.get("lambda_n", 0.0),
        )
        pmos = PMOS(
            W=params["W_p"], L=params["L_p"], mu=params["mu_p"],
            Cox=params["Cox"], VTH=VTH_p, lambda_=params.get("lambda_p", 0.0),
        )
        n_info = nmos.calculate_ID(VM, VOUT)
        p_info = pmos.calculate_ID(VM - VDD, VOUT - VDD)
        vgs_n = VM
        vsg_p = VDD - VM
        vov_n = vgs_n - VTH_n
        vov_p = vsg_p - abs(VTH_p)
        id_n = n_info["ID"]
        id_p_abs = abs(p_info["ID"])
        balance_error = id_n - id_p_abs
        balance_relative_error = abs(balance_error) / max(id_n, id_p_abs, 1e-30)
        both_conducting = id_n > 1e-18 and id_p_abs > 1e-18
        checks.append({
            "name": "CMOS Current Balance",
            "condition": (
                f"VTH_n={VTH_n:.8g} V, VTH_p={VTH_p:.8g} V; "
                f"VGS_n={vgs_n:.8g} V, VSG_p={vsg_p:.8g} V; "
                f"VOV_n={vov_n:.8g} V, VOV_p={vov_p:.8g} V; "
                f"VDS_n={VOUT:.8g} V, VSD_p={VDD - VOUT:.8g} V; "
                f"ID_n={id_n:.8g} A, |ID_p|={id_p_abs:.8g} A; "
                f"regions={n_info['region']}/{p_info['region']}; "
                f"balance_error={balance_error:.8g} A ({balance_relative_error:.3e} rel)"
            ),
            "satisfied": not both_conducting or balance_relative_error <= 1e-6,
            "severity": "CRITICAL" if both_conducting and balance_relative_error > 1e-6 else "OK",
            "rule": "At a conducting CMOS switching point, independently calculated NMOS and PMOS currents must balance",
        })
        overdrive_tolerance = 1e-12
        for label, vov_key, id_key, region_key in (
            ("NMOS", "nmos_VOV", "nmos_ID", "nmos_region"),
            ("PMOS", "pmos_VOV", "pmos_ID", "pmos_region"),
        ):
            vov = results.get(vov_key, 0.0)
            current = results.get(id_key, 0.0)
            region = results.get(region_key, "unknown")
            active = vov > overdrive_tolerance
            checks.append({
                "name": f"{label} Operating Point",
                "condition": f"{label} VOV = {vov:.8g} V; ID = {current:.8g} A; region = {region}",
                "satisfied": active or abs(current) <= 1e-18,
                "severity": "CRITICAL" if not active and abs(current) > 1e-18 else "OK",
                "rule": "Positive overdrive is required for an active transistor; zero current is valid only in cutoff",
            })
            checks.append({
                "name": f"{label} Overdrive",
                "condition": f"VOV = {vov:.8g} V > {overdrive_tolerance:.1e} V",
                "satisfied": active,
                "severity": "CRITICAL" if not active else "OK",
                "rule": f"{label} must have positive overdrive at the switching operating point",
            })
        NML = results.get("NML", 0)
        NMH = results.get("NMH", 0)
        checks.append({
            "name": "Noise Margin Low",
            "condition": f"NML = {NML:.4f} V > 0",
            "satisfied": NML > 0,
            "severity": "CRITICAL" if NML <= 0 else "OK",
            "rule": "Low noise margin must be positive",
        })
        checks.append({
            "name": "Noise Margin High",
            "condition": f"NMH = {NMH:.4f} V > 0",
            "satisfied": NMH > 0,
            "severity": "CRITICAL" if NMH <= 0 else "OK",
            "rule": "High noise margin must be positive",
        })
        absolute_error = abs(VM - VDD / 2.0)
        relative_error = absolute_error / max(VDD / 2.0, 1e-12)
        absolute_tolerance = 0.05
        relative_tolerance = 0.10
        threshold_ok = absolute_error <= absolute_tolerance or relative_error <= relative_tolerance
        checks.append({
            "name": "Switching Threshold",
            "condition": (
                f"VM = {VM:.8g} V; VDD/2 = {VDD/2:.8g} V; "
                f"error = {absolute_error:.8g} V ({relative_error:.3%}); "
                f"limits = {absolute_tolerance:.3g} V or {relative_tolerance:.1%}"
            ),
            "satisfied": threshold_ok,
            "severity": "WARNING" if not threshold_ok else "OK",
            "rule": "Switching threshold must be close to half the supply within explicit tolerance",
        })
        return checks

    # ── Current Mirror ──────────────────────────────────────────
    @staticmethod
    def _check_current_mirror(params, results) -> List[dict]:
        checks = []
        VDS_out = params.get("VDS_out", 0)
        VOV = results.get("VOV_ref", results.get("compliance_voltage", 0))
        checks.append({
            "name": "Output Saturation",
            "condition": f"VDS_out ({VDS_out:.4f}) ≥ VOV ({VOV:.4f})",
            "satisfied": VDS_out >= VOV,
            "severity": "CRITICAL" if VDS_out < VOV else "OK",
            "rule": "Output transistor must be in saturation",
        })
        mismatch = results.get("mismatch_percent", 0)
        checks.append({
            "name": "Current Mismatch",
            "condition": f"Mismatch = {mismatch:.2f}% (due to CLM)",
            "satisfied": mismatch < 10,
            "severity": "WARNING" if mismatch >= 10 else "OK",
            "rule": "Current mismatch should be < 10%",
        })
        return checks

    # ── Single-Stage Amplifier ─────────────────────────────────
    @staticmethod
    def _check_single_stage_opamp(params, results) -> List[dict]:
        checks = []
        Av = results.get("Av", 0.0)
        checks.append({
            "name": "Single-Stage Gain",
            "condition": f"Av = {Av:.4f} should be positive",
            "satisfied": Av > 0,
            "severity": "WARNING" if Av <= 0 else "OK",
            "rule": "Single-stage amplifier gain should be positive for a non-inverting stage",
        })
        region = results.get("region", "unknown")
        checks.append({
            "name": "Single-Stage Region",
            "condition": f"Region = {region} should be saturation",
            "satisfied": region == "saturation",
            "severity": "CRITICAL" if region != "saturation" else "OK",
            "rule": "Amplifier transistors should be in saturation for linear gain",
        })
        swing = results.get("output_swing_V", 0.0)
        checks.append({
            "name": "Single-Stage Swing",
            "condition": f"Output swing = {swing:.3f} V should be positive",
            "satisfied": swing > 0,
            "severity": "WARNING" if swing <= 0 else "OK",
            "rule": "The stage should maintain a usable output swing",
        })
        return checks

    # ── Two-Stage Amplifier ───────────────────────────────────
    @staticmethod
    def _check_two_stage_opamp(params, results) -> List[dict]:
        checks = []
        Av = results.get("Av", 0.0)
        pm = results.get("phase_margin_deg", 90.0)
        checks.append({
            "name": "Two-Stage Gain",
            "condition": f"Av = {Av:.4f} should be positive",
            "satisfied": Av > 0,
            "severity": "WARNING" if Av <= 0 else "OK",
            "rule": "Two-stage amplifier should have positive DC gain",
        })
        checks.append({
            "name": "Phase Margin",
            "condition": f"PM = {pm:.1f}° should be ≥ 45°",
            "satisfied": pm >= 45.0,
            "severity": "WARNING" if pm < 45.0 else "OK",
            "rule": "Phase margin should remain stable for the compensation network",
        })
        return checks

    # ── Differential Amplifier ──────────────────────────────────
    @staticmethod
    def _check_differential_amplifier(params, results) -> List[dict]:
        checks = []
        CMRR_dB = results.get("CMRR_dB", 0)
        checks.append({
            "name": "CMRR Adequacy",
            "condition": f"CMRR = {CMRR_dB:.2f} dB should be ≥ 40 dB",
            "satisfied": CMRR_dB >= 40,
            "severity": "WARNING" if CMRR_dB < 40 else "OK",
            "rule": "Adequate common-mode rejection",
        })
        VCM = params.get("VCM", 0)
        VICM_max = results.get("VICM_max", 0)
        VICM_min = results.get("VICM_min", 0)
        checks.append({
            "name": "VICM in Range",
            "condition": f"VICM_min ({VICM_min:.3f}) ≤ VCM ({VCM:.3f}) ≤ VICM_max ({VICM_max:.3f})",
            "satisfied": VICM_min <= VCM <= VICM_max,
            "severity": "CRITICAL" if not (VICM_min <= VCM <= VICM_max) else "OK",
            "rule": "Input common-mode voltage must be within valid range",
        })
        return checks

    # ── Ring Oscillator ─────────────────────────────────────────
    @staticmethod
    def _check_ring_oscillator(params, results) -> List[dict]:
        checks = []
        N = int(params.get("N_stages", 0))
        checks.append({
            "name": "Odd Stages",
            "condition": f"N_stages = {N} must be odd",
            "satisfied": N % 2 == 1 and N >= 3,
            "severity": "CRITICAL" if N % 2 == 0 or N < 3 else "OK",
            "rule": "Ring oscillator requires odd number of stages (≥ 3)",
        })
        f_osc = results.get("f_osc", 0)
        checks.append({
            "name": "Oscillation Feasibility",
            "condition": f"f_osc = {f_osc/1e6:.2f} MHz > 0",
            "satisfied": f_osc > 0,
            "severity": "CRITICAL" if f_osc <= 0 else "OK",
            "rule": "Oscillation frequency must be positive",
        })
        return checks
