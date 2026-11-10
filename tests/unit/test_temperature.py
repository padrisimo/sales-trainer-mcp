"""Temperature model test."""
import pytest

from sales_trainer.temperature.model import TemperatureModel


def test_initial_temperature() -> None:
    m = TemperatureModel()
    assert m.current_temp == 50


def test_update_increases_temp() -> None:
    m = TemperatureModel(sensitivity=1.0, max_delta=15)
    new_temp = m.update(100)  # perfect score
    assert new_temp == 65  # 50 + (100-50)/50*1*15 = 65


def test_update_decreases_temp() -> None:
    m = TemperatureModel(sensitivity=1.0, max_delta=15)
    new_temp = m.update(0)  # terrible score
    assert new_temp == 35  # 50 + (0-50)/50*1*15 = 35


def test_moving_average_inertia() -> None:
    """With window=3, after perfect→terrible→medium, avg delta = (15-15+0)/3=0, temp stays."""
    m = TemperatureModel(sensitivity=1.0, max_delta=15, moving_average_window=3)
    t1 = m.update(100)  # 65
    t2 = m.update(0)    # 50 (65-15)
    t3 = m.update(50)   # 50 (avg delta 0, no change)
    assert t3 == 50


def test_minimum_delta_enforced() -> None:
    """If raw delta is 0 (below min_delta), temperature should not change."""
    m = TemperatureModel(sensitivity=1.0, max_delta=15, min_delta=2)
    new_temp = m.update(51)  # raw delta = int((51-50)/50*1*15) = int(0.3) = 0
    # Below min_delta, so no change: new_temp stays at 50
    assert new_temp == 50


def test_bounds_clamped() -> None:
    m = TemperatureModel(sensitivity=1.0, max_delta=15)
    # Very high score
    t1 = m.update(100)
    assert t1 == 65
    # Very low score many times
    for _ in range(10):
        m.update(0)
    assert 0 <= m.current_temp <= 100


def test_cause_stored() -> None:
    m = TemperatureModel()
    m.update(80, cause="buen argumento con figuras")
    assert "buen argumento" in m.last_cause
