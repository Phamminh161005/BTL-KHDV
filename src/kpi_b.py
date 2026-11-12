"""KPI and independently recomputed soft penalties for problem B (data_schema 9.11)."""
from __future__ import annotations

from src.instance_b import InstanceB, WeekSlot


def _slot(session: dict) -> WeekSlot:
    return session["weekday"], session["period"]


def compute_penalties(instance: InstanceB, timetable: dict, rho: float = 0.85) -> dict[str, int]:
    """Recalculate the four unweighted B penalties from scheduled sessions."""
    sessions = [s for s in timetable["sessions"]
                if s["class_id"] in instance.classes and s["room_id"] in instance.rooms]
    waste = sum(instance.rooms[s["room_id"]].capacity - instance.classes[s["class_id"]].size
                for s in sessions)
    avoid = sum(_slot(s) in instance.lecturers[instance.classes[s["class_id"]].lecturer_id].avoid
                for s in sessions)
    class_days: dict[tuple[str, int], int] = {}
    lab_slots: dict[WeekSlot, int] = {}
    for s in sessions:
        key = (s["class_id"], s["weekday"])
        class_days[key] = class_days.get(key, 0) + 1
        if instance.classes[s["class_id"]].needs_lab:
            slot = _slot(s)
            lab_slots[slot] = lab_slots.get(slot, 0) + 1
    extra = sum(max(0, count - 1) for count in class_days.values())
    over = sum(max(0, count - instance.lab_limit(slot, rho)) for slot, count in lab_slots.items()
               if slot in instance.slots)
    return {"B-S1": waste, "B-S2": avoid, "B-S3": extra, "B-S4": over}


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
