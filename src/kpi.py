"""Tính KPI (data_schema mục 7.4) và tính lại điểm phạt P_1..P_6 (model_spec A.6) từ schedule.json.

Hàm compute_penalties dùng để đối chiếu với điểm phạt solver báo: hai con số phải bằng nhau.
"""
from __future__ import annotations

import datetime as dt
from typing import Optional

from src.instance import Instance


def _starts_per_student_day(schedule: dict) -> dict[tuple[str, str], int]:
    count: dict[tuple[str, str], int] = {}
    for s in schedule["sittings"]:
        for room in s["rooms"]:
            for i in room["students"]:
                count[(i, s["date"])] = count.get((i, s["date"]), 0) + 1
    return count


def _proctor_loads(instance: Instance, schedule: dict) -> dict[str, int]:
    loads = {g: 0 for g in instance.proctors}
    for s in schedule["sittings"]:
        for room in s["rooms"]:
            for g in room["proctors"]:
                if g in loads:
                    loads[g] += len(s["periods"])
    return loads


def compute_penalties(instance: Instance, schedule: dict) -> dict[str, int]:
    """P_1..P_6 theo định nghĩa model_spec A.6, tính lại từ lịch."""
    starts = _starts_per_student_day(schedule)
    students = {i for c in instance.courses.values() for i in c.students}
    days = [d.isoformat() for d in instance.days]
    pairs = [(a.isoformat(), b.isoformat()) for a, b in instance.day_pairs]
    p1 = sum(max(0, starts.get((i, d), 0) - 1) for i in students for d in days)
    p2 = sum(max(0, starts.get((i, a), 0) + starts.get((i, b), 0) - 1) for i in students for a, b in pairs)
    p3 = sum(len(s["rooms"]) - 1 for s in schedule["sittings"])
    p4 = sum(len(s["periods"]) * (sum(r["exam_capacity"] for r in s["rooms"]) - s["num_students"])
             for s in schedule["sittings"])
    loads = _proctor_loads(instance, schedule)
    p5 = (max(loads.values()) - min(loads.values())) if loads else 0
    per_course = {}
    for s in schedule["sittings"]:
        per_course[s["course_id"]] = per_course.get(s["course_id"], 0) + 1
    p6 = sum(per_course.get(c, 0) - 1 for c in instance.courses)
    return {"A-S1": p1, "A-S2": p2, "A-S3": p3, "A-S4": p4, "A-S5": p5, "A-S6": p6}


def compute_kpi(instance: Instance, schedule: dict, hard_violations: int) -> dict:
    sittings = schedule["sittings"]

    starts = _starts_per_student_day(schedule)
    multi = {i for (i, _), n in starts.items() if n >= 2}

    dates_of: dict[str, list[dt.date]] = {}
    for s in sittings:
        for room in s["rooms"]:
            for i in room["students"]:
                dates_of.setdefault(i, []).append(dt.date.fromisoformat(s["date"]))
    gaps_avg, gaps_min = [], []
    for dates in dates_of.values():
        if len(dates) >= 2:
            dates.sort()
            gaps = [(b - a).days for a, b in zip(dates, dates[1:])]
            gaps_avg.append(sum(gaps) / len(gaps))
            gaps_min.append(min(gaps))

    loads = _proctor_loads(instance, schedule)

    def utilization(room_type: str) -> Optional[float]:
        rooms = [r for r in instance.rooms.values() if r.room_type == room_type]
        available = sum(1 for r in rooms for t in instance.slots if t not in r.busy)
        if available == 0:
            return None
        used = sum(len(s["periods"]) for s in sittings for room in s["rooms"]
                   if room["room_id"] in instance.rooms and instance.rooms[room["room_id"]].room_type == room_type)
        return round(used / available, 4)

    seat_ca = sum(len(s["periods"]) * sum(r["exam_capacity"] for r in s["rooms"]) for s in sittings)
    student_ca = sum(len(s["periods"]) * s["num_students"] for s in sittings)

    return {
        "hard_violations": hard_violations,
        "students_multi_exam_day": len(multi),
        "avg_gap_days": round(sum(gaps_avg) / len(gaps_avg), 3) if gaps_avg else None,
        "min_gap_days": min(gaps_min) if gaps_min else None,
        "proctor_load_min": min(loads.values()) if loads else None,
        "proctor_load_max": max(loads.values()) if loads else None,
        "proctor_load_range": (max(loads.values()) - min(loads.values())) if loads else None,
        "num_sittings": len(sittings),
        "room_utilization_normal": utilization("normal"),
        "room_utilization_lab": utilization("lab"),
        "seat_fill_rate": round(student_ca / seat_ca, 4) if seat_ca else None,
        "solve_time_sec": schedule["solve_time_sec"],
    }
