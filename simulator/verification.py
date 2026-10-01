"""
Verification Engine — full pipeline consistency check.

Ensures every result is:
  1. Computed from correct equations
  2. Consistent with operating-region conditions
  3. Within valid physical parameter ranges
  4. Cross-checked between ML and physics (if ML is available)
"""

from __future__ import annotations
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from typing import Dict, List, Optional


class VerificationEngine:
    """
    Verify a forward-analysis result for internal consistency.

    If the ML prediction violates physics, the engine will:
      1. Flag the violation
      2. Report which constraint was violated
      3. Recommend using the physics result instead
    """

    @staticmethod
    def verify(analysis_result: dict) -> dict:
        """
        Run verification on a forward-analysis result dict.

        Returns enriched result with verification_report.
        """
        report = {
            "physics_valid": True,
            "ml_consistent": True,
            "issues": [],
            "recommendations": [],
        }

        # ── 1. Check constraint results ─────────────────────────
        checks = analysis_result.get("constraint_checks", [])
        for check in checks:
            if not check["satisfied"]:
                report["issues"].append({
                    "type": "constraint_violation",
                    "name": check["name"],
                    "condition": check["condition"],
                    "severity": check["severity"],
                })
                if check["severity"] == "CRITICAL":
                    report["physics_valid"] = False

        # ── 2. Check ML vs physics consistency ──────────────────
        ml_comparison = analysis_result.get("ml_vs_physics", {})
        if ml_comparison:
            for param_name, comp in ml_comparison.items():
                if not comp.get("match", True):
                    report["ml_consistent"] = False
                    report["issues"].append({
                        "type": "ml_physics_mismatch",
                        "parameter": param_name,
                        "physics_value": comp["physics"],
                        "ml_value": comp["ml"],
                        "error_percent": comp["error_percent"],
                    })
                    report["recommendations"].append(
                        f"ML prediction for {param_name} deviates {comp['error_percent']:.1f}% "
                        f"from physics. Using physics value ({comp['physics']:.4e}) instead."
                    )

        # ── 3. Region consistency ───────────────────────────────
        region_conditions = analysis_result.get("region_conditions", [])
        for cond in region_conditions:
            if not cond.get("satisfied", True):
                report["physics_valid"] = False
                report["issues"].append({
                    "type": "region_inconsistency",
                    "condition": cond["condition"],
                    "rule": cond.get("rule", ""),
                })

        # ── 4. Final verdict ────────────────────────────────────
        if report["physics_valid"] and report["ml_consistent"]:
            report["verdict"] = "VERIFIED — All physics constraints satisfied"
            report["confidence"] = "HIGH"
        elif report["physics_valid"] and not report["ml_consistent"]:
            report["verdict"] = (
                "PARTIALLY VERIFIED — Physics valid but ML prediction differs. "
                "Using physics-computed values."
            )
            report["confidence"] = "MEDIUM"
        else:
            report["verdict"] = (
                "VERIFICATION FAILED — Physics constraint violations detected. "
                "Results may be unreliable."
            )
            report["confidence"] = "LOW"
            report["recommendations"].append(
                "Review input parameters and ensure the transistor is biased correctly."
            )

        return report

    @staticmethod
    def verify_ml_prediction(
        ml_prediction: dict,
        physics_results: dict,
        tolerance_pct: float = 10.0,
    ) -> dict:
        """
        Directly compare an ML prediction against physics ground truth.

        Any parameter deviating more than tolerance_pct is flagged as invalid.
        The physics value is used as the correction.

        Returns:
            dict with corrected values, flags, and explanation.
        """
        corrected = {}
        flags = []
        all_valid = True

        for key in ml_prediction:
            ml_val = ml_prediction[key]
            phys_val = physics_results.get(key)

            if phys_val is None or isinstance(phys_val, str):
                corrected[key] = ml_val
                continue

            try:
                ml_f = float(ml_val)
                phys_f = float(phys_val)
            except (TypeError, ValueError):
                corrected[key] = ml_val
                continue

            if abs(phys_f) > 1e-12:
                error = abs(ml_f - phys_f) / abs(phys_f) * 100
            else:
                error = abs(ml_f - phys_f)

            if error > tolerance_pct:
                corrected[key] = phys_f  # Use physics value
                all_valid = False
                flags.append({
                    "parameter": key,
                    "ml_value": ml_f,
                    "physics_value": phys_f,
                    "error_percent": error,
                    "action": "CORRECTED — using physics value",
                })
            else:
                corrected[key] = ml_f
                flags.append({
                    "parameter": key,
                    "ml_value": ml_f,
                    "physics_value": phys_f,
                    "error_percent": error,
                    "action": "ACCEPTED — within tolerance",
                })

        return {
            "corrected_prediction": corrected,
            "all_valid": all_valid,
            "flags": flags,
            "n_corrected": sum(1 for f in flags if "CORRECTED" in f["action"]),
        }
