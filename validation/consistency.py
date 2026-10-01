"""
Consistency Checker — end-to-end validation wrapper.

Orchestrates physics constraint checks, ML verification,
and produces a final PASS/FAIL report with explanations.
"""

from __future__ import annotations
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from typing import Dict, List


class ConsistencyChecker:
    """
    Final consistency validation layer.

    Produces a structured report with:
      - Overall status (PASS / FAIL / WARNING)
      - List of all checks with status
      - Recommendations for fixing failures
    """

    @staticmethod
    def generate_report(analysis_result: dict, verification_report: dict = None) -> dict:
        """
        Generate a comprehensive consistency report.

        Args:
            analysis_result: output from ForwardAnalyzer.analyze()
            verification_report: output from VerificationEngine.verify()

        Returns:
            Structured report dict.
        """
        checks = analysis_result.get("constraint_checks", [])
        summary = analysis_result.get("verification_summary", {})

        report_items = []
        for check in checks:
            report_items.append({
                "check_name": check["name"],
                "condition": check["condition"],
                "status": "PASS" if check["satisfied"] else "FAIL",
                "severity": check["severity"],
                "rule": check.get("rule", ""),
            })

        # Overall status
        critical_fails = [r for r in report_items if r["status"] == "FAIL" and r["severity"] == "CRITICAL"]
        warnings = [r for r in report_items if r["status"] == "FAIL" and r["severity"] == "WARNING"]

        if critical_fails:
            overall = "FAIL"
        elif warnings:
            overall = "WARNING"
        else:
            overall = "PASS"

        # Build recommendations
        recommendations = []
        if verification_report:
            recommendations.extend(verification_report.get("recommendations", []))
        for fail in critical_fails:
            recommendations.append(
                f"CRITICAL: {fail['check_name']} failed — {fail['rule']}"
            )

        return {
            "overall_status": overall,
            "total_checks": len(report_items),
            "passed": sum(1 for r in report_items if r["status"] == "PASS"),
            "failed": sum(1 for r in report_items if r["status"] == "FAIL"),
            "critical_failures": len(critical_fails),
            "warnings": len(warnings),
            "checks": report_items,
            "recommendations": recommendations,
            "confidence": verification_report.get("confidence", "N/A") if verification_report else "N/A",
        }

    @staticmethod
    def format_text_report(report: dict) -> str:
        """Format the report as a human-readable text block."""
        lines = []
        lines.append("=" * 60)
        lines.append("  CONSISTENCY VERIFICATION REPORT")
        lines.append("=" * 60)
        lines.append(f"  Overall Status : {report['overall_status']}")
        lines.append(f"  Confidence     : {report.get('confidence', 'N/A')}")
        lines.append(f"  Checks Passed  : {report['passed']} / {report['total_checks']}")
        lines.append(f"  Critical Fails : {report['critical_failures']}")
        lines.append(f"  Warnings       : {report['warnings']}")
        lines.append("-" * 60)

        for item in report["checks"]:
            icon = "✓" if item["status"] == "PASS" else "✗"
            lines.append(f"  {icon} [{item['severity']:8s}] {item['check_name']}")
            lines.append(f"    {item['condition']}")

        if report["recommendations"]:
            lines.append("-" * 60)
            lines.append("  RECOMMENDATIONS:")
            for rec in report["recommendations"]:
                lines.append(f"  • {rec}")

        lines.append("=" * 60)
        return "\n".join(lines)
