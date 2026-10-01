"""
Synthetic training-data generator.

Generates labelled data by sweeping device/circuit parameters
through the physics engine.  This data is used to train and validate
ML models — but crucially, the physics equations are the ground truth.
"""

from __future__ import annotations
import numpy as np
import json
import os
from typing import List, Dict

# Add project root to path
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from equations.circuit_equations import get_circuit_equations
from config.circuit_configs import CIRCUIT_CONFIGS


class DataGenerator:
    """Generate physics-based training data for any supported circuit."""

    def __init__(self, circuit_type: str, n_samples: int = 5000, seed: int = 42):
        self.circuit_type = circuit_type.lower().replace(" ", "_").replace("-", "_")
        self.n_samples = n_samples
        self.rng = np.random.default_rng(seed)
        self.config = CIRCUIT_CONFIGS[self.circuit_type]
        self.eq_class = get_circuit_equations(self.circuit_type)

    def _sample_params(self) -> Dict[str, float]:
        """Sample random parameters within configured ranges."""
        params = {}
        input_params = self.config["input_parameters"]
        for pname, pinfo in input_params.items():
            default = pinfo["default"]
            # Generate within ±50% of default (clamped to sensible range)
            lo = default * 0.3 if default > 0 else default * 1.7
            hi = default * 1.7 if default > 0 else default * 0.3
            if pname == "N_stages":
                # Must be odd integer >= 3
                val = self.rng.choice([3, 5, 7, 9, 11, 13, 15])
            elif pname in ("VTH_p",):
                # Negative value
                lo, hi = -1.0, -0.1
                val = float(self.rng.uniform(lo, hi))
            elif pname in ("VTH", "VTH_n"):
                lo, hi = 0.15, 0.8
                val = float(self.rng.uniform(lo, hi))
            elif pname in ("VGS",):
                vth = params.get("VTH", params.get("VTH_n", 0.4))
                lo = vth * 0.5
                hi = min(params.get("VDD", 1.8), vth + 1.0)
                val = float(self.rng.uniform(lo, hi))
            elif pname in ("VDS",):
                vov = params.get("VGS", 0.8) - params.get("VTH", 0.4)
                lo = 0.05
                hi = params.get("VDD", 1.8)
                val = float(self.rng.uniform(lo, hi))
            else:
                if lo > hi:
                    lo, hi = hi, lo
                if lo == hi:
                    hi = lo + abs(lo) * 0.1 + 0.01
                val = float(self.rng.uniform(lo, hi))
            params[pname] = val
        return params

    def generate(self) -> Dict[str, np.ndarray]:
        """
        Generate n_samples data points.

        Returns dict with:
            input_data:  np.array  (n_samples, n_input_features)
            output_data: np.array  (n_samples, n_output_features)
            input_names: list of input parameter names
            output_names: list of output parameter names
            raw_records: list of full result dicts (for debugging)
        """
        input_records = []
        output_records = []
        raw_records = []
        failures = 0

        output_names = self.config["output_parameters"]
        input_names = list(self.config["input_parameters"].keys())

        attempts = 0
        max_attempts = self.n_samples * 5

        while len(input_records) < self.n_samples and attempts < max_attempts:
            attempts += 1
            params = self._sample_params()
            try:
                results = self.eq_class.compute_all(params)

                # Skip if any output is NaN or inf
                out_vals = []
                skip = False
                for oname in output_names:
                    v = results.get(oname, 0)
                    if isinstance(v, str):
                        v = 0
                    if isinstance(v, float) and (np.isnan(v) or np.isinf(v)):
                        skip = True
                        break
                    out_vals.append(float(v) if not isinstance(v, str) else 0.0)

                if skip:
                    failures += 1
                    continue

                in_vals = [float(params.get(n, 0)) for n in input_names]
                input_records.append(in_vals)
                output_records.append(out_vals)
                raw_records.append({"params": params, "results": results})

            except Exception:
                failures += 1
                continue

        if len(input_records) == 0:
            raise RuntimeError(
                f"Could not generate any valid data for {self.circuit_type} "
                f"after {max_attempts} attempts."
            )

        return {
            "input_data": np.array(input_records),
            "output_data": np.array(output_records),
            "input_names": input_names,
            "output_names": output_names,
            "n_samples": len(input_records),
            "n_failures": failures,
            "raw_records": raw_records,
        }

    def save(self, data: dict, directory: str = "data/generated"):
        """Save generated data to disk."""
        os.makedirs(directory, exist_ok=True)
        prefix = os.path.join(directory, self.circuit_type)
        np.save(f"{prefix}_inputs.npy", data["input_data"])
        np.save(f"{prefix}_outputs.npy", data["output_data"])
        meta = {
            "circuit_type": self.circuit_type,
            "n_samples": data["n_samples"],
            "n_failures": data["n_failures"],
            "input_names": data["input_names"],
            "output_names": data["output_names"],
        }
        with open(f"{prefix}_meta.json", "w") as f:
            json.dump(meta, f, indent=2)
        return prefix

    @staticmethod
    def load(circuit_type: str, directory: str = "data/generated") -> dict:
        """Load previously saved data."""
        prefix = os.path.join(directory, circuit_type)
        with open(f"{prefix}_meta.json") as f:
            meta = json.load(f)
        return {
            "input_data": np.load(f"{prefix}_inputs.npy"),
            "output_data": np.load(f"{prefix}_outputs.npy"),
            **meta,
        }
