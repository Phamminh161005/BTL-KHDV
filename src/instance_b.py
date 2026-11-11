"""Cấu trúc dữ liệu của bài toán B: lịch phòng học/phòng máy theo tuần.

Ký hiệu toán học trong chú thích tham chiếu đến docs/model_spec.md mục B. Thông báo (Message) và kết quả solver
(SolveResult) dùng chung với bài toán A, xem src/instance.py.

Giao ước với solver bài toán B (src/room_solver.py):
    solve(instance: InstanceB, config: dict) -> SolveResult
    - SolveResult.solution là một SolutionB, mỗi Session ứng với một biến y_{k,r,t} = 1.
    - SolveResult.penalties có khóa "B-S1".."B-S4", giá trị P^B_1..P^B_4 chưa nhân trọng số.
    - Trọng số lấy từ config["weights"]["B-S1".."B-S4"], rho lấy từ config["lab_reserve_ratio"].
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

# Một ca học trong tuần: (thứ 2..7, ca trong ngày 1..4)
WeekSlot = tuple[int, int]


@dataclass
class RoomB:
    room_id: str
    room_type: str              # "normal" (R^V) hoặc "lab" (R^M)
    capacity: int               # sigma_r: số ghế với phòng thường, số máy với phòng máy
    name: str = ""
    building: str = ""
    busy: set[WeekSlot] = field(default_factory=set)   # B^R_r
    source_line: Optional[int] = None                  # dòng trong rooms.csv, dùng cho thông báo


@dataclass
class ClassB:
    class_id: str
    needs_lab: bool             # True: k thuộc K^M, False: k thuộc K^V
    size: int                   # n_k
    sessions: int               # h_k
    lecturer_id: str            # g(k)
    name: str = ""
    course_id: str = ""         # chỉ để hiển thị
    groups: set[str] = field(default_factory=set)      # các nhóm h có k thuộc K_h
    source_line: Optional[int] = None                  # dòng trong classes.csv

    @property
    def room_type(self) -> str:
        return "lab" if self.needs_lab else "normal"


@dataclass
class LecturerB:
    lecturer_id: str
    name: str = ""
    busy: set[WeekSlot] = field(default_factory=set)    # B^G_g
    avoid: set[WeekSlot] = field(default_factory=set)   # A_g, đã bỏ các ca nằm trong busy


@dataclass
class InstanceB:
    """Dữ liệu bài toán B sau khi đã đọc và kiểm tra (data_schema mục 9.9)."""
    name: str
    slots: list[WeekSlot]               # T, đã sắp xếp
    rooms: dict[str, RoomB]             # R, đã loại phòng P9
    classes: dict[str, ClassB]          # K
    lecturers: dict[str, LecturerB]     # mọi giảng viên trong lecturers.csv; G là những người có lớp
    groups: dict[str, list[str]]        # H -> K_h, các class_id đã sắp xếp

    @property
    def days(self) -> list[int]:
        """W."""
        return sorted({d for d, _ in self.slots})

    def slots_on(self, day: int) -> list[WeekSlot]:
        """T_d."""
        return [s for s in self.slots if s[0] == day]

    @property
    def teaching(self) -> dict[str, list[str]]:
        """G -> K_g: giảng viên có ít nhất một lớp và các lớp của họ."""
        result: dict[str, list[str]] = {}
        for k, cls in sorted(self.classes.items()):
            result.setdefault(cls.lecturer_id, []).append(k)
        return result

    @property
    def lab_rooms(self) -> list[str]:
        """R^M."""
        return [r for r, room in self.rooms.items() if room.room_type == "lab"]

    def rooms_for(self, class_id: str) -> list[str]:
        """R_k: phòng đúng loại và đủ chỗ (B-H3, B-H4)."""
        cls = self.classes[class_id]
        return [r for r, room in self.rooms.items() if room.room_type == cls.room_type and room.capacity >= cls.size]

    def slots_for(self, class_id: str, room_id: str) -> list[WeekSlot]:
        """T_{k,r}: ca không bận của phòng r và của giảng viên lớp k (B-H5, B-H6)."""
        busy = self.rooms[room_id].busy | self.lecturers[self.classes[class_id].lecturer_id].busy
        return [t for t in self.slots if t not in busy]

    def labs_available(self, slot: WeekSlot) -> int:
        """m_t: số phòng máy không bận ở ca t."""
        return sum(1 for r in self.lab_rooms if slot not in self.rooms[r].busy)

    def lab_limit(self, slot: WeekSlot, rho: float) -> int:
        """m̄_t = floor(rho * m_t). Cộng 1e-9 để tránh sai số dấu phẩy động, ví dụ 0,85 × 20 = 16,999..."""
        return math.floor(rho * self.labs_available(slot) + 1e-9)


@dataclass
class Session:
    """Một buổi học trong lời giải: bộ (k, r, t) có y_{k,r,t} = 1."""
    class_id: str
    room_id: str
    slot: WeekSlot


@dataclass
class SolutionB:
    """Lời giải solver bài toán B trả về, chưa hậu xử lý."""
    sessions: list[Session]
