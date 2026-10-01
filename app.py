"""
Flask application entry point.

Routes:
  GET  /                          → UI
  GET  /api/circuits              → list all supported circuits
  POST /api/forward               → forward analysis
  POST /api/inverse               → inverse design
  GET  /api/technologies          → list all technology nodes (with metadata)
  GET  /api/technology/<node>     → full detail for one technology node
  GET  /api/tech-defaults/<node>  → recommended defaults for a node + device type
"""

import os
import sys
import math
import logging
from flask import Flask, request, jsonify, render_template, send_from_directory

# ── Path setup ────────────────────────────────────────────────────────────────
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config.circuit_configs import (
    list_circuit_types, get_circuit_config, get_parameter_classification,
    get_ui_input_parameters, get_dependency_map,
)
from optimizer.forward import ForwardAnalyzer
from optimizer.inverse import InverseDesigner
from models.model_selector import ModelSelector
from technology.tech_database import TechDatabase
from technology.tech_constraints import TechConstraintEngine

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── Flask app ─────────────────────────────────────────────────────────────────
app = Flask(__name__, static_folder="ui/static", template_folder="ui")

# ── Global instances ──────────────────────────────────────────────────────────
ml_selector      = ModelSelector()
forward_analyzer = ForwardAnalyzer(ml_selector=ml_selector)
inverse_designer = InverseDesigner(ml_selector=ml_selector)

# Pre-load technology database at startup
try:
    _tech_db = TechDatabase.get_instance()
    logger.info(
        "Technology database loaded: %d nodes, %d with PTM model files",
        len(_tech_db.list_nodes()),
        _tech_db.loaded_count,
    )
    if _tech_db.folder_error:
        logger.warning("Tech folder warning: %s", _tech_db.folder_error)
except Exception as exc:
    logger.error("Failed to load technology database: %s", exc)
    _tech_db = None

_tech_engine = TechConstraintEngine()


# ── Utility: sanitise floats for JSON ────────────────────────────────────────
def sanitize_for_json(obj):
    if isinstance(obj, dict):
        return {k: sanitize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [sanitize_for_json(v) for v in obj]
    if isinstance(obj, float):
        if math.isinf(obj):
            return "Infinity" if obj > 0 else "-Infinity"
        if math.isnan(obj):
            return "NaN"
    return obj


# ═══════════════════════════════════════════════════════════════════════════════
# UI Route
# ═══════════════════════════════════════════════════════════════════════════════
@app.route("/")
def index():
    return render_template("index.html")


# ═══════════════════════════════════════════════════════════════════════════════
# Circuit Routes
# ═══════════════════════════════════════════════════════════════════════════════
@app.route("/api/circuits", methods=["GET"])
def get_circuits():
    circuits = list_circuit_types()
    details = {}
    for circuit in circuits:
        config = dict(get_circuit_config(circuit))
        config["input_parameters"] = get_ui_input_parameters(circuit)
        config["parameter_classification"] = get_parameter_classification(circuit)
        config["dependency_map"] = get_dependency_map(circuit)
        details[circuit] = config
    return jsonify({"circuits": circuits, "details": details})


# ═══════════════════════════════════════════════════════════════════════════════
# Technology Routes
# ═══════════════════════════════════════════════════════════════════════════════
@app.route("/api/technologies", methods=["GET"])
def get_technologies():
    """
    Return all known technology nodes with summary metadata.

    The response is sourced only from technology model files on disk.
    """
    if _tech_db is None:
        return jsonify({
            "error": "Technology database not available.",
            "nodes": [],
        }), 500

    nodes = _tech_db.list_nodes_meta()

    response = {
        "nodes":        nodes,
        "loaded_count": _tech_db.loaded_count,
        "total_count":  len(nodes),
    }
    if _tech_db.folder_error:
        response["folder_warning"] = _tech_db.folder_error

    return jsonify(sanitize_for_json(response))


@app.route("/api/technology/<node_name>", methods=["GET"])
def get_technology_detail(node_name: str):
    """Return full detail for a specific technology node."""
    if _tech_db is None:
        return jsonify({"error": "Technology database not available."}), 500

    node = _tech_db.get_node(node_name)
    if node is None:
        return jsonify({
            "error": f"Unknown technology node: {node_name!r}",
            "available": _tech_db.list_nodes(),
        }), 404

    device_type = request.args.get("device_type", "NMOS").upper()
    return jsonify(sanitize_for_json(node.to_api_dict()))


@app.route("/api/tech-defaults/<node_name>", methods=["GET"])
def get_tech_defaults(node_name: str):
    """
    Return recommended parameter defaults for a node + device type.
    Only values from the PTM file are returned (none invented).
    """
    device_type = request.args.get("device_type", "NMOS")
    defaults = _tech_engine.get_tech_defaults(node_name, device_type)
    return jsonify(sanitize_for_json({
        "node_name":   node_name,
        "device_type": device_type,
        "defaults":    defaults,
    }))


# ═══════════════════════════════════════════════════════════════════════════════
# Forward Analysis Route
# ═══════════════════════════════════════════════════════════════════════════════
@app.route("/api/forward", methods=["POST"])
def forward_analysis():
    """
    Run forward analysis.

    Request body:
      {
        "circuit_type":    "common_source",
        "params":          { "VDD": 0.9, "VGS": 0.7, ... },
        "include_ml":      true,
        "technology_node": "16nm",       ← NEW
        "device_type":     "NMOS"        ← NEW
      }
    """
    data         = request.json or {}
    circuit_type = data.get("circuit_type")
    params       = data.get("params", {})
    include_ml   = data.get("include_ml", True)
    tech_node    = data.get("technology_node", None)
    device_type  = data.get("device_type")

    if not circuit_type:
        return jsonify({"error": "circuit_type is required"}), 400

    result = forward_analyzer.analyze(
        circuit_type=circuit_type,
        params=params,
        include_ml=include_ml,
        technology_node=tech_node,
        device_type=device_type,
    )
    return jsonify(sanitize_for_json(result))


# ═══════════════════════════════════════════════════════════════════════════════
# Inverse Design Route
# ═══════════════════════════════════════════════════════════════════════════════
@app.route("/api/inverse", methods=["POST"])
def inverse_design():
    """
    Run inverse design.

    Request body:
      {
        "circuit_type":    "common_source",
        "targets":         { "Av_dB": 20, "BW_MHz": 100 },
        "fixed_params":    { "VDD": 0.9 },
        "technology_node": "16nm",        ← NEW
        "device_type":     "NMOS"         ← NEW
      }
    """
    data         = request.json or {}
    circuit_type = data.get("circuit_type")
    targets      = data.get("targets", {})
    fixed_params = data.get("fixed_params", {})
    tech_node    = data.get("technology_node", None)
    device_type  = data.get("device_type", "NMOS")

    if not circuit_type or not targets:
        return jsonify({"error": "circuit_type and targets are required"}), 400

    result = inverse_designer.design(
        circuit_type=circuit_type,
        targets=targets,
        fixed_params=fixed_params,
        technology_node=tech_node,
        device_type=device_type,
    )
    return jsonify(sanitize_for_json(result))


# ═══════════════════════════════════════════════════════════════════════════════
# Startup
# ═══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    os.makedirs("ui/static/css", exist_ok=True)
    os.makedirs("ui/static/js",  exist_ok=True)
    app.run(debug=True, port=5000)
