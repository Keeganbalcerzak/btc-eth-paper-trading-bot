from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.mixture import GaussianMixture
from sklearn.preprocessing import StandardScaler


@dataclass(frozen=True)
class RegimePrediction:
    label: int
    name: str
    probability: float
    volatility: float


class MarketRegimeDetector:
    """Offline statistical regime detector for research and validation.

    This is deliberately not wired directly into live execution. It helps test
    whether strategy behavior differs across low-volatility and high-volatility
    windows without introducing fragile model retraining into the paper loop.
    """

    def __init__(
        self,
        n_components: int = 2,
        volatility_window: int = 20,
        random_state: int = 7,
    ) -> None:
        self.n_components = n_components
        self.volatility_window = volatility_window
        self.random_state = random_state
        self.scaler = StandardScaler()
        self.model = GaussianMixture(n_components=n_components, random_state=random_state)
        self._high_vol_label: int | None = None

    def fit_predict(self, bars: pd.DataFrame) -> pd.DataFrame:
        features = self._features(bars)
        scaled = self.scaler.fit_transform(features[["return", "volatility"]])
        labels = self.model.fit_predict(scaled)
        probabilities = self.model.predict_proba(scaled)

        output = features.copy()
        output["regime"] = labels
        output["regime_probability"] = probabilities[np.arange(len(labels)), labels]
        output["regime_name"] = self._name_regimes(labels, output["volatility"])
        return output

    def latest(self, bars: pd.DataFrame) -> RegimePrediction:
        regimes = self.fit_predict(bars)
        latest = regimes.iloc[-1]
        return RegimePrediction(
            label=int(latest["regime"]),
            name=str(latest["regime_name"]),
            probability=float(latest["regime_probability"]),
            volatility=float(latest["volatility"]),
        )

    def _features(self, bars: pd.DataFrame) -> pd.DataFrame:
        if "timestamp" not in bars or "close" not in bars:
            raise ValueError("bars must include timestamp and close columns")
        close = pd.to_numeric(bars["close"], errors="coerce")
        returns = close.pct_change().fillna(0.0)
        volatility = (
            returns.rolling(
                window=self.volatility_window,
                min_periods=max(self.volatility_window // 2, 2),
            )
            .std(ddof=0)
            .fillna(0.0)
        )
        features = pd.DataFrame(
            {
                "timestamp": bars["timestamp"].to_numpy(),
                "return": returns.to_numpy(),
                "volatility": volatility.to_numpy(),
            }
        )
        return features.replace([np.inf, -np.inf], 0.0).fillna(0.0)

    def _name_regimes(self, labels: np.ndarray, volatility: pd.Series) -> list[str]:
        vol_by_label = {
            label: float(volatility[labels == label].mean()) for label in set(labels)
        }
        self._high_vol_label = max(vol_by_label, key=vol_by_label.get)
        return [
            "high_volatility" if int(label) == self._high_vol_label else "low_volatility"
            for label in labels
        ]
