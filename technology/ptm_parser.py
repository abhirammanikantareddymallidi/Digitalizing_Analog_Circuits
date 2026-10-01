"""
PTM (Predictive Technology Model) SPICE .pm file parser.

Reads Berkeley PTM Low Power model files and extracts:
  - Nominal VDD (from comment header)
  - NMOS and PMOS model parameters:
      vth0, u0 (mobility), toxe (oxide thickness), vsat, rsh, rdsw, etc.
  - Derived parameters:
      Cox = ε_ox / toxe  [F/m²] → fF/µm²
      mu_n, mu_p in cm²/V·s

IMPORTANT: Only parameters that are explicitly present in the file are extracted.
No values are invented. If a parameter is absent, it is reported as missing.

PTM file format example:
    * PTM Low Power 16nm Metal Gate / High-K / Strained-Si
    * nominal Vdd = 0.9V
    .model  nmos  nmos  level = 54
    +vth0    = 0.68191         k1      = 0.4  ...
    .model  pmos  pmos  level = 54
    +vth0    = -0.6862         ...
"""

from __future__ import annotations
import re
import os
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple


# Physical constants
EPS_SIO2 = 3.9 * 8.854e-12   # F/m  —  permittivity of SiO2
EPS_SIO2_FF_UM2 = EPS_SIO2 * 1e15 * 1e-12  # → fF/µm² conversion factor


@dataclass
class DeviceModelParams:
    """
    Extracted parameters for one device type (NMOS or PMOS).
    All values are stored as parsed floats in SI or PTM native units.
    Missing parameters are stored as None.
    """
    device_type: str                    # "NMOS" or "PMOS"

    # Threshold voltage
    vth0: Optional[float] = None        # V  (NMOS: positive, PMOS: negative)

    # Gate oxide
    toxe: Optional[float] = None        # m  (effective oxide thickness)
    toxp: Optional[float] = None        # m  (physical oxide thickness)
    epsrox: Optional[float] = None      # relative permittivity

    # Mobility
    u0: Optional[float] = None          # m²/V·s  (raw PTM unit)

    # Saturation velocity
    vsat: Optional[float] = None        # m/s

    # Channel-length modulation proxy (pclm)
    pclm: Optional[float] = None        # unitless

    # Drain-induced barrier lowering
    eta0: Optional[float] = None

    # Source/drain resistance
    rsh: Optional[float] = None         # Ω/sq
    rdsw: Optional[float] = None        # Ω·µm

    # Junction depth
    xj: Optional[float] = None          # m

    # Doping
    ndep: Optional[float] = None        # cm⁻³

    # Off-state current parameters
    nfactor: Optional[float] = None
    voff: Optional[float] = None        # V

    # BSIM4 level
    model_level: Optional[int] = None

    # Raw parameter dict (all parsed key=value pairs)
    raw_params: Dict[str, float] = field(default_factory=dict)

    # --- Derived properties ---

    @property
    def Cox_si(self) -> Optional[float]:
        """Oxide capacitance per unit area in F/m²."""
        if self.toxe is not None and self.toxe > 0:
            eps = (self.epsrox or 3.9) * 8.854e-12
            return eps / self.toxe
        return None

    @property
    def Cox_fF_um2(self) -> Optional[float]:
        """Oxide capacitance per unit area in fF/µm²."""
        cox_si = self.Cox_si
        if cox_si is not None:
            # F/m² → fF/µm²:  ×1e15 (F→fF) × 1e-12 (m²→µm²) = ×1e3
            return cox_si * 1e3
        return None

    @property
    def mu_cm2Vs(self) -> Optional[float]:
        """
        Low-field mobility in cm²/V·s.
        PTM stores u0 in m²/V·s (it is actually in m²/V·s in BSIM4).
        Convert: 1 m²/V·s = 10000 cm²/V·s.
        """
        if self.u0 is not None:
            return self.u0 * 1e4   # m²/V·s → cm²/V·s
        return None


@dataclass
class PTMNodeData:
    """
    Complete data extracted from one PTM .pm file.
    """
    filename: str                           # e.g. "16nm.pm"
    node_name: str                          # e.g. "16nm"
    node_nm: Optional[float] = None         # numeric node size in nm
    nominal_vdd: Optional[float] = None     # V
    nmos: Optional[DeviceModelParams] = None
    pmos: Optional[DeviceModelParams] = None
    parse_errors: list = field(default_factory=list)
    parse_warnings: list = field(default_factory=list)


class PTMParser:
    """
    Parser for Berkeley PTM BSIM4 SPICE model files (.pm extension).

    Usage:
        data = PTMParser.parse_file("/path/to/16nm.pm")
        print(data.nominal_vdd)    # 0.9
        print(data.nmos.vth0)      # 0.68191
        print(data.nmos.Cox_fF_um2)  # derived from toxe
    """

    # Regex: match "nominal Vdd = 0.9V" in comment lines
    _VDD_COMMENT_RE = re.compile(
        r"nominal\s+v[dD][dD]\s*=\s*([\d.]+)\s*[Vv]", re.IGNORECASE
    )

    # Regex: match BSIM model declaration  ".model  nmos  nmos  level = 54"
    _MODEL_DECL_RE = re.compile(
        r"\.model\s+(\S+)\s+(nmos|pmos)\s+.*level\s*=\s*(\d+)",
        re.IGNORECASE
    )

    # Regex: match a parameter assignment block continuation line
    # "+param1 = value1    param2 = value2   ..."
    _PARAM_LINE_RE = re.compile(r"\+\s*(.*)")

    # Regex: split parameter assignments in one line
    _KV_RE = re.compile(r"(\w+)\s*=\s*([+-]?[\d.]+(?:[eE][+-]?\d+)?)")

    @classmethod
    def parse_file(cls, filepath: str) -> PTMNodeData:
        """
        Parse a PTM .pm file and return a PTMNodeData object.

        Args:
            filepath: absolute path to the .pm file

        Returns:
            PTMNodeData with all extracted parameters.
        """
        filename = os.path.basename(filepath)
        node_name = os.path.splitext(filename)[0]   # e.g. "16nm"
        node_nm = cls._parse_node_nm(node_name)

        data = PTMNodeData(
            filename=filename,
            node_name=node_name,
            node_nm=node_nm,
        )

        if not os.path.isfile(filepath):
            data.parse_errors.append(f"File not found: {filepath}")
            return data

        try:
            with open(filepath, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
        except OSError as e:
            data.parse_errors.append(f"Cannot read file: {e}")
            return data

        # Pass 1: find nominal VDD from comment lines
        for line in lines:
            line_s = line.strip()
            if line_s.startswith("*"):
                m = cls._VDD_COMMENT_RE.search(line_s)
                if m:
                    try:
                        data.nominal_vdd = float(m.group(1))
                    except ValueError:
                        data.parse_warnings.append(f"Could not parse VDD from: {line_s}")

        # Pass 2: parse model declarations and parameter blocks
        current_device: Optional[DeviceModelParams] = None
        current_model_key: Optional[str] = None   # "nmos" or "pmos"

        for line in lines:
            line_s = line.strip()

            # Skip pure comment lines
            if line_s.startswith("*") or not line_s:
                continue

            # Check for model declaration
            m_decl = cls._MODEL_DECL_RE.match(line_s)
            if m_decl:
                model_key = m_decl.group(2).lower()   # "nmos" or "pmos"
                level = int(m_decl.group(3))
                dev = DeviceModelParams(
                    device_type=model_key.upper(),
                    model_level=level,
                )
                if model_key == "nmos":
                    data.nmos = dev
                else:
                    data.pmos = dev
                current_device = dev
                current_model_key = model_key
                continue

            # Check for continuation line
            m_param = cls._PARAM_LINE_RE.match(line_s)
            if m_param and current_device is not None:
                param_str = m_param.group(1)
                # Find all key=value pairs in this line
                for kv_match in cls._KV_RE.finditer(param_str):
                    key = kv_match.group(1).lower()
                    try:
                        val = float(kv_match.group(2))
                    except ValueError:
                        continue

                    current_device.raw_params[key] = val

                    # Map to named fields
                    cls._assign_named_field(current_device, key, val)

        return data

    @classmethod
    def _assign_named_field(cls, dev: DeviceModelParams, key: str, val: float):
        """Map a PTM parameter key to a named field on the DeviceModelParams."""
        mapping = {
            "vth0":    "vth0",
            "toxe":    "toxe",
            "toxp":    "toxp",
            "epsrox":  "epsrox",
            "u0":      "u0",
            "vsat":    "vsat",
            "pclm":    "pclm",
            "eta0":    "eta0",
            "rsh":     "rsh",
            "rdsw":    "rdsw",
            "xj":      "xj",
            "ndep":    "ndep",
            "nfactor": "nfactor",
            "voff":    "voff",
        }
        field_name = mapping.get(key)
        if field_name:
            setattr(dev, field_name, val)

    @classmethod
    def _parse_node_nm(cls, node_name: str) -> Optional[float]:
        """
        Extract numeric node size from name like "16nm" → 16.0.
        """
        m = re.match(r"([\d.]+)\s*nm", node_name, re.IGNORECASE)
        if m:
            try:
                return float(m.group(1))
            except ValueError:
                pass
        return None
