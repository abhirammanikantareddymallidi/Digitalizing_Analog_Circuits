import sys
from optimizer.forward import ForwardAnalyzer
from optimizer.inverse import InverseDesigner

fwd = ForwardAnalyzer()
inv = InverseDesigner(n_candidates=3)

print("--- Testing Forward CS with Aliases (Wn, Ln, VBIAS) ---")
res_cs = fwd.analyze("common_source", {"Wn": 10.0, "Ln": 0.18, "RD": 2.0, "VDD": 1.8, "VBIAS": 0.6, "CL": 50.0})
if "error" in res_cs:
    print("Error:", res_cs["error"])
    sys.exit(1)

print("CS Outputs:")
for k in [
    "Av_dB", "BW_MHz", "GBW_MHz", "phase_margin_deg", "power_mW",
    "total_noise_nV", "output_swing_pp", "total_area_um2", "IIP3_V",
    "PSRR_dB", "ID_uA", "VDS", "operating_region"
]:
    print(f"  {k}: {res_cs['physics_results'].get(k)}")

print("\n--- Testing Inverse CS ---")
targets = {"Av_dB": 20.0, "BW_MHz": 80.0, "power_mW": 0.5, "phase_margin_deg": 65.0}
res_inv = inv.design("common_source", targets)
if "error" in res_inv:
    print("Error:", res_inv["error"])
    sys.exit(1)

print(f"Candidates found: {res_inv['n_candidates']}")
for i, c in enumerate(res_inv["candidates"]):
    print(f"Candidate {i+1} ({c['method']}): Valid={c['physically_valid']}")
    var_p = {k: round(v, 3) for k, v in c["design_parameters"].items() if k in res_inv["variable_params"]}
    print("  Parameters:", var_p)
    achieved = {k: round(v["achieved"], 2) for k, v in c["target_status"].items()}
    print("  Achieved:", achieved)

print("\n--- All tests PASSED! ---")
