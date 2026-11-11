"""Kiểm tra lịch học bài toán B độc lập với solver (model_spec B.5, B.8; data_schema mục 9.11).

Validator không dùng biến hay công thức của mô hình. Nó đọc mảng sessions trong timetable.json và soát trực tiếp
theo dữ liệu đầu vào: số buổi của từng lớp, phòng, giảng viên, nhóm sinh viên. Mỗi vi phạm mang đúng mã ràng buộc
cứng B-H1 .. B-H7, cùng dạng với data_schema mục 7.5.

compute_penalties_b tính lại P^B_1..P^B_4 từ lịch, để đối chiếu với penalties và objective solver báo.
"""
from __future__ import annotations

from src.instance_b import InstanceB

WEEKDAY = {2: "Thứ 2", 3: "Thứ 3", 4: "Thứ 4", 5: "Thứ 5", 6: "Thứ 6", 7: "Thứ 7"}


def _slot(s: dict) -> tuple[int, int]:
    return s["weekday"], s["period"]


def _when(slot: tuple[int, int]) -> str:
    return f"{WEEKDAY.get(slot[0], f'thứ {slot[0]}')} ca {slot[1]}"


def validate_b(instance: InstanceB, timetable: dict) -> list[dict]:
    """Trả về danh sách vi phạm; rỗng nếu lịch hợp lệ."""
    out: list[dict] = []

    def add(code, message, **refs):
        out.append({"code": code, "message": message, "refs": refs})

    sessions = timetable["sessions"]
    week = set(instance.slots)

    # Buổi không thuộc lớp nào hoặc nằm ngoài lịch tuần không được tính là một buổi hợp lệ của lớp (B-H1)
    valid = []
    for s in sessions:
        sid, slot = s["session_id"], _slot(s)
        if s["class_id"] not in instance.classes:
            add("B-H1", f"Buổi {sid} thuộc lớp {s['class_id']} không có trong dữ liệu", session_ids=[sid])
        elif slot not in week:
            add("B-H1", f"Buổi {sid} xếp vào {_when(slot)}, không có trong lịch tuần", session_ids=[sid],
                class_id=s["class_id"])
        else:
            valid.append(s)

    # B-H1: mỗi lớp đủ số buổi mỗi tuần
    by_class: dict[str, list[dict]] = {}
    for s in valid:
        by_class.setdefault(s["class_id"], []).append(s)
    for class_id, cls in instance.classes.items():
        n = len(by_class.get(class_id, []))
        if n != cls.sessions:
            add("B-H1", f"Lớp {class_id} có {n} buổi/tuần, cần {cls.sessions}", class_id=class_id)

    # B-H3, B-H4, B-H6: phòng có thật, đủ chỗ, đúng loại, không bận
    by_room_slot: dict[tuple[str, tuple[int, int]], list[str]] = {}
    for s in valid:
        sid, rid, slot = s["session_id"], s["room_id"], _slot(s)
        cls = instance.classes[s["class_id"]]
        room = instance.rooms.get(rid)
        if room is None:
            add("B-H3", f"Buổi {sid} xếp vào phòng {rid} không có trong dữ liệu", session_ids=[sid], room_id=rid)
            continue
        by_room_slot.setdefault((rid, slot), []).append(sid)
        if room.capacity < cls.size:
            add("B-H3", f"Lớp {cls.class_id} có {cls.size} sinh viên, phòng {rid} chỉ có {room.capacity} chỗ",
                session_ids=[sid], class_id=cls.class_id, room_id=rid)
        if room.room_type != cls.room_type:
            need = "phòng máy" if cls.needs_lab else "phòng thường"
            add("B-H4", f"Lớp {cls.class_id} cần {need} nhưng xếp vào phòng {rid} ({room.room_type})",
                session_ids=[sid], class_id=cls.class_id, room_id=rid)
        if slot in room.busy:
            add("B-H6", f"Phòng {rid} bận {_when(slot)} nhưng có buổi {sid}", session_ids=[sid], room_id=rid)

    # B-H2: mỗi phòng, mỗi ca tối đa một buổi
    for (rid, slot), sids in sorted(by_room_slot.items()):
        if len(sids) > 1:
            add("B-H2", f"Phòng {rid} {_when(slot)} có {len(sids)} buổi: {', '.join(sids)}",
                room_id=rid, session_ids=sids)

    # B-H5: giảng viên không dạy hai buổi cùng ca, không dạy vào ca bận.
    # Gồm cả trường hợp một lớp có hai buổi cùng ca (cùng giảng viên).
    by_lecturer_slot: dict[tuple[str, tuple[int, int]], list[str]] = {}
    for s in valid:
        sid, slot = s["session_id"], _slot(s)
        g = instance.classes[s["class_id"]].lecturer_id
        by_lecturer_slot.setdefault((g, slot), []).append(sid)
        if slot in instance.lecturers[g].busy:
            add("B-H5", f"Giảng viên {g} bận {_when(slot)} nhưng có buổi {sid}", session_ids=[sid], lecturer_id=g)
    for (g, slot), sids in sorted(by_lecturer_slot.items()):
        if len(sids) > 1:
            add("B-H5", f"Giảng viên {g} dạy {len(sids)} buổi {_when(slot)}: {', '.join(sids)}",
                lecturer_id=g, session_ids=sids)

    # B-H7: các lớp bắt buộc của cùng một nhóm không trùng ca
    for group_id, class_ids in instance.groups.items():
        members = set(class_ids)
        at: dict[tuple[int, int], list[str]] = {}
        for s in valid:
            if s["class_id"] in members:
                at.setdefault(_slot(s), []).append(s["session_id"])
        for slot, sids in sorted(at.items()):
            if len(sids) > 1:
                add("B-H7", f"Nhóm {group_id} có {len(sids)} buổi bắt buộc {_when(slot)}: {', '.join(sids)}",
                    group_id=group_id, session_ids=sids)
    return out


def compute_penalties_b(instance: InstanceB, timetable: dict, rho: float) -> dict[str, int]:
    """P^B_1..P^B_4 theo model_spec B.6, tính lại từ lịch. Bỏ qua buổi có lớp hoặc phòng lạ (validator đã báo)."""
    sessions = [s for s in timetable["sessions"]
                if s["class_id"] in instance.classes and s["room_id"] in instance.rooms]

    waste = sum(instance.rooms[s["room_id"]].capacity - instance.classes[s["class_id"]].size for s in sessions)

    avoid = sum(1 for s in sessions
                if _slot(s) in instance.lecturers[instance.classes[s["class_id"]].lecturer_id].avoid)

    per_day: dict[tuple[str, int], int] = {}
    for s in sessions:
        key = (s["class_id"], s["weekday"])
        per_day[key] = per_day.get(key, 0) + 1
    extra = sum(n - 1 for n in per_day.values() if n > 1)

    labs_used: dict[tuple[int, int], int] = {}
    for s in sessions:
        if instance.classes[s["class_id"]].needs_lab:
            labs_used[_slot(s)] = labs_used.get(_slot(s), 0) + 1
    over = sum(max(0, n - instance.lab_limit(t, rho)) for t, n in labs_used.items() if t in set(instance.slots))

    return {"B-S1": waste, "B-S2": avoid, "B-S3": extra, "B-S4": over}
