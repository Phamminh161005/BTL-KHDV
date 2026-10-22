"""Cấu trúc dữ liệu dùng chung cho toàn hệ thống (bài toán A).

Ký hiệu toán học trong chú thích tham chiếu đến docs/model_spec.md.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Optional

# Một ca thi: (ngày, thứ tự ca trong ngày 1..4)
Slot = tuple[dt.date, int]

# Khung giờ ca theo scope mục 4.2, tính bằng phút từ 0 giờ
PERIOD_TIMES: dict[int, tuple[int, int]] = {
    1: (7 * 60, 9 * 60 + 30),
    2: (9 * 60 + 40, 12 * 60 + 10),
    3: (13 * 60, 15 * 60 + 30),
    4: (15 * 60 + 40, 18 * 60 + 10),
}
MAX_MINUTES_ONE_PERIOD = 120   # spec A.3: l_c = 1 nếu tau_c <= 120
MAX_MINUTES_TWO_PERIODS = 280  # spec A.3: l_c = 2 nếu 120 < tau_c <= 280


def next_period(slot: Slot) -> Optional[Slot]:
    """t^+ trong spec A.2: ca kế tiếp cùng buổi, chỉ định nghĩa với ca 1 và ca 3."""
    d, k = slot
    return (d, k + 1) if k in (1, 3) else None


@dataclass
class Room:
    room_id: str
    room_type: str              # "normal" (R^V) hoặc "lab" (R^M)
    exam_capacity: int          # kappa_r
    name: str = ""
    building: str = ""
    busy: set[Slot] = field(default_factory=set)   # B^R_r
    source_line: Optional[int] = None              # dòng trong rooms.csv, dùng cho thông báo


@dataclass
class Course:
    course_id: str
    exam_type: str              # "written" (C^V) hoặc "computer" (C^M)
    duration_min: int           # tau_c
    max_sittings: int           # L_c
    name: str = ""
    students: set[str] = field(default_factory=set)  # I_c
    source_line: Optional[int] = None                # dòng trong courses.csv, dùng cho thông báo

    @property
    def num_periods(self) -> int:
        """l_c: số ca mỗi lượt chiếm."""
        return 1 if self.duration_min <= MAX_MINUTES_ONE_PERIOD else 2

    @property
    def room_type(self) -> str:
        """Loại phòng phù hợp, dùng để tính R_c."""
        return "normal" if self.exam_type == "written" else "lab"

    @property
    def splittable(self) -> bool:
        """c thuộc C^P."""
        return self.max_sittings >= 2


@dataclass
class Lecturer:
    lecturer_id: str
    is_proctor: bool
    name: str = ""
    busy: set[Slot] = field(default_factory=set)       # B^G_g
    teaches: set[str] = field(default_factory=set)     # Phi_g


@dataclass
class Instance:
    """Dữ liệu một bài toán sau khi đã đọc và kiểm tra (data_schema mục 4)."""
    name: str
    slots: list[Slot]                 # T, đã sắp xếp
    rooms: dict[str, Room]            # R, đã loại phòng P9
    courses: dict[str, Course]        # C, đã loại môn P2
    lecturers: dict[str, Lecturer]    # mọi giảng viên; G là những người is_proctor
    day_pairs: list[tuple[dt.date, dt.date]]  # Q

    @property
    def proctors(self) -> dict[str, Lecturer]:
        """G."""
        return {g: lec for g, lec in self.lecturers.items() if lec.is_proctor}

    @property
    def days(self) -> list[dt.date]:
        """D."""
        return sorted({d for d, _ in self.slots})

    def rooms_for(self, course_id: str) -> list[str]:
        """R_c."""
        rtype = self.courses[course_id].room_type
        return [r for r, room in self.rooms.items() if room.room_type == rtype]

    def start_slots(self, course_id: str) -> list[Slot]:
        """S_c (spec A.3)."""
        if self.courses[course_id].num_periods == 1:
            return list(self.slots)
        slot_set = set(self.slots)
        return [s for s in self.slots if s[1] in (1, 3) and next_period(s) in slot_set]

    def covered(self, course_id: str, start: Slot) -> list[Slot]:
        """Cov(c, s) (spec A.3)."""
        return [start] if self.courses[course_id].num_periods == 1 else [start, next_period(start)]


@dataclass
class Message:
    """Thông báo khi đọc dữ liệu, kiểm tra trước khi giải hoặc hậu xử lý (data_schema mục 5)."""
    code: str
    level: str                  # "error", "warning" hoặc "info"
    message: str
    file: Optional[str] = None
    line: Optional[int] = None

    def to_dict(self) -> dict:
        return {"code": self.code, "level": self.level, "file": self.file, "line": self.line,
                "message": self.message}


@dataclass
class Sitting:
    """Một lượt thi trong lời giải: cặp (môn, ca bắt đầu) có x_{c,s} = 1."""
    course_id: str
    start: Slot
    rooms: list[str]            # các r có u_{c,r,s} = 1
    students: list[str]         # sinh viên của lượt


@dataclass
class Solution:
    """Lời giải solver trả về, chưa hậu xử lý."""
    sittings: list[Sitting]
    # (room_id, slot) -> danh sách giám thị coi phòng đó ở ca đó (các g có w_{g,r,t} = 1)
    proctoring: dict[tuple[str, Slot], list[str]]


@dataclass
class SolveResult:
    """Giá trị trả về của mọi solver bài toán A (exam_solver, exam_solver_pulp)."""
    status: str                          # OPTIMAL, FEASIBLE, INFEASIBLE, UNKNOWN
    solve_time_sec: float
    objective: Optional[int] = None
    best_bound: Optional[float] = None
    penalties: Optional[dict[str, int]] = None   # khóa "A-S1".."A-S6", giá trị P_1..P_6
    solution: Optional[Solution] = None
    messages: list[Message] = field(default_factory=list)
    solver_name: str = ""
