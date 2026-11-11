"""Đọc bộ dữ liệu bài toán B theo docs/data_schema.md mục 9 và kiểm tra trước khi giải (model_spec B.7).

Cách dùng:
    from src.data_loader_b import load_instance_b
    result = load_instance_b("data/toy_b", "configs/default.json")
    if result.ok:
        instance, config = result.instance, result.config

Hoặc dùng src.data_loader.load_instance với cấu hình có "problem": "B".
"""
from __future__ import annotations

import os
from typing import Optional

from src.config import load_config
from src.data_loader import LoadResult, Row, _Reader
from src.instance import Message
from src.instance_b import ClassB, InstanceB, LecturerB, RoomB, WeekSlot

# Cột bắt buộc và tùy chọn của từng file (data_schema mục 9)
SCHEMA_B = {
    "week_slots.csv": (["weekday", "period"], []),
    "rooms.csv": (["room_id", "room_type"], ["room_name", "building", "seats", "num_computers", "exam_capacity"]),
    "lecturers.csv": (["lecturer_id"], ["lecturer_name", "is_proctor"]),
    "classes.csv": (["class_id", "needs_lab", "size", "sessions_per_week", "lecturer_id"],
                    ["class_name", "course_id"]),
    "class_groups.csv": (["class_id", "group_id"], []),
    "week_unavailability.csv": (["resource_type", "resource_id", "weekday"], ["period", "note"]),
    "preferences.csv": (["lecturer_id", "weekday"], ["period", "note"]),
}
REQUIRED_FILES_B = ["week_slots.csv", "rooms.csv", "lecturers.csv", "classes.csv"]
WEEKDAY_NAMES = {2: "Thứ 2", 3: "Thứ 3", 4: "Thứ 4", 5: "Thứ 5", 6: "Thứ 6", 7: "Thứ 7"}


def load_instance_b(folder: str, config_path: Optional[str] = None) -> LoadResult:
    """Đọc bộ dữ liệu bài toán B, bất kể khóa "problem" trong cấu hình."""
    messages: list[Message] = []
    config = load_config(config_path, messages)
    config["problem"] = "B"
    return read_problem_b(folder, config, messages)


def read_problem_b(folder: str, config: dict, messages: list[Message]) -> LoadResult:
    """Đọc dữ liệu khi cấu hình đã được đọc. Gom hết thông báo, không dừng ở lỗi đầu tiên."""
    rd = _Reader(messages)
    name = os.path.basename(os.path.normpath(folder))
    if config["strategy"] == "two_phase":
        rd.add("D12", "error", "Bài toán B chỉ dùng chiến lược single, không dùng two_phase", "config.json")

    data: dict[str, Optional[list[Row]]] = {}
    for fname in SCHEMA_B:
        path = os.path.join(folder, fname)
        if os.path.exists(path):
            data[fname] = rd.read_csv(path, fname, SCHEMA_B)
        else:
            data[fname] = None
            if fname in REQUIRED_FILES_B:
                rd.add("D01", "error", f"Thiếu file bắt buộc {fname}", fname)
    if any(data[f] is None for f in REQUIRED_FILES_B) or rd.has_error():
        return LoadResult(None, config, messages)

    # Mã xuất hiện trong file, kể cả dòng lỗi: quy tắc tránh lỗi dây chuyền D05 (data_schema mục 5)
    raw_ids = {
        "room": {row.get("room_id", "") for _, row in data["rooms.csv"]},
        "lecturer": {row.get("lecturer_id", "") for _, row in data["lecturers.csv"]},
        "class": {row.get("class_id", "") for _, row in data["classes.csv"]},
    }

    def unusable_ref(kind, value, valid, fname, line, label) -> bool:
        if value in valid:
            return False
        if value not in raw_ids[kind]:
            rd.add("D05", "error", f"{label} '{value}' không tồn tại", fname, line)
        return True

    slots = _read_week_slots(rd, data["week_slots.csv"])
    rooms = _read_rooms_b(rd, data["rooms.csv"])
    lecturers = _read_lecturers_b(rd, data["lecturers.csv"])
    classes = _read_classes(rd, data["classes.csv"], lecturers, unusable_ref)
    groups: dict[str, set[str]] = {}
    if data["class_groups.csv"] is not None:
        groups = _read_class_groups(rd, data["class_groups.csv"], classes, unusable_ref)
    if data["week_unavailability.csv"] is not None:
        _read_week_unavailability(rd, data["week_unavailability.csv"], slots, rooms, lecturers, unusable_ref)
    if data["preferences.csv"] is not None:
        _read_preferences(rd, data["preferences.csv"], slots, lecturers, unusable_ref)
    if rd.has_error():
        return LoadResult(None, config, messages)

    for lec in lecturers.values():
        lec.avoid -= lec.busy        # ca vừa bận vừa không muốn dạy thì coi là bận, không báo (mục 9.7)
    instance = _precheck_b(rd, name, slots, rooms, classes, lecturers, groups, config)
    return LoadResult(instance, config, messages)


def _as_weekday(rd: _Reader, fname, line, value) -> Optional[int]:
    day = rd.as_int(fname, line, "weekday", value)
    if day is not None and not 2 <= day <= 7:
        rd.add("D03", "error", f"weekday phải từ 2 đến 7, gặp {day}", fname, line)
        return None
    return day


def _when(day: int, period: Optional[int]) -> str:
    return f"{WEEKDAY_NAMES[day]} ca {period}" if period is not None else f"cả {WEEKDAY_NAMES[day]}"


def _read_week_slots(rd: _Reader, rows: list[Row]) -> set[WeekSlot]:
    fname = "week_slots.csv"
    slots: set[WeekSlot] = set()
    for line, row in rows:
        day = _as_weekday(rd, fname, line, rd.required(fname, line, row, "weekday"))
        period = rd.as_period(fname, line, rd.required(fname, line, row, "period"))
        if day is None or period is None:
            continue
        if (day, period) in slots:
            rd.add("D04", "error", f"Trùng ca {_when(day, period)}", fname, line)
        slots.add((day, period))
    return slots


def _read_rooms_b(rd: _Reader, rows: list[Row]) -> dict[str, RoomB]:
    """Sức chứa khi học sigma_r: seats với phòng thường, num_computers với phòng máy (mục 9.3).
    Cột exam_capacity chỉ dùng cho bài toán A nên không đọc."""
    fname = "rooms.csv"
    rooms: dict[str, RoomB] = {}
    for line, row in rows:
        room_id = rd.as_id(fname, line, "room_id", rd.required(fname, line, row, "room_id"))
        room_type = rd.required(fname, line, row, "room_type")
        if room_type is not None and room_type not in ("normal", "lab"):
            rd.add("D03", "error", f"room_type phải là normal hoặc lab, gặp {room_type!r}", fname, line)
            room_type = None
        seats = rd.as_int(fname, line, "seats", row.get("seats", ""), 0)
        computers = rd.as_int(fname, line, "num_computers", row.get("num_computers", ""), 0)
        if room_id is None or room_type is None:
            continue
        if any(row.get(col, "") != "" and val is None for col, val in (("seats", seats), ("num_computers", computers))):
            continue
        if room_id in rooms:
            rd.add("D04", "error", f"Trùng room_id {room_id}", fname, line)
            continue
        if room_type == "normal":
            if computers is not None:
                rd.add("D14", "warning", f"Phòng thường {room_id} có num_computers, bị bỏ qua", fname, line)
            if seats is None:
                rd.add("D08", "error", f"Phòng thường {room_id} thiếu seats", fname, line)
                continue
            capacity = seats
        else:
            if computers is None:
                rd.add("D08", "error", f"Phòng máy {room_id} thiếu num_computers", fname, line)
                continue
            capacity = computers
        rooms[room_id] = RoomB(room_id, room_type, capacity, row.get("room_name", ""), row.get("building", ""),
                               source_line=line)
    return rooms


def _read_lecturers_b(rd: _Reader, rows: list[Row]) -> dict[str, LecturerB]:
    """Cùng định dạng mục 3.5; cột is_proctor vẫn được kiểm tra định dạng nhưng không dùng."""
    fname = "lecturers.csv"
    lecturers: dict[str, LecturerB] = {}
    for line, row in rows:
        lecturer_id = rd.as_id(fname, line, "lecturer_id", rd.required(fname, line, row, "lecturer_id"))
        flag = row.get("is_proctor", "")
        if flag not in ("", "0", "1"):
            rd.add("D03", "error", f"is_proctor phải là 0 hoặc 1, gặp {flag!r}", fname, line)
            continue
        if lecturer_id is None:
            continue
        if lecturer_id in lecturers:
            rd.add("D04", "error", f"Trùng lecturer_id {lecturer_id}", fname, line)
            continue
        lecturers[lecturer_id] = LecturerB(lecturer_id, row.get("lecturer_name", ""))
    return lecturers


def _read_classes(rd: _Reader, rows: list[Row], lecturers, unusable_ref) -> dict[str, ClassB]:
    fname = "classes.csv"
    classes: dict[str, ClassB] = {}
    for line, row in rows:
        class_id = rd.as_id(fname, line, "class_id", rd.required(fname, line, row, "class_id"))
        course_id = row.get("course_id", "")
        course_ok = course_id == "" or rd.as_id(fname, line, "course_id", course_id) is not None
        needs_lab = rd.required(fname, line, row, "needs_lab")
        if needs_lab is not None and needs_lab not in ("0", "1"):
            rd.add("D03", "error", f"needs_lab phải là 0 hoặc 1, gặp {needs_lab!r}", fname, line)
            needs_lab = None
        size = rd.as_int(fname, line, "size", rd.required(fname, line, row, "size"), 1)
        sessions = rd.as_int(fname, line, "sessions_per_week",
                             rd.required(fname, line, row, "sessions_per_week"), 1)
        lecturer_id = rd.as_id(fname, line, "lecturer_id", rd.required(fname, line, row, "lecturer_id"))
        if None in (class_id, needs_lab, size, sessions, lecturer_id) or not course_ok:
            continue
        if class_id in classes:
            rd.add("D04", "error", f"Trùng class_id {class_id}", fname, line)
            continue
        if unusable_ref("lecturer", lecturer_id, lecturers, fname, line, "lecturer_id"):
            continue
        classes[class_id] = ClassB(class_id, needs_lab == "1", size, sessions, lecturer_id,
                                   row.get("class_name", ""), course_id, source_line=line)
    return classes


def _read_class_groups(rd: _Reader, rows: list[Row], classes, unusable_ref) -> dict[str, set[str]]:
    """H -> K_h. Dòng lặp chỉ giữ một dòng, không báo (mục 9.5)."""
    fname = "class_groups.csv"
    groups: dict[str, set[str]] = {}
    for line, row in rows:
        class_id = rd.as_id(fname, line, "class_id", rd.required(fname, line, row, "class_id"))
        group_id = rd.as_id(fname, line, "group_id", rd.required(fname, line, row, "group_id"))
        if class_id is None or group_id is None:
            continue
        if unusable_ref("class", class_id, classes, fname, line, "class_id"):
            continue
        groups.setdefault(group_id, set()).add(class_id)
        classes[class_id].groups.add(group_id)
    return groups


def _read_week_unavailability(rd: _Reader, rows: list[Row], slots, rooms, lecturers, unusable_ref) -> None:
    fname = "week_unavailability.csv"
    for line, row in rows:
        kind = rd.required(fname, line, row, "resource_type")
        if kind is not None and kind not in ("room", "lecturer"):
            rd.add("D03", "error", f"resource_type phải là room hoặc lecturer, gặp {kind!r}", fname, line)
            kind = None
        resource_id = rd.as_id(fname, line, "resource_id", rd.required(fname, line, row, "resource_id"))
        day = _as_weekday(rd, fname, line, rd.required(fname, line, row, "weekday"))
        raw_period = row.get("period", "")
        period = rd.as_period(fname, line, raw_period)
        if kind is None or resource_id is None or day is None or (raw_period != "" and period is None):
            continue
        target = rooms if kind == "room" else lecturers
        if unusable_ref(kind, resource_id, target, fname, line, kind):
            continue
        hit = _slots_hit(slots, day, period)
        if not hit:
            rd.add("D10", "warning", f"Ca bận {_when(day, period)} nằm ngoài lịch tuần, bỏ qua", fname, line)
        target[resource_id].busy |= hit


def _read_preferences(rd: _Reader, rows: list[Row], slots, lecturers, unusable_ref) -> None:
    fname = "preferences.csv"
    for line, row in rows:
        lecturer_id = rd.as_id(fname, line, "lecturer_id", rd.required(fname, line, row, "lecturer_id"))
        day = _as_weekday(rd, fname, line, rd.required(fname, line, row, "weekday"))
        raw_period = row.get("period", "")
        period = rd.as_period(fname, line, raw_period)
        if lecturer_id is None or day is None or (raw_period != "" and period is None):
            continue
        if unusable_ref("lecturer", lecturer_id, lecturers, fname, line, "lecturer_id"):
            continue
        hit = _slots_hit(slots, day, period)
        if not hit:
            rd.add("D10", "warning", f"Ca không muốn dạy {_when(day, period)} nằm ngoài lịch tuần, bỏ qua",
                   fname, line)
        lecturers[lecturer_id].avoid |= hit


def _slots_hit(slots: set[WeekSlot], day: int, period: Optional[int]) -> set[WeekSlot]:
    periods = [period] if period is not None else [1, 2, 3, 4]
    return {(day, k) for k in periods if (day, k) in slots}


def _precheck_b(rd: _Reader, name, slots, rooms, classes, lecturers, groups, config) -> Optional[InstanceB]:
    """Kiểm tra P9, PB1–PB7 (model_spec B.7, data_schema mục 9.10) và dựng InstanceB."""
    for room_id in [r for r, room in rooms.items() if room.capacity <= 0]:
        rd.add("P9", "warning", f"Phòng {room_id} có sức chứa khi học bằng 0, đã loại", "rooms.csv",
               rooms[room_id].source_line)
        del rooms[room_id]
    if not classes or not rooms or not slots:
        rd.add("D15", "error", "Sau khi lọc không còn lớp, phòng hoặc ca nào để xếp")
        return None

    instance = InstanceB(
        name=name,
        slots=sorted(slots),
        rooms=rooms,
        classes=classes,
        lecturers=lecturers,
        groups={h: sorted(ks) for h, ks in sorted(groups.items())},
    )
    fname = "classes.csv"
    num_days = len(instance.days)
    for class_id, cls in classes.items():
        room_ids = instance.rooms_for(class_id)
        if not room_ids:
            kind = "phòng máy" if cls.needs_lab else "phòng thường"
            rd.add("PB1", "error", f"Lớp {class_id} ({cls.size} sinh viên) không có {kind} nào đủ chỗ",
                   fname, cls.source_line)
            continue
        usable = set().union(*(instance.slots_for(class_id, r) for r in room_ids))
        if len(usable) < cls.sessions:
            rd.add("PB2", "error", f"Lớp {class_id} cần {cls.sessions} buổi/tuần nhưng chỉ có {len(usable)} ca "
                                   f"dùng được", fname, cls.source_line)
        if cls.sessions > num_days:
            rd.add("PB6", "info", f"Lớp {class_id} có {cls.sessions} buổi/tuần, nhiều hơn {num_days} ngày học: "
                                  f"B-S3 không thể bằng 0 với lớp này", fname, cls.source_line)

    for lecturer_id, class_ids in instance.teaching.items():
        need = sum(classes[k].sessions for k in class_ids)
        free = len([t for t in instance.slots if t not in lecturers[lecturer_id].busy])
        if need > free:
            rd.add("PB3", "error", f"Giảng viên {lecturer_id} dạy {need} buổi/tuần nhưng chỉ rảnh {free} ca",
                   "lecturers.csv")

    for group_id, class_ids in instance.groups.items():
        need = sum(classes[k].sessions for k in class_ids)
        if need > len(instance.slots):
            rd.add("PB4", "error", f"Nhóm {group_id} có {need} buổi bắt buộc/tuần, nhiều hơn {len(instance.slots)} "
                                   f"ca trong tuần", "class_groups.csv")

    for room_type, label in (("lab", "phòng máy"), ("normal", "phòng thường")):
        need = sum(cls.sessions for cls in classes.values() if cls.room_type == room_type)
        supply = sum(len([t for t in instance.slots if t not in room.busy])
                     for room in rooms.values() if room.room_type == room_type)
        if need > supply:
            rd.add("PB5", "error", f"Cần {need} buổi {label}/tuần nhưng chỉ có {supply} cặp ({label}, ca) không bận")

    rho = config["lab_reserve_ratio"]
    lab_need = sum(cls.sessions for cls in classes.values() if cls.needs_lab)
    lab_supply = sum(instance.labs_available(t) for t in instance.slots)
    if lab_supply > 0 and lab_need / lab_supply > rho:
        rd.add("PB7", "warning", f"Hệ số sử dụng phòng máy cả tuần là {lab_need}/{lab_supply} = "
                                 f"{lab_need / lab_supply:.0%}, lớn hơn ngưỡng {rho:.0%}: không thể chừa phòng máy "
                                 f"dự phòng ở mọi ca")
    return None if rd.has_error() else instance
