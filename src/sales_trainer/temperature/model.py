from __future__ import annotations

from collections import deque
from typing import Deque, Dict, Optional


class TemperatureModel:
    """Models the character's temperature per turn.

    Update formula (from MEMORY.md §5 & design):
      delta = (turn_score - 50) / 50 × character_sensitivity × max_delta
    Inertia: moving average of last N deltas to avoid sudden jumps.
    Per-level sensitivity multipliers from config/scoring.yaml.
    Bounds: temperature clamped to [0, 100].

    Attributes:
        sensitivity: per-level multiplier (from config).
        max_delta: maximum absolute change per turn (default 15).
        moving_average_window: number of previous deltas to average (default 3).
        min_delta: smallest absolute change that will be applied (default 1).
        history: deque of recent deltas for the moving average.
        current_temp: the character's current temperature (0-100).
        last_cause: natural language reason for the last change.
    """

    def __init__(
        self,
        *,
        sensitivity: float = 1.0,
        max_delta: int = 15,
        moving_average_window: int = 3,
        min_delta: int = 1,
    ) -> None:
        self.sensitivity = sensitivity
        self.max_delta = max_delta
        self.moving_average_window = moving_average_window
        self.min_delta = min_delta
        self.history: Deque[int] = deque(maxlen=moving_average_window)
        self.current_temp: int = 50  # start at midpoint
        self.last_cause: str = "inicio de conversación"

    def update(self, turn_score: int, cause: str | None = None) -> int:
        """Update temperature based on the judge's turn score (0-10).

        Returns the new temperature (clamped to 0-100).
        """
        # 1. Compute raw delta
        raw_delta = int((turn_score - 50) / 50 * self.sensitivity * self.max_delta)

        # 2. Apply moving average inertia
        self.history.append(raw_delta)
        if len(self.history) >= self.moving_average_window:
            avg_delta = sum(self.history) // len(self.history)
        else:
            avg_delta = raw_delta

        # 3. Enforce minimum delta
        if abs(avg_delta) < self.min_delta:
            avg_delta = 0 if avg_delta == 0 else (self.min_delta if avg_delta > 0 else -self.min_delta)

        # 4. Apply delta
        new_temp = self.current_temp + avg_delta

        # 5. Clamp to [0, 100]
        new_temp = max(0, min(100, new_temp))

        # 6. Store state
        self.current_temp = new_temp
        if cause is not None:
            self.last_cause = cause
        elif self.last_cause == "inicio de conversación":
            self.last_cause = f"score {turn_score} → δ={avg_delta}"

        return self.current_temp

    def reset(self) -> None:
        """Reset to initial state (temperature 50, empty history)."""
        self.current_temp = 50
        self.history.clear()
        self.last_cause = "reiniciado"
