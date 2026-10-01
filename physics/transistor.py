"""
Transistor physics model — NMOS and PMOS.

Supports:
  - Operating-region detection from terminal voltages
  - Drain current (ID) calculation per region (cutoff / triode / saturation)
  - Small-signal parameter extraction (gm, ro/gds, VOV)
  - Channel-length modulation (CLM)

All units are SI internally.  Convenience wrappers accept
"lab units" (µm, fF/µm², cm²/V·s, µA, kΩ) and convert automatically.
"""

from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import Optional


# ──────────────────────────────────────────────────────────────
# Operating-region enumeration
# ──────────────────────────────────────────────────────────────
class Region:
    CUTOFF = "cutoff"
    TRIODE = "triode"
    SATURATION = "saturation"


# ──────────────────────────────────────────────────────────────
# Unit conversion helpers (lab ↔ SI)
# ──────────────────────────────────────────────────────────────
def _um_to_m(val):
    """Micrometers → metres."""
    return val * 1e-6

def _cm2Vs_to_m2Vs(val):
    """cm²/V·s → m²/V·s."""
    return val * 1e-4

def _fF_um2_to_F_m2(val):
    """fF/µm² → F/m²."""
    return val * 1e-15 / (1e-6 * 1e-6)  # = val * 1e-3

def _uA_to_A(val):
    """Micro-amps → amps."""
    return val * 1e-6

def _kOhm_to_Ohm(val):
    """kΩ → Ω."""
    return val * 1e3

def _fF_to_F(val):
    """Femto-farads → farads."""
    return val * 1e-15


# ──────────────────────────────────────────────────────────────
# Transistor data class
# ──────────────────────────────────────────────────────────────
@dataclass
class TransistorParams:
    """Container for transistor parameters in *lab* units."""
    transistor_type: str = "NMOS"        # "NMOS" or "PMOS"
    W: float = 10.0                      # µm
    L: float = 0.18                      # µm
    mu: float = 450.0                    # cm²/V·s
    Cox: float = 8.63                    # fF/µm²
    VTH: float = 0.4                     # V  (positive for NMOS, negative for PMOS)
    lambda_: float = 0.1                 # V⁻¹

    @property
    def W_m(self):
        return _um_to_m(self.W)

    @property
    def L_m(self):
        return _um_to_m(self.L)

    @property
    def mu_si(self):
        return _cm2Vs_to_m2Vs(self.mu)

    @property
    def Cox_si(self):
        return _fF_um2_to_F_m2(self.Cox)

    @property
    def kp(self):
        """Process transconductance parameter k' = µ·Cox  (A/V²)."""
        return self.mu_si * self.Cox_si

    @property
    def beta(self):
        """β = k'·(W/L)  (A/V²)."""
        return self.kp * (self.W_m / self.L_m)

    @property
    def WL_ratio(self):
        return self.W / self.L


# ──────────────────────────────────────────────────────────────
# Core Transistor model
# ──────────────────────────────────────────────────────────────
class Transistor:
    """
    Physics-based MOS transistor model.

    Accepts lab-unit parameters and performs all calculations
    using exact equations with region-dependent formulations.
    """

    def __init__(self, params: TransistorParams):
        self.params = params
        self.is_pmos = params.transistor_type.upper() == "PMOS"

    # ── Region detection ────────────────────────────────────────
    def detect_region(self, VGS: float, VDS: float) -> dict:
        """
        Determine operating region from terminal voltages.

        For NMOS:
            Cutoff:     VGS < VTH
            Triode:     VGS >= VTH  AND  VDS < VGS - VTH
            Saturation: VGS >= VTH  AND  VDS >= VGS - VTH

        For PMOS (using |VGS|, |VTH|, |VDS|):
            Same conditions with magnitudes.

        Returns a dict with region name, conditions checked, and pass/fail.
        """
        VTH = self.params.VTH

        if self.is_pmos:
            # For PMOS, work with magnitudes (SGD convention)
            vgs_eff = abs(VGS)
            vds_eff = abs(VDS)
            vth_eff = abs(VTH)
        else:
            vgs_eff = VGS
            vds_eff = VDS
            vth_eff = VTH

        VOV = vgs_eff - vth_eff  # Overdrive voltage

        conditions = []

        if VOV <= 0:
            region = Region.CUTOFF
            conditions.append({
                "condition": f"|VGS| <= |VTH|  →  {vgs_eff:.4f} <= {vth_eff:.4f}",
                "satisfied": True,
                "rule": "Cutoff: gate voltage below threshold",
            })
        elif vds_eff < VOV:
            region = Region.TRIODE
            conditions.append({
                "condition": f"|VGS| > |VTH|  →  {vgs_eff:.4f} > {vth_eff:.4f}",
                "satisfied": True,
                "rule": "Gate overdrive present",
            })
            conditions.append({
                "condition": f"|VDS| < VOV  →  {vds_eff:.4f} < {VOV:.4f}",
                "satisfied": True,
                "rule": "Triode: channel not pinched off",
            })
        else:
            region = Region.SATURATION
            conditions.append({
                "condition": f"|VGS| > |VTH|  →  {vgs_eff:.4f} > {vth_eff:.4f}",
                "satisfied": True,
                "rule": "Gate overdrive present",
            })
            conditions.append({
                "condition": f"|VDS| >= VOV  →  {vds_eff:.4f} >= {VOV:.4f}",
                "satisfied": True,
                "rule": "Saturation: channel pinched off",
            })

        return {
            "region": region,
            "VOV": VOV,
            "conditions": conditions,
        }

    # ── Drain current ───────────────────────────────────────────
    def calculate_ID(self, VGS: float, VDS: float) -> dict:
        """
        Calculate drain current using region-appropriate equation.

        Returns dict with ID (in amps), equation used, region, and explanation.
        """
        region_info = self.detect_region(VGS, VDS)
        region = region_info["region"]
        VOV = region_info["VOV"]
        beta = self.params.beta
        lam = self.params.lambda_

        if self.is_pmos:
            vds_eff = abs(VDS)
        else:
            vds_eff = VDS

        if region == Region.CUTOFF:
            ID = 0.0
            equation_used = "ID = 0  (cutoff)"
            equation_latex = "I_D = 0"

        elif region == Region.TRIODE:
            # ID = β * [(VGS-VTH)*VDS - VDS²/2]
            ID = beta * (VOV * vds_eff - 0.5 * vds_eff ** 2)
            equation_used = (
                f"ID = β·[(VGS−VTH)·VDS − VDS²/2]"
                f" = {beta:.6e}·[{VOV:.4f}·{vds_eff:.4f} − {0.5*vds_eff**2:.4f}]"
                f" = {ID:.6e} A"
            )
            equation_latex = (
                r"I_D = \mu C_{ox} \frac{W}{L} "
                r"\left[(V_{GS}-V_{TH})V_{DS} - \frac{V_{DS}^2}{2}\right]"
            )

        else:  # Saturation
            # ID = (β/2) * VOV² * (1 + λ·VDS)
            ID = 0.5 * beta * VOV ** 2 * (1 + lam * vds_eff)
            equation_used = (
                f"ID = (β/2)·VOV²·(1+λ·VDS)"
                f" = {0.5*beta:.6e}·{VOV**2:.4f}·{1+lam*vds_eff:.4f}"
                f" = {ID:.6e} A"
            )
            equation_latex = (
                r"I_D = \frac{1}{2}\mu C_{ox}\frac{W}{L}"
                r"(V_{GS}-V_{TH})^2 (1+\lambda V_{DS})"
            )

        return {
            "ID": ID,
            "ID_uA": ID * 1e6,
            "region": region,
            "VOV": VOV,
            "equation_used": equation_used,
            "equation_latex": equation_latex,
            "conditions": region_info["conditions"],
        }

    # ── Small-signal parameters ─────────────────────────────────
    def calculate_small_signal(self, VGS: float, VDS: float) -> dict:
        """
        Compute small-signal parameters gm, ro (gds), for the detected region.

        In saturation:
            gm = 2·ID / VOV = β·VOV = sqrt(2·β·ID)
            gds = λ·ID
            ro = 1 / gds

        In triode:
            gm = β·VDS
            gds = β·(VOV − VDS)
            ro = 1 / gds

        In cutoff:
            gm = 0, ro = ∞
        """
        id_info = self.calculate_ID(VGS, VDS)
        ID = id_info["ID"]
        region = id_info["region"]
        VOV = id_info["VOV"]
        beta = self.params.beta
        lam = self.params.lambda_

        if self.is_pmos:
            vds_eff = abs(VDS)
        else:
            vds_eff = VDS

        equations = []

        if region == Region.CUTOFF:
            gm = 0.0
            gds = 0.0
            ro = float("inf")
            equations.append("gm = 0 (cutoff)")
            equations.append("ro = ∞ (cutoff)")

        elif region == Region.TRIODE:
            gm = beta * vds_eff
            gds = beta * (VOV - vds_eff)
            ro = 1.0 / gds if gds > 0 else float("inf")
            equations.append(f"gm = β·VDS = {beta:.6e}·{vds_eff:.4f} = {gm:.6e} S")
            equations.append(f"gds = β·(VOV−VDS) = {beta:.6e}·{VOV - vds_eff:.4f} = {gds:.6e} S")
            equations.append(f"ro = 1/gds = {ro:.2f} Ω")

        else:  # Saturation
            # Differentiate the CLM-inclusive saturation current with respect
            # to VGS: gm = 2*ID/VOV. This keeps gm consistent with the ID
            # equation when (1 + lambda*VDS) is present.
            gm = 2.0 * ID / VOV if VOV > 0 else 0.0
            gds = lam * ID
            ro = 1.0 / gds if gds > 0 else float("inf")
            equations.append(f"gm = 2·ID/VOV = 2·{ID:.6e}/{VOV:.8g} = {gm:.6e} S")
            equations.append(f"gds = λ·ID = {lam}·{ID:.6e} = {gds:.6e} S")
            equations.append(f"ro = 1/gds = {ro:.2f} Ω")

        return {
            **id_info,
            "gm": gm,
            "gm_mS": gm * 1e3,
            "gds": gds,
            "ro": ro,
            "ro_kOhm": ro / 1e3,
            "small_signal_equations": equations,
        }

    # ── VGS from ID (inverse) ──────────────────────────────────
    def VGS_from_ID(self, ID: float, VDS: float = None) -> float:
        """
        Compute VGS required for a given ID in saturation (ignoring CLM for simplicity).

        VGS = VTH + sqrt(2·ID / β)
        """
        beta = self.params.beta
        VTH = self.params.VTH
        if ID <= 0:
            return VTH  # cutoff boundary
        VOV = math.sqrt(2.0 * ID / beta)
        if self.is_pmos:
            return -(abs(VTH) + VOV)
        return VTH + VOV

    # ── Full analysis ───────────────────────────────────────────
    def full_analysis(self, VGS: float, VDS: float) -> dict:
        """Run complete transistor analysis and return all results."""
        ss = self.calculate_small_signal(VGS, VDS)
        return {
            "transistor_type": self.params.transistor_type,
            "W": self.params.W,
            "L": self.params.L,
            "W_L": self.params.WL_ratio,
            "mu": self.params.mu,
            "Cox": self.params.Cox,
            "VTH": self.params.VTH,
            "lambda": self.params.lambda_,
            "kp": self.params.kp,
            "beta": self.params.beta,
            "VGS": VGS,
            "VDS": VDS,
            **ss,
        }


# ──────────────────────────────────────────────────────────────
# Convenience constructors
# ──────────────────────────────────────────────────────────────
def NMOS(W=10.0, L=0.18, mu=450.0, Cox=8.63, VTH=0.4, lambda_=0.1) -> Transistor:
    """Create an NMOS transistor with lab-unit parameters."""
    return Transistor(TransistorParams(
        transistor_type="NMOS", W=W, L=L, mu=mu, Cox=Cox, VTH=VTH, lambda_=lambda_,
    ))


def PMOS(W=10.0, L=0.18, mu=120.0, Cox=8.63, VTH=-0.4, lambda_=0.2) -> Transistor:
    """Create a PMOS transistor with lab-unit parameters."""
    return Transistor(TransistorParams(
        transistor_type="PMOS", W=W, L=L, mu=mu, Cox=Cox, VTH=VTH, lambda_=lambda_,
    ))
