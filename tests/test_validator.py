"""Kiểm thử validator và KPI trên kết quả tham chiếu output/toy/schedule.json.

Ngoài việc xác nhận kết quả tham chiếu hợp lệ, các ca kiểm thử cố ý làm hỏng lịch để chắc chắn validator
phát hiện được từng loại vi phạm (không phải lúc nào cũng báo "ổn").
"""
import copy
import datetime as dt
import json
import os

import pytest

from src.data_loader import load_instance
from src.instance import Sitting, Solution
from src.kpi import compute_kpi, compute_penalties
from src.validator import validate, validate_raw_proctoring

ROOT = os.path.join(os.path.dirname(__file__), "..")
LOADED = load_instance(os.path.join(ROOT, "data", "toy"), os.path.join(ROOT, "configs", "default.json"))
INST, CFG = LOADED.instance, LOADED.config
with open(os.path.join(ROOT, "output", "toy", "schedule.json"), encoding="utf-8") as f:
    REFERENCE = json.load(f)


def codes(violations):
    return {v["code"] for v in violations}


def sitting(schedule, course_id, k=0):
    return [s for s in schedule["sittings"] if s["course_id"] == course_id][k]


def test_reference_is_valid():
    assert REFERENCE["status"] == "OPTIMAL"
    assert validate(INST, REFERENCE, CFG) == []


def test_reference_penalties_match_recomputation():
    assert compute_penalties(INST, REFERENCE) == REFERENCE["penalties"]
    w = CFG["weights"]
    assert sum(w[k] * v for k, v in REFERENCE["penalties"].items()) == REFERENCE["objective"]


def test_reference_kpi_recomputes():
    kpi = compute_kpi(INST, REFERENCE, 0)
    assert kpi == REFERENCE["kpi"]


def _break_two_period_start(s):
    c = sitting(s, "MAT1099")
    c["start_period"], c["periods"] = 2, [2, 3]


def _wrong_room_type(s):
    sitting(s, "INT2204")["rooms"][0]["room_id"] = "G2-LAB1"


def _overfill(s):
    """INT2204 có 40 sinh viên chia 2 phòng; dồn hết vào phòng đầu (30 chỗ)."""
    x = sitting(s, "INT2204")
    x["rooms"][0]["students"] += x["rooms"][1]["students"]
    x["rooms"].pop(1)


def _drop_sitting(s):
    s["sittings"].remove(sitting(s, "INT2211"))


def _duplicate_student(s):
    first, second = sitting(s, "INT2211", 0), sitting(s, "INT2211", 1)
    second["rooms"][0]["students"].append(first["rooms"][0]["students"][0])


def _clash(s):
    a, b = sitting(s, "INT3505"), sitting(s, "INT2204")
    a["date"], a["start_period"], a["periods"] = b["date"], b["start_period"], b["periods"]


def _one_proctor(s):
    s["sittings"][0]["rooms"][0]["proctors"] = s["sittings"][0]["rooms"][0]["proctors"][:1]


def _busy_proctor(s):
    """GV01 đi công tác cả ngày 14/12; xếp GV01 coi một phòng ngày đó."""
    x = next(x for x in s["sittings"] if x["date"] == "2026-12-14")
    other = next(g for g in x["rooms"][0]["proctors"] if g != "GV01")
    x["rooms"][0]["proctors"] = sorted(["GV01", other])


MUTATIONS = [
    ("A-H1", "lượt 2 ca vắt qua giờ nghỉ trưa", _break_two_period_start),
    ("A-H3", "dồn sinh viên vào một phòng", _overfill),
    ("A-H5", "thi viết trong phòng máy", _wrong_room_type),
    ("A-H9", "bỏ một lượt thi máy", _drop_sitting),
    ("A-H9", "một sinh viên thi hai lượt", _duplicate_student),
    ("A-H2", "hai môn chung sinh viên trùng ca", _clash),
    ("A-H7", "phòng chỉ có một giám thị", _one_proctor),
    ("A-H8", "giám thị coi vào ngày đi công tác", _busy_proctor),
]


@pytest.mark.parametrize("code,name,mutate", MUTATIONS, ids=[f"{c}-{n}" for c, n, _ in MUTATIONS])
def test_validator_catches(code, name, mutate):
    broken = copy.deepcopy(REFERENCE)
    mutate(broken)
    found = codes(validate(INST, broken, CFG))
    assert code in found, f"{name}: validator báo {sorted(found)}"


def test_validator_room_busy():
    """Dời một lượt vào ca 1 ngày 14/12, khi G2-101 đang có hội nghị."""
    broken = copy.deepcopy(REFERENCE)
    target = next(x for x in broken["sittings"] if x["exam_type"] == "written")
    target["date"], target["start_period"] = "2026-12-14", 1
    target["periods"] = [1] if len(target["periods"]) == 1 else [1, 2]
    target["rooms"][0]["room_id"] = "G2-101"
    assert "A-H6" in codes(validate(INST, broken, CFG))


def test_validator_forbid_own_course():
    cfg = dict(CFG, forbid_own_course=True)
    broken = copy.deepcopy(REFERENCE)
    target = sitting(broken, "INT3505")
    target["rooms"][0]["proctors"] = sorted({"GV05", "GV06"})   # GV05 dạy INT3505
    assert "A-H10" in codes(validate(INST, broken, cfg))


def test_raw_proctoring_checks():
    """Hai lỗi chỉ thấy được ở lời giải gốc: đổi giám thị giữa hai ca, giám thị ở phòng không có lượt thi."""
    day = dt.date(2026, 12, 16)
    sol = Solution([Sitting("MAT1099", (day, 1), ["G2-102"], [])],
                   {("G2-102", (day, 1)): ["GV01", "GV02"], ("G2-102", (day, 2)): ["GV01", "GV03"],
                    ("G2-101", (day, 4)): ["GV04", "GV05"]})
    msgs = [v["message"] for v in validate_raw_proctoring(INST, sol)]
    assert len(msgs) == 2 and all(v["code"] == "A-H7" for v in validate_raw_proctoring(INST, sol))
