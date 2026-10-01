"""
Model selector — trains multiple ML models, compares them,
and selects the best one based on validation metrics.

The selected model is NOT blindly trusted:
  every prediction is verified through the physics engine.
"""

from __future__ import annotations
import numpy as np
from typing import Dict, List
from .ml_models import MLModelFactory, BaseMLModel


class ModelSelector:
    """
    Train and compare multiple ML models for a given circuit type.

    Selection is based on R² score on the validation set.
    """

    def __init__(self, model_names: List[str] = None):
        if model_names is None:
            model_names = ["random_forest", "xgboost", "neural_network"]
        self.model_names = model_names
        self.models: Dict[str, BaseMLModel] = {}
        self.comparison: Dict[str, dict] = {}
        self.best_model_name: str = ""
        self.best_model: BaseMLModel = None

    def train_and_compare(
        self,
        X: np.ndarray,
        Y: np.ndarray,
        input_names: List[str] = None,
        output_names: List[str] = None,
    ) -> Dict[str, dict]:
        """
        Train all models and return comparison metrics.

        Returns:
            dict mapping model_name → metrics (mse, mae, r2, n_train, n_test)
        """
        for name in self.model_names:
            try:
                model = MLModelFactory.create(name)
                metrics = model.fit(X, Y, input_names, output_names)
                self.models[name] = model
                self.comparison[name] = {
                    "model_name": model.name,
                    **metrics,
                    "status": "trained",
                }
            except Exception as e:
                self.comparison[name] = {
                    "model_name": name,
                    "status": "failed",
                    "error": str(e),
                    "r2": -999,
                }

        # Select best by R²
        best_r2 = -999
        for name, info in self.comparison.items():
            if info.get("r2", -999) > best_r2:
                best_r2 = info["r2"]
                self.best_model_name = name

        if self.best_model_name in self.models:
            self.best_model = self.models[self.best_model_name]

        return self.comparison

    def predict(self, params: dict, model_name: str = None) -> dict:
        """
        Predict using the specified or best model.

        IMPORTANT: This prediction is raw ML output.
        It MUST be verified against the physics engine before being accepted.
        """
        model = self.models.get(model_name, self.best_model)
        if model is None:
            raise RuntimeError("No trained model available.")
        prediction = model.predict_dict(params)
        return {
            "model_used": model.name,
            "prediction": prediction,
            "warning": "ML prediction — must be verified against physics constraints",
        }

    def get_comparison_table(self) -> List[dict]:
        """Return comparison as a list of dicts for display."""
        rows = []
        for name, info in self.comparison.items():
            rows.append({
                "model": info.get("model_name", name),
                "r2": f"{info.get('r2', 'N/A'):.4f}" if isinstance(info.get("r2"), float) else "N/A",
                "mse": f"{info.get('mse', 'N/A'):.6e}" if isinstance(info.get("mse"), float) else "N/A",
                "mae": f"{info.get('mae', 'N/A'):.6e}" if isinstance(info.get("mae"), float) else "N/A",
                "status": info.get("status", "unknown"),
                "is_best": name == self.best_model_name,
            })
        return rows
