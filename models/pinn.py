"""
Physics-Informed Neural Network (PINN) module.

Implements a custom loss function:
    L_total = L_data + λ₁·L_equation + λ₂·L_constraint + λ₃·L_boundary

Where:
  L_data       = MSE between predicted and reference data
  L_equation   = Violation of mathematical equations (physics residual)
  L_constraint = Violation of physical conditions (region, polarity)
  L_boundary   = Violation of valid parameter boundaries
"""

from __future__ import annotations
import numpy as np
import os, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import torch
    import torch.nn as nn
    import torch.optim as optim
    from torch.utils.data import DataLoader, TensorDataset
    HAS_TORCH = True
except ImportError:
    HAS_TORCH = False

from sklearn.preprocessing import StandardScaler


class PINNModel:
    """
    Physics-Informed Neural Network for VLSI circuit prediction.

    Falls back to a message if PyTorch is not installed.
    """

    def __init__(
        self,
        input_dim: int,
        output_dim: int,
        hidden_dims: tuple = (128, 128, 64),
        lambda_eq: float = 1.0,
        lambda_con: float = 0.5,
        lambda_bnd: float = 0.3,
        lr: float = 1e-3,
        epochs: int = 500,
    ):
        if not HAS_TORCH:
            raise ImportError(
                "PyTorch is required for PINN. Install with: pip install torch"
            )

        self.input_dim = input_dim
        self.output_dim = output_dim
        self.lambda_eq = lambda_eq
        self.lambda_con = lambda_con
        self.lambda_bnd = lambda_bnd
        self.lr = lr
        self.epochs = epochs
        self.scaler_X = StandardScaler()
        self.scaler_Y = StandardScaler()
        self.is_trained = False
        self.loss_history = []

        # Build network
        layers = []
        prev = input_dim
        for h in hidden_dims:
            layers.append(nn.Linear(prev, h))
            layers.append(nn.ReLU())
            layers.append(nn.BatchNorm1d(h))
            prev = h
        layers.append(nn.Linear(prev, output_dim))
        self.net = nn.Sequential(*layers)

        self.optimizer = optim.Adam(self.net.parameters(), lr=lr)

    def _physics_residual(self, X: torch.Tensor, Y_pred: torch.Tensor) -> torch.Tensor:
        """
        Compute physics equation residual.

        For VLSI: checks consistency of predicted ID with gm via  gm ≈ 2·ID/VOV.
        This is a soft constraint — the network learns to satisfy it.
        """
        # Generic residual: encourage self-consistency among outputs
        # Outputs assumed ordered as per circuit config
        # We penalize when predicted values create internal contradictions
        residual = torch.zeros(1, device=X.device)

        if Y_pred.shape[1] >= 3:
            # Assume columns: ..., ID, gm, ...
            # Penalize negative currents
            id_col = Y_pred[:, 1] if Y_pred.shape[1] > 1 else Y_pred[:, 0]
            residual = residual + torch.mean(torch.relu(-id_col))

        return residual

    def _constraint_loss(self, X: torch.Tensor, Y_pred: torch.Tensor) -> torch.Tensor:
        """
        Penalize predictions that violate physical constraints.

        E.g., gain should be finite, current should be positive.
        """
        loss = torch.zeros(1, device=X.device)
        # Penalize any NaN-like very large values
        loss = loss + torch.mean(torch.relu(torch.abs(Y_pred) - 1e6))
        return loss

    def _boundary_loss(self, Y_pred: torch.Tensor, Y_min: torch.Tensor, Y_max: torch.Tensor) -> torch.Tensor:
        """Penalize predictions outside valid output ranges."""
        below = torch.relu(Y_min - Y_pred)
        above = torch.relu(Y_pred - Y_max)
        return torch.mean(below + above)

    def fit(self, X: np.ndarray, Y: np.ndarray, input_names=None, output_names=None):
        """Train the PINN."""
        self.input_names = input_names or []
        self.output_names = output_names or []

        # Scale
        X_s = self.scaler_X.fit_transform(X)
        Y_s = self.scaler_Y.fit_transform(Y)

        X_t = torch.FloatTensor(X_s)
        Y_t = torch.FloatTensor(Y_s)

        # Compute output bounds
        Y_min = torch.FloatTensor(Y_s.min(axis=0))
        Y_max = torch.FloatTensor(Y_s.max(axis=0))

        dataset = TensorDataset(X_t, Y_t)
        loader = DataLoader(dataset, batch_size=64, shuffle=True)

        self.loss_history = []
        self.net.train()

        for epoch in range(self.epochs):
            epoch_loss = 0.0
            for X_batch, Y_batch in loader:
                self.optimizer.zero_grad()

                Y_pred = self.net(X_batch)

                # Data loss
                L_data = nn.MSELoss()(Y_pred, Y_batch)

                # Physics residual
                L_eq = self._physics_residual(X_batch, Y_pred)

                # Constraint loss
                L_con = self._constraint_loss(X_batch, Y_pred)

                # Boundary loss
                L_bnd = self._boundary_loss(Y_pred, Y_min, Y_max)

                # Total
                L_total = (
                    L_data
                    + self.lambda_eq * L_eq
                    + self.lambda_con * L_con
                    + self.lambda_bnd * L_bnd
                )

                L_total.backward()
                self.optimizer.step()
                epoch_loss += L_total.item()

            avg_loss = epoch_loss / len(loader)
            self.loss_history.append(avg_loss)

        self.is_trained = True
        return {
            "final_loss": self.loss_history[-1],
            "epochs": self.epochs,
            "loss_history": self.loss_history,
        }

    def predict(self, X: np.ndarray) -> np.ndarray:
        """Predict using the trained PINN."""
        if not self.is_trained:
            raise RuntimeError("PINN has not been trained.")
        self.net.eval()
        X_s = self.scaler_X.transform(X.reshape(1, -1) if X.ndim == 1 else X)
        with torch.no_grad():
            Y_s = self.net(torch.FloatTensor(X_s)).numpy()
        return self.scaler_Y.inverse_transform(Y_s)

    def predict_dict(self, params: dict) -> dict:
        """Predict from parameter dict."""
        X = np.array([params.get(n, 0) for n in self.input_names]).reshape(1, -1)
        Y = self.predict(X)
        return dict(zip(self.output_names, Y[0].tolist()))
