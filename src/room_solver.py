"""CP-SAT bài toán B, model_spec B.4–B.6.

relax={"B-H5", "B-H7", "B-H6"} bỏ riêng nhóm giảng viên (cả
ca bận), nhóm sinh viên, phòng bận để chẩn đoán B.7. Không sửa instance.
Ngân sách time_limit_sec bắt đầu trước khi dựng mô hình.
"""
from __future__ import annotations

from collections import defaultdict
import time
import math

from ortools import __version__
from ortools.sat.python import cp_model

from src.instance import Message, SolveResult
from src.instance_b import InstanceB, Session, SolutionB
from src.validator_b import compute_penalties_b

RELAX_GROUPS = ("B-H5", "B-H7", "B-H6")
DEFAULT_WEIGHTS = {"B-S1": 1, "B-S2": 50, "B-S3": 100, "B-S4": 30}


class _Deadline(Exception):
    pass


def solve(instance: InstanceB, config: dict, *, relax=frozenset(),
          optimize: bool = True) -> SolveResult:
    """Trả SolveResult chứa SolutionB; optimize=False chỉ tìm nghiệm khả thi.

    relax là tập con RELAX_GROUPS. B-H5 bao gồm xung đột và ca bận GV.
    Luôn giữ mỗi lớp tối đa một buổi/ca để lịch chẩn đoán có nghĩa.
    Kết quả chẩn đoán có thể vi phạm nhóm đã bỏ, không dùng như lịch chính thức.
    """
    started = time.monotonic()
    budget = float(config.get("time_limit_sec", 300))
    if not math.isfinite(budget) or budget < 0:
        raise ValueError("time_limit_sec phải là số hữu hạn không âm")
    deadline = started + budget
    relax = frozenset(relax)
    if relax - set(RELAX_GROUPS):
        raise ValueError(f"Nhóm ràng buộc không hỗ trợ: {sorted(relax - set(RELAX_GROUPS))}")
    if config.get("strategy", "single") != "single":
        raise ValueError("Bài toán B chỉ hỗ trợ strategy=single")
    weights = DEFAULT_WEIGHTS | config.get("weights", {})
    if any(not isinstance(weights[k], int) or isinstance(weights[k], bool) or weights[k] < 0 for k in DEFAULT_WEIGHTS):
        raise ValueError("Trọng số B-S1..B-S4 phải là số nguyên không âm")
    rho = float(config.get("lab_reserve_ratio", 0.85))
    if not 0 < rho <= 1:
        raise ValueError("lab_reserve_ratio phải thuộc (0, 1]")
    result = SolveResult("UNKNOWN", 0, solver_name=f"OR-Tools CP-SAT {__version__}")

    def tick():
        if time.monotonic() >= deadline:
            raise _Deadline

    try:
        tick()
        model = cp_model.CpModel()
        y = {}
        by_class = defaultdict(list)
        by_class_slot = defaultdict(list)
        by_class_day = defaultdict(list)
        by_room_slot = defaultdict(list)
        by_lecturer_slot = defaultdict(list)
        labs = defaultdict(list)
        waste, avoid = [], []
        for k, cls in sorted(instance.classes.items()):
            tick()
            lecturer = instance.lecturers[cls.lecturer_id]
            for r in sorted(instance.rooms_for(k)):
                room = instance.rooms[r]
                for t in instance.slots:
                    tick()
                    if "B-H6" not in relax and t in room.busy:
                        continue
                    if "B-H5" not in relax and t in lecturer.busy:
                        continue
                    var = model.new_bool_var(f"y[{k},{r},{t}]")
                    y[k, r, t] = var
                    by_class[k].append(var)
                    by_class_slot[k, t].append(var)
                    by_class_day[k, t[0]].append(var)
                    by_room_slot[r, t].append(var)
                    by_lecturer_slot[cls.lecturer_id, t].append(var)
                    waste.append((room.capacity - cls.size) * var)
                    if t in lecturer.avoid:
                        avoid.append(var)
                    if cls.needs_lab:
                        labs[t].append(var)
            model.add(sum(by_class[k]) == cls.sessions)  # B-H1, y domain: H3/H4/H6
        for variables in by_room_slot.values():
            tick()
            model.add(sum(variables) <= 1)  # B-H2
        for variables in by_class_slot.values():
            tick()
            model.add(sum(variables) <= 1)
        if "B-H5" not in relax:
            for variables in by_lecturer_slot.values():
                tick()
                model.add(sum(variables) <= 1)
        if "B-H7" not in relax:
            for members in instance.groups.values():
                for t in instance.slots:
                    tick()
                    model.add(sum(v for k in members for v in by_class_slot[k, t]) <= 1)
        extra, over = [], []
        for k, cls in instance.classes.items():
            for d in instance.days:
                tick()
                e = model.new_int_var(0, cls.sessions, f"e[{k},{d}]")
                model.add_max_equality(e, [0, sum(by_class_day[k, d]) - 1])
                extra.append(e)
        for t in instance.slots:
            tick()
            available = instance.labs_available(t)
            limit = math.floor(rho * available + 1e-9)
            v = model.new_int_var(0, len(instance.lab_rooms), f"v[{t}]")
            model.add_max_equality(v, [0, sum(labs[t]) - limit])
            over.append(v)
        if optimize:
            model.minimize(sum(weights[key] * sum(terms) for key, terms in
                               zip(DEFAULT_WEIGHTS, [waste, avoid, extra, over])))
        tick()
        solver = cp_model.CpSolver()
        # Chừa một ít thời gian cho gọi API và trích xuất; model build đã trừ.
        remaining = deadline - time.monotonic() - 0.01
        if remaining <= 0:
            raise _Deadline
        solver.parameters.max_time_in_seconds = remaining
        solver.parameters.num_search_workers = int(config.get("num_workers", 8))
        solver.parameters.random_seed = int(config.get("random_seed", 0))
        status = solver.solve(model)
        if status == cp_model.MODEL_INVALID:
            raise RuntimeError(f"Mô hình B không hợp lệ: {solver.response_stats()}")
        result.status = ("FEASIBLE" if not optimize and status in (cp_model.OPTIMAL, cp_model.FEASIBLE)
                         else solver.status_name(status))
        if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            result.solution = SolutionB([Session(k, r, t) for (k, r, t), v in y.items()
                                         if solver.boolean_value(v)])
            # Tính lại từ lịch, kể cả khi trọng số bằng 0, không đọc giá trị slack.
            timetable = {"sessions": [{"class_id": s.class_id, "room_id": s.room_id,
                                        "weekday": s.slot[0], "period": s.slot[1]}
                                       for s in result.solution.sessions]}
            result.penalties = compute_penalties_b(instance, timetable, rho)
            result.objective = sum(weights[k] * p for k, p in result.penalties.items())
            if optimize:
                result.best_bound = solver.best_objective_bound
        elif optimize and status == cp_model.UNKNOWN:
            result.best_bound = solver.best_objective_bound
    except _Deadline:
        result.messages.append(Message("S03", "warning", "Hết ngân sách thời gian trong khi dựng mô hình B"))
    result.solve_time_sec = time.monotonic() - started
    return result
