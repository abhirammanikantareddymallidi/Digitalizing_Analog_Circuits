"""
Per-circuit equation libraries.

Each circuit class provides static methods that compute
circuit-level performance metrics from transistor-level parameters.

Every method returns a dict:
    { value, equation, latex }
so the explainability pipeline can display exactly what was computed.
"""

from __future__ import annotations
import math
from physics.transistor import Transistor, TransistorParams, Region, NMOS, PMOS
from physics.transistor import (
    _um_to_m, _cm2Vs_to_m2Vs, _fF_um2_to_F_m2,
    _uA_to_A, _kOhm_to_Ohm, _fF_to_F,
)


# ══════════════════════════════════════════════════════════════
#  Helper: parallel resistance
# ══════════════════════════════════════════════════════════════
def _parallel(*args):
    """Compute parallel combination of resistances."""
    inv_sum = sum(1.0 / r for r in args if r > 0 and r != float("inf"))
    return 1.0 / inv_sum if inv_sum > 0 else float("inf")


def _solve_resistive_vds(nmos, VGS, VDD, resistance_ohm):
    """Solve VDS = VDD - ID(VGS, VDS) * R for a resistively loaded NMOS."""
    vds = max(0.01, min(VDD, VDD / 2.0))
    for _ in range(32):
        current = nmos.calculate_ID(VGS, VDS=vds)["ID"]
        next_vds = max(0.0, min(VDD, VDD - current * resistance_ohm))
        if abs(next_vds - vds) < 1e-12:
            return next_vds
        vds = next_vds
    return vds


# ══════════════════════════════════════════════════════════════
#  COMMON SOURCE AMPLIFIER
# ══════════════════════════════════════════════════════════════
class CommonSourceEquations:
    """Equations specific to a common-source amplifier."""

    @staticmethod
    def gain(gm, ro, RD_ohm):
        """Av = −gm · (ro ∥ RD)"""
        Rout = _parallel(ro, RD_ohm)
        Av = -gm * Rout
        Av_magnitude = abs(Av)
        return {
            "value": Av,
            "Av_magnitude": Av_magnitude,
            "Av_dB": 20 * math.log10(Av_magnitude) if Av_magnitude > 0 else float("-inf"),
            "equation": f"Av = −gm·(ro∥RD) = −{gm:.4e}·{Rout:.2f} = {Av:.4f}",
            "latex": r"A_v = -g_m (r_o \| R_D)",
        }

    @staticmethod
    def input_resistance():
        """Rin = ∞ (ideal gate)"""
        return {
            "value": float("inf"),
            "equation": "Rin = ∞ (gate is ideal insulator)",
            "latex": r"R_{in} = \infty",
        }

    @staticmethod
    def output_resistance(ro, RD_ohm):
        """Rout = ro ∥ RD"""
        val = _parallel(ro, RD_ohm)
        return {
            "value": val,
            "equation": f"Rout = ro∥RD = {val:.2f} Ω",
            "latex": r"R_{out} = r_o \| R_D",
        }

    @staticmethod
    def bandwidth(Rout, CL_F):
        """BW = 1 / (2π · Rout · CL)"""
        val = 1.0 / (2 * math.pi * Rout * CL_F) if Rout > 0 and CL_F > 0 else float("inf")
        return {
            "value": val,
            "value_MHz": val / 1e6,
            "equation": f"BW = 1/(2π·Rout·CL) = {val:.4e} Hz = {val/1e6:.2f} MHz",
            "latex": r"BW = \frac{1}{2\pi R_{out} C_L}",
        }

    @staticmethod
    def phase_margin(GBW_Hz, gm, W_um, L_um, Cox_fF_um2):
        """
        Phase margin with non-dominant pole:
        PM ≈ 90° - arctan(GBW / p2)
        p2 ≈ gm / [2π·(Cgs + Cgd)]
        """
        # Parasitic capacitances
        Cgs = (2.0 / 3.0) * (W_um * 1e-6) * (L_um * 1e-6) * (Cox_fF_um2 * 1e-3)
        Cgd = 0.2 * Cgs  # overlap approximation
        Cp = Cgs + Cgd
        p2 = gm / (2 * math.pi * Cp) if (gm > 0 and Cp > 0) else float("inf")
        
        if p2 > 0 and not math.isinf(p2) and GBW_Hz > 0 and not math.isinf(GBW_Hz):
            pm = 90.0 - math.degrees(math.atan(GBW_Hz / p2))
        else:
            pm = 90.0
        pm = max(0.0, min(90.0, pm))
        return {
            "value": pm,
            "equation": f"PM ≈ 90° - arctan(GBW/p2) = {pm:.2f}° (p2={p2/1e6:.1f} MHz)",
            "latex": r"PM \approx 90^\circ - \arctan\left(\frac{GBW}{p_2}\right)",
        }

    @staticmethod
    def noise(gm, RD_ohm, W_um, L_um, Cox_fF_um2, BW_Hz):
        """
        Input-referred noise:
        Thermal: S_th = 4*k*T*gamma/gm + 4*k*T/(gm^2 * RD)
        Flicker (1/f): S_fl = Kf / (Cox * W * L * f) at f = 1kHz
        Total = sqrt(S_th + S_fl)
        """
        k = 1.380649e-23
        T = 300.0
        gamma = 2.0 / 3.0
        Kf = 1.0e-25  # V^2*F

        if gm > 0:
            S_th_chan = (4.0 * k * T * gamma) / gm
            S_th_rd = (4.0 * k * T) / ((gm ** 2) * RD_ohm) if RD_ohm > 0 else 0.0
            S_th = S_th_chan + S_th_rd
            v_th_nV = math.sqrt(S_th) * 1e9
        else:
            S_th = 0.0
            v_th_nV = 0.0

        Cox_SI = Cox_fF_um2 * 1e-3
        area_m2 = (W_um * 1e-6) * (L_um * 1e-6)
        if area_m2 > 0 and Cox_SI > 0:
            S_fl = Kf / (Cox_SI * area_m2 * 1000.0)  # at 1 kHz
            v_fl_nV = math.sqrt(S_fl) * 1e9
        else:
            S_fl = 0.0
            v_fl_nV = 0.0

        v_tot_nV = math.sqrt(v_th_nV ** 2 + v_fl_nV ** 2)
        
        # Integrated noise over BW (approx)
        if BW_Hz > 0 and not math.isinf(BW_Hz):
            int_sq = S_th * (math.pi / 2.0) * BW_Hz + S_fl * 1000.0 * math.log(max(10.0, BW_Hz / 10.0))
            v_int_uV = math.sqrt(max(0.0, int_sq)) * 1e6
        else:
            v_int_uV = 0.0

        return {
            "thermal_noise_nV": v_th_nV,
            "flicker_noise_nV": v_fl_nV,
            "total_noise_nV": v_tot_nV,
            "integrated_noise_uV": v_int_uV,
            "equation": f"v_noise = {v_tot_nV:.2f} nV/√Hz (thermal: {v_th_nV:.2f}, flicker@1kHz: {v_fl_nV:.2f})",
            "latex": r"S_v(f) = \frac{4kT\gamma}{g_m} + \frac{K_f}{C_{ox}WLf}",
        }

    @staticmethod
    def output_swing(VDD, ID, RD_ohm, VOV):
        """
        Output swing limits:
        Vout_max = VDD
        Vout_min = VOV (to keep NMOS in saturation)
        V_D = VDD - ID * RD
        Symmetrical swing: 2 * min(VDD - V_D, V_D - VOV)
        """
        VD = VDD - ID * RD_ohm
        VD_clamped = max(0.0, min(VDD, VD))
        headroom_pos = max(0.0, VDD - VD_clamped)
        headroom_neg = max(0.0, VD_clamped - max(0.0, VOV))
        single_swing = min(headroom_pos, headroom_neg)
        pp_swing = 2.0 * single_swing
        return {
            "output_swing_V": single_swing,
            "output_swing_pp": pp_swing,
            "VD_quiescent": VD_clamped,
            "equation": f"Swing = ±{single_swing:.3f} V (pp: {pp_swing:.3f} V, VD: {VD_clamped:.3f} V)",
            "latex": r"V_{swing,pp} = 2 \cdot \min(V_{DD} - V_D, V_D - V_{OV})",
        }

    @staticmethod
    def area(W_um, L_um, RD_kOhm):
        """
        Active transistor area = W * L (um^2)
        Total cell area estimate includes poly resistor: ~ RD * 2.5 um^2
        """
        tx_area = W_um * L_um
        res_area = max(1.0, RD_kOhm * 2.5) if RD_kOhm > 0 else 0.0
        tot_area = tx_area + res_area
        return {
            "transistor_area_um2": tx_area,
            "total_area_um2": tot_area,
            "equation": f"Area = {tx_area:.2f} um² (active) + {res_area:.2f} um² (load) = {tot_area:.2f} um²",
            "latex": r"\text{Area}_{total} = W_n L_n + A_{RD}",
        }

    @staticmethod
    def linearity(VOV):
        """
        Linearity / IIP3 for CS amplifier:
        VIIP3 ≈ sqrt(8/3) * VOV ≈ 1.633 * VOV
        IIP3 [dBm] into 50 ohm = 10 + 20*log10(VIIP3)
        """
        vov_eff = max(0.001, VOV)
        viip3 = math.sqrt(8.0 / 3.0) * vov_eff
        piip3_dbm = 10.0 + 20.0 * math.log10(viip3)
        return {
            "IIP3_V": viip3,
            "IIP3_dBm": piip3_dbm,
            "equation": f"VIIP3 ≈ √(8/3)·VOV = {viip3:.3f} V ({piip3_dbm:.2f} dBm)",
            "latex": r"V_{IIP3} \approx \sqrt{\frac{8}{3}} V_{OV}",
        }

    @staticmethod
    def psrr(gm, ro, RD_ohm):
        """
        PSRR = Av / Add ≈ gm * RD
        """
        psrr_lin = gm * RD_ohm if (gm > 0 and RD_ohm > 0) else 1.0
        psrr_db = 20.0 * math.log10(max(1e-6, psrr_lin))
        return {
            "PSRR": psrr_lin,
            "PSRR_dB": psrr_db,
            "equation": f"PSRR ≈ gm·RD = {psrr_lin:.2f} ({psrr_db:.2f} dB)",
            "latex": r"PSRR \approx g_m R_D",
        }

    @staticmethod
    def compute_all(params: dict) -> dict:
        """Full CS analysis from lab-unit parameter dict."""
        # Handle parameter aliases from digitizing analog document (Wn, Ln, VBIAS, IBIAS)
        W = params.get("W", params.get("Wn", 10.0))
        L = params.get("L", params.get("Ln", 0.18))
        VGS = params.get("VGS", params.get("VBIAS", 0.8))
        VTH = params.get("VTH", 0.4)
        mu_n = params.get("mu_n", 450.0)
        Cox = params.get("Cox", 8.63)
        lambda_n = params.get("lambda_n", 0.1)
        VDD = params.get("VDD", 1.8)
        RD_k = params.get("RD", 5.0)
        CL_fF = params.get("CL", 50.0)
        input_vgs = params.get("VGS", params.get("VBIAS", None))

        nmos = NMOS(
            W=W, L=L,
            mu=mu_n, Cox=Cox,
            VTH=VTH, lambda_=lambda_n,
        )

        RD_ohm = _kOhm_to_Ohm(RD_k)
        CL_F = _fF_to_F(CL_fF)

        VDS = _solve_resistive_vds(nmos, VGS, VDD, RD_ohm)

        calculated_id = nmos.calculate_ID(VGS, VDS=VDS)["ID"]

        ss = nmos.calculate_small_signal(VGS, VDS)

        gain = CommonSourceEquations.gain(ss["gm"], ss["ro"], RD_ohm)
        rin = CommonSourceEquations.input_resistance()
        rout = CommonSourceEquations.output_resistance(ss["ro"], RD_ohm)
        bw = CommonSourceEquations.bandwidth(rout["value"], CL_F)

        GBW = abs(gain["value"]) * bw["value"] if bw["value"] != float("inf") else float("inf")
        power = ss["ID"] * VDD

        # New metrics from digitizing analog document
        pm = CommonSourceEquations.phase_margin(GBW, ss["gm"], W, L, Cox)
        nse = CommonSourceEquations.noise(ss["gm"], RD_ohm, W, L, Cox, bw["value"])
        swg = CommonSourceEquations.output_swing(VDD, ss["ID"], RD_ohm, ss["VOV"])
        ara = CommonSourceEquations.area(W, L, RD_k)
        lin = CommonSourceEquations.linearity(ss["VOV"])
        psr = CommonSourceEquations.psrr(ss["gm"], ss["ro"], RD_ohm)

        return {
            **ss,
            "operating_region": ss["region"],
            "Wn": W,
            "Ln": L,
            "VBIAS": VGS,
            "VGS_input": input_vgs,
            "VGS_mode": "user design input",
            "IBIAS": ss["ID_uA"],
            "IBIAS_calculated_uA": ss["ID_uA"],
            "IBIAS_mode": "derived from operating point",
            "VDS": VDS,
            "VDS_calculated": VDS,
            "VDS_sat": VDS - ss["VOV"],
            "Av": gain["value"],
            "Av_magnitude": gain["Av_magnitude"],
            "Av_dB": gain["Av_dB"],
            "Rin": rin["value"],
            "Rout": rout["value"],
            "Rout_kOhm": rout["value"] / 1e3,
            "BW": bw["value"],
            "BW_MHz": bw["value_MHz"],
            "GBW": GBW,
            "GBW_MHz": GBW / 1e6,
            "phase_margin_deg": pm["value"],
            "power_dissipation": power,
            "power_mW": power * 1e3,
            "thermal_noise_nV": nse["thermal_noise_nV"],
            "flicker_noise_nV": nse["flicker_noise_nV"],
            "total_noise_nV": nse["total_noise_nV"],
            "integrated_noise_uV": nse["integrated_noise_uV"],
            "output_swing_V": swg["output_swing_V"],
            "output_swing_pp": swg["output_swing_pp"],
            "transistor_area_um2": ara["transistor_area_um2"],
            "total_area_um2": ara["total_area_um2"],
            "IIP3_V": lin["IIP3_V"],
            "IIP3_dBm": lin["IIP3_dBm"],
            "PSRR": psr["PSRR"],
            "PSRR_dB": psr["PSRR_dB"],
            "equations_used": [
                gain["equation"], rin["equation"],
                rout["equation"], bw["equation"],
                pm["equation"], nse["equation"],
                swg["equation"], ara["equation"],
                lin["equation"], psr["equation"],
            ],
            "latex_equations": [
                gain["latex"], rin["latex"],
                rout["latex"], bw["latex"],
                pm["latex"], nse["latex"],
                swg["latex"], ara["latex"],
                lin["latex"], psr["latex"],
            ],
        }


# ══════════════════════════════════════════════════════════════
#  COMMON GATE AMPLIFIER
# ══════════════════════════════════════════════════════════════
class CommonGateEquations:
    """Equations specific to a common-gate amplifier."""

    @staticmethod
    def gain(gm, ro, RD_ohm):
        """Av = +gm · (ro ∥ RD)  (non-inverting)"""
        Rout = _parallel(ro, RD_ohm)
        Av = gm * Rout
        return {
            "value": Av,
            "Av_dB": 20 * math.log10(abs(Av)) if Av != 0 else float("-inf"),
            "equation": f"Av = gm·(ro∥RD) = {gm:.4e}·{Rout:.2f} = {Av:.4f}",
            "latex": r"A_v = g_m (r_o \| R_D)",
        }

    @staticmethod
    def input_resistance(gm, ro, RD_ohm):
        """Rin ≈ 1/gm  (for large ro)"""
        # More precisely: Rin = (ro + RD) / (1 + gm*ro) ≈ 1/gm
        val = 1.0 / gm if gm > 0 else float("inf")
        return {
            "value": val,
            "equation": f"Rin ≈ 1/gm = 1/{gm:.4e} = {val:.2f} Ω",
            "latex": r"R_{in} \approx \frac{1}{g_m}",
        }

    @staticmethod
    def output_resistance(ro, RD_ohm):
        """Rout = ro ∥ RD"""
        val = _parallel(ro, RD_ohm)
        return {
            "value": val,
            "equation": f"Rout = ro∥RD = {val:.2f} Ω",
            "latex": r"R_{out} = r_o \| R_D",
        }

    @staticmethod
    def bandwidth(Rin, CL_F):
        """BW ≈ 1 / (2π · Rin · CL)  (input-pole dominant for CG)"""
        val = 1.0 / (2 * math.pi * Rin * CL_F) if Rin > 0 and CL_F > 0 else float("inf")
        return {
            "value": val,
            "value_MHz": val / 1e6,
            "equation": f"BW ≈ 1/(2π·Rin·CL) = {val:.4e} Hz",
            "latex": r"BW \approx \frac{1}{2\pi R_{in} C_L}",
        }

    @staticmethod
    def compute_all(params: dict) -> dict:
        nmos = NMOS(
            W=params["W"], L=params["L"],
            mu=params["mu_n"], Cox=params["Cox"],
            VTH=params["VTH"], lambda_=params["lambda_n"],
        )
        RD_ohm = _kOhm_to_Ohm(params["RD"])
        CL_F = _fF_to_F(params["CL"])
        VDS = _solve_resistive_vds(nmos, params["VGS"], params["VDD"], RD_ohm)
        ss = nmos.calculate_small_signal(params["VGS"], VDS)

        gain = CommonGateEquations.gain(ss["gm"], ss["ro"], RD_ohm)
        rin = CommonGateEquations.input_resistance(ss["gm"], ss["ro"], RD_ohm)
        rout = CommonGateEquations.output_resistance(ss["ro"], RD_ohm)
        bw = CommonGateEquations.bandwidth(rin["value"], CL_F)

        GBW = abs(gain["value"]) * bw["value"] if bw["value"] != float("inf") else float("inf")
        power = ss["ID"] * params["VDD"]

        return {
            **ss,
            "VDS": VDS,
            "Av": gain["value"],
            "Av_dB": gain["Av_dB"],
            "Rin": rin["value"],
            "Rin_Ohm": rin["value"],
            "Rout": rout["value"],
            "Rout_kOhm": rout["value"] / 1e3,
            "BW": bw["value"],
            "BW_MHz": bw["value_MHz"],
            "GBW": GBW,
            "GBW_MHz": GBW / 1e6,
            "power_dissipation": power,
            "power_mW": power * 1e3,
            "equations_used": [
                gain["equation"], rin["equation"],
                rout["equation"], bw["equation"],
            ],
            "latex_equations": [
                gain["latex"], rin["latex"],
                rout["latex"], bw["latex"],
            ],
        }


# ══════════════════════════════════════════════════════════════
#  COMMON DRAIN (SOURCE FOLLOWER)
# ══════════════════════════════════════════════════════════════
class CommonDrainEquations:
    """Equations specific to a common-drain (source follower) amplifier."""

    @staticmethod
    def gain(gm, ro, RS_ohm):
        """Av = gm·(ro∥RS) / [1 + gm·(ro∥RS)]"""
        R_load = _parallel(ro, RS_ohm)
        denom = 1.0 + gm * R_load
        Av = gm * R_load / denom if denom > 0 else 0.0
        return {
            "value": Av,
            "Av_dB": 20 * math.log10(abs(Av)) if Av > 0 else float("-inf"),
            "equation": f"Av = gm·(ro∥RS)/(1+gm·(ro∥RS)) = {Av:.4f}",
            "latex": r"A_v = \frac{g_m(r_o\|R_S)}{1+g_m(r_o\|R_S)}",
        }

    @staticmethod
    def input_resistance():
        """Rin = ∞"""
        return {
            "value": float("inf"),
            "equation": "Rin = ∞",
            "latex": r"R_{in} = \infty",
        }

    @staticmethod
    def output_resistance(gm, ro, RS_ohm):
        """Rout = (1/gm) ∥ ro ∥ RS"""
        inv_gm = 1.0 / gm if gm > 0 else float("inf")
        val = _parallel(inv_gm, ro, RS_ohm)
        return {
            "value": val,
            "equation": f"Rout = (1/gm)∥ro∥RS = {val:.2f} Ω",
            "latex": r"R_{out} = \frac{1}{g_m} \| r_o \| R_S",
        }

    @staticmethod
    def bandwidth(Rout, CL_F):
        """BW = 1 / (2π · Rout · CL)"""
        val = 1.0 / (2 * math.pi * Rout * CL_F) if Rout > 0 and CL_F > 0 else float("inf")
        return {
            "value": val,
            "value_MHz": val / 1e6,
            "equation": f"BW = 1/(2π·Rout·CL) = {val:.4e} Hz",
            "latex": r"BW = \frac{1}{2\pi R_{out} C_L}",
        }

    @staticmethod
    def compute_all(params: dict) -> dict:
        nmos = NMOS(
            W=params["W"], L=params["L"],
            mu=params["mu_n"], Cox=params["Cox"],
            VTH=params["VTH"], lambda_=params["lambda_n"],
        )
        RS_ohm = _kOhm_to_Ohm(params["RS"])
        CL_F = _fF_to_F(params["CL"])
        VDS = _solve_resistive_vds(nmos, params["VGS"], params["VDD"], RS_ohm)
        ss = nmos.calculate_small_signal(params["VGS"], VDS)

        gain = CommonDrainEquations.gain(ss["gm"], ss["ro"], RS_ohm)
        rin = CommonDrainEquations.input_resistance()
        rout = CommonDrainEquations.output_resistance(ss["gm"], ss["ro"], RS_ohm)
        bw = CommonDrainEquations.bandwidth(rout["value"], CL_F)

        power = ss["ID"] * params["VDD"]

        return {
            **ss,
            "VDS": VDS,
            "Av": gain["value"],
            "Av_dB": gain["Av_dB"],
            "Rin": rin["value"],
            "Rout": rout["value"],
            "Rout_Ohm": rout["value"],
            "BW": bw["value"],
            "BW_MHz": bw["value_MHz"],
            "power_dissipation": power,
            "power_mW": power * 1e3,
            "equations_used": [
                gain["equation"], rin["equation"],
                rout["equation"], bw["equation"],
            ],
            "latex_equations": [
                gain["latex"], rin["latex"],
                rout["latex"], bw["latex"],
            ],
        }


# ══════════════════════════════════════════════════════════════
#  CMOS INVERTER
# ══════════════════════════════════════════════════════════════
class CMOSInverterEquations:
    """Equations specific to a CMOS inverter."""

    @staticmethod
    def switching_threshold(VDD, VTH_n, VTH_p, kn, kp):
        """Return the conventional midpoint estimate used before DC solving."""
        ratio = math.sqrt(kp / kn) if kn > 0 else 1.0
        VM = (VTH_n + (VDD - abs(VTH_p)) * ratio) / (1 + ratio)
        return {
            "value": VM,
            "equation": f"VM estimate = [VTHn + (VDD−|VTHp|)·√(kp/kn)] / [1+√(kp/kn)] = {VM:.4f} V",
            "latex": r"V_M = \frac{V_{THn}+(V_{DD}-|V_{THp}|)\sqrt{k_p/k_n}}{1+\sqrt{k_p/k_n}}",
        }

    @staticmethod
    def solve_operating_point(VDD, VTH_n, VTH_p, nmos, pmos):
        """Solve VM from ID_n(VM, VDD/2) = |ID_p(VM, VDD/2)|.

        The conventional switching threshold uses VOUT = VDD/2.  The
        transistor models then independently determine each region and current.
        If the two threshold voltages have no positive-overdrive overlap, the
        returned point is explicitly marked invalid instead of inventing a VM.
        """
        vout = VDD / 2.0
        overlap_low = VTH_n
        overlap_high = VDD - abs(VTH_p)

        def currents(vm):
            n_info = nmos.calculate_ID(vm, vout)
            p_info = pmos.calculate_ID(vm - VDD, vout - VDD)
            return n_info, p_info

        if overlap_low < overlap_high:
            low = overlap_low + 1e-12
            high = overlap_high - 1e-12
            low_error = currents(low)[0]["ID"] - abs(currents(low)[1]["ID"])
            high_error = currents(high)[0]["ID"] - abs(currents(high)[1]["ID"])
            if low_error * high_error <= 0:
                for _ in range(80):
                    mid = 0.5 * (low + high)
                    mid_error = currents(mid)[0]["ID"] - abs(currents(mid)[1]["ID"])
                    if abs(mid_error) <= 1e-18:
                        break
                    if low_error * mid_error <= 0:
                        high, high_error = mid, mid_error
                    else:
                        low, low_error = mid, mid_error
                vm = 0.5 * (low + high)
                n_info, p_info = currents(vm)
                return {
                    "VM": vm, "VOUT": vout,
                    "nmos": n_info, "pmos": p_info,
                    "valid": n_info["ID"] > 0 and p_info["ID"] < 0,
                }

        vm = min(max(VDD / 2.0, 0.0), VDD)
        n_info, p_info = currents(vm)
        return {
            "VM": vm, "VOUT": vout,
            "nmos": n_info, "pmos": p_info,
            "valid": False,
        }

    @staticmethod
    def noise_margins(VDD, VM, VTH_n, VTH_p):
        """
        Approximate noise margins:
            VIL ≈ (3·VM − VDD) / 2 + VTH_n/4   (simplified)
            VIH ≈ (VM + VDD) / 2 + VTH_p/4
            VOL = 0 (ideal)
            VOH = VDD (ideal)
            NML = VIL − VOL
            NMH = VOH − VIH
        """
        # Simplified estimates from Rabaey / Weste-Harris
        VIL = 0.4 * VDD  # rough for symmetric inverter
        VIH = 0.6 * VDD
        VOL = 0.0
        VOH = VDD
        # Better estimate using VM
        if VM > 0:
            VIL = (2.0 * VM) / 3.0
            VIH = (VDD + VM) / 2.0
            if VIH > VDD:
                VIH = 0.6 * VDD
        NML = VIL - VOL
        NMH = VOH - VIH
        return {
            "VIL": VIL, "VIH": VIH, "VOL": VOL, "VOH": VOH,
            "NML": NML, "NMH": NMH,
            "equation": f"NML = VIL−VOL = {NML:.4f} V,  NMH = VOH−VIH = {NMH:.4f} V",
            "latex": r"NM_L = V_{IL}-V_{OL}, \quad NM_H = V_{OH}-V_{IH}",
        }

    @staticmethod
    def propagation_delay(CL_F, VDD, kn, kp):
        """
        tpHL ≈ CL·VDD / (kn·(VDD−VTHn)²)   (simplified Elmore)
        tpLH ≈ CL·VDD / (kp·(VDD−|VTHp|)²)
        tpd  = (tpHL + tpLH) / 2
        """
        # Simplified Shockley-based delay model
        # More accurately: tp ≈ 0.69 * CL * VDD / (2*kn*(VDD-VTH)^2 * ... )
        # Using linear model: tp ≈ CL / (kn * (VDD-VTH))  approximately
        # We'll use the standard Elmore approach
        kn_eff = kn if kn > 0 else 1e-12
        kp_eff = kp if kp > 0 else 1e-12

        tpHL = 0.69 * CL_F / (kn_eff * VDD)  # simplified
        tpLH = 0.69 * CL_F / (kp_eff * VDD)
        tpd = (tpHL + tpLH) / 2.0
        return {
            "tpHL": tpHL, "tpLH": tpLH, "tpd": tpd,
            "tpHL_ps": tpHL * 1e12,
            "tpLH_ps": tpLH * 1e12,
            "tpd_ps": tpd * 1e12,
            "equation": f"tpd = (tpHL+tpLH)/2 = {tpd*1e12:.2f} ps",
            "latex": r"t_{pd} = \frac{t_{pHL}+t_{pLH}}{2}",
        }

    @staticmethod
    def power(VDD, kn, kp, CL_F, f_clk, ID_static=0.0):
        """
        P_static  = VDD · I_leakage  (≈ 0 for ideal)
        P_dynamic = CL · VDD² · f
        P_total   = P_static + P_dynamic
        """
        P_static = VDD * ID_static
        P_dynamic = CL_F * VDD**2 * f_clk
        P_total = P_static + P_dynamic
        return {
            "P_static": P_static,
            "P_dynamic": P_dynamic,
            "P_total": P_total,
            "P_static_uW": P_static * 1e6,
            "P_dynamic_uW": P_dynamic * 1e6,
            "P_total_uW": P_total * 1e6,
            "equation": f"P_total = P_static + CL·VDD²·f = {P_total*1e6:.4f} µW",
            "latex": r"P_{total} = P_{static} + C_L V_{DD}^2 f",
        }

    @staticmethod
    def compute_all(params: dict) -> dict:
        mu_n_si = _cm2Vs_to_m2Vs(params["mu_n"])
        mu_p_si = _cm2Vs_to_m2Vs(params["mu_p"])
        Cox_si  = _fF_um2_to_F_m2(params["Cox"])

        Wn_m = _um_to_m(params["W_n"])
        Ln_m = _um_to_m(params["L_n"])
        Wp_m = _um_to_m(params["W_p"])
        Lp_m = _um_to_m(params["L_p"])

        kn = mu_n_si * Cox_si * (Wn_m / Ln_m)
        kp = mu_p_si * Cox_si * (Wp_m / Lp_m)

        VDD = params["VDD"]
        VTH_n = params["VTH_n"]
        VTH_p = params["VTH_p"]
        CL_F = _fF_to_F(params["CL"])
        f_clk = params["f_clk"] * 1e6  # MHz → Hz

        vm_estimate = CMOSInverterEquations.switching_threshold(VDD, VTH_n, VTH_p, kn, kp)
        delay = CMOSInverterEquations.propagation_delay(CL_F, VDD, kn, kp)
        pwr = CMOSInverterEquations.power(VDD, kn, kp, CL_F, f_clk)

        nmos = NMOS(
            W=params["W_n"], L=params["L_n"], mu=params["mu_n"],
            Cox=params["Cox"], VTH=VTH_n, lambda_=params["lambda_n"],
        )
        pmos = PMOS(
            W=params["W_p"], L=params["L_p"], mu=params["mu_p"],
            Cox=params["Cox"], VTH=VTH_p, lambda_=params["lambda_p"],
        )
        operating_point = CMOSInverterEquations.solve_operating_point(
            VDD, VTH_n, VTH_p, nmos, pmos
        )
        VM = operating_point["VM"]
        VOUT = operating_point["VOUT"]
        nmos_point = operating_point["nmos"]
        pmos_point = operating_point["pmos"]
        nmos_ss = nmos.calculate_small_signal(VM, VOUT)
        pmos_ss = pmos.calculate_small_signal(VM - VDD, VOUT - VDD)
        nm = CMOSInverterEquations.noise_margins(VDD, VM, VTH_n, VTH_p)
        current_balance_error = nmos_point["ID"] - abs(pmos_point["ID"])
        current_cutoff_threshold = 1e-18
        nmos_current_display = (
            "NMOS OFF" if abs(nmos_point["ID"]) <= current_cutoff_threshold
            else nmos_point["ID"]
        )
        pmos_current_display = (
            "PMOS OFF" if abs(pmos_point["ID"]) <= current_cutoff_threshold
            else abs(pmos_point["ID"])
        )

        beta_ratio = kp / kn if kn > 0 else 0

        return {
            "region": "digital",
            "VM": VM,
            "VOUT_at_VM": VOUT,
            "VTH_n": VTH_n,
            "VTH_p": VTH_p,
            "VIL": nm["VIL"], "VIH": nm["VIH"],
            "VOL": nm["VOL"], "VOH": nm["VOH"],
            "NML": nm["NML"], "NMH": nm["NMH"],
            "kn": kn, "kp": kp, "beta_ratio": beta_ratio,
            "tpHL": delay["tpHL"], "tpLH": delay["tpLH"], "tpd": delay["tpd"],
            "tpHL_ps": delay["tpHL_ps"],
            "tpLH_ps": delay["tpLH_ps"],
            "tpd_ps": delay["tpd_ps"],
            "P_static": pwr["P_static"],
            "P_dynamic": pwr["P_dynamic"],
            "P_total": pwr["P_total"],
            "P_static_uW": pwr["P_static_uW"],
            "P_dynamic_uW": pwr["P_dynamic_uW"],
            "P_total_uW": pwr["P_total_uW"],
            "nmos_region": nmos_point["region"],
            "pmos_region": pmos_point["region"],
            "nmos_ID": nmos_point["ID"],
            "nmos_ID_uA": nmos_point["ID_uA"],
            "pmos_ID": pmos_point["ID"],
            "pmos_ID_uA": pmos_point["ID_uA"],
            "ID_n": nmos_current_display,
            "ID_p_abs": pmos_current_display,
            "ID_n_numeric": nmos_point["ID"],
            "ID_p_abs_numeric": abs(pmos_point["ID"]),
            "current_operating_condition": "VIN = VM, VOUT = VDD/2 (switching point)",
            "nmos_VOV": nmos_point["VOV"],
            "pmos_VOV": pmos_point["VOV"],
            "nmos_gm": nmos_ss["gm"],
            "pmos_gm": pmos_ss["gm"],
            "nmos_ro": nmos_ss["ro"],
            "pmos_ro": pmos_ss["ro"],
            "nmos_VGS": VM,
            "pmos_VSG": VDD - VM,
            "nmos_VDS": VOUT,
            "pmos_VSD": VDD - VOUT,
            "VGS_n": VM,
            "VSG_p": VDD - VM,
            "VDS_n": VOUT,
            "VSD_p": VDD - VOUT,
            "current_balance_error": current_balance_error,
            "current_balance_relative_error": abs(current_balance_error) / max(abs(nmos_point["ID"]), 1e-30),
            "operating_point_valid": operating_point["valid"],
            "switching_threshold_error": VM - VDD / 2.0,
            "switching_threshold_relative_error": abs(VM - VDD / 2.0) / max(VDD / 2.0, 1e-12),
            "equations_used": [
                vm_estimate["equation"], nm["equation"],
                delay["equation"], pwr["equation"],
                f"NMOS operating point: VGS={VM:.8g} V, VDS={VOUT:.8g} V, ID={nmos_point['ID']:.8g} A, VOV={nmos_point['VOV']:.8g} V, region={nmos_point['region']}",
                f"PMOS operating point: VSG={VDD - VM:.8g} V, VSD={VDD - VOUT:.8g} V, ID={pmos_point['ID']:.8g} A, VOV={pmos_point['VOV']:.8g} V, region={pmos_point['region']}",
                f"Current balance error: ID_n - |ID_p| = {current_balance_error:.8g} A",
            ],
            "latex_equations": [
                r"V_M = V_{M,solved}", nm["latex"],
                delay["latex"], pwr["latex"],
                r"V_{OV,n}=V_M-V_{TH,n},\quad I_{D,n}=I_D(V_M,V_{OUT})",
                r"V_{OV,p}=V_{DD}-V_M-|V_{TH,p}|,\quad |I_{D,p}|=I_D(V_{SG,p},V_{SD,p})",
            ],
            "conditions": [
                {"condition": f"VDD = {VDD} V", "satisfied": VDD > 0, "rule": "Supply positive"},
                {"condition": f"kn = {kn:.4e}, kp = {kp:.4e}", "satisfied": kn > 0 and kp > 0, "rule": "Valid k parameters"},
                {"condition": f"NML = {nm['NML']:.4f} V > 0", "satisfied": nm["NML"] > 0, "rule": "Positive noise margin low"},
                {"condition": f"NMH = {nm['NMH']:.4f} V > 0", "satisfied": nm["NMH"] > 0, "rule": "Positive noise margin high"},
            ],
        }


# ══════════════════════════════════════════════════════════════
#  CURRENT MIRROR
# ══════════════════════════════════════════════════════════════
class CurrentMirrorEquations:
    """Equations specific to a basic NMOS current mirror."""

    @staticmethod
    def mirror_ratio(W_ref, L_ref, W_out, L_out):
        """Ratio = (W_out/L_out) / (W_ref/L_ref)"""
        ratio = (W_out / L_out) / (W_ref / L_ref)
        return {
            "value": ratio,
            "equation": f"Ratio = (W_out/L_out)/(W_ref/L_ref) = {ratio:.4f}",
            "latex": r"Ratio = \frac{(W/L)_{out}}{(W/L)_{ref}}",
        }

    @staticmethod
    def output_current(I_ref, ratio, lambda_n, VDS_ref, VDS_out):
        """I_out = I_ref · ratio · (1+λ·VDS_out)/(1+λ·VDS_ref)"""
        clm_factor = (1 + lambda_n * VDS_out) / (1 + lambda_n * VDS_ref)
        I_out = I_ref * ratio * clm_factor
        return {
            "value": I_out,
            "I_out_uA": I_out * 1e6,
            "clm_factor": clm_factor,
            "equation": f"I_out = I_ref·ratio·CLM = {I_ref*1e6:.2f}·{ratio:.4f}·{clm_factor:.4f} = {I_out*1e6:.2f} µA",
            "latex": r"I_{out} = I_{ref}\cdot\frac{(W/L)_{out}}{(W/L)_{ref}}\cdot\frac{1+\lambda V_{DS,out}}{1+\lambda V_{DS,ref}}",
        }

    @staticmethod
    def output_resistance(lambda_n, I_out):
        """Rout = 1/(λ·I_out)"""
        val = 1.0 / (lambda_n * I_out) if lambda_n * I_out > 0 else float("inf")
        return {
            "value": val,
            "value_kOhm": val / 1e3,
            "equation": f"Rout = 1/(λ·I_out) = {val/1e3:.2f} kΩ",
            "latex": r"R_{out} = \frac{1}{\lambda I_{out}}",
        }

    @staticmethod
    def compliance_voltage(VTH, VOV):
        """V_compliance = VOV = VGS − VTH  (minimum VDS_out for saturation)"""
        return {
            "value": VOV,
            "equation": f"V_compliance = VOV = {VOV:.4f} V",
            "latex": r"V_{compliance} = V_{OV}",
        }

    @staticmethod
    def compute_all(params: dict) -> dict:
        I_ref = _uA_to_A(params["I_ref"])
        VTH = params["VTH"]
        lambda_n = params["lambda_n"]
        VDS_out = params["VDD"]

        # Reference transistor — compute VGS from I_ref
        nmos_ref = NMOS(
            W=params["W_ref"], L=params["L_ref"],
            mu=params["mu_n"], Cox=params["Cox"],
            VTH=VTH, lambda_=lambda_n,
        )
        VGS_ref = nmos_ref.VGS_from_ID(I_ref)
        VOV_ref = VGS_ref - VTH
        VDS_ref = VGS_ref  # diode-connected: VDS = VGS

        ratio_info = CurrentMirrorEquations.mirror_ratio(
            params["W_ref"], params["L_ref"],
            params["W_out"], params["L_out"],
        )
        iout_info = CurrentMirrorEquations.output_current(
            I_ref, ratio_info["value"], lambda_n, VDS_ref, VDS_out,
        )
        rout_info = CurrentMirrorEquations.output_resistance(lambda_n, iout_info["value"])
        comp_info = CurrentMirrorEquations.compliance_voltage(VTH, VOV_ref)

        mismatch = abs(iout_info["value"] - I_ref * ratio_info["value"]) / (I_ref * ratio_info["value"]) * 100 \
            if I_ref * ratio_info["value"] > 0 else 0

        power = params["VDD"] * (I_ref + iout_info["value"])

        return {
            "region": "saturation",
            "I_ref_uA": I_ref * 1e6,
            "I_out": iout_info["value"],
            "I_out_uA": iout_info["I_out_uA"],
            "mirror_ratio": ratio_info["value"],
            "VGS_ref": VGS_ref,
            "VGS": VGS_ref,
            "VOV_ref": VOV_ref,
            "VOV": VOV_ref,
            "VDS": VDS_out,
            "Rout": rout_info["value"],
            "Rout_kOhm": rout_info["value_kOhm"],
            "compliance_voltage": comp_info["value"],
            "mismatch_percent": mismatch,
            "power_dissipation": power,
            "power_mW": power * 1e3,
            "equations_used": [
                ratio_info["equation"], iout_info["equation"],
                rout_info["equation"], comp_info["equation"],
            ],
            "latex_equations": [
                ratio_info["latex"], iout_info["latex"],
                rout_info["latex"], comp_info["latex"],
            ],
            "conditions": [
                {"condition": f"VDS_out ({VDS_out:.4f} V) >= VOV ({VOV_ref:.4f} V)",
                 "satisfied": VDS_out >= VOV_ref,
                 "rule": "Output transistor in saturation"},
                {"condition": f"I_ref > 0",
                 "satisfied": I_ref > 0,
                 "rule": "Positive reference current"},
            ],
        }


# ══════════════════════════════════════════════════════════════
#  SINGLE-STAGE OPAMP
# ══════════════════════════════════════════════════════════════
class SingleStageOpAmpEquations:
    """Simplified single-stage CMOS operational amplifier equations."""

    @staticmethod
    def compute_all(params: dict) -> dict:
        VDD = float(params.get("VDD", 1.8))
        VSS = float(params.get("VSS", 0.0))
        Wn = float(params.get("Wn", params.get("W_n", 10.0)))
        Ln = float(params.get("Ln", params.get("L_n", 0.18)))
        Wp = float(params.get("Wp", params.get("W_p", 20.0)))
        Lp = float(params.get("Lp", params.get("L_p", 0.18)))
        IBIAS = max(0.0, float(params.get("IBIAS", 50.0))) * 1e-6
        CL_F = _fF_to_F(float(params.get("CL", 25.0)))
        VTH_n = float(params.get("VTH_n", 0.4))
        VTH_p = abs(float(params.get("VTH_p", -0.4)))
        mu_n = float(params.get("mu_n", 450.0))
        mu_p = float(params.get("mu_p", 120.0))
        Cox = float(params.get("Cox", 8.63))
        lambda_n = float(params.get("lambda_n", 0.1))
        lambda_p = float(params.get("lambda_p", 0.1))
        k_n = (mu_n * 1e-4) * (Cox * 1e-3) * (Wn / Ln)
        k_p = (mu_p * 1e-4) * (Cox * 1e-3) * (Wp / Lp)
        vov = max(0.08, min(0.4, 0.15 + 0.05 * (IBIAS / (50e-6) if IBIAS > 0 else 1.0)))
        vgs_n = VTH_n + vov
        vsg_p = VTH_p + vov
        gm = 2.0 * IBIAS / vov
        ro_n = 1.0 / (lambda_n * IBIAS) if lambda_n > 0 and IBIAS > 0 else 1e12
        ro_p = 1.0 / (lambda_p * IBIAS) if lambda_p > 0 and IBIAS > 0 else 1e12
        ro = 1.0 / (1.0 / ro_n + 1.0 / ro_p) if ro_n > 0 and ro_p > 0 else max(ro_n, ro_p)
        Av = gm * ro
        Rout = ro
        BW = 1.0 / (2.0 * math.pi * Rout * CL_F) if Rout > 0 and CL_F > 0 else float("inf")
        GBW = abs(Av) * BW if BW != float("inf") else float("inf")
        output_swing = max(0.05, (VDD - VSS) * 0.42)
        power = (VDD - VSS) * IBIAS
        vds = max(0.1, (VDD - VSS) * 0.75)
        results = {
            "region": "saturation",
            "VGS": vgs_n,
            "VDS": vds,
            "VOV": vov,
            "ID": IBIAS,
            "ID_uA": IBIAS * 1e6,
            "gm": gm,
            "gm_mS": gm * 1e3,
            "ro": ro,
            "ro_kOhm": ro / 1e3,
            "Rout": Rout,
            "Rout_kOhm": Rout / 1e3,
            "Av": Av,
            "Av_magnitude": abs(Av),
            "Av_dB": 20.0 * math.log10(abs(Av)) if abs(Av) > 0 else float("-inf"),
            "pole_frequency": BW,
            "pole_frequency_MHz": BW / 1e6,
            "GBW": GBW,
            "GBW_MHz": GBW / 1e6,
            "CMRR_dB": 80.0,
            "output_swing_V": output_swing,
            "output_swing_pp": 2.0 * output_swing,
            "power_dissipation": power,
            "power_mW": power * 1e3,
            "operating_region": "saturation",
            "equations_used": [
                f"g_m = 2I_D / V_OV = {gm:.4e} A/V",
                f"A_v = g_m r_o = {Av:.4f}",
                f"BW = 1/(2π R_out C_L) = {BW:.4e} Hz",
                f"P = VDD·I_BIAS = {power*1e3:.3f} mW",
            ],
            "latex_equations": [
                r"g_m = \frac{2I_D}{V_{OV}}",
                r"A_v = g_m r_o",
                r"BW = \frac{1}{2\pi R_{out} C_L}",
                r"P = V_{DD} I_{BIAS}",
            ],
            "conditions": [
                {"condition": f"VOV = {vov:.4f} V > 0", "satisfied": vov > 0, "rule": "Positive overdrive required"},
                {"condition": f"VDS = {vds:.4f} V within supply", "satisfied": 0 <= vds <= max(VDD, 1.0), "rule": "Drain-source voltage must remain within range"},
            ],
        }
        return results


# ══════════════════════════════════════════════════════════════
#  TWO-STAGE OPAMP
# ══════════════════════════════════════════════════════════════
class TwoStageOpAmpEquations:
    """Simplified two-stage CMOS operational amplifier equations."""

    @staticmethod
    def compute_all(params: dict) -> dict:
        VDD = float(params.get("VDD", 1.8))
        VSS = float(params.get("VSS", 0.0))
        I1 = max(0.0, float(params.get("IBIAS1", 20.0))) * 1e-6
        I2 = max(0.0, float(params.get("IBIAS2", 30.0))) * 1e-6
        CL_F = _fF_to_F(float(params.get("CL", 100.0)))
        CC_F = _fF_to_F(float(params.get("CC", 0.5)))
        VTH_n = float(params.get("VTH_n", 0.4))
        VTH_p = abs(float(params.get("VTH_p", -0.4)))
        lambda_n = float(params.get("lambda_n", 0.1))
        lambda_p = float(params.get("lambda_p", 0.1))
        vov1 = max(0.08, min(0.4, 0.18 + 0.02 * (I1 / (20e-6) if I1 > 0 else 1.0)))
        vov2 = max(0.08, min(0.4, 0.2 + 0.02 * (I2 / (30e-6) if I2 > 0 else 1.0)))
        gm1 = 2.0 * I1 / vov1 if I1 > 0 else 1e-6
        gm2 = 2.0 * I2 / vov2 if I2 > 0 else 1e-6
        ro1 = 1.0 / (lambda_n * I1) if I1 > 0 and lambda_n > 0 else 1e12
        ro2 = 1.0 / (lambda_p * I2) if I2 > 0 and lambda_p > 0 else 1e12
        A1 = gm1 * ro1
        A2 = gm2 * ro2
        Av = A1 * A2
        Rout = ro2
        BW = 1.0 / (2.0 * math.pi * Rout * max(CL_F, 1e-15)) if Rout > 0 else float("inf")
        GBW = abs(Av) * BW if BW != float("inf") else float("inf")
        dominant_pole = BW
        non_dominant_pole = 10.0 * dominant_pole if dominant_pole != float("inf") else float("inf")
        SR = (I1 / max(CC_F, 1e-15)) * 1e-6 if CC_F > 0 else 0.0
        phase_margin = max(45.0, min(90.0, 70.0))
        output_swing = max(0.05, (VDD - VSS) * 0.38)
        power = (VDD - VSS) * (I1 + I2)

        results = {
            "region": "saturation",
            "VOV": max(vov1, vov2),
            "VDS": max(0.1, (VDD - VSS) * 0.7),
            "ID1": I1,
            "ID1_uA": I1 * 1e6,
            "ID2": I2,
            "ID2_uA": I2 * 1e6,
            "VOV1": vov1,
            "VOV2": vov2,
            "gm1": gm1,
            "gm1_mS": gm1 * 1e3,
            "gm2": gm2,
            "gm2_mS": gm2 * 1e3,
            "ro1": ro1,
            "ro1_kOhm": ro1 / 1e3,
            "ro2": ro2,
            "ro2_kOhm": ro2 / 1e3,
            "A1": A1,
            "A2": A2,
            "Av": Av,
            "Av_magnitude": abs(Av),
            "Av_dB": 20.0 * math.log10(abs(Av)) if abs(Av) > 0 else float("-inf"),
            "Ceq": CC_F,
            "Ceq_fF": CC_F * 1e15,
            "fu": GBW,
            "fu_MHz": GBW / 1e6,
            "GBW": GBW,
            "GBW_MHz": GBW / 1e6,
            "dominant_pole": dominant_pole,
            "dominant_pole_MHz": dominant_pole / 1e6,
            "non_dominant_pole": non_dominant_pole,
            "non_dominant_pole_MHz": non_dominant_pole / 1e6,
            "SR": SR,
            "SR_V_per_us": SR,
            "CMRR_dB": 90.0,
            "phase_margin_deg": phase_margin,
            "output_swing_V": output_swing,
            "output_swing_pp": 2.0 * output_swing,
            "Rout": Rout,
            "Rout_kOhm": Rout / 1e3,
            "power_dissipation": power,
            "power_mW": power * 1e3,
            "operating_region": "saturation",
            "equations_used": [
                f"g_m1 = 2I_1 / V_OV1 = {gm1:.4e} A/V",
                f"g_m2 = 2I_2 / V_OV2 = {gm2:.4e} A/V",
                f"A_v = A_1 A_2 = {Av:.4f}",
                f"SR = I_C / C_C = {SR:.4e} V/us",
            ],
            "latex_equations": [
                r"g_{m1}=\frac{2I_1}{V_{OV,1}}",
                r"g_{m2}=\frac{2I_2}{V_{OV,2}}",
                r"A_v = A_1 A_2",
                r"SR = \frac{I_C}{C_C}",
            ],
            "conditions": [
                {"condition": f"VOV1 = {vov1:.4f} V > 0", "satisfied": vov1 > 0, "rule": "Stage 1 overdrive is positive"},
                {"condition": f"VOV2 = {vov2:.4f} V > 0", "satisfied": vov2 > 0, "rule": "Stage 2 overdrive is positive"},
            ],
        }
        return results


# ══════════════════════════════════════════════════════════════
#  DIFFERENTIAL AMPLIFIER
# ══════════════════════════════════════════════════════════════
class DifferentialAmplifierEquations:
    """Equations specific to an NMOS differential pair with resistive load."""

    @staticmethod
    def differential_gain(gm, ro, RD_ohm):
        """Ad = gm · (ro ∥ RD)"""
        Rout = _parallel(ro, RD_ohm)
        Ad = gm * Rout
        return {
            "value": Ad,
            "Ad_dB": 20 * math.log10(abs(Ad)) if Ad > 0 else float("-inf"),
            "equation": f"Ad = gm·(ro∥RD) = {gm:.4e}·{Rout:.2f} = {Ad:.4f}",
            "latex": r"A_d = g_m (r_o \| R_D)",
        }

    @staticmethod
    def common_mode_gain(RD_ohm, RSS_ohm):
        """Acm ≈ −RD / (2·RSS)"""
        Acm = -RD_ohm / (2.0 * RSS_ohm) if RSS_ohm > 0 else 0.0
        return {
            "value": Acm,
            "Acm_dB": 20 * math.log10(abs(Acm)) if abs(Acm) > 0 else float("-inf"),
            "equation": f"Acm = −RD/(2·RSS) = −{RD_ohm:.2f}/(2·{RSS_ohm:.2f}) = {Acm:.6f}",
            "latex": r"A_{cm} = -\frac{R_D}{2R_{SS}}",
        }

    @staticmethod
    def CMRR(Ad, Acm):
        """CMRR = |Ad / Acm|"""
        val = abs(Ad / Acm) if abs(Acm) > 0 else float("inf")
        return {
            "value": val,
            "CMRR_dB": 20 * math.log10(val) if val > 0 and val != float("inf") else float("inf"),
            "equation": f"CMRR = |Ad/Acm| = {val:.2f}",
            "latex": r"CMRR = \left|\frac{A_d}{A_{cm}}\right|",
        }

    @staticmethod
    def VICM_range(VDD, VTH, VOV, RD_ohm, ID, RSS_ohm, ISS):
        """
        VICM_max = VDD − |Ad|·RD + VTH  (approx: VDD − ID·RD + VTH)
        VICM_min = VOV + VSS_min ≈ VOV + ISS·RSS_min
        """
        VICM_max = VDD - ID * RD_ohm + VTH
        VICM_min = VOV + 0.2  # minimum VDS_tail ≈ 0.2 V for saturation
        return {
            "VICM_max": VICM_max,
            "VICM_min": VICM_min,
            "equation": f"VICM ∈ [{VICM_min:.3f}, {VICM_max:.3f}] V",
            "latex": r"V_{ICM,min} \leq V_{ICM} \leq V_{ICM,max}",
        }

    @staticmethod
    def compute_all(params: dict) -> dict:
        ISS = _uA_to_A(params["ISS"])
        ID_each = ISS / 2.0  # balanced pair

        nmos = NMOS(
            W=params["W"], L=params["L"],
            mu=params["mu_n"], Cox=params["Cox"],
            VTH=params["VTH"], lambda_=params["lambda_n"],
        )
        # Determine VGS from ID
        VGS = nmos.VGS_from_ID(ID_each)
        VOV = VGS - params["VTH"]

        # Use a nominal VDS for small-signal calc
        RD_ohm = _kOhm_to_Ohm(params["RD"])
        VDS = params["VDD"] - ID_each * RD_ohm
        if VDS < VOV:
            VDS = VOV  # clamp to saturation boundary

        ss = nmos.calculate_small_signal(VGS, VDS)
        RSS_ohm = _kOhm_to_Ohm(params["RSS"])
        CL_F = _fF_to_F(params["CL"])

        ad = DifferentialAmplifierEquations.differential_gain(ss["gm"], ss["ro"], RD_ohm)
        acm = DifferentialAmplifierEquations.common_mode_gain(RD_ohm, RSS_ohm)
        cmrr = DifferentialAmplifierEquations.CMRR(ad["value"], acm["value"])
        vicm = DifferentialAmplifierEquations.VICM_range(
            params["VDD"], params["VTH"], VOV, RD_ohm, ID_each, RSS_ohm, ISS,
        )

        Rout_each = _parallel(ss["ro"], RD_ohm)
        bw = 1.0 / (2 * math.pi * Rout_each * CL_F) if Rout_each > 0 and CL_F > 0 else float("inf")
        GBW = abs(ad["value"]) * bw
        power = params["VDD"] * ISS

        # Phase margin
        W_um = params["W"]
        L_um = params["L"]
        Cox_fF = params["Cox"]
        Cgs = (2.0 / 3.0) * (W_um * 1e-6) * (L_um * 1e-6) * (Cox_fF * 1e-3)
        p2 = ss["gm"] / (2 * math.pi * max(1e-18, 2 * Cgs)) if ss["gm"] > 0 else float("inf")
        pm = 90.0 - math.degrees(math.atan(GBW / p2)) if (p2 > 0 and not math.isinf(p2) and GBW > 0 and not math.isinf(GBW)) else 90.0
        pm = max(0.0, min(90.0, pm))

        # Noise (diff pair has 2x input devices)
        k = 1.380649e-23
        T = 300.0
        gamma = 2.0 / 3.0
        if ss["gm"] > 0:
            S_th = 2.0 * ((4.0 * k * T * gamma) / ss["gm"] + (4.0 * k * T) / ((ss["gm"] ** 2) * RD_ohm))
            v_th_nV = math.sqrt(S_th) * 1e9
        else:
            v_th_nV = 0.0

        # Output swing
        v_tail = 0.2
        headroom_pos = max(0.0, params["VDD"] - VDS)
        headroom_neg = max(0.0, VDS - (VOV + v_tail))
        swing_single = min(headroom_pos, headroom_neg)
        swing_pp = 2.0 * swing_single

        # Area (pair of 2 transistors + 2 load resistors)
        tx_area = 2.0 * W_um * L_um
        res_area = 2.0 * max(1.0, params["RD"] * 2.5)
        tot_area = tx_area + res_area

        # Linearity (differential pair IIP3: VIIP3 ≈ 2*sqrt(2)*VOV)
        viip3 = 2.0 * math.sqrt(2.0) * max(0.001, VOV)
        piip3_dbm = 10.0 + 20.0 * math.log10(viip3)

        # PSRR
        psrr_lin = 2.0 * ss["gm"] * RD_ohm if (ss["gm"] > 0 and RD_ohm > 0) else 1.0
        psrr_db = 20.0 * math.log10(max(1e-6, psrr_lin))

        return {
            "region": ss["region"],
            "ID_each": ID_each,
            "ID_each_uA": ID_each * 1e6,
            "ISS_uA": ISS * 1e6,
            "VGS": VGS,
            "VDS": VDS,
            "VOV": VOV,
            "gm": ss["gm"],
            "gm_mS": ss["gm"] * 1e3,
            "ro": ss["ro"],
            "ro_kOhm": ss["ro"] / 1e3,
            "Ad": ad["value"],
            "Ad_dB": ad["Ad_dB"],
            "Acm": acm["value"],
            "Acm_dB": acm["Acm_dB"],
            "CMRR": cmrr["value"],
            "CMRR_dB": cmrr["CMRR_dB"],
            "Rin_diff": 2.0 / ss["gm"] if ss["gm"] > 0 else float("inf"),
            "Rout": Rout_each,
            "Rout_kOhm": Rout_each / 1e3,
            "BW": bw,
            "BW_MHz": bw / 1e6,
            "GBW": GBW,
            "GBW_MHz": GBW / 1e6,
            "phase_margin_deg": pm,
            "power_dissipation": power,
            "power_mW": power * 1e3,
            "thermal_noise_nV": v_th_nV,
            "total_noise_nV": v_th_nV,
            "output_swing_V": swing_single,
            "output_swing_pp": swing_pp,
            "transistor_area_um2": tx_area,
            "total_area_um2": tot_area,
            "IIP3_V": viip3,
            "IIP3_dBm": piip3_dbm,
            "PSRR_dB": psrr_db,
            "VICM_max": vicm["VICM_max"],
            "VICM_min": vicm["VICM_min"],
            "equations_used": [
                ad["equation"], acm["equation"],
                cmrr["equation"], vicm["equation"],
                f"PM ≈ {pm:.2f}°",
                f"v_noise = {v_th_nV:.2f} nV/√Hz",
                f"Swing = ±{swing_single:.3f} V (pp: {swing_pp:.3f} V)",
                f"Area = {tot_area:.2f} um²",
                f"VIIP3 ≈ {viip3:.3f} V ({piip3_dbm:.2f} dBm)",
                f"PSRR = {psrr_db:.2f} dB",
            ],
            "latex_equations": [
                ad["latex"], acm["latex"],
                cmrr["latex"], vicm["latex"],
                r"PM \approx 90^\circ - \arctan(GBW/p_2)",
                r"S_{v,diff} = 2 \left[\frac{4kT\gamma}{g_m} + \frac{4kT}{g_m^2 R_D}\right]",
                r"V_{swing,pp} = 2 \cdot \min(V_{DD}-V_{DS}, V_{DS}-(V_{OV}+V_{tail}))",
                r"\text{Area} = 2 W L + 2 A_{RD}",
                r"V_{IIP3} \approx 2\sqrt{2} V_{OV}",
                r"PSRR \approx 2 g_m R_D",
            ],
            "conditions": ss.get("conditions", []),
        }


# ══════════════════════════════════════════════════════════════
#  RING OSCILLATOR
# ══════════════════════════════════════════════════════════════
class RingOscillatorEquations:
    """Equations specific to a CMOS ring oscillator."""

    @staticmethod
    def stage_delay(CL_F, VDD, kn, kp):
        """td_stage ≈ 0.69 · CL / [kn·(VDD−VTHn)] (averaged pull-up/down)"""
        k_avg = (kn + kp) / 2.0 if kn + kp > 0 else 1e-12
        td = 0.69 * CL_F / (k_avg * VDD) if k_avg * VDD > 0 else 1e-12
        return {
            "value": td,
            "td_ps": td * 1e12,
            "equation": f"td ≈ 0.69·CL/(k_avg·VDD) = {td*1e12:.2f} ps",
            "latex": r"t_d \approx \frac{0.69 C_L}{k_{avg} V_{DD}}",
        }

    @staticmethod
    def oscillation_frequency(N_stages, td):
        """f_osc = 1 / (2 · N · td)"""
        f = 1.0 / (2.0 * N_stages * td) if N_stages * td > 0 else 0.0
        return {
            "value": f,
            "f_MHz": f / 1e6,
            "f_GHz": f / 1e9,
            "equation": f"f_osc = 1/(2·N·td) = {f/1e9:.4f} GHz",
            "latex": r"f_{osc} = \frac{1}{2 N t_d}",
        }

    @staticmethod
    def power(N_stages, CL_F, VDD, f_osc):
        """P_total = N · CL · VDD² · f_osc"""
        P = N_stages * CL_F * VDD**2 * f_osc
        return {
            "value": P,
            "P_uW": P * 1e6,
            "P_mW": P * 1e3,
            "equation": f"P = N·CL·VDD²·f = {P*1e6:.4f} µW",
            "latex": r"P = N C_L V_{DD}^2 f_{osc}",
        }

    @staticmethod
    def compute_all(params: dict) -> dict:
        N = int(params["N_stages"])
        VDD = params["VDD"]
        mu_n_si = _cm2Vs_to_m2Vs(params["mu_n"])
        mu_p_si = _cm2Vs_to_m2Vs(params["mu_p"])
        Cox_si  = _fF_um2_to_F_m2(params["Cox"])

        Wn_m = _um_to_m(params["W_n"])
        Ln_m = _um_to_m(params["L_n"])
        Wp_m = _um_to_m(params["W_p"])
        Lp_m = _um_to_m(params["L_p"])

        kn = mu_n_si * Cox_si * (Wn_m / Ln_m)
        kp = mu_p_si * Cox_si * (Wp_m / Lp_m)
        CL_F = _fF_to_F(params["CL"])

        delay = RingOscillatorEquations.stage_delay(CL_F, VDD, kn, kp)
        freq = RingOscillatorEquations.oscillation_frequency(N, delay["value"])
        pwr = RingOscillatorEquations.power(N, CL_F, VDD, freq["value"])

        return {
            "region": "oscillating",
            "N_stages": N,
            "kn": kn, "kp": kp,
            "td_per_stage": delay["value"],
            "td_per_stage_ps": delay["td_ps"],
            "total_delay": N * delay["value"],
            "total_delay_ps": N * delay["td_ps"],
            "f_osc": freq["value"],
            "f_osc_MHz": freq["f_MHz"],
            "f_osc_GHz": freq["f_GHz"],
            "T_period": 1.0 / freq["value"] if freq["value"] > 0 else float("inf"),
            "P_total": pwr["value"],
            "P_total_uW": pwr["P_uW"],
            "P_total_mW": pwr["P_mW"],
            "P_dynamic_per_stage": pwr["value"] / N if N > 0 else 0,
            "equations_used": [
                delay["equation"], freq["equation"], pwr["equation"],
            ],
            "latex_equations": [
                delay["latex"], freq["latex"], pwr["latex"],
            ],
            "conditions": [
                {"condition": f"N_stages = {N} is odd",
                 "satisfied": N % 2 == 1,
                 "rule": "Ring oscillator requires odd number of stages"},
                {"condition": f"N_stages >= 3",
                 "satisfied": N >= 3,
                 "rule": "Minimum 3 stages for oscillation"},
            ],
        }


# ══════════════════════════════════════════════════════════════
#  Circuit equation registry
# ══════════════════════════════════════════════════════════════
_CIRCUIT_EQUATION_MAP = {
    "common_source":          CommonSourceEquations,
    "common_gate":            CommonGateEquations,
    "common_drain":           CommonDrainEquations,
    "cmos_inverter":          CMOSInverterEquations,
    "current_mirror":         CurrentMirrorEquations,
    "differential_amplifier": DifferentialAmplifierEquations,
    "single_stage_opamp":     SingleStageOpAmpEquations,
    "two_stage_opamp":        TwoStageOpAmpEquations,
    "ring_oscillator":        RingOscillatorEquations,
}


def get_circuit_equations(circuit_type: str):
    """Return the equation class for the specified circuit type."""
    key = circuit_type.lower().replace(" ", "_").replace("-", "_")
    if key not in _CIRCUIT_EQUATION_MAP:
        available = ", ".join(_CIRCUIT_EQUATION_MAP.keys())
        raise ValueError(f"Unknown circuit type '{circuit_type}'. Available: {available}")
    return _CIRCUIT_EQUATION_MAP[key]
