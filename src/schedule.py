"""Hậu xử lý: dựng file kết quả schedule.json từ lời giải (data_schema mục 7, model_spec A.10)."""
from __future__ import annotations

import datetime as dt
import json
from typing import Optional

from src.instance import PERIOD_TIMES, Instance, Message, SolveResult

STATUSES = ("OPTIMAL", "FEASIBLE", "INFEASIBLE", "UNKNOWN", "INPUT_ERROR")


def _hhmm(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def build_sittings(instance: Instance, result: SolveResult, messages: list[Message]) -> list[dict]:
    """Chia sinh viên vào phòng theo quy tắc mục 7.3 và dựng danh sách lượt thi."""
    if result.solution is None:
        return []
    sittings = []
    for sitting in result.solution.sittings:
        course = instance.courses[sitting.course_id]
        day, period = sitting.start
        periods = [period] if course.num_periods == 1 else [period, period + 1]
        sitting_id = f"{course.course_id}@{day.isoformat()}_{period}"
        rooms = sorted(sitting.rooms, key=lambda r: (-instance.rooms[r].exam_capacity, r))
        students = sorted(sitting.students)
        position = 0
        room_entries = []
        for room_id in rooms:
            capacity = instance.rooms[room_id].exam_capacity
            part = students[position:position + capacity]
            position += len(part)
            if not part:
                messages.append(Message("R01", "info", f"Phòng {room_id} của lượt {sitting_id} không có sinh viên"))
            room_entries.append({
                "room_id": room_id,
                "exam_capacity": capacity,
                "num_students": len(part),
                "students": part,
                "proctors": sorted(result.solution.proctoring.get((room_id, sitting.start), [])),
            })
        if position < len(students):
            # Không thể xảy ra với lời giải đúng (A-H3); validator sẽ báo A-H3.
            room_entries.append({"room_id": None, "exam_capacity": 0, "num_students": len(students) - position,
                                 "students": students[position:], "proctors": []})
        sittings.append({
            "sitting_id": sitting_id,
            "course_id": course.course_id,
            "course_name": course.name,
            "exam_type": course.exam_type,
            "date": day.isoformat(),
            "start_period": period,
            "periods": periods,
            "start_time": _hhmm(PERIOD_TIMES[periods[0]][0]),
            "end_time": _hhmm(PERIOD_TIMES[periods[-1]][1]),
            "duration_min": course.duration_min,
            "num_students": len(students),
            "rooms": room_entries,
        })
    sittings.sort(key=lambda s: (s["date"], s["start_period"], s["course_id"]))
    return sittings


def build_schedule(instance: Optional[Instance], config: dict, messages: list[Message],
                   result: Optional[SolveResult], dataset: str, problem: str = "A") -> dict:
    """Dựng toàn bộ nội dung schedule.json. Khi dữ liệu lỗi (instance None) trả trạng thái INPUT_ERROR."""
    from src.kpi import compute_kpi          # tránh import vòng
    from src.validator import validate, validate_raw_proctoring

    meta = {
        "problem": problem,
        "dataset": dataset,
        "created_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "solver": result.solver_name if result else None,
        "strategy": config["strategy"],
        "config": config,
    }
    if instance is None or result is None:
        return {"meta": meta, "status": "INPUT_ERROR", "objective": None, "best_bound": None,
                "solve_time_sec": 0, "penalties": None, "kpi": None, "sittings": [],
                "messages": [m.to_dict() for m in messages], "violations": []}

    messages = messages + result.messages
    sittings = build_sittings(instance, result, messages)
    schedule = {
        "meta": meta,
        "status": result.status,
        "objective": result.objective,
        "best_bound": result.best_bound,
        "solve_time_sec": round(result.solve_time_sec, 3),
        "penalties": result.penalties,
        "kpi": None,
        "sittings": sittings,
        "messages": [m.to_dict() for m in messages],
        "violations": [],
    }
    if sittings:
        schedule["violations"] = (validate(instance, schedule, config)
                                  + validate_raw_proctoring(instance, result.solution))
        schedule["kpi"] = compute_kpi(instance, schedule, len(schedule["violations"]))
    return schedule


def write_schedule(schedule: dict, path: str) -> None:
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(schedule, f, ensure_ascii=False, indent=2)
        f.write("\n")
