"""Kiểm tra lời giải độc lập với solver (model_spec A.10, data_schema mục 7.5).

Validator không dùng lại công thức của mô hình. Nó đọc lịch trong schedule.json và soát trực tiếp theo
luật trong docs/scope.md, tính thời gian bằng giờ đồng hồ thật của từng ca (scope mục 4.2).
Mỗi vi phạm mang đúng mã ràng buộc cứng (A-H1 .. A-H10).
"""
from __future__ import annotations

import datetime as dt
import itertools

from src.instance import PERIOD_TIMES, Instance, Solution

OVERHEAD_MIN = 30  # scope 4.3: 30 phút gọi tên, phát đề, thu bài
SESSION = {1: "sáng", 2: "sáng", 3: "chiều", 4: "chiều"}


def _expected_periods(duration: int, start_period: int):
    """Các ca một lượt phải chiếm, suy ra trực tiếp từ khung giờ (không dùng l_c của mô hình)."""
    start, end = PERIOD_TIMES[start_period]
    if duration + OVERHEAD_MIN <= end - start:
        return [start_period]
    nxt = start_period + 1
    if nxt in PERIOD_TIMES and SESSION[nxt] == SESSION[start_period] \
            and duration + OVERHEAD_MIN <= PERIOD_TIMES[nxt][1] - start:
        return [start_period, nxt]
    return None


def _interval(date: str, periods: list[int]):
    return date, PERIOD_TIMES[periods[0]][0], PERIOD_TIMES[periods[-1]][1]


def _overlap(a, b) -> bool:
    return a[0] == b[0] and a[1] < b[2] and b[1] < a[2]


def validate(instance: Instance, schedule: dict, config: dict) -> list[dict]:
    """Trả về danh sách vi phạm; rỗng nếu lịch hợp lệ."""
    out: list[dict] = []

    def add(code, message, **refs):
        out.append({"code": code, "message": message, "refs": refs})

    sittings = schedule["sittings"]
    slots = {(d.isoformat(), k) for d, k in instance.slots}
    nu = config["proctors_per_room"]

    # A-H1: thời gian của từng lượt và số lượt của từng môn
    occupied = {}
    for s in sittings:
        sid = s["sitting_id"]
        course = instance.courses.get(s["course_id"])
        if course is None:
            add("A-H1", f"Lượt {sid} thuộc môn không có trong dữ liệu", sitting_id=sid)
            continue
        periods = _expected_periods(course.duration_min, s["start_period"])
        if periods is None or periods != s["periods"] or any((s["date"], k) not in slots for k in periods):
            add("A-H1", f"Lượt {sid} không đặt được vào khung ca hợp lệ "
                        f"(thi {course.duration_min} phút, bắt đầu ca {s['start_period']})", sitting_id=sid)
        occupied[sid] = periods or s["periods"]
    by_course = {}
    for s in sittings:
        by_course.setdefault(s["course_id"], []).append(s)
    for course_id, course in instance.courses.items():
        n = len(by_course.get(course_id, []))
        if not 1 <= n <= course.max_sittings:
            add("A-H1", f"Môn {course_id} có {n} lượt, cho phép 1 đến {course.max_sittings}", course_id=course_id)

    # A-H9: mỗi sinh viên thi đúng một lượt của mỗi môn mình đăng ký, không lượt nào rỗng
    for course_id, course in instance.courses.items():
        count = {}
        for s in by_course.get(course_id, []):
            if s["num_students"] == 0:
                add("A-H9", f"Lượt {s['sitting_id']} không có sinh viên", sitting_id=s["sitting_id"])
            for room in s["rooms"]:
                for i in room["students"]:
                    count[i] = count.get(i, 0) + 1
        for i in sorted(course.students):
            if count.get(i, 0) != 1:
                add("A-H9", f"Sinh viên {i} xuất hiện {count.get(i, 0)} lần trong môn {course_id}",
                    student_id=i, course_id=course_id)
        for i in sorted(set(count) - course.students):
            add("A-H9", f"Sinh viên {i} không đăng ký môn {course_id} nhưng có trong lượt thi",
                student_id=i, course_id=course_id)

    # A-H2: không sinh viên nào thi hai lượt trùng thời gian
    per_student = {}
    for s in sittings:
        iv = _interval(s["date"], occupied[s["sitting_id"]])
        for room in s["rooms"]:
            for i in room["students"]:
                per_student.setdefault(i, []).append((iv, s["sitting_id"]))
    for i, items in per_student.items():
        for (a, sa), (b, sb) in itertools.combinations(items, 2):
            if _overlap(a, b):
                add("A-H2", f"Sinh viên {i} thi trùng giờ: {sa} và {sb}", student_id=i, sitting_ids=[sa, sb])

    # A-H3, A-H5: đủ chỗ trong từng phòng, đúng loại phòng
    for s in sittings:
        course = instance.courses.get(s["course_id"])
        for room in s["rooms"]:
            rid = room["room_id"]
            info = instance.rooms.get(rid)
            if info is None:
                add("A-H3", f"Lượt {s['sitting_id']} có {room['num_students']} sinh viên không có phòng",
                    sitting_id=s["sitting_id"])
                continue
            if len(room["students"]) > info.exam_capacity:
                add("A-H3", f"Phòng {rid} của lượt {s['sitting_id']} có {len(room['students'])} sinh viên, "
                            f"sức chứa {info.exam_capacity}", sitting_id=s["sitting_id"], room_id=rid)
            if course is not None and info.room_type != course.room_type:
                add("A-H5", f"Môn {course.course_id} ({course.exam_type}) xếp vào phòng {rid} ({info.room_type})",
                    sitting_id=s["sitting_id"], room_id=rid)

    # A-H4, A-H6: mỗi phòng mỗi ca tối đa một môn, không dùng phòng vào ca bận
    room_use = {}
    for s in sittings:
        for room in s["rooms"]:
            rid = room["room_id"]
            if rid not in instance.rooms:
                continue
            for k in occupied[s["sitting_id"]]:
                room_use.setdefault((rid, s["date"], k), []).append(s["sitting_id"])
                if (dt.date.fromisoformat(s["date"]), k) in instance.rooms[rid].busy:
                    add("A-H6", f"Phòng {rid} bận ở ca {k} ngày {s['date']}", room_id=rid, sitting_id=s["sitting_id"])
    for (rid, date, k), sids in room_use.items():
        if len(sids) > 1:
            add("A-H4", f"Phòng {rid} ca {k} ngày {date} có nhiều lượt: {', '.join(sids)}", room_id=rid,
                sitting_ids=sids)

    # A-H7, A-H8, A-H10: giám thị
    proctors = instance.proctors
    at_time = {}
    for s in sittings:
        course = instance.courses.get(s["course_id"])
        for room in s["rooms"]:
            if room["room_id"] is None:
                continue
            names = room["proctors"]
            if len(set(names)) != nu or len(names) != nu:
                add("A-H7", f"Phòng {room['room_id']} của lượt {s['sitting_id']} có {len(set(names))} giám thị, "
                            f"cần {nu}", sitting_id=s["sitting_id"], room_id=room["room_id"])
            for g in set(names):
                lec = proctors.get(g)
                if lec is None:
                    add("A-H8", f"{g} không phải giám thị hợp lệ", lecturer_id=g, sitting_id=s["sitting_id"])
                    continue
                for k in occupied[s["sitting_id"]]:
                    at_time.setdefault((g, s["date"], k), []).append(s["sitting_id"] + "/" + room["room_id"])
                    if (dt.date.fromisoformat(s["date"]), k) in lec.busy:
                        add("A-H8", f"Giám thị {g} bận ở ca {k} ngày {s['date']}", lecturer_id=g,
                            sitting_id=s["sitting_id"])
                if config["forbid_own_course"] and course is not None and course.course_id in lec.teaches:
                    add("A-H10", f"Giám thị {g} coi thi môn mình dạy {course.course_id}", lecturer_id=g,
                        sitting_id=s["sitting_id"])
    for (g, date, k), places in at_time.items():
        if len(places) > 1:
            add("A-H8", f"Giám thị {g} coi nhiều phòng ở ca {k} ngày {date}: {', '.join(places)}", lecturer_id=g)
    return out


def validate_raw_proctoring(instance: Instance, solution: Solution) -> list[dict]:
    """Kiểm tra phần giám thị trong lời giải gốc của solver, trước khi gộp vào schedule.json.

    schedule.json chỉ ghi một danh sách giám thị cho mỗi phòng của một lượt, nên không thể hiện được hai lỗi:
    giám thị khác nhau giữa hai ca của lượt 2 ca, và giám thị được xếp vào phòng-ca không có lượt thi.
    """
    out: list[dict] = []
    used: set = set()
    for s in solution.sittings:
        cover = instance.covered(s.course_id, s.start)
        for rid in s.rooms:
            used.update((rid, t) for t in cover)
            lists = [sorted(solution.proctoring.get((rid, t), [])) for t in cover]
            if any(lst != lists[0] for lst in lists):
                out.append({"code": "A-H7",
                            "message": f"Lượt 2 ca {s.course_id} ở phòng {rid} đổi giám thị giữa hai ca: {lists}",
                            "refs": {"course_id": s.course_id, "room_id": rid}})
    for (rid, t), names in solution.proctoring.items():
        if names and (rid, t) not in used:
            out.append({"code": "A-H7",
                        "message": f"Phòng {rid} ca {t[1]} ngày {t[0].isoformat()} không có lượt thi nhưng "
                                   f"có giám thị {sorted(names)}",
                        "refs": {"room_id": rid}})
    return out
