"""Xuất timetable.json và KPI bài B theo data_schema 9.11."""
from collections import Counter
import datetime as dt

from src.instance import PERIOD_TIMES
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
    table["kpi"] = compute_kpi_b(instance, table, config["lab_reserve_ratio"])
    return table


def compute_kpi_b(instance, table, rho):
    sessions = table["sessions"]
    labs = Counter((s["weekday"], s["period"]) for s in sessions if s["needs_lab"])
    per_class_day = Counter((s["class_id"], s["weekday"]) for s in sessions)
    per_group_day = Counter((g, s["weekday"]) for s in sessions for g in s["groups"])
    def utilization(kind):
        used = len({(s["room_id"], s["weekday"], s["period"]) for s in sessions
                    if instance.rooms[s["room_id"]].room_type == kind})
        supply = sum(t not in r.busy for r in instance.rooms.values()
                     if r.room_type == kind for t in instance.slots)
        return used / supply if supply else None
    capacity = sum(s["room_capacity"] for s in sessions)
    return {
        "hard_violations": len(table["violations"]),
        "room_utilization_normal": utilization("normal"),
        "room_utilization_lab": utilization("lab"),
        "lab_peak_utilization": max((labs[t] / instance.labs_available(t) for t in instance.slots
                                     if instance.labs_available(t)), default=None),
        "slots_without_lab_reserve": sum(labs[t] > instance.lab_limit(t, rho) for t in instance.slots),
        "seat_fill_rate": sum(s["size"] for s in sessions) / capacity if capacity else None,
        "preference_violations": table["penalties"]["B-S2"],
        "classes_same_day": len({k for (k, _), n in per_class_day.items() if n > 1}),
        "group_max_sessions_per_day": max(per_group_day.values(), default=None),
        "solve_time_sec": table["solve_time_sec"],
    }
