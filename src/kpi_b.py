"""KPI bài toán B (data_schema mục 9.11), tính lại từ lịch và dữ liệu đầu vào, không tin số đính kèm trong JSON.

Điểm phạt B-S1..B-S4 tính lại bằng validator_b.compute_penalties_b; compute_penalties ở đây chỉ là tên gọi tắt.
"""
from __future__ import annotations

from src.instance_b import InstanceB, WeekSlot
from src.validator_b import compute_penalties_b


def _slot(session: dict) -> WeekSlot:
    return session["weekday"], session["period"]


def compute_penalties(instance: InstanceB, timetable: dict, rho: float = 0.85) -> dict[str, int]:
    """P^B_1..P^B_4 chưa nhân trọng số, xem validator_b.compute_penalties_b."""
    return compute_penalties_b(instance, timetable, rho)


def compute_kpi(instance: InstanceB, timetable: dict, hard_violations: int) -> dict:
    """Calculate weekly room, lab reserve, class and group indicators."""
    sessions = timetable["sessions"]
    occupied = {(s["room_id"], _slot(s)) for s in sessions
                if s["room_id"] in instance.rooms and _slot(s) in instance.slots}

    def utilization(room_type: str) -> float | None:
        rooms = {rid for rid, room in instance.rooms.items() if room.room_type == room_type}
        available = sum(slot not in instance.rooms[rid].busy for rid in rooms for slot in instance.slots)
        if not available:
            return None
        return round(sum(rid in rooms for rid, _ in occupied) / available, 4)

    lab_rooms = set(instance.lab_rooms)
    lab_usage: dict[WeekSlot, int] = {}
    for rid, slot in occupied:
        if rid in lab_rooms:
            lab_usage[slot] = lab_usage.get(slot, 0) + 1
    lab_ratios = [lab_usage.get(slot, 0) / available for slot in instance.slots
                  if (available := instance.labs_available(slot)) > 0]
    rho = timetable.get("meta", {}).get("config", {}).get("lab_reserve_ratio", 0.85)
    without_reserve = sum(lab_usage.get(slot, 0) > instance.lab_limit(slot, rho)
                          for slot in instance.slots)

    valid = [s for s in sessions if s["class_id"] in instance.classes and s["room_id"] in instance.rooms]
    seats = sum(instance.rooms[s["room_id"]].capacity for s in valid)
    students = sum(instance.classes[s["class_id"]].size for s in valid)
    preference = sum(_slot(s) in instance.lecturers[instance.classes[s["class_id"]].lecturer_id].avoid
                     for s in valid)
    class_days: dict[tuple[str, int], int] = {}
    group_days: dict[tuple[str, int], int] = {}
    groups_by_class: dict[str, set[str]] = {}
    for group, class_ids in instance.groups.items():
        for class_id in class_ids:
            groups_by_class.setdefault(class_id, set()).add(group)
    for s in valid:
        key = (s["class_id"], s["weekday"])
        class_days[key] = class_days.get(key, 0) + 1
        for group in groups_by_class.get(s["class_id"], ()):
            group_key = (group, s["weekday"])
            group_days[group_key] = group_days.get(group_key, 0) + 1

    return {
        "hard_violations": hard_violations,
        "room_utilization_normal": utilization("normal"),
        "room_utilization_lab": utilization("lab"),
        "lab_peak_utilization": round(max(lab_ratios), 4) if lab_ratios else None,
        "slots_without_lab_reserve": without_reserve,
        "seat_fill_rate": round(students / seats, 4) if seats else None,
        "preference_violations": preference,
        "classes_same_day": len({class_id for (class_id, _), count in class_days.items() if count >= 2}),
        "group_max_sessions_per_day": max(group_days.values(), default=0) if instance.groups else None,
        "solve_time_sec": timetable["solve_time_sec"],
    }
