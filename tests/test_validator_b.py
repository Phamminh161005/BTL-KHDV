"""Kiểm thử src/validator_b.py trên bộ data/toy_b.

OPTIMAL là một lịch tối ưu của toy_b (Z = 355, model_spec B.12), lấy từ mô hình nguyên mẫu dùng khi kiểm chứng spec.
Các ca kiểm thử cố ý làm hỏng lịch để chắc chắn validator phát hiện được từng loại vi phạm.
"""
import copy
import os

import pytest

from src.data_loader_b import load_instance_b
from src.validator_b import compute_penalties_b, validate_b

ROOT = os.path.join(os.path.dirname(__file__), "..")
LOADED = load_instance_b(os.path.join(ROOT, "data", "toy_b"), os.path.join(ROOT, "configs", "default.json"))
INST, CFG = LOADED.instance, LOADED.config

# (class_id, room_id, weekday, period)
OPTIMAL = [
    ("INT2204-LT", "G2-101", 2, 3), ("ELT2035", "G2-102", 2, 3), ("INT3306-TH", "G2-LAB1", 2, 4),
    ("ELT2035", "G2-102", 3, 2), ("INT3306-TH", "G2-LAB1", 3, 2), ("INT2211-TH", "G2-LAB1", 3, 4),
    ("MAT1099", "G2-101", 4, 1), ("ELT2035", "G2-102", 4, 1), ("INT3306-TH", "G2-LAB1", 4, 2),
    ("INT2211-LT", "G2-102", 4, 3), ("INT3306-TH", "G2-LAB1", 4, 4), ("ELT2035", "G2-102", 5, 1),
    ("INT2204-TH2", "G2-LAB1", 5, 1), ("MAT1099", "G2-101", 5, 2), ("INT2211-TH", "G2-LAB1", 5, 4),
    ("INT2211-LT", "G2-102", 6, 1), ("INT2204-LT", "G2-101", 6, 2), ("INT3505", "G2-102", 6, 2),
    ("MAT1099", "G2-101", 6, 4), ("ELT2035", "G2-102", 6, 4), ("INT3505-TH", "G2-LAB1", 6, 4),
    ("ELT2035", "G2-102", 7, 1), ("INT2204-TH1", "G2-LAB2", 7, 1), ("ELT2035", "G2-102", 7, 2),
]


def session(class_id, room_id, weekday, period):
    """Một phần tử của sessions theo data_schema mục 9.11 (chỉ các trường validator dùng và session_id)."""
    return {"session_id": f"{class_id}@T{weekday}_{period}", "class_id": class_id, "room_id": room_id,
            "weekday": weekday, "period": period}


def timetable(rows=OPTIMAL):
    return {"sessions": [session(*r) for r in rows]}


def codes(violations):
    return {v["code"] for v in violations}


def find(tt, class_id, k=0):
    return [s for s in tt["sessions"] if s["class_id"] == class_id][k]


def move(tt, class_id, weekday, period, k=0, room_id=None):
    s = find(tt, class_id, k)
    s["weekday"], s["period"] = weekday, period
    s["session_id"] = f"{class_id}@T{weekday}_{period}"
    if room_id is not None:
        s["room_id"] = room_id


def test_optimal_is_valid():
    assert LOADED.ok
    assert validate_b(INST, timetable()) == []


def test_optimal_penalties_match_reference():
    """Đáp án tham chiếu 355 = 75 + 50 × 1 + 100 × 2 + 30 × 1 (model_spec B.12, data/toy_b/README.md)."""
    p = compute_penalties_b(INST, timetable(), CFG["lab_reserve_ratio"])
    assert p == {"B-S1": 75, "B-S2": 1, "B-S3": 2, "B-S4": 1}
    assert sum(CFG["weights"][k] * v for k, v in p.items()) == 355


def _drop_session(tt):
    tt["sessions"].remove(find(tt, "MAT1099"))


def _extra_session(tt):
    tt["sessions"].append(session("INT3505", "G2-102", 6, 3))


def _unknown_class(tt):
    tt["sessions"].append(session("INT9999", "G2-102", 5, 3))


def _outside_week(tt):
    move(tt, "INT3505", 7, 3)            # Thứ 7 chỉ học ca 1, 2


def _room_clash(tt):
    move(tt, "INT3505", 4, 3)            # G2-102 Thứ 4 ca 3 đã có INT2211-LT


def _too_small(tt):
    find(tt, "INT2204-TH1")["room_id"] = "G2-LAB1"      # 18 sinh viên, 15 máy


def _unknown_room(tt):
    find(tt, "INT3505")["room_id"] = "G9-999"


def _theory_in_lab(tt):
    find(tt, "INT3505")["room_id"] = "G2-LAB2"          # lớp lý thuyết không vào phòng máy (B-H4)


def _lab_in_normal_room(tt):
    find(tt, "INT3505-TH")["room_id"] = "G2-102"


def _lecturer_busy(tt):
    move(tt, "INT3505", 5, 3)            # GV06 chỉ rảnh Thứ 6


def _lecturer_double(tt):
    move(tt, "INT2204-TH2", 7, 1, room_id="G2-LAB1")    # GV04 đã dạy INT2204-TH1 Thứ 7 ca 1


def _same_class_same_slot(tt):
    move(tt, "MAT1099", 4, 1, k=1, room_id="G2-102")    # hai buổi MAT1099 cùng Thứ 4 ca 1


def _room_busy(tt):
    move(tt, "INT2204-LT", 2, 1)         # G2-101 bận Thứ 2 ca 1 (sinh hoạt khoa)


def _group_clash(tt):
    move(tt, "INT3306-TH", 4, 3)         # K67-KHMT đã có INT2211-LT Thứ 4 ca 3; khác giảng viên, phòng trống


@pytest.mark.parametrize("breaker, code", [
    (_drop_session, "B-H1"),
    (_extra_session, "B-H1"),
    (_unknown_class, "B-H1"),
    (_outside_week, "B-H1"),
    (_room_clash, "B-H2"),
    (_too_small, "B-H3"),
    (_unknown_room, "B-H3"),
    (_theory_in_lab, "B-H4"),
    (_lab_in_normal_room, "B-H4"),
    (_lecturer_busy, "B-H5"),
    (_lecturer_double, "B-H5"),
    (_same_class_same_slot, "B-H5"),
    (_room_busy, "B-H6"),
    (_group_clash, "B-H7"),
])
def test_detects_violation(breaker, code):
    tt = timetable()
    breaker(tt)
    found = validate_b(INST, tt)
    assert code in codes(found)
    for v in found:
        assert v["message"] and isinstance(v["refs"], dict)


def test_different_groups_may_share_a_slot():
    """INT2204-TH1 (K67-CN1) và INT3306-TH (K67-KHMT) khác nhóm, khác giảng viên: được học cùng ca."""
    tt = timetable()
    move(tt, "INT2204-TH1", 2, 4, room_id="G2-LAB2")     # cùng ca với INT3306-TH ở G2-LAB1
    assert "B-H7" not in codes(validate_b(INST, tt))


def test_elective_may_clash_with_required():
    """INT3505 là lớp tự chọn, được trùng ca với lớp bắt buộc INT2211-LT."""
    tt = timetable()
    move(tt, "INT3505", 6, 1, room_id="G2-101")          # INT2211-LT học G2-102 Thứ 6 ca 1
    assert validate_b(INST, tt) == []


def test_group_clash_refs():
    tt = timetable()
    _group_clash(tt)
    found = validate_b(INST, tt)
    assert codes(found) == {"B-H7"}
    assert len(found) == 1
    assert found[0]["refs"]["group_id"] == "K67-KHMT"
    assert sorted(found[0]["refs"]["session_ids"]) == ["INT2211-LT@T4_3", "INT3306-TH@T4_3"]


def test_lab_reserve_counts_b_s4():
    """Thứ 6 G2-LAB2 bảo trì, chỉ còn 1 phòng máy nên ngưỡng là 0. Dời INT2204-TH2 sang Thứ 6 ca 3: B-S4 từ 1 lên 2."""
    tt = timetable()
    move(tt, "INT2204-TH2", 6, 3)
    assert validate_b(INST, tt) == []
    assert compute_penalties_b(INST, tt, CFG["lab_reserve_ratio"])["B-S4"] == 2


def test_avoid_slot_counts_b_s2():
    """GV01 không muốn dạy Thứ 7. Dời buổi Thứ 6 ca 2 của INT2204-LT sang Thứ 7 ca 2: B-S2 từ 1 lên 2."""
    tt = timetable()
    move(tt, "INT2204-LT", 7, 2, k=1)
    assert validate_b(INST, tt) == []
    assert compute_penalties_b(INST, tt, CFG["lab_reserve_ratio"])["B-S2"] == 2


def test_same_day_counts_b_s3():
    """Dời buổi Thứ 4 ca 1 của MAT1099 sang Thứ 5 ca 3 (cùng ngày với buổi Thứ 5 ca 2): B-S3 từ 2 lên 3."""
    tt = timetable()
    move(tt, "MAT1099", 5, 3)
    assert validate_b(INST, tt) == []
    assert compute_penalties_b(INST, tt, CFG["lab_reserve_ratio"])["B-S3"] == 3
