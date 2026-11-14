"""Kiểm thử xếp lại bài toán B (src/reschedule_b.py, model_spec B.9) trên data/toy_b.

Lịch cũ là lịch tham chiếu tests/reference/toy_timetable.json (Z = 355). Trên toy_b, Thứ 6 G2-LAB2 bảo trì nên chỉ
còn G2-LAB1; GV06 chỉ rảnh Thứ 6.
"""
import json
import shutil
from pathlib import Path

import pytest

from src.reschedule_b import diff_timetables, parse_incident_b, reschedule_b
from src.validator_b import compute_penalties_b

ROOT = Path(__file__).resolve().parents[1]
TOY_B = ROOT / "data" / "toy_b"
CONFIG = ROOT / "configs" / "problem_b.json"
BASE = ROOT / "tests" / "reference" / "toy_timetable.json"
BASE_JSON = json.loads(BASE.read_text(encoding="utf-8"))


def go(tmp_path, incidents, data=TOY_B, base=BASE):
    return reschedule_b(str(data), str(base) if isinstance(base, Path) else base, incidents, str(CONFIG),
                        str(tmp_path / "retimetable.json"))


def codes(table):
    return [m["code"] for m in table["messages"]]


def session_of(table, class_id):
    return sorted((s["weekday"], s["period"], s["room_id"]) for s in table["sessions"] if s["class_id"] == class_id)


def unchanged_except(old, new, class_ids):
    keep = lambda t: sorted((s["class_id"], s["weekday"], s["period"], s["room_id"]) for s in t["sessions"]
                            if s["class_id"] not in class_ids)
    return keep(old) == keep(new)


def test_lab_broken_on_friday_moves_only_that_session(tmp_path):
    """G2-LAB1 hỏng Thứ 6 ca 4: INT3505-TH phải dời ca (Thứ 6 không còn phòng máy nào khác), lớp khác giữ nguyên."""
    new = go(tmp_path, [{"resource_type": "room", "resource_id": "G2-LAB1", "weekday": 6, "period": 4}])
    assert new["status"] in ("OPTIMAL", "FEASIBLE") and new["violations"] == []
    info = new["reschedule"]
    assert info["change_penalties"] == {"B-R1": 1, "B-R2": 0}
    assert info["change_cost"] == 100
    assert info["summary"]["sessions_moved"] == 1 and info["summary"]["classes_affected"] == 1
    assert [ch["kinds"] for ch in new["changes"]] == [["time"]]
    assert new["changes"][0]["class_id"] == "INT3505-TH"
    assert new["changes"][0]["new"]["weekday"] == 6                    # GV06 chỉ rảnh Thứ 6
    assert unchanged_except(BASE_JSON, new, {"INT3505-TH"})
    assert new["meta"]["config"]["time_limit_sec"] == new["meta"]["config"]["reschedule"]["time_limit_sec"]
    assert new["best_bound"] is None
    assert json.loads((tmp_path / "retimetable.json").read_text(encoding="utf-8")) == new


def test_room_change_is_cheaper_than_moving(tmp_path):
    """G2-LAB1 hỏng Thứ 3 ca 4: INT2211-TH (15 sinh viên) chuyển sang G2-LAB2 cùng ca. Đổi phòng tốn
    B-R2 20 + B-S1 5 (phòng 20 máy) + B-S4 30 (ca đó chỉ còn 1 phòng máy), vẫn rẻ hơn dời ca (B-R1 100)."""
    new = go(tmp_path, [{"resource_type": "room", "resource_id": "G2-LAB1", "weekday": 3, "period": 4}])
    assert new["violations"] == []
    assert new["reschedule"]["change_penalties"] == {"B-R1": 0, "B-R2": 1}
    assert [(ch["class_id"], ch["kinds"], ch["new"]["room_id"]) for ch in new["changes"]] == \
        [("INT2211-TH", ["rooms"], "G2-LAB2")]
    assert new["objective"] == 355 + 5 + 30
    assert new["reschedule"]["summary"]["sessions_room_changed"] == 1


def test_lecturer_busy_whole_day(tmp_path):
    """GV02 bận cả Thứ 4: buổi INT2211-LT Thứ 4 phải dời; các lớp khác của GV02 không học Thứ 4 nên giữ nguyên."""
    new = go(tmp_path, [parse_incident_b("lecturer,GV02,4")])
    assert new["violations"] == []
    assert new["reschedule"]["incidents"] == [{"resource_type": "lecturer", "resource_id": "GV02", "weekday": 4,
                                               "period": None}]
    assert all(s["weekday"] != 4 for s in new["sessions"] if s["lecturer_id"] == "GV02")
    assert new["reschedule"]["change_penalties"]["B-R1"] == 1


def test_no_incident_keeps_timetable(tmp_path):
    new = go(tmp_path, [])
    assert new["status"] == "OPTIMAL" and new["objective"] == 355
    assert new["changes"] == [] and new["reschedule"]["change_cost"] == 0


def test_add_class_incident(tmp_path):
    """Thêm lớp thực hành mới 2 buổi cho nhóm K67-KHMT: hai buổi mới là "added", lịch cũ giữ nguyên."""
    incident = {"type": "add_class", "class": {"class_id": "INT9999-TH", "class_name": "Lớp mới",
                                              "lecturer_id": "GV04", "size": 12, "sessions_per_week": 2,
                                              "needs_lab": True, "groups": ["K67-KHMT"]}}
    new = go(tmp_path, [incident])
    assert new["status"] in ("OPTIMAL", "FEASIBLE") and new["violations"] == []
    assert len(session_of(new, "INT9999-TH")) == 2
    assert all(s["groups"] == ["K67-KHMT"] for s in new["sessions"] if s["class_id"] == "INT9999-TH")
    assert [ch["kinds"] for ch in new["changes"]] == [["added"], ["added"]]
    assert new["reschedule"]["summary"]["sessions_added"] == 2
    assert new["reschedule"]["change_penalties"] == {"B-R1": 0, "B-R2": 0}
    assert unchanged_except(BASE_JSON, new, {"INT9999-TH"})


def test_new_class_in_data_files(tmp_path):
    """Lớp mới khai báo trong classes.csv (cách của spec B.9): có trong dữ liệu, không có trong lịch cũ."""
    data = tmp_path / "toy_b"
    shutil.copytree(TOY_B, data)
    with (data / "classes.csv").open("a", encoding="utf-8", newline="") as f:
        f.write("NEW-LT,Lớp lý thuyết mới,NEW,0,30,1,GV07\n")
    new = go(tmp_path, [], data=data)
    assert any(m["code"] == "I04" and "NEW-LT" in m["message"] for m in new["messages"])
    assert len(session_of(new, "NEW-LT")) == 1 and new["violations"] == []
    assert unchanged_except(BASE_JSON, new, {"NEW-LT"})


@pytest.mark.parametrize("incident, code", [
    ({"resource_type": "room", "resource_id": "G9-999", "weekday": 2, "period": 1}, "I01"),
    ({"resource_type": "room", "resource_id": "G2-101", "weekday": 8, "period": 1}, "I01"),
    ({"resource_type": "room", "resource_id": "G2-101", "weekday": 2, "period": 5}, "I01"),
    ({"resource_type": "proctor", "resource_id": "GV01", "weekday": 2}, "I01"),
    ({"type": "add_class", "class": {"class_id": "MAT1099", "lecturer_id": "GV01", "size": 10,
                                     "sessions_per_week": 1}}, "I01"),
    ({"type": "add_class", "class": {"class_id": "X", "lecturer_id": "GV99", "size": 0,
                                     "sessions_per_week": 1}}, "I01"),
    ({"type": "add_class", "class": {"class_id": "BIG", "lecturer_id": "GV01", "size": 100,
                                     "sessions_per_week": 1}}, "PB1"),
])
def test_bad_incidents_stop_before_solving(tmp_path, incident, code):
    new = go(tmp_path, [incident])
    assert new["status"] == "INPUT_ERROR" and code in codes(new)


def test_incident_outside_week_is_ignored(tmp_path):
    new = go(tmp_path, [{"resource_type": "room", "resource_id": "G2-101", "weekday": 7, "period": 4}])
    assert "I02" in codes(new) and new["changes"] == []


def test_bad_base_timetable(tmp_path):
    bad = dict(BASE_JSON, sessions=[{"session_id": "X@T2_1", "class_id": "X", "room_id": "G2-101",
                                     "weekday": 2, "period": 1}])
    new = go(tmp_path, [], base=bad)
    assert new["status"] == "INPUT_ERROR" and "I03" in codes(new)
    new = go(tmp_path, [], base=tmp_path / "khong_co.json")
    assert new["status"] == "INPUT_ERROR" and "I03" in codes(new)


def test_infeasible_reschedule_is_diagnosed(tmp_path):
    """GV06 chỉ rảnh Thứ 6; báo bận cả Thứ 6 thì hai lớp của GV06 không còn ca nào: vô nghiệm, chẩn đoán chỉ ra B-H5."""
    new = go(tmp_path, [{"resource_type": "lecturer", "resource_id": "GV06", "weekday": 6, "period": None}])
    assert new["status"] == "INFEASIBLE" and new["sessions"] == [] and new["changes"] == []
    assert new["reschedule"]["summary"] is None
    assert any(m["code"] == "N01" and "B-H5" in m["message"] for m in new["messages"])


def test_penalties_and_cost_are_consistent(tmp_path):
    new = go(tmp_path, [{"resource_type": "room", "resource_id": "G2-101", "weekday": 6, "period": None}])
    assert new["violations"] == []
    from src.data_loader_b import load_instance_b
    inst = load_instance_b(str(TOY_B), str(CONFIG)).instance
    assert compute_penalties_b(inst, new, 0.85) == new["penalties"]
    weights = new["meta"]["config"]["reschedule"]["weights"]
    info = new["reschedule"]
    assert info["change_cost"] == sum(weights[k] * v for k, v in info["change_penalties"].items())
    assert info["change_penalties"]["B-R1"] == info["summary"]["sessions_moved"]
    assert info["change_penalties"]["B-R2"] == info["summary"]["sessions_room_changed"]


def test_diff_pairs_same_slot_first():
    s = lambda k, d, p, r: {"session_id": f"{k}@T{d}_{p}", "class_id": k, "weekday": d, "period": p, "room_id": r,
                            "lecturer_id": "G"}
    old = {"sessions": [s("K", 2, 1, "R1"), s("K", 3, 1, "R1")]}
    new = {"sessions": [s("K", 2, 1, "R2"), s("K", 4, 2, "R1"), s("K", 5, 1, "R1")]}
    changes, summary = diff_timetables(old, new)
    assert [ch["kinds"] for ch in changes] == [["rooms"], ["time"], ["added"]]
    assert summary["sessions_moved"] == 1 and summary["sessions_room_changed"] == 1
    assert summary["sessions_added"] == 1 and summary["lecturers_affected"] == 1


@pytest.mark.parametrize("text", ["room,G2-LAB1", "room,G2-LAB1,thu6", "room,G2-LAB1,6,ca4"])
def test_parse_incident_rejects_bad_text(text):
    with pytest.raises(ValueError):
        parse_incident_b(text)


def test_medium_b_reschedule_under_one_minute(tmp_path):
    """KPI scope mục 7: xếp lại khi có sự cố dưới 1 phút. Lịch cũ giải trên medium_b, rồi một phòng máy hỏng cả Thứ 3."""
    from src.run import run
    base = run(str(ROOT / "data" / "medium_b"), str(CONFIG), str(tmp_path / "base.json"), problem="B")
    lab = next(s["room_id"] for s in base["sessions"] if s["needs_lab"] and s["weekday"] == 3)
    new = go(tmp_path, [{"resource_type": "room", "resource_id": lab, "weekday": 3, "period": None}],
             data=ROOT / "data" / "medium_b", base=base)
    assert new["status"] in ("OPTIMAL", "FEASIBLE") and new["violations"] == []
    assert new["solve_time_sec"] < 60
    assert all(not (s["room_id"] == lab and s["weekday"] == 3) for s in new["sessions"])
