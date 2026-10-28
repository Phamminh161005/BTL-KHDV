"""Sinh dữ liệu giả lập cho bài toán A theo docs/data_schema.md.

Người phụ trách: Khỏe (task KHOE-1).

Cách chạy:
    py -m src.generator --size medium --seed 1 --out data/medium
    py -m src.generator --size toy --seed 1 --out data/toy_gen

Quy mô theo docs/scope.md mục 3:
    toy    5 môn,  3 phòng (1 phòng máy),  ~50 sinh viên
    medium 30 môn, 10 phòng (3 phòng máy), ~500 sinh viên
    large  60 môn, 15 phòng (4 phòng máy), ~1.000 sinh viên

Cách sinh (tóm tắt, chi tiết ở các hàm bên dưới):
    1. Lịch: toy 6 ngày (1 tuần), medium/large 2 tuần (Thứ 2 – Thứ 7), mỗi ngày 4 ca, bỏ đi 1 ca nghỉ lễ.
    2. Phòng: sinh trước để biết tổng sức chứa.
    3. Môn: khoảng 1/3 thi máy; thời lượng chủ yếu 60/90/120, vài môn 150–180 phút.
    4. Sinh viên chia theo khóa/ngành (cohort). Mỗi cohort có một "rổ" môn; sinh viên cùng cohort
       học nhiều môn giống nhau. Mỗi sinh viên học 4–6 môn.
    5. Sĩ số từng môn bị chặn theo sức chứa phòng, để không vi phạm kiểm tra P5 của data_loader.
    6. Giảng viên: mỗi môn 1–2 giảng viên; khoảng 10% ca bận của phòng và giảng viên.

Cùng (size, seed) luôn cho đúng cùng một bộ dữ liệu: mọi lựa chọn ngẫu nhiên đi qua một đối tượng
random.Random duy nhất, và không có chỗ nào duyệt qua set/dict theo thứ tự không xác định.

Lưu ý: generator giả định cấu hình mặc định (written_capacity_ratio = 0.5,
default_max_sittings_computer = 3, proctors_per_room = 2). Nếu đổi các giá trị này trong
configs/*.json, hãy sinh lại hoặc kiểm tra lại dữ liệu.

data/toy là bộ tham chiếu viết tay dùng cho kiểm thử, nên script từ chối ghi vào thư mục có tên
"toy" (trừ khi có --force). Bộ toy do script sinh nên ghi vào data/toy_gen.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import os
import random
import sys
from dataclasses import dataclass
from typing import Optional

START_DATE = dt.date(2026, 12, 14)

DEFAULT_MAX_SITTINGS_COMPUTER = 3
WRITTEN_RATIO = 0.5
MIN_COURSES_PER_STUDENT = 4
MAX_COURSES_PER_STUDENT = 6
BUSY_RATE = 0.10  # tỷ lệ ca bận của mỗi phòng/giảng viên
COMPUTER_FRACTION = 1 / 3
MIN_COURSE_SIZE = 5  # sĩ số tối thiểu của một môn


@dataclass(frozen=True)
class Spec:
    courses: int
    students: int
    cohorts: int  # số khóa/ngành
    general: int  # số môn đại cương, mỗi môn thuộc rổ của 2 cohort
    lecturers: int
    days: int  # số ngày thi
    normal_rooms: int
    lab_rooms: int
    seat_choices: tuple[int, ...]  # số ghế phòng thường, chọn ngẫu nhiên
    computer_choices: tuple[int, ...]  # số máy phòng máy, chọn ngẫu nhiên
    override_prob: float  # xác suất một phòng có cột exam_capacity
    split_written_prob: float  # xác suất một môn thi viết được phép chia lượt
    fixed_seats: Optional[tuple[int, ...]] = None
    fixed_computers: Optional[tuple[int, ...]] = None


SIZES: dict[str, Spec] = {
    "toy": Spec(
        courses=5,
        students=50,
        cohorts=2,
        general=2,
        lecturers=8,
        days=6,  # 4–6 môn/SV cần đủ ngày để A-S1 (thi 2 môn/ngày) còn ý nghĩa
        normal_rooms=2,
        lab_rooms=1,
        seat_choices=(),
        computer_choices=(),
        override_prob=0.0,
        split_written_prob=0.0,
        fixed_seats=(100, 80),
        fixed_computers=(30,),
    ),
    "medium": Spec(
        courses=30,
        students=500,
        cohorts=5,
        general=6,
        lecturers=24,
        days=12,
        normal_rooms=7,
        lab_rooms=3,
        seat_choices=(60, 80, 100, 120, 140),
        computer_choices=(20, 24, 28, 30),
        override_prob=0.15,
        split_written_prob=0.10,
    ),
    "large": Spec(
        courses=60,
        students=1000,
        cohorts=8,
        general=12,
        lecturers=40,
        days=12,
        normal_rooms=11,
        lab_rooms=4,
        seat_choices=(60, 80, 100, 120, 140, 160),
        computer_choices=(20, 24, 28, 30, 36),
        override_prob=0.15,
        split_written_prob=0.10,
    ),
}

GENERAL_NAMES = [
    "Giải tích 1",
    "Đại số tuyến tính",
    "Xác suất thống kê",
    "Vật lý đại cương",
    "Triết học Mác-Lênin",
    "Tiếng Anh học thuật",
    "Toán rời rạc",
    "Kinh tế chính trị",
    "Giải tích 2",
    "Vật lý 2",
    "Pháp luật đại cương",
    "Tư tưởng Hồ Chí Minh",
]
SPECIAL_NAMES = [
    "Lập trình hướng đối tượng",
    "Cơ sở dữ liệu",
    "Cấu trúc dữ liệu và giải thuật",
    "Mạng máy tính",
    "Hệ điều hành",
    "Phát triển ứng dụng Web",
    "Công nghệ phần mềm",
    "Trí tuệ nhân tạo",
    "Kiến trúc máy tính",
    "Phân tích thiết kế hệ thống",
    "Học máy",
    "An toàn thông tin",
    "Xử lý ảnh",
    "Điện toán đám mây",
    "Khoa học dữ liệu",
    "Lập trình di động",
    "Kiểm thử phần mềm",
    "Hệ thống nhúng",
    "Truyền thông số",
    "Điện tử số",
    "Xử lý tín hiệu số",
    "Khai phá dữ liệu",
    "Lập trình mạng",
    "Thiết kế giao diện",
    "Quản lý dự án phần mềm",
    "Hệ quản trị cơ sở dữ liệu",
    "Đồ họa máy tính",
    "Khoa học dịch vụ",
    "Thương mại điện tử",
    "Internet vạn vật",
]
FAMILY_NAMES = [
    "Nguyễn",
    "Trần",
    "Lê",
    "Phạm",
    "Hoàng",
    "Vũ",
    "Đặng",
    "Bùi",
    "Đỗ",
    "Ngô",
]
MIDDLE_NAMES = ["Văn", "Thị", "Minh", "Quốc", "Hữu", "Thanh", "Ngọc", "Đức"]
GIVEN_NAMES = [
    "An",
    "Bình",
    "Cường",
    "Dũng",
    "Hà",
    "Hải",
    "Hùng",
    "Lan",
    "Linh",
    "Long",
    "Mai",
    "Nam",
    "Phương",
    "Quang",
    "Sơn",
    "Thảo",
    "Trang",
    "Tuấn",
    "Việt",
    "Yến",
]

ROOM_BUSY_NOTES = ["Bảo trì", "Sự kiện của khoa", "Sửa chữa", ""]
LECTURER_BUSY_NOTES = ["Đi công tác", "Họp hội đồng", "Việc cá nhân", ""]

Slot = tuple[dt.date, int]


# ---------------------------------------------------------------------------
# Lịch thi
# ---------------------------------------------------------------------------


def _exam_days(n: int) -> list[dt.date]:
    """n ngày thi liên tiếp kể từ START_DATE, bỏ Chủ nhật"""
    days: list[dt.date] = []
    day = START_DATE
    while len(days) < n:
        if day.weekday() != 6:
            days.append(day)
        day += dt.timedelta(days=1)
    return days


def _make_slots(
    rng: random.Random, spec: Spec
) -> tuple[list[dt.date], list[Slot], Slot]:
    """Trả về (các ngày, các ca dùng được, ca nghỉ lễ). Ca nghỉ lễ chỉ đơn giản là không có dòng."""
    days = _exam_days(spec.days)
    # Chọn ngày ở giữa đợt thi để ca nghỉ lễ thực sự cắt ngang lịch
    middle = days[1:-1] if len(days) > 2 else days
    holiday = (rng.choice(middle), rng.randint(1, 4))
    slots = [(d, k) for d in days for k in range(1, 5) if (d, k) != holiday]
    return days, slots, holiday


# ---------------------------------------------------------------------------
# Phòng
# ---------------------------------------------------------------------------


def _make_rooms(rng: random.Random, spec: Spec) -> list[dict]:
    rooms: list[dict] = []
    for i in range(spec.normal_rooms):
        building = ("G2", "G3")[i % 2]
        number = 101 + i // 2
        seats = (
            spec.fixed_seats[i] if spec.fixed_seats else rng.choice(spec.seat_choices)
        )
        override = int(seats * 0.6) if rng.random() < spec.override_prob else None
        rooms.append(
            {
                "room_id": f"{building}-{number}",
                "room_name": f"Phòng {number}",
                "building": building,
                "room_type": "normal",
                "seats": seats,
                "num_computers": None,
                "exam_capacity": override,
            }
        )
    for j in range(spec.lab_rooms):
        building = ("G2", "E3")[j % 2]
        computers = (
            spec.fixed_computers[j]
            if spec.fixed_computers
            else rng.choice(spec.computer_choices)
        )
        # 3 máy dự phòng: sức chứa khi thi nhỏ hơn số máy
        override = computers - 3 if rng.random() < spec.override_prob else None
        rooms.append(
            {
                "room_id": f"{building}-LAB{j + 1}",
                "room_name": f"Phòng máy {j + 1}",
                "building": building,
                "room_type": "lab",
                "seats": None,
                "num_computers": computers,
                "exam_capacity": override,
            }
        )
    return rooms


def _exam_capacity(room: dict) -> int:
    """kappa_r, tính đúng như data_schema mục 3.2."""
    if room["exam_capacity"] is not None:
        return room["exam_capacity"]
    if room["room_type"] == "normal":
        return int(room["seats"] * WRITTEN_RATIO)
    return room["num_computers"]


# ---------------------------------------------------------------------------
# Môn thi
# ---------------------------------------------------------------------------

WRITTEN_DURATIONS = ([60, 90, 120, 150, 180], [0.26, 0.32, 0.31, 0.05, 0.06])
COMPUTER_DURATIONS = ([60, 90, 120, 150, 180], [0.30, 0.31, 0.26, 0.04, 0.09])


def _course_name(names: list[str], index: int) -> str:
    base = names[index % len(names)]
    return base if index < len(names) else f"{base} nâng cao"


def _make_courses(rng: random.Random, spec: Spec) -> list[dict]:
    """Môn đầu danh sách là môn đại cương, phần còn lại là môn chuyên ngành."""
    n = spec.courses
    courses: list[dict] = []
    for i in range(n):
        if i < spec.general:
            prefix = ("MAT", "PHY", "POL", "ENG")[i % 4]
            course = {
                "course_id": f"{prefix}{1001 + i}",
                "course_name": _course_name(GENERAL_NAMES, i),
                "group": "general",
            }
        else:
            j = i - spec.general
            prefix = ("INT", "ELE", "ITS")[j % 3]
            course = {
                "course_id": f"{prefix}{2001 + j}",
                "course_name": _course_name(SPECIAL_NAMES, j),
                "group": "special",
            }
        courses.append(course)

    # Khoảng 1/3 số môn thi máy, chỉ chọn trong các môn chuyên ngành
    special = [i for i, c in enumerate(courses) if c["group"] == "special"]
    n_computer = min(len(special), int(n * COMPUTER_FRACTION))
    computer = set(rng.sample(special, n_computer))

    for i, course in enumerate(courses):
        is_computer = i in computer
        course["exam_type"] = "computer" if is_computer else "written"
        durations, weights = COMPUTER_DURATIONS if is_computer else WRITTEN_DURATIONS
        course["duration_min"] = rng.choices(durations, weights)[0]

    # Bảo đảm "vài môn" 150–180 phút (ít nhất ~10% số môn, tối thiểu 1) để lượt thi 2 ca luôn được thử
    target_long = max(1, round(0.1 * n))
    short = [i for i, c in enumerate(courses) if c["duration_min"] <= 120]
    rng.shuffle(short)
    while sum(c["duration_min"] > 120 for c in courses) < target_long and short:
        courses[short.pop()]["duration_min"] = rng.choice([150, 180])

    for course in courses:
        course["max_sittings"] = None  # để trống = lấy mặc định
        if course["exam_type"] == "computer":
            if course["duration_min"] >= 150:
                course["max_sittings"] = rng.choice([2, 3])
            elif rng.random() < 0.5:
                course["max_sittings"] = rng.choice([2, 3, 4])
        elif rng.random() < spec.split_written_prob:
            course["max_sittings"] = 2
    return courses


def _effective_sittings(course: dict) -> int:
    if course["max_sittings"] is not None:
        return course["max_sittings"]
    return 1 if course["exam_type"] == "written" else DEFAULT_MAX_SITTINGS_COMPUTER


def _size_limits(courses: list[dict], total_normal: int, total_lab: int) -> list[int]:
    """Sĩ số tối đa của từng môn, nhỏ hơn giới hạn P5 để solver còn dư địa:
    - Môn thi viết: không quá 60% tổng sức chứa phòng thường (chỉ có 1 lượt).
    - Môn thi máy: không quá 80% của L_c × tổng sức chứa phòng máy, và không quá 2 × tổng sức chứa
      (để vẫn có môn phải chia lượt nhưng không đòi hỏi quá nhiều lượt)."""
    limits = []
    for course in courses:
        if course["exam_type"] == "written":
            limits.append(int(0.6 * total_normal * min(_effective_sittings(course), 1)))
        else:
            limits.append(
                int(min(0.8 * _effective_sittings(course) * total_lab, 2.0 * total_lab))
            )
    return limits


# ---------------------------------------------------------------------------
# Sinh viên và đăng ký môn
# ---------------------------------------------------------------------------


def _cohort_sizes(rng: random.Random, spec: Spec) -> list[int]:
    """Chia đều sinh viên cho các cohort, lệch nhau tối đa khoảng 8% rồi bù để tổng đúng bằng spec.students."""
    base, extra = divmod(spec.students, spec.cohorts)
    sizes = [base + (1 if k < extra else 0) for k in range(spec.cohorts)]
    jitter = base // 12
    for k in range(spec.cohorts - 1):
        delta = rng.randint(-jitter, jitter)
        sizes[k] += delta
        sizes[k + 1] -= delta
    return sizes


def _student_id(cohort: int, seq: int) -> str:
    """Dạng 22020001 = khóa (22) + ngành (02) + số thứ tự (0001), giống ví dụ trong data_schema."""
    return f"{21 + cohort % 4}{1 + cohort // 4:02d}{seq:04d}"


def _build_pools(
    rng: random.Random, spec: Spec, courses: list[dict]
) -> list[list[tuple[int, float]]]:
    """Rổ môn của từng cohort: danh sách (chỉ số môn, trọng số). Môn lõi có trọng số 3, môn tự chọn 1."""
    n, k_total = len(courses), spec.cohorts
    general = [i for i, c in enumerate(courses) if c["group"] == "general"]
    special = [i for i, c in enumerate(courses) if c["group"] == "special"]
    core: list[list[int]] = [[] for _ in range(k_total)]
    elective: list[list[int]] = [[] for _ in range(k_total)]

    for j, i in enumerate(general):  # môn đại cương: chung cho 2 cohort liền nhau
        for k in sorted({j % k_total, (j + 1) % k_total}):
            core[k].append(i)
    for j, i in enumerate(
        special
    ):  # môn chuyên ngành: thuộc 1 cohort, đôi khi thêm 1 cohort nữa
        k = j % k_total
        core[k].append(i)
        if k_total > 1 and rng.random() < 0.35:
            elective[rng.choice([x for x in range(k_total) if x != k])].append(i)

    pools = []
    for k in range(k_total):
        pool = [(i, 3.0) for i in core[k]] + [(i, 1.0) for i in elective[k]]
        in_pool = {i for i, _ in pool}
        others = [i for i in range(n) if i not in in_pool]
        rng.shuffle(others)
        while len(pool) < min(n, 7) and others:  # rổ phải đủ rộng để chọn 4–6 môn
            pool.append((others.pop(), 1.0))
        pools.append(pool)
    return pools


def _make_enrollments(
    rng: random.Random, spec: Spec, courses: list[dict], limits: list[int]
) -> dict[str, list[int]]:
    """Trả về {mã sinh viên: danh sách chỉ số môn}."""
    n = len(courses)
    # Kiểm tra trước: tổng chỗ của mọi môn phải đủ cho số lượt đăng ký tối thiểu (4 môn/SV), nếu không thì
    # không cách nào bù môn cho sinh viên mà không vượt sức chứa phòng.
    needed, available = spec.students * MIN_COURSES_PER_STUDENT, sum(limits)
    if available < needed:
        raise ValueError(
            f"Sức chứa phòng quá nhỏ: tổng sĩ số tối đa của các môn là {available}, "
            f"nhưng {spec.students} sinh viên × {MIN_COURSES_PER_STUDENT} môn cần {needed} chỗ. "
            f"Hãy tăng số ghế/số máy hoặc giảm số sinh viên."
        )
    pools = _build_pools(rng, spec, courses)
    student_courses: dict[str, list[int]] = {}
    cohort_of: dict[str, int] = {}

    for cohort, size in enumerate(_cohort_sizes(rng, spec)):
        pool = pools[cohort]
        pool_set = {i for i, _ in pool}
        outside = [i for i in range(n) if i not in pool_set]
        for seq in range(1, size + 1):
            m = min(
                rng.randint(MIN_COURSES_PER_STUDENT, MAX_COURSES_PER_STUDENT), len(pool)
            )
            # Chọn m môn không lặp, môn lõi dễ được chọn hơn (khóa Efraimidis–Spirakis)
            keyed = sorted(
                ((rng.random() ** (1.0 / w), i) for i, w in pool), reverse=True
            )
            chosen = [i for _, i in keyed[:m]]
            if (
                outside and rng.random() < 0.08
            ):  # thỉnh thoảng đăng ký một môn ngoài rổ (học vượt, học lại)
                chosen[-1] = rng.choice(outside)
            student_id = _student_id(cohort, seq)
            student_courses[student_id] = chosen
            cohort_of[student_id] = cohort

    _trim_oversized(rng, student_courses, limits)
    _repair_short_students(rng, student_courses, cohort_of, pools, limits)
    _top_up_small(rng, student_courses, n)
    return student_courses


def _count(student_courses: dict[str, list[int]], n: int) -> list[int]:
    count = [0] * n
    for chosen in student_courses.values():
        for i in chosen:
            count[i] += 1
    return count


def _trim_oversized(
    rng: random.Random, student_courses: dict[str, list[int]], limits: list[int]
) -> None:
    """Giảm sĩ số các môn vượt giới hạn. Sinh viên bị bớt một môn mà còn dưới 4 môn thì được bù một môn khác."""
    n = len(limits)
    count = _count(student_courses, n)
    student_ids = sorted(student_courses)
    for c in range(n):
        while count[c] > limits[c]:
            members = [s for s in student_ids if c in student_courses[s]]
            chosen = student_courses[rng.choice(members)]
            chosen.remove(c)
            count[c] -= 1
            if len(chosen) < MIN_COURSES_PER_STUDENT:
                # Ưu tiên môn còn dư chỗ rõ rệt (dưới 90% giới hạn); nếu không có thì chấp nhận môn chưa chạm giới hạn
                candidates = [
                    i
                    for i in range(n)
                    if i not in chosen and i != c and count[i] < 0.9 * limits[i]
                ]
                if not candidates:
                    candidates = [
                        i
                        for i in range(n)
                        if i not in chosen and i != c and count[i] < limits[i]
                    ]
                if candidates:
                    j = rng.choice(candidates)
                    chosen.append(j)
                    count[j] += 1


def _repair_short_students(
    rng: random.Random,
    student_courses: dict[str, list[int]],
    cohort_of: dict[str, int],
    pools: list[list[tuple[int, float]]],
    limits: list[int],
) -> None:
    """Soát lại sau khi cắt: sinh viên nào còn dưới 4 môn thì bổ sung môn còn chỗ trống.

    Thứ tự ưu tiên khi chọn môn bổ sung (đều phải chưa đầy sĩ số và sinh viên chưa học):
      1. Môn trong rổ của chính khóa/ngành đó (phù hợp với chương trình học),
      2. Nếu hết thì môn nào còn chỗ.
    Trong mỗi nhóm chọn môn ít đầy nhất (sĩ số/giới hạn nhỏ nhất) để dàn đều, hòa thì chọn ngẫu nhiên.
    Nếu tổng chỗ trống không đủ thì báo lỗi rõ ràng thay vì để lọt dữ liệu thiếu môn.
    """
    n = len(limits)
    count = _count(student_courses, n)
    short = [
        s
        for s in sorted(student_courses)
        if len(student_courses[s]) < MIN_COURSES_PER_STUDENT
    ]
    missing = sum(MIN_COURSES_PER_STUDENT - len(student_courses[s]) for s in short)
    free_seats = sum(max(0, limits[i] - count[i]) for i in range(n))
    if missing > free_seats:
        raise RuntimeError(
            f"Không đủ chỗ trống để bù môn: còn thiếu {missing} lượt đăng ký "
            f"nhưng các môn chỉ còn {free_seats} chỗ."
        )

    for student_id in short:
        chosen = student_courses[student_id]
        in_pool = {i for i, _ in pools[cohort_of[student_id]]}
        while len(chosen) < MIN_COURSES_PER_STUDENT:
            open_courses = [
                i for i in range(n) if i not in chosen and count[i] < limits[i]
            ]
            if not open_courses:
                raise RuntimeError(
                    f"Không còn môn nào còn chỗ để bù cho sinh viên {student_id}."
                )
            preferred = [i for i in open_courses if i in in_pool] or open_courses
            lowest = min(count[i] / limits[i] for i in preferred)
            pick = rng.choice(
                [i for i in preferred if count[i] / limits[i] <= lowest + 0.05]
            )
            chosen.append(pick)
            count[pick] += 1


def _top_up_small(
    rng: random.Random, student_courses: dict[str, list[int]], n: int
) -> None:
    """Phòng hờ: môn có quá ít sinh viên thì thêm sinh viên (hầu như không xảy ra với các rổ ở trên)."""
    count = _count(student_courses, n)
    student_ids = sorted(student_courses)
    for c in range(n):
        while count[c] < MIN_COURSE_SIZE:
            free = [
                s
                for s in student_ids
                if c not in student_courses[s]
                and len(student_courses[s]) < MAX_COURSES_PER_STUDENT
            ]
            if not free:
                break
            student_courses[rng.choice(free)].append(c)
            count[c] += 1


# ---------------------------------------------------------------------------
# Giảng viên, giảng dạy, ca bận
# ---------------------------------------------------------------------------


def _make_lecturers(rng: random.Random, spec: Spec) -> list[dict]:
    ids = [f"GV{i + 1:02d}" for i in range(spec.lecturers)]
    non_proctors = set(
        rng.sample(ids, round(0.1 * spec.lecturers))
    )  # khoảng 10% không coi thi (bận cả đợt)
    names: set[str] = set()
    lecturers = []
    for lecturer_id in ids:
        while True:
            name = f"{rng.choice(FAMILY_NAMES)} {rng.choice(MIDDLE_NAMES)} {rng.choice(GIVEN_NAMES)}"
            if name not in names:
                names.add(name)
                break
        lecturers.append(
            {
                "lecturer_id": lecturer_id,
                "lecturer_name": name,
                "is_proctor": 0 if lecturer_id in non_proctors else 1,
            }
        )
    return lecturers


def _make_teaching(
    rng: random.Random, courses: list[dict], lecturers: list[dict]
) -> list[tuple[str, str]]:
    """Mỗi môn 1 giảng viên (70%) hoặc 2 giảng viên (30%)."""
    ids = [lec["lecturer_id"] for lec in lecturers]
    rows = []
    for course in courses:
        k = 1 if rng.random() < 0.7 else 2
        for lecturer_id in sorted(rng.sample(ids, k)):
            rows.append((lecturer_id, course["course_id"]))
    return rows


def _busy_slots(
    rng: random.Random, days: list[dt.date], slots: list[Slot]
) -> list[tuple[dt.date, Optional[int]]]:
    """Ca bận của một phòng hoặc giảng viên, khoảng BUSY_RATE tổng số ca.

    Hai kiểu, để thử cả dòng "bận cả ngày" (period để trống) lẫn dòng từng ca:
    30% tài nguyên bận cả một ngày (khoảng 8%) cộng thêm vài ca lẻ (2%); phần còn lại mỗi ca bận độc lập
    với xác suất 10%. Đợt thi dưới 6 ngày chỉ dùng kiểu thứ hai. Chỉ trả về ca có trong slots.csv nên không gây cảnh báo D10.
    Trả về danh sách (ngày, ca) với ca = None nghĩa là cả ngày.
    """
    by_day: dict[dt.date, list[int]] = {
        d: sorted(k for dd, k in slots if dd == d) for d in days
    }
    busy: set[Slot] = set()
    whole_day: Optional[dt.date] = None
    if (
        len(days) >= 6 and rng.random() < 0.3
    ):  # đợt thi quá ngắn (toy) thì một ngày bận chiếm tỷ lệ quá lớn
        whole_day = rng.choice(days)
        busy |= {(whole_day, k) for k in by_day[whole_day]}
        rate = 0.02
    else:
        rate = BUSY_RATE
    for slot in slots:
        if slot[0] != whole_day and rng.random() < rate:
            busy.add(slot)

    entries: list[tuple[dt.date, Optional[int]]] = []
    for d in days:
        periods = [k for k in by_day[d] if (d, k) in busy]
        if periods and len(periods) == len(by_day[d]) and len(periods) > 1:
            entries.append((d, None))
        else:
            entries.extend((d, k) for k in periods)
    return entries


def _make_unavailability(
    rng: random.Random,
    days: list[dt.date],
    slots: list[Slot],
    rooms: list[dict],
    lecturers: list[dict],
) -> list[list]:
    rows: list[list] = []
    for kind, resources, notes in (
        ("room", [r["room_id"] for r in rooms], ROOM_BUSY_NOTES),
        ("lecturer", [g["lecturer_id"] for g in lecturers], LECTURER_BUSY_NOTES),
    ):
        for resource_id in resources:
            for day, period in _busy_slots(rng, days, slots):
                rows.append(
                    [
                        kind,
                        resource_id,
                        day.isoformat(),
                        "" if period is None else period,
                        rng.choice(notes),
                    ]
                )
    return rows


# ---------------------------------------------------------------------------
# Ghi file
# ---------------------------------------------------------------------------


def _write_csv(path: str, header: list[str], rows: list) -> None:
    # utf-8-sig để Excel trên Windows hiện đúng dấu tiếng Việt; data_loader chấp nhận cả hai dạng
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(header)
        writer.writerows(rows)


def _blank(value) -> object:
    return "" if value is None else value


def generate(size: str, seed: int, out_dir: str, force: bool = False) -> dict:
    """Sinh một bộ dữ liệu cỡ size ("toy", "medium", "large") vào thư mục out_dir.

    Trả về một dict thống kê ngắn (số môn, phòng, sinh viên...) để in ra hoặc kiểm thử.
    """
    if size not in SIZES:
        raise ValueError(f"size phải là một trong {sorted(SIZES)}, gặp {size!r}")
    if os.path.basename(os.path.normpath(out_dir)) == "toy" and not force:
        raise SystemExit(
            "Từ chối ghi vào thư mục 'toy': đó là bộ tham chiếu viết tay. "
            "Hãy ghi bộ toy sinh tự động vào data/toy_gen (hoặc thêm --force nếu thật sự muốn)."
        )

    spec = SIZES[size]
    rng = random.Random(
        f"{size}:{seed}"
    )  # chuỗi → seed ổn định giữa các lần chạy và các phiên bản Python 3

    days, slots, holiday = _make_slots(rng, spec)
    rooms = _make_rooms(rng, spec)
    total_normal = sum(_exam_capacity(r) for r in rooms if r["room_type"] == "normal")
    total_lab = sum(_exam_capacity(r) for r in rooms if r["room_type"] == "lab")
    courses = _make_courses(rng, spec)
    limits = _size_limits(courses, total_normal, total_lab)
    student_courses = _make_enrollments(rng, spec, courses, limits)
    lecturers = _make_lecturers(rng, spec)
    teaching = _make_teaching(rng, courses, lecturers)
    unavailability = _make_unavailability(rng, days, slots, rooms, lecturers)

    os.makedirs(out_dir, exist_ok=True)
    path = lambda name: os.path.join(out_dir, name)  # noqa: E731

    _write_csv(
        path("slots.csv"), ["date", "period"], [[d.isoformat(), k] for d, k in slots]
    )
    _write_csv(
        path("rooms.csv"),
        [
            "room_id",
            "room_name",
            "building",
            "room_type",
            "seats",
            "num_computers",
            "exam_capacity",
        ],
        [
            [
                r["room_id"],
                r["room_name"],
                r["building"],
                r["room_type"],
                _blank(r["seats"]),
                _blank(r["num_computers"]),
                _blank(r["exam_capacity"]),
            ]
            for r in rooms
        ],
    )
    _write_csv(
        path("courses.csv"),
        ["course_id", "course_name", "exam_type", "duration_min", "max_sittings"],
        [
            [
                c["course_id"],
                c["course_name"],
                c["exam_type"],
                c["duration_min"],
                _blank(c["max_sittings"]),
            ]
            for c in courses
        ],
    )
    _write_csv(
        path("enrollments.csv"),
        ["student_id", "course_id"],
        [
            [s, courses[i]["course_id"]]
            for s in sorted(student_courses)
            for i in sorted(student_courses[s], key=lambda i: courses[i]["course_id"])
        ],
    )
    _write_csv(
        path("lecturers.csv"),
        ["lecturer_id", "lecturer_name", "is_proctor"],
        [[g["lecturer_id"], g["lecturer_name"], g["is_proctor"]] for g in lecturers],
    )
    _write_csv(path("teaching.csv"), ["lecturer_id", "course_id"], teaching)
    _write_csv(
        path("unavailability.csv"),
        ["resource_type", "resource_id", "date", "period", "note"],
        unavailability,
    )

    count = _count(student_courses, len(courses))
    per_student = [len(v) for v in student_courses.values()]
    busy_pairs = len(unavailability)
    return {
        "size": size,
        "seed": seed,
        "out_dir": out_dir,
        "courses": len(courses),
        "computer_courses": sum(c["exam_type"] == "computer" for c in courses),
        "long_courses": sum(c["duration_min"] > 120 for c in courses),
        "rooms": len(rooms),
        "lab_rooms": spec.lab_rooms,
        "students": len(student_courses),
        "enrollments": sum(per_student),
        "courses_per_student": (min(per_student), max(per_student)),
        "course_size": (min(count), max(count)),
        "slots": len(slots),
        "holiday": f"{holiday[0]} ca {holiday[1]}",
        "lecturers": len(lecturers),
        "proctors": sum(g["is_proctor"] for g in lecturers),
        "busy_rows": busy_pairs,
        "total_normal_capacity": total_normal,
        "total_lab_capacity": total_lab,
    }


def check(out_dir: str) -> bool:
    """Đọc lại bằng data_loader.load_instance và in thông báo. True nếu không có thông báo mức error."""
    from src.data_loader import (
        load_instance,
    )  # nhập muộn để generator vẫn dùng được khi loader đang sửa

    result = load_instance(out_dir, None)
    for m in result.messages:
        if m.level in ("error", "warning"):
            where = f" ({m.file}:{m.line})" if m.file else ""
            print(f"  [{m.level}] {m.code}{where}: {m.message}")
    errors = [m for m in result.messages if m.level == "error"]
    loader_ok = result.ok and not errors
    print(
        f"  load_instance: {'OK' if loader_ok else 'LỖI'} "
        f"({len(errors)} error, {sum(m.level == 'warning' for m in result.messages)} warning)"
    )
    if not loader_ok:
        return False

    # Yêu cầu của task T1, không thuộc schema nên data_loader không kiểm tra
    bad = students_outside_range(result.instance)
    if bad:
        print(
            f"  số môn/SV: LỖI, {len(bad)} sinh viên ngoài khoảng "
            f"{MIN_COURSES_PER_STUDENT}–{MAX_COURSES_PER_STUDENT} môn, ví dụ: "
            + ", ".join(f"{s} ({n} môn)" for s, n in bad[:5])
        )
        return False
    print(
        f"  số môn/SV: OK (mọi sinh viên học {MIN_COURSES_PER_STUDENT}–{MAX_COURSES_PER_STUDENT} môn)"
    )
    return True


def students_outside_range(instance) -> list[tuple[str, int]]:
    """Các (mã sinh viên, số môn) nằm ngoài khoảng 4–6 môn, sắp theo mã sinh viên."""
    per_student: dict[str, int] = {}
    for course in instance.courses.values():
        for student_id in course.students:
            per_student[student_id] = per_student.get(student_id, 0) + 1
    return sorted(
        (s, n)
        for s, n in per_student.items()
        if not MIN_COURSES_PER_STUDENT <= n <= MAX_COURSES_PER_STUDENT
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Sinh dữ liệu giả lập cho bài toán lịch thi"
    )
    parser.add_argument("--size", choices=["toy", "medium", "large"], required=True)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--out", required=True)
    parser.add_argument(
        "--force", action="store_true", help="cho phép ghi vào thư mục tên 'toy'"
    )
    parser.add_argument(
        "--no-check",
        action="store_true",
        help="không đọc lại bằng data_loader sau khi sinh",
    )
    args = parser.parse_args()

    stats = generate(args.size, args.seed, args.out, force=args.force)
    print(f"Đã sinh bộ '{args.size}' (seed {args.seed}) vào {args.out}")
    print(
        f"  {stats['courses']} môn ({stats['computer_courses']} thi máy, {stats['long_courses']} môn > 120 phút), "
        f"{stats['rooms']} phòng ({stats['lab_rooms']} phòng máy), {stats['students']} sinh viên, "
        f"{stats['enrollments']} lượt đăng ký"
    )
    print(
        f"  {stats['slots']} ca (nghỉ lễ: {stats['holiday']}), {stats['lecturers']} giảng viên "
        f"({stats['proctors']} coi thi), {stats['busy_rows']} dòng ca bận"
    )
    if not args.no_check and not check(args.out):
        sys.exit(1)


if __name__ == "__main__":
    main()
