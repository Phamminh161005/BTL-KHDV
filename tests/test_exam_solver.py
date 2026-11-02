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


# ---- Solver đối chứng PuLP + CBC (src/exam_solver_pulp.py, người phụ trách: Minh) ----

def _load_toy(time_limit):
    loaded = load_instance(os.path.join(ROOT, "data", "toy"), os.path.join(ROOT, "configs", "default.json"))
    loaded.config.update(time_limit_sec=time_limit)
    return loaded


def test_pulp_solver_finds_reference_optimum():
    """CBC tìm ra lời giải đạt giá trị tối ưu 2391 sau khoảng 10 giây, nhưng không chứng minh được tối ưu trong
    vài phút (model_spec A.13). Vì vậy chấp nhận cả OPTIMAL lẫn FEASIBLE, miễn đạt đúng giá trị tối ưu."""
    from src.exam_solver_pulp import solve
    loaded = _load_toy(60)
    result = solve(loaded.instance, loaded.config)
    assert result.status in ("OPTIMAL", "FEASIBLE")
    assert result.objective == REFERENCE_OBJECTIVE
    schedule = build_schedule(loaded.instance, loaded.config, loaded.messages, result, "toy")
    assert schedule["violations"] == [], schedule["violations"]
    assert compute_penalties(loaded.instance, schedule) == result.penalties
    weights = loaded.config["weights"]
    assert sum(weights[k] * v for k, v in result.penalties.items()) == result.objective
    assert result.best_bound == (result.objective if result.status == "OPTIMAL" else None)


def test_pulp_solver_detects_infeasible(tmp_path):
    """Chỉ còn 2 ca (ca 1 và ca 2 ngày 14/12) nhưng sinh viên 22020031 thi 4 môn, trong đó 2 môn chiếm 2 ca:
    qua được mọi kiểm tra trước khi giải nhưng không thể xếp lịch."""
    from src.exam_solver_pulp import solve
    toy = os.path.join(ROOT, "data", "toy")
    for name in os.listdir(toy):
        if name.endswith(".csv"):
            text = open(os.path.join(toy, name), encoding="utf-8").read()
            if name == "slots.csv":
                text = "date,period\n2026-12-14,1\n2026-12-14,2\n"
            if name == "unavailability.csv":
                text = "resource_type,resource_id,date,period,note\n"
            (tmp_path / name).write_text(text, encoding="utf-8")
    loaded = load_instance(str(tmp_path), os.path.join(ROOT, "configs", "default.json"))
    assert loaded.ok, [m.to_dict() for m in loaded.messages]
    loaded.config.update(time_limit_sec=60)
    result = solve(loaded.instance, loaded.config)
    assert result.status == "INFEASIBLE"
    assert result.solution is None and result.objective is None


@pytest.mark.filterwarnings("ignore:PULP_CBC_CMD is deprecated:DeprecationWarning")
def test_pulp_hard_deadline_stops_cbc():
    """CBC không tự dừng thì phải bị dừng cưỡng bức ở hạn cứng (không treo vô thời hạn)."""
    import time

    import pulp

    from src.exam_solver_pulp import _Model, _solve_with_deadline, hard_deadline
    assert hard_deadline(300) == 360 and hard_deadline(60) == 90
    loaded = _load_toy(10)
    model = _Model(loaded.instance, loaded.config)
    cbc = pulp.PULP_CBC_CMD(msg=False, gapRel=0)          # không đặt timeLimit: CBC cần vài phút trên toy
    started = time.time()
    assert _solve_with_deadline(model.prob, cbc, deadline=3) is True
    assert time.time() - started < 15


def test_pulp_solver_rejects_two_phase():
    from src.exam_solver_pulp import solve
    loaded = _load_toy(10)
    loaded.config.update(strategy="two_phase")
    with pytest.raises(NotImplementedError):
        solve(loaded.instance, loaded.config)
