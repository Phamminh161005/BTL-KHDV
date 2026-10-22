"""Kiểm thử chấp nhận cho solver bài toán A (src/exam_solver.py, người phụ trách: Khỏe).

Đáp án tham chiếu: trên data/toy với configs/default.json, giá trị mục tiêu tối ưu là 2391. Con số này được
tính bằng bản cài đặt thử của spec và xác nhận bằng validator độc lập (output/toy/schedule.json).
Lịch tối ưu có thể khác nhau giữa các lần chạy, nhưng giá trị mục tiêu tối ưu là duy nhất.

Các ca kiểm thử tự bỏ qua (skip) khi solver chưa được cài đặt.
"""
import os

import pytest

from src.data_loader import load_instance
from src.kpi import compute_penalties
from src.schedule import build_schedule

ROOT = os.path.join(os.path.dirname(__file__), "..")
REFERENCE_OBJECTIVE = 2391


def _solve(strategy):
    from src.exam_solver import solve
    loaded = load_instance(os.path.join(ROOT, "data", "toy"), os.path.join(ROOT, "configs", "default.json"))
    loaded.config.update(strategy=strategy, time_limit_sec=300)
    try:
        result = solve(loaded.instance, loaded.config)
    except NotImplementedError:
        pytest.skip(f"exam_solver chưa cài đặt strategy '{strategy}'")
    return loaded, result


@pytest.mark.parametrize("strategy", ["single", "two_phase"])
def test_solver_on_toy(strategy):
    loaded, result = _solve(strategy)
    schedule = build_schedule(loaded.instance, loaded.config, loaded.messages, result, "toy")
    assert schedule["violations"] == [], schedule["violations"]
    assert compute_penalties(loaded.instance, schedule) == result.penalties, "penalties không khớp với lịch"
    weights = loaded.config["weights"]
    assert sum(weights[k] * v for k, v in result.penalties.items()) == result.objective
    if strategy == "single":
        assert result.status == "OPTIMAL"
        assert result.objective == REFERENCE_OBJECTIVE
    else:
        # Hai pha có thể kém hơn giải một lần (model_spec A.7), nhưng không bao giờ tốt hơn tối ưu.
        assert result.status in ("OPTIMAL", "FEASIBLE")
        assert result.objective >= REFERENCE_OBJECTIVE
