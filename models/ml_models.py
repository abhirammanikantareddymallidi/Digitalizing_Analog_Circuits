"""
Machine Learning model wrappers.

Supports:
  - Random Forest
  - XGBoost (Gradient Boosting)
  - Neural Network (sklearn MLPRegressor)
  - Model comparison and selection based on validation metrics

All models follow a unified interface: fit(), predict(), evaluate().
"""

from __future__ import annotations
import numpy as np
import json
import os
import pickle
from typing import Dict, Optional, List
from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
from sklearn.neural_network import MLPRegressor
from sklearn.multioutput import MultiOutputRegressor
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score


class BaseMLModel:
    """Base class for all ML models in the framework."""

    def __init__(self, name: str):
        self.name = name
        self.model = None
        self.scaler_X = StandardScaler()
        self.scaler_Y = StandardScaler()
        self.is_trained = False
        self.metrics = {}
        self.input_names = []
        self.output_names = []

    def fit(self, X: np.ndarray, Y: np.ndarray,
            input_names: List[str] = None, output_names: List[str] = None,
            test_size: float = 0.2):
        """Train the model with train/test split."""
        self.input_names = input_names or []
        self.output_names = output_names or []

        X_train, X_test, Y_train, Y_test = train_test_split(
            X, Y, test_size=test_size, random_state=42
        )

        # Scale
        X_train_s = self.scaler_X.fit_transform(X_train)
        Y_train_s = self.scaler_Y.fit_transform(Y_train)
        X_test_s = self.scaler_X.transform(X_test)
        Y_test_s = self.scaler_Y.transform(Y_test)

        # Train
        self.model.fit(X_train_s, Y_train_s)
        self.is_trained = True

        # Evaluate
        Y_pred_s = self.model.predict(X_test_s)
        Y_pred = self.scaler_Y.inverse_transform(
            Y_pred_s.reshape(-1, Y.shape[1]) if Y_pred_s.ndim == 1 else Y_pred_s
        )
        Y_test_orig = self.scaler_Y.inverse_transform(Y_test_s)

        self.metrics = {
            "mse": float(mean_squared_error(Y_test_orig, Y_pred)),
            "mae": float(mean_absolute_error(Y_test_orig, Y_pred)),
            "r2": float(r2_score(Y_test_orig, Y_pred)),
            "n_train": len(X_train),
            "n_test": len(X_test),
        }
        return self.metrics

    def predict(self, X: np.ndarray) -> np.ndarray:
        """Predict outputs for input array."""
        if not self.is_trained:
            raise RuntimeError(f"Model '{self.name}' has not been trained yet.")
        X_s = self.scaler_X.transform(X.reshape(1, -1) if X.ndim == 1 else X)
        Y_s = self.model.predict(X_s)
        Y = self.scaler_Y.inverse_transform(
            Y_s.reshape(-1, len(self.output_names)) if Y_s.ndim == 1 else Y_s
        )
        return Y

    def predict_dict(self, params: dict) -> dict:
        """Predict from a parameter dict and return a result dict."""
        X = np.array([params.get(n, 0) for n in self.input_names]).reshape(1, -1)
        Y = self.predict(X)
        return dict(zip(self.output_names, Y[0].tolist()))

    def evaluate(self, X: np.ndarray, Y_true: np.ndarray) -> dict:
        """Evaluate on a given dataset."""
        Y_pred = self.predict(X)
        return {
            "mse": float(mean_squared_error(Y_true, Y_pred)),
            "mae": float(mean_absolute_error(Y_true, Y_pred)),
            "r2": float(r2_score(Y_true, Y_pred)),
        }

    def save(self, path: str):
        """Save model to disk."""
        os.makedirs(os.path.dirname(path) if os.path.dirname(path) else ".", exist_ok=True)
        with open(path, "wb") as f:
            pickle.dump({
                "name": self.name,
                "model": self.model,
                "scaler_X": self.scaler_X,
                "scaler_Y": self.scaler_Y,
                "metrics": self.metrics,
                "input_names": self.input_names,
                "output_names": self.output_names,
                "is_trained": self.is_trained,
            }, f)

    def load(self, path: str):
        """Load model from disk."""
        with open(path, "rb") as f:
            data = pickle.load(f)
        self.name = data["name"]
        self.model = data["model"]
        self.scaler_X = data["scaler_X"]
        self.scaler_Y = data["scaler_Y"]
        self.metrics = data["metrics"]
        self.input_names = data["input_names"]
        self.output_names = data["output_names"]
        self.is_trained = data["is_trained"]
        return self


class RandomForestModel(BaseMLModel):
    """Random Forest regressor."""

    def __init__(self, n_estimators=200, max_depth=20):
        super().__init__("Random Forest")
        self.model = MultiOutputRegressor(
            RandomForestRegressor(
                n_estimators=n_estimators,
                max_depth=max_depth,
                random_state=42,
                n_jobs=-1,
            )
        )


class GradientBoostingModel(BaseMLModel):
    """Gradient Boosting regressor (sklearn)."""

    def __init__(self, n_estimators=200, max_depth=6, learning_rate=0.1):
        super().__init__("Gradient Boosting")
        self.model = MultiOutputRegressor(
            GradientBoostingRegressor(
                n_estimators=n_estimators,
                max_depth=max_depth,
                learning_rate=learning_rate,
                random_state=42,
            )
        )


class XGBoostModel(BaseMLModel):
    """XGBoost regressor (falls back to GradientBoosting if xgboost not installed)."""

    def __init__(self, n_estimators=200, max_depth=6, learning_rate=0.1):
        super().__init__("XGBoost")
        try:
            from xgboost import XGBRegressor
            self.model = MultiOutputRegressor(
                XGBRegressor(
                    n_estimators=n_estimators,
                    max_depth=max_depth,
                    learning_rate=learning_rate,
                    random_state=42,
                    verbosity=0,
                )
            )
        except ImportError:
            # Fall back to sklearn GradientBoosting
            self.name = "Gradient Boosting (fallback)"
            self.model = MultiOutputRegressor(
                GradientBoostingRegressor(
                    n_estimators=n_estimators,
                    max_depth=max_depth,
                    learning_rate=learning_rate,
                    random_state=42,
                )
            )


class NeuralNetModel(BaseMLModel):
    """Multi-layer perceptron regressor."""

    def __init__(self, hidden_layers=(128, 64, 32), max_iter=1000):
        super().__init__("Neural Network")
        self.model = MLPRegressor(
            hidden_layer_sizes=hidden_layers,
            activation="relu",
            solver="adam",
            max_iter=max_iter,
            random_state=42,
            early_stopping=True,
            validation_fraction=0.15,
        )


class MLModelFactory:
    """Factory for creating ML models by name."""

    _REGISTRY = {
        "random_forest": RandomForestModel,
        "xgboost": XGBoostModel,
        "gradient_boosting": GradientBoostingModel,
        "neural_network": NeuralNetModel,
    }

    @classmethod
    def create(cls, model_name: str, **kwargs) -> BaseMLModel:
        key = model_name.lower().replace(" ", "_").replace("-", "_")
        if key not in cls._REGISTRY:
            available = ", ".join(cls._REGISTRY.keys())
            raise ValueError(f"Unknown model '{model_name}'. Available: {available}")
        return cls._REGISTRY[key](**kwargs)

    @classmethod
    def list_models(cls) -> List[str]:
        return list(cls._REGISTRY.keys())
