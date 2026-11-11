"""Hồi quy cho các thay đổi đo thời gian và trạng thái solver KHOE-4."""
from pathlib import Path

from src.data_loader import load_instance
from src.exam_solver import solve

ROOT = Path(__file__).resolve().parents[1]


def _toy_config(**changes):
    loaded = load_instance(str(ROOT / "data" / "toy"), str(ROOT / "configs" / "default.json"))
    assert loaded.ok, [m.to_dict() for m in loaded.messages]
    config = dict(loaded.config, strategy="single", **changes)
    return loaded.instance, config


def test_feasibility_search_does_not_claim_global_optimality():
    instance, config = _toy_config(time_limit_sec=30)
    result = solve(instance, config, optimize=False)
    assert result.status == "FEASIBLE"
    assert result.solution is not None
    assert result.solve_time_sec >= 0


def test_single_zero_budget_does_not_start_search():
    instance, config = _toy_config(time_limit_sec=0)
    result = solve(instance, config)
    assert result.status == "UNKNOWN"
    assert result.solution is None
    assert result.objective is None
    assert result.solve_time_sec >= 0
