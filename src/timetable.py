"""Hậu xử lý bài toán B: dựng timetable.json theo data_schema mục 9.11 (model_spec B.8).

Mỗi Session của solver thành một buổi học; sau đó chạy validator độc lập (src/validator_b.py) và tính KPI
(src/kpi_b.py).
"""
import datetime as dt

from src.instance import PERIOD_TIMES
from src.kpi_b import compute_kpi
from src.validator_b import validate_b


def build_timetable(instance, config, messages, result, dataset):
    table = {
        "meta": {"problem": "B", "dataset": dataset,
                 "created_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
                 "solver": result.solver_name if result else None,
                 "strategy": "single", "config": config},
        "status": result.status if result else "INPUT_ERROR",
        "objective": result.objective if result else None,
        "best_bound": result.best_bound if result else None,
        "solve_time_sec": result.solve_time_sec if result else 0,
        "penalties": result.penalties if result else None,
        "sessions": [], "kpi": None, "violations": [],
        "messages": [m.to_dict() for m in messages + (result.messages if result else [])],
    }
    if instance is None or result is None or result.solution is None:
        return table
    for s in sorted(result.solution.sessions, key=lambda s: (s.slot, s.room_id, s.class_id)):
        cls, room = instance.classes[s.class_id], instance.rooms[s.room_id]
        start, end = PERIOD_TIMES[s.slot[1]]
        table["sessions"].append({
            "session_id": f"{s.class_id}@T{s.slot[0]}_{s.slot[1]}",
            "class_id": s.class_id, "class_name": cls.name, "course_id": cls.course_id,
            "needs_lab": cls.needs_lab, "weekday": s.slot[0], "period": s.slot[1],
            "start_time": f"{start // 60:02d}:{start % 60:02d}",
            "end_time": f"{end // 60:02d}:{end % 60:02d}",
            "room_id": s.room_id, "room_capacity": room.capacity, "size": cls.size,
            "lecturer_id": cls.lecturer_id, "groups": sorted(cls.groups)})
    table["violations"] = validate_b(instance, table)
    table["kpi"] = compute_kpi(instance, table, len(table["violations"]))
    return table
