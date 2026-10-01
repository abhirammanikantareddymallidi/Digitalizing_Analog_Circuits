"""
Standalone transistor equation functions.

These are pure-math functions used by the constraint checker and
the physics-informed loss to evaluate equation residuals independently
of the Transistor class.  Each function returns a dict with:
    value, equation_str, latex
"""

from __future__ import annotations
import math


class TransistorEquations:
    """Collection of static transistor-level equations."""

    # ── Drain current ───────────────────────────────────────────
    @staticmethod
    def ID_saturation(beta: float, VOV: float, lambda_: float, VDS: float) -> dict:
        """ID = (β/2)·VOV²·(1+λ·VDS)"""
        val = 0.5 * beta * VOV**2 * (1 + lambda_ * VDS)
        return {
            "value": val,
            "equation": f"ID = (β/2)·VOV²·(1+λ·VDS) = {val:.6e} A",
            "latex": r"I_D=\tfrac{\beta}{2}(V_{GS}-V_{TH})^2(1+\lambda V_{DS})",
        }

    @staticmethod
    def ID_triode(beta: float, VOV: float, VDS: float) -> dict:
        """ID = β·[(VOV)·VDS − VDS²/2]"""
        val = beta * (VOV * VDS - 0.5 * VDS**2)
        return {
            "value": val,
            "equation": f"ID = β·[VOV·VDS − VDS²/2] = {val:.6e} A",
            "latex": r"I_D=\beta\left[(V_{GS}-V_{TH})V_{DS}-\tfrac{V_{DS}^2}{2}\right]",
        }

    # ── Small-signal ────────────────────────────────────────────
    @staticmethod
    def gm_saturation(beta: float, VOV: float) -> dict:
        """gm = β·VOV"""
        val = beta * VOV
        return {
            "value": val,
            "equation": f"gm = β·VOV = {val:.6e} S",
            "latex": r"g_m = \beta \cdot V_{OV}",
        }

    @staticmethod
    def gm_from_ID(ID: float, VOV: float) -> dict:
        """gm = 2·ID / VOV"""
        val = 2.0 * ID / VOV if VOV > 0 else 0.0
        return {
            "value": val,
            "equation": f"gm = 2·ID/VOV = {val:.6e} S",
            "latex": r"g_m = \frac{2I_D}{V_{OV}}",
        }

    @staticmethod
    def ro_saturation(lambda_: float, ID: float) -> dict:
        """ro = 1 / (λ·ID)"""
        denom = lambda_ * ID
        val = 1.0 / denom if denom > 0 else float("inf")
        return {
            "value": val,
            "equation": f"ro = 1/(λ·ID) = {val:.2f} Ω",
            "latex": r"r_o = \frac{1}{\lambda I_D}",
        }

    # ── Overdrive voltage ───────────────────────────────────────
    @staticmethod
    def VOV(VGS: float, VTH: float) -> dict:
        """VOV = VGS − VTH"""
        val = VGS - VTH
        return {
            "value": val,
            "equation": f"VOV = VGS − VTH = {VGS:.4f} − {VTH:.4f} = {val:.4f} V",
            "latex": r"V_{OV} = V_{GS} - V_{TH}",
        }

    # ── VGS from ID (saturation, no CLM) ───────────────────────
    @staticmethod
    def VGS_from_ID(ID: float, beta: float, VTH: float) -> dict:
        """VGS = VTH + sqrt(2·ID / β)"""
        if ID <= 0:
            return {"value": VTH, "equation": "VGS = VTH (cutoff)", "latex": ""}
        VOV = math.sqrt(2.0 * ID / beta)
        val = VTH + VOV
        return {
            "value": val,
            "equation": f"VGS = VTH + √(2·ID/β) = {VTH:.4f} + {VOV:.4f} = {val:.4f} V",
            "latex": r"V_{GS} = V_{TH} + \sqrt{\frac{2I_D}{\beta}}",
        }

    # ── Beta (device transconductance parameter) ───────────────
    @staticmethod
    def beta(kp: float, W: float, L: float) -> dict:
        """β = k'·(W/L)"""
        val = kp * W / L
        return {
            "value": val,
            "equation": f"β = k'·(W/L) = {kp:.6e}·{W/L:.2f} = {val:.6e} A/V²",
            "latex": r"\beta = \mu C_{ox} \frac{W}{L}",
        }

    # ── kp (process transconductance) ──────────────────────────
    @staticmethod
    def kp(mu_si: float, Cox_si: float) -> dict:
        """k' = µ·Cox"""
        val = mu_si * Cox_si
        return {
            "value": val,
            "equation": f"k' = µ·Cox = {mu_si:.6e}·{Cox_si:.6e} = {val:.6e} A/V²",
            "latex": r"k' = \mu C_{ox}",
        }
