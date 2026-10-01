"""
Technology Database — singleton that discovers and loads all .pm files
from the Technology nodes folder.

Usage:
    from technology.tech_database import TechDatabase
    db = TechDatabase.get_instance()
    nodes = db.list_nodes()           # ["16nm", "22nm", "32nm", "45nm"]
    info  = db.get_node("16nm")       # TechnologyNodeInfo
    meta  = db.list_nodes_meta()      # list of dicts for API
"""

from __future__ import annotations
import os
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any

from technology.ptm_parser import PTMParser, PTMNodeData, DeviceModelParams

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class TechnologyNodeInfo:
    """
    Complete information about a technology node.
    Wraps PTMNodeData with additional metadata.
    """
    node_name: str                      # "16nm"
    node_nm: Optional[float]            # 16.0
    has_model_file: bool = False        # True if a .pm file was found
    ptm_data: Optional[PTMNodeData] = None
    parse_errors: List[str] = field(default_factory=list)
    parse_warnings: List[str] = field(default_factory=list)

    # ── Convenience accessors ──────────────────────────────────────
    @property
    def nominal_vdd(self) -> Optional[float]:
        return self.ptm_data.nominal_vdd if self.ptm_data else None

    @property
    def nmos(self) -> Optional[DeviceModelParams]:
        return self.ptm_data.nmos if self.ptm_data else None

    @property
    def pmos(self) -> Optional[DeviceModelParams]:
        return self.ptm_data.pmos if self.ptm_data else None

    def get_constraint_ranges(self, device_type: str = "NMOS") -> Dict[str, Any]:
        """
        Return technology-specific allowed ranges for key parameters.

        Only values extracted from the .pm file are returned.
        No values are invented.

        Returns a dict of:
          param_name → { "min": float, "max": float, "nominal": float, "unit": str, "source": str }
        """
        if not self.has_model_file or not self.ptm_data:
            return {}

        dev_type = device_type.upper()
        dev = self.nmos if dev_type == "NMOS" else self.pmos
        if dev is None:
            return {}

        ranges = {}

        # ── VDD ───────────────────────────────────────────────────
        vdd_nom = self.nominal_vdd
        if vdd_nom is not None:
            vdd_tol = 0.20  # ±20 % from nominal is the typical operating window
            ranges["VDD"] = {
                "nominal": vdd_nom,
                "min": round(vdd_nom * (1 - vdd_tol), 4),
                "max": round(vdd_nom * (1 + vdd_tol), 4),
                "unit": "V",
                "source": f"PTM nominal Vdd = {vdd_nom} V  (±{int(vdd_tol*100)}% window)",
            }

        # ── VTH ───────────────────────────────────────────────────
        if dev.vth0 is not None:
            vth_nom = dev.vth0
            vth_tol = 0.15   # ±15 % process variation window
            vth_min = vth_nom * (1 - vth_tol) if vth_nom >= 0 else vth_nom * (1 + vth_tol)
            vth_max = vth_nom * (1 + vth_tol) if vth_nom >= 0 else vth_nom * (1 - vth_tol)
            ranges["VTH"] = {
                "nominal": round(vth_nom, 5),
                "min": round(min(vth_min, vth_max), 5),
                "max": round(max(vth_min, vth_max), 5),
                "unit": "V",
                "source": f"PTM vth0 = {vth_nom:.5f} V  (±{int(vth_tol*100)}% process variation)",
            }

        # ── Cox ────────────────────────────────────────────────────
        cox = dev.Cox_fF_um2
        if cox is not None:
            cox_tol = 0.10
            ranges["Cox"] = {
                "nominal": round(cox, 4),
                "min": round(cox * (1 - cox_tol), 4),
                "max": round(cox * (1 + cox_tol), 4),
                "unit": "fF/µm²",
                "source": f"Derived: Cox = ε_ox/toxe, toxe = {dev.toxe:.3e} m",
            }

        # ── Electron / Hole mobility ───────────────────────────────
        mu = dev.mu_cm2Vs
        if mu is not None:
            mu_key = "mu_n" if dev_type == "NMOS" else "mu_p"
            mu_tol = 0.15
            ranges[mu_key] = {
                "nominal": round(mu, 2),
                "min": round(mu * (1 - mu_tol), 2),
                "max": round(mu * (1 + mu_tol), 2),
                "unit": "cm²/V·s",
                "source": f"PTM u0 = {dev.u0:.4e} m²/V·s  (×10⁴ → cm²/V·s)",
            }

        # ── Channel length (minimum = node_nm / 1000 µm) ──────────
        if self.node_nm is not None:
            L_min_um = self.node_nm / 1000.0   # nm → µm
            L_max_um = L_min_um * 50.0          # 50× for longer devices
            ranges["L"] = {
                "nominal": round(L_min_um, 5),
                "min": round(L_min_um, 5),
                "max": round(L_max_um, 4),
                "unit": "µm",
                "source": f"Technology node = {self.node_nm} nm → L_min = {L_min_um:.4f} µm",
            }

        return ranges

    def to_api_dict(self) -> Dict[str, Any]:
        """Serialise to a dict safe for JSON API responses."""
        d: Dict[str, Any] = {
            "node_name":     self.node_name,
            "node_nm":       self.node_nm,
            "has_model_file": self.has_model_file,
            "valid":         self.is_valid,
            "parse_errors":  self.parse_errors,
        }
        if self.ptm_data and self.has_model_file:
            d["nominal_vdd"] = self.ptm_data.nominal_vdd

            def _dev_dict(dev: Optional[DeviceModelParams]) -> Optional[Dict]:
                if dev is None:
                    return None
                return {
                    "device_type":  dev.device_type,
                    "vth0":         dev.vth0,
                    "toxe_m":       dev.toxe,
                    "u0_m2Vs":      dev.u0,
                    "mu_cm2Vs":     dev.mu_cm2Vs,
                    "Cox_fF_um2":   dev.Cox_fF_um2,
                    "vsat_ms":      dev.vsat,
                    "rsh_ohm_sq":   dev.rsh,
                    "rdsw_ohm_um":  dev.rdsw,
                    "pclm":         dev.pclm,
                    "eta0":         dev.eta0,
                    "nfactor":      dev.nfactor,
                    "voff":         dev.voff,
                    "model_level":  dev.model_level,
                }

            d["nmos"] = _dev_dict(self.ptm_data.nmos)
            d["pmos"] = _dev_dict(self.ptm_data.pmos)

            nmos_ranges = self.get_constraint_ranges("NMOS")
            pmos_ranges = self.get_constraint_ranges("PMOS")
            d["constraint_ranges"] = {
                "NMOS": nmos_ranges,
                "PMOS": pmos_ranges,
            }

            d["parse_warnings"] = self.parse_warnings

        else:
            d["message"] = (
                "Technology-specific parameter file not available for this node. "
                "Analysis cannot proceed with invented constraint values."
            )
        return d

    @property
    def is_valid(self) -> bool:
        """Whether the file contains the model data required by circuit calculations."""
        return self.has_model_file and not self.parse_errors


# ─────────────────────────────────────────────────────────────────────────────
# Technology Database (singleton)
# ─────────────────────────────────────────────────────────────────────────────

class TechDatabase:
    """
    Singleton technology node database.

    Discovers and parses every .pm file in the technology model folder.

    Call TechDatabase.get_instance() to obtain the singleton.
    """

    _instance: Optional["TechDatabase"] = None

    # Default folder — can be overridden before first call
    TECH_NODES_FOLDER: str = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "Technology nodes",
    )

    def __init__(self):
        self._nodes: Dict[str, TechnologyNodeInfo] = {}
        self._folder_error: Optional[str] = None
        self._loaded = False

    @classmethod
    def get_instance(cls) -> "TechDatabase":
        if cls._instance is None:
            cls._instance = cls()
            cls._instance._load()
        return cls._instance

    @classmethod
    def reset(cls):
        """Force a reload (useful after changing TECH_NODES_FOLDER)."""
        cls._instance = None

    def _load(self):
        """Discover and parse every technology model file without inventing nodes."""
        self._loaded = True
        folder = self.TECH_NODES_FOLDER

        # Discover .pm files
        pm_files: Dict[str, str] = {}   # node_name → filepath
        if not os.path.isdir(folder):
            self._folder_error = (
                f"Technology nodes folder not found: {folder!r}. "
                "Please verify the path exists."
            )
            logger.warning(self._folder_error)
        else:
            for fname in os.listdir(folder):
                if fname.lower().endswith(".pm"):
                    node_name = os.path.splitext(fname)[0].lower()
                    pm_files[node_name] = os.path.join(folder, fname)
            logger.info("Found %d .pm files: %s", len(pm_files), list(pm_files.keys()))

        # Every discovered file becomes one entry; there is no catalog of fake nodes.
        for pm_key, pm_path in pm_files.items():
            ptm_data = PTMParser.parse_file(pm_path)
            self._validate_required_parameters(ptm_data)
            self._nodes[pm_key] = TechnologyNodeInfo(
                node_name=ptm_data.node_name,
                node_nm=ptm_data.node_nm,
                has_model_file=True,
                ptm_data=ptm_data,
                parse_errors=ptm_data.parse_errors,
                parse_warnings=ptm_data.parse_warnings,
            )
            logger.info("Loaded technology model %s (valid=%s)", pm_key,
                        not ptm_data.parse_errors)

    @staticmethod
    def _validate_required_parameters(ptm_data: PTMNodeData) -> None:
        """Record actionable errors instead of allowing incomplete models to fall back."""
        if ptm_data.nominal_vdd is None:
            ptm_data.parse_errors.append("Missing required parameter: nominal_vdd")
        for device_name, device in (("NMOS", ptm_data.nmos), ("PMOS", ptm_data.pmos)):
            if device is None:
                ptm_data.parse_errors.append(f"Missing required {device_name} model")
                continue
            for parameter in ("vth0", "u0", "toxe"):
                if getattr(device, parameter) is None:
                    ptm_data.parse_errors.append(
                        f"Missing required {device_name} parameter: {parameter}"
                    )

    # ── Public API ─────────────────────────────────────────────────
    def list_nodes(self) -> List[str]:
        """Return all known node names."""
        return [info.node_name for info in self._sorted_nodes()]

    def list_nodes_with_files(self) -> List[str]:
        """Return only node names that have a parsed .pm file."""
        return [info.node_name for info in self._sorted_nodes() if info.is_valid]

    def get_node(self, node_name: str) -> Optional[TechnologyNodeInfo]:
        """Look up a node by name (case-insensitive). Returns None if unknown."""
        return self._nodes.get(node_name.lower())

    def list_nodes_meta(self) -> List[Dict[str, Any]]:
        """
        Return a summary list of all nodes for the API / UI dropdown.
        """
        result = []
        for info in self._sorted_nodes():
            result.append({
                "node_name":       info.node_name,
                "node_nm":         info.node_nm,
                "has_model_file":  info.has_model_file,
                "valid":           info.is_valid,
                "nominal_vdd":     info.nominal_vdd,
                "parse_errors":    info.parse_errors,
                "nmos_vth0":       info.nmos.vth0 if info.nmos else None,
                "pmos_vth0":       info.pmos.vth0 if info.pmos else None,
            })
        return result

    def _sorted_nodes(self) -> List[TechnologyNodeInfo]:
        """Order numeric nodes naturally while keeping non-numeric names deterministic."""
        return sorted(
            self._nodes.values(),
            key=lambda info: (info.node_nm is None, info.node_nm or float("inf"), info.node_name.lower()),
        )

    @property
    def folder_error(self) -> Optional[str]:
        return self._folder_error

    @property
    def loaded_count(self) -> int:
        return sum(1 for i in self._nodes.values() if i.is_valid)
