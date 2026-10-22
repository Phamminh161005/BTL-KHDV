"""Đọc một bộ dữ liệu theo docs/data_schema.md và kiểm tra trước khi giải (model_spec A.8).

Cách dùng:
    from src.data_loader import load_instance
    result = load_instance("data/toy", "configs/default.json")
    if result.ok:
        instance, config = result.instance, result.config
"""
from __future__ import annotations

import csv
import datetime as dt
import io
import math
import os
import re
from dataclasses import dataclass, field
from typing import Optional

from src.config import load_config
from src.instance import Course, Instance, Lecturer, Message, Room

ID_RE = re.compile(r"^[A-Za-z0-9_.\-]{1,50}$")
INT_RE = re.compile(r"^-?\d+$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# Cột bắt buộc và tùy chọn của từng file (data_schema mục 3)
SCHEMA = {
    "slots.csv": (["date", "period"], []),
    "rooms.csv": (["room_id", "room_type"], ["room_name", "building", "seats", "num_computers", "exam_capacity"]),
    "courses.csv": (["course_id", "exam_type", "duration_min"], ["course_name", "max_sittings"]),
    "enrollments.csv": (["student_id", "course_id"], []),
    "lecturers.csv": (["lecturer_id"], ["lecturer_name", "is_proctor"]),
    "teaching.csv": (["lecturer_id", "course_id"], []),
    "unavailability.csv": (["resource_type", "resource_id", "date"], ["period", "note"]),
}
REQUIRED_FILES = ["slots.csv", "rooms.csv", "courses.csv", "enrollments.csv", "lecturers.csv"]

Row = tuple[int, dict]  # (số dòng trong file, tiêu đề là dòng 1; giá trị các cột)


@dataclass
class LoadResult:
    instance: Optional[Instance]
    config: dict
    messages: list[Message] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.instance is not None


class _Reader:
    """Gom thông báo và các hàm đọc giá trị dùng chung cho mọi file."""

    def __init__(self, messages: list[Message]):
        self.messages = messages

    def add(self, code, level, message, file=None, line=None):
        self.messages.append(Message(code, level, message, file, line))

    def has_error(self) -> bool:
        return any(m.level == "error" for m in self.messages)

    def read_csv(self, path: str, fname: str) -> Optional[list[Row]]:
        """Đọc file theo quy ước mục 2. Trả None nếu thiếu cột bắt buộc."""
        with open(path, "rb") as f:
            text = f.read().decode("utf-8-sig")
        first = next((ln for ln in text.splitlines() if ln.strip()), "")
        delimiter = ","
        if ";" in first and "," not in first:
            delimiter = ";"
            self.add("D16", "warning", "File dùng dấu chấm phẩy làm dấu phân cách", fname)

        header: Optional[list[str]] = None
        rows: list[Row] = []
        for lineno, record in enumerate(csv.reader(io.StringIO(text), delimiter=delimiter), start=1):
            if not record or all(not cell.strip() for cell in record):
                continue
            record = [cell.strip() for cell in record]
            if header is None:
                header = [h.lower() for h in record]
                continue
            rows.append((lineno, {header[k]: (record[k] if k < len(record) else "") for k in range(len(header))}))

        required, optional = SCHEMA[fname]
        header = header or []
        for col in required:
            if col not in header:
                self.add("D02", "error", f"Thiếu cột bắt buộc '{col}'", fname)
        for col in header:
            if col not in required + optional:
                self.add("D09", "warning", f"Cột '{col}' không có trong tài liệu, bị bỏ qua", fname)
        return rows if all(col in header for col in required) else None

    def required(self, fname, line, row, col) -> Optional[str]:
        value = row.get(col, "")
        if value == "":
            self.add("D03", "error", f"Cột bắt buộc '{col}' để trống", fname, line)
            return None
        return value

    def as_int(self, fname, line, col, value, minimum=None) -> Optional[int]:
        if value is None or value == "":
            return None
        if not INT_RE.match(value):
            self.add("D03", "error", f"'{col}' phải là số nguyên, gặp {value!r}", fname, line)
            return None
        number = int(value)
        if minimum is not None and number < minimum:
            self.add("D03", "error", f"'{col}' phải ≥ {minimum}, gặp {number}", fname, line)
            return None
        return number

    def as_id(self, fname, line, col, value) -> Optional[str]:
        if value is None:
            return None
        if not ID_RE.match(value):
            self.add("D06", "error", f"Mã '{value}' ở cột '{col}' chứa ký tự không hợp lệ", fname, line)
            return None
        return value

    def as_date(self, fname, line, value) -> Optional[dt.date]:
        if value is None:
            return None
        if DATE_RE.match(value):
            try:
                return dt.date.fromisoformat(value)
            except ValueError:
                pass
        self.add("D03", "error", f"Ngày không đúng dạng YYYY-MM-DD: {value!r}", fname, line)
        return None

    def as_period(self, fname, line, value) -> Optional[int]:
        period = self.as_int(fname, line, "period", value)
        if period is not None and not 1 <= period <= 4:
            self.add("D03", "error", f"period phải từ 1 đến 4, gặp {period}", fname, line)
            return None
        return period


def load_instance(folder: str, config_path: Optional[str] = None) -> LoadResult:
    """Đọc toàn bộ bộ dữ liệu. Không dừng ở lỗi đầu tiên mà gom hết thông báo (data_schema mục 5)."""
    messages: list[Message] = []
    rd = _Reader(messages)
    config = load_config(config_path, messages)
    name = os.path.basename(os.path.normpath(folder))

    data: dict[str, Optional[list[Row]]] = {}
    for fname in SCHEMA:
        path = os.path.join(folder, fname)
        if os.path.exists(path):
            data[fname] = rd.read_csv(path, fname)
        else:
            data[fname] = None
            if fname in REQUIRED_FILES:
                rd.add("D01", "error", f"Thiếu file bắt buộc {fname}", fname)
    if config["forbid_own_course"] and not os.path.exists(os.path.join(folder, "teaching.csv")):
        rd.add("D11", "error", "Bật forbid_own_course nhưng thiếu teaching.csv", "teaching.csv")
    if any(data[f] is None for f in REQUIRED_FILES) or rd.has_error():
        return LoadResult(None, config, messages)

    # Mã xuất hiện trong file, kể cả dòng lỗi: dùng cho quy tắc tránh lỗi dây chuyền D05 (mục 5)
    raw_ids = {
        "room": {row.get("room_id", "") for _, row in data["rooms.csv"]},
        "course": {row.get("course_id", "") for _, row in data["courses.csv"]},
        "lecturer": {row.get("lecturer_id", "") for _, row in data["lecturers.csv"]},
    }

    def unusable_ref(kind, value, valid, fname, line, label) -> bool:
        if value in valid:
            return False
        if value not in raw_ids[kind]:
            rd.add("D05", "error", f"{label} '{value}' không tồn tại", fname, line)
        return True

    slots = _read_slots(rd, data["slots.csv"])
    rooms = _read_rooms(rd, data["rooms.csv"], config)
    courses = _read_courses(rd, data["courses.csv"], config)
    _read_enrollments(rd, data["enrollments.csv"], courses, unusable_ref)
    lecturers = _read_lecturers(rd, data["lecturers.csv"])
    if data["teaching.csv"] is not None:
        _read_teaching(rd, data["teaching.csv"], lecturers, courses, unusable_ref)
    if data["unavailability.csv"] is not None:
        _read_unavailability(rd, data["unavailability.csv"], slots, rooms, lecturers, unusable_ref)
    if rd.has_error():
        return LoadResult(None, config, messages)

    instance = _precheck(rd, name, slots, rooms, courses, lecturers, config)
    return LoadResult(instance, config, messages)


def _read_slots(rd: _Reader, rows: list[Row]) -> set:
    fname = "slots.csv"
    slots = set()
    for line, row in rows:
        day = rd.as_date(fname, line, rd.required(fname, line, row, "date"))
        period = rd.as_period(fname, line, rd.required(fname, line, row, "period"))
        if day is not None and day.weekday() == 6:
            rd.add("D07", "error", f"Ngày {day} là Chủ nhật", fname, line)
            day = None
        if day is None or period is None:
            continue
        if (day, period) in slots:
            rd.add("D04", "error", f"Trùng ca {day} ca {period}", fname, line)
        slots.add((day, period))
    return slots


def _read_rooms(rd: _Reader, rows: list[Row], config: dict) -> dict[str, Room]:
    fname = "rooms.csv"
    rooms: dict[str, Room] = {}
    for line, row in rows:
        room_id = rd.as_id(fname, line, "room_id", rd.required(fname, line, row, "room_id"))
        room_type = rd.required(fname, line, row, "room_type")
        if room_type is not None and room_type not in ("normal", "lab"):
            rd.add("D03", "error", f"room_type phải là normal hoặc lab, gặp {room_type!r}", fname, line)
            room_type = None
        seats = rd.as_int(fname, line, "seats", row.get("seats", ""), 0)
        computers = rd.as_int(fname, line, "num_computers", row.get("num_computers", ""), 0)
        override = rd.as_int(fname, line, "exam_capacity", row.get("exam_capacity", ""))
        if room_id is None or room_type is None:
            continue
        # Ô có giá trị nhưng sai kiểu đã báo D03; không báo thêm D08 (quy tắc tránh lỗi dây chuyền)
        if any(row.get(col, "") != "" and val is None
               for col, val in (("seats", seats), ("num_computers", computers), ("exam_capacity", override))):
            continue
        if room_id in rooms:
            rd.add("D04", "error", f"Trùng room_id {room_id}", fname, line)
            continue
        if room_type == "normal":
            if computers is not None:
                rd.add("D14", "warning", f"Phòng thường {room_id} có num_computers, bị bỏ qua", fname, line)
            if override is None and seats is None:
                rd.add("D08", "error", f"Phòng thường {room_id} thiếu seats và exam_capacity", fname, line)
                continue
            if override is not None and seats is not None and override > seats:
                rd.add("D13", "warning", f"exam_capacity của {room_id} lớn hơn seats", fname, line)
            capacity = override if override is not None else math.floor(seats * config["written_capacity_ratio"])
        else:
            if computers is None:
                rd.add("D08", "error", f"Phòng máy {room_id} thiếu num_computers", fname, line)
                continue
            if override is not None and override > computers:
                rd.add("D13", "warning", f"exam_capacity của {room_id} lớn hơn num_computers", fname, line)
            capacity = override if override is not None else computers
        rooms[room_id] = Room(room_id, room_type, capacity, row.get("room_name", ""), row.get("building", ""),
                              source_line=line)
    return rooms


def _read_courses(rd: _Reader, rows: list[Row], config: dict) -> dict[str, Course]:
    fname = "courses.csv"
    courses: dict[str, Course] = {}
    for line, row in rows:
        course_id = rd.as_id(fname, line, "course_id", rd.required(fname, line, row, "course_id"))
        exam_type = rd.required(fname, line, row, "exam_type")
        if exam_type is not None and exam_type not in ("written", "computer"):
            rd.add("D03", "error", f"exam_type phải là written hoặc computer, gặp {exam_type!r}", fname, line)
            exam_type = None
        duration = rd.as_int(fname, line, "duration_min", rd.required(fname, line, row, "duration_min"), 1)
        max_sittings = rd.as_int(fname, line, "max_sittings", row.get("max_sittings", ""), 1)
        if course_id is None or exam_type is None or duration is None:
            continue
        if row.get("max_sittings", "") != "" and max_sittings is None:
            continue
        if course_id in courses:
            rd.add("D04", "error", f"Trùng course_id {course_id}", fname, line)
            continue
        if duration > 280:
            rd.add("P1", "error", f"Môn {course_id} thi {duration} phút, vượt quá 280 phút", fname, line)
            continue
        if max_sittings is None:
            max_sittings = 1 if exam_type == "written" else config["default_max_sittings_computer"]
        if exam_type == "written" and max_sittings >= 2:
            rd.add("P7", "info", f"Môn thi viết {course_id} được phép chia tối đa {max_sittings} lượt", fname, line)
        courses[course_id] = Course(course_id, exam_type, duration, max_sittings, row.get("course_name", ""),
                                    source_line=line)
    return courses


def _read_enrollments(rd: _Reader, rows: list[Row], courses: dict[str, Course], unusable_ref) -> None:
    fname = "enrollments.csv"
    seen = set()
    for line, row in rows:
        student_id = rd.as_id(fname, line, "student_id", rd.required(fname, line, row, "student_id"))
        course_id = rd.as_id(fname, line, "course_id", rd.required(fname, line, row, "course_id"))
        if student_id is None or course_id is None:
            continue
        if unusable_ref("course", course_id, courses, fname, line, "course_id"):
            continue
        if (student_id, course_id) in seen:
            rd.add("P8", "warning", f"Đăng ký lặp ({student_id}, {course_id}), đã loại", fname, line)
            continue
        seen.add((student_id, course_id))
        courses[course_id].students.add(student_id)


def _read_lecturers(rd: _Reader, rows: list[Row]) -> dict[str, Lecturer]:
    fname = "lecturers.csv"
    lecturers: dict[str, Lecturer] = {}
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
        lecturers[lecturer_id] = Lecturer(lecturer_id, flag != "0", row.get("lecturer_name", ""))
    return lecturers


def _read_teaching(rd: _Reader, rows: list[Row], lecturers, courses, unusable_ref) -> None:
    fname = "teaching.csv"
    for line, row in rows:
        lecturer_id = rd.as_id(fname, line, "lecturer_id", rd.required(fname, line, row, "lecturer_id"))
        course_id = rd.as_id(fname, line, "course_id", rd.required(fname, line, row, "course_id"))
        if lecturer_id is None or course_id is None:
            continue
        bad_lecturer = unusable_ref("lecturer", lecturer_id, lecturers, fname, line, "lecturer_id")
        bad_course = unusable_ref("course", course_id, courses, fname, line, "course_id")
        if not (bad_lecturer or bad_course):
            lecturers[lecturer_id].teaches.add(course_id)


def _read_unavailability(rd: _Reader, rows: list[Row], slots, rooms, lecturers, unusable_ref) -> None:
    fname = "unavailability.csv"
    for line, row in rows:
        kind = rd.required(fname, line, row, "resource_type")
        if kind is not None and kind not in ("room", "lecturer"):
            rd.add("D03", "error", f"resource_type phải là room hoặc lecturer, gặp {kind!r}", fname, line)
            kind = None
        resource_id = rd.as_id(fname, line, "resource_id", rd.required(fname, line, row, "resource_id"))
        day = rd.as_date(fname, line, rd.required(fname, line, row, "date"))
        raw_period = row.get("period", "")
        period = rd.as_period(fname, line, raw_period)
        if kind is None or resource_id is None or day is None or (raw_period != "" and period is None):
            continue
        target = rooms if kind == "room" else lecturers
        if unusable_ref(kind, resource_id, target, fname, line, kind):
            continue
        periods = [period] if period is not None else [1, 2, 3, 4]
        hit = {(day, k) for k in periods if (day, k) in slots}
        if not hit:
            when = f"ca {period}" if period is not None else "cả ngày"
            rd.add("D10", "warning", f"Ca bận {day} {when} nằm ngoài lịch thi, bỏ qua", fname, line)
        target[resource_id].busy |= hit


def _precheck(rd: _Reader, name, slots, rooms, courses, lecturers, config) -> Optional[Instance]:
    """Kiểm tra P2–P6, P9 (model_spec A.8) và dựng Instance."""
    for room_id in [r for r, room in rooms.items() if room.exam_capacity <= 0]:
        rd.add("P9", "warning", f"Phòng {room_id} có sức chứa khi thi ≤ 0, đã loại", "rooms.csv",
               rooms[room_id].source_line)
        del rooms[room_id]
    for course_id in [c for c, course in courses.items() if not course.students]:
        rd.add("P2", "warning", f"Môn {course_id} không có sinh viên đăng ký, đã loại", "courses.csv",
               courses[course_id].source_line)
        del courses[course_id]
    if not courses or not rooms or not slots:
        rd.add("D15", "error", "Sau khi lọc không còn môn, phòng hoặc ca nào để xếp")
        return None

    days = sorted({d for d, _ in slots})
    day_set = set(days)
    instance = Instance(
        name=name,
        slots=sorted(slots),
        rooms=rooms,
        courses=courses,
        lecturers=lecturers,
        day_pairs=[(d, d + dt.timedelta(days=1)) for d in days if d + dt.timedelta(days=1) in day_set],
    )
    for course_id, course in courses.items():
        room_ids = instance.rooms_for(course_id)
        if not room_ids:
            rd.add("P3", "error", f"Môn {course_id} không có phòng phù hợp", "courses.csv", course.source_line)
            continue
        if not instance.start_slots(course_id):
            rd.add("P4", "error", f"Môn {course_id} không có ca bắt đầu hợp lệ", "courses.csv", course.source_line)
            continue
        if len(course.students) > course.max_sittings * sum(rooms[r].exam_capacity for r in room_ids):
            rd.add("P5", "error",
                   f"Môn {course_id} có {len(course.students)} sinh viên, vượt sức chứa tối đa của "
                   f"{course.max_sittings} lượt", "courses.csv", course.source_line)
    if len(instance.proctors) < config["proctors_per_room"]:
        rd.add("P6", "error",
               f"Chỉ có {len(instance.proctors)} giám thị, cần ít nhất {config['proctors_per_room']}")
    return None if rd.has_error() else instance
