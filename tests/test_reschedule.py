"""Kiểm thử xếp lại khi có sự cố (src/reschedule.py), so sánh hai lịch và chẩn đoán vô nghiệm (src/diagnose.py).

Lịch cũ là kết quả tham chiếu tests/reference/toy_schedule.json (mục tiêu 2391). Trong lịch này, lượt
INT3306@2026-12-15_3 (2 ca: ca 3 và ca 4 ngày 15/12) dùng phòng máy G2-LAB1, phòng máy duy nhất của bộ toy.
"""
import copy
import json
import os
import shutil

import pytest

from src.data_loader import load_instance
from src.diagnose import diagnose
from src.reschedule import diff_schedules, parse_incident, reschedule
from src.run import run

ROOT = os.path.join(os.path.dirname(__file__), "..")
TOY = os.path.join(ROOT, "data", "toy")
CONFIG = os.path.join(ROOT, "configs", "default.json")
BASE = os.path.join(ROOT, "tests", "reference", "toy_schedule.json")

with open(BASE, encoding="utf-8") as f:
    BASE_SCHEDULE = json.load(f)


def _reschedule(tmp_path, incidents):
    return reschedule(TOY, BASE, incidents, CONFIG, str(tmp_path / "reschedule.json"))


def _uses(schedule, room_id, date, period):
    return [s["sitting_id"] for s in schedule["sittings"]
            if s["date"] == date and period in s["periods"] and any(r["room_id"] == room_id for r in s["rooms"])]


# ---------------------------------------------------------------- xếp lại

def test_room_incident_moves_only_affected_sitting(tmp_path):
    assert _uses(BASE_SCHEDULE, "G2-LAB1", "2026-12-15", 3) == ["INT3306@2026-12-15_3"]
    new = _reschedule(tmp_path, [{"resource_type": "room", "resource_id": "G2-LAB1", "date": "2026-12-15",
                                  "period": 3}])
    assert new["status"] in ("OPTIMAL", "FEASIBLE")
    assert new["violations"] == [], new["violations"]
    assert _uses(new, "G2-LAB1", "2026-12-15", 3) == []
    assert new["solve_time_sec"] < 60
    # Phần lớn lượt khác giữ nguyên ca và phòng; chỉ INT3306 bị dời ca.
    same = {(s["sitting_id"], tuple(r["room_id"] for r in s["rooms"])) for s in BASE_SCHEDULE["sittings"]} & \
           {(s["sitting_id"], tuple(r["room_id"] for r in s["rooms"])) for s in new["sittings"]}
    assert len(same) >= len(BASE_SCHEDULE["sittings"]) - 2
    moved = [ch for ch in new["changes"] if "time" in ch["kinds"]]
    assert [ch["old"]["sitting_id"] for ch in moved] == ["INT3306@2026-12-15_3"]
    info = new["reschedule"]
    assert info["incidents"] == [{"resource_type": "room", "resource_id": "G2-LAB1", "date": "2026-12-15",
                                  "period": 3}]
    assert info["change_penalties"]["A-R1"] == 1
    assert info["summary"]["sittings_moved"] == 1
    weights = new["meta"]["config"]["reschedule"]["weights"]
    assert info["change_cost"] == sum(weights[k] * v for k, v in info["change_penalties"].items())
    assert os.path.exists(tmp_path / "reschedule.json")


def test_no_incident_keeps_schedule(tmp_path):
    new = _reschedule(tmp_path, [])
    assert new["violations"] == []
    assert new["changes"] == []
    assert new["objective"] == BASE_SCHEDULE["objective"]
    assert new["reschedule"]["change_cost"] == 0


def test_lecturer_incident_only_changes_proctors(tmp_path):
    new = _reschedule(tmp_path, [parse_incident("lecturer,GV02,2026-12-15")])
    assert new["violations"] == []
    proctoring_gv02 = [s["sitting_id"] for s in new["sittings"] if s["date"] == "2026-12-15"
                       for r in s["rooms"] if "GV02" in r["proctors"]]
    assert proctoring_gv02 == []
    summary = new["reschedule"]["summary"]
    assert summary["sittings_moved"] == 0 and summary["sittings_room_changed"] == 0
    assert summary["students_affected"] == 0
    assert summary["proctors_affected"] >= 2
    assert all(ch["kinds"] == ["proctors"] for ch in new["changes"])


def test_invalid_incidents_are_reported(tmp_path):
    new = _reschedule(tmp_path, [
        {"resource_type": "room", "resource_id": "G2-LAB9", "date": "2026-12-15", "period": 3},
        {"resource_type": "printer", "resource_id": "X", "date": "2026-12-15", "period": 3},
        {"resource_type": "room", "resource_id": "G2-101", "date": "15/12/2026", "period": 3},
        {"resource_type": "room", "resource_id": "G2-101", "date": "2026-12-15", "period": 7},
        {"resource_type": "room", "resource_id": "G2-101", "date": "2026-12-25", "period": None},
    ])
    assert new["status"] == "INPUT_ERROR"
    codes = [m["code"] for m in new["messages"]]
    assert codes.count("I01") == 4 and codes.count("I02") == 1
    assert new["changes"] == []


def test_base_schedule_from_other_dataset_is_rejected(tmp_path):
    other = copy.deepcopy(BASE_SCHEDULE)
    other["sittings"][0]["rooms"][0]["students"].append("99999999")
    path = tmp_path / "other.json"
    path.write_text(json.dumps(other), encoding="utf-8")
    new = reschedule(TOY, str(path), [], CONFIG, str(tmp_path / "out.json"))
    assert new["status"] == "INPUT_ERROR"
    assert any(m["code"] == "I03" for m in new["messages"])


def test_parse_incident():
    assert parse_incident("room,G2-LAB1,2026-12-15,3") == {"resource_type": "room", "resource_id": "G2-LAB1",
                                                           "date": "2026-12-15", "period": 3}
    assert parse_incident("lecturer, GV02 ,2026-12-15")["period"] is None
    with pytest.raises(ValueError):
        parse_incident("room,G2-LAB1")


# ---------------------------------------------------------------- so sánh hai lịch

def test_diff_identical_schedules():
    changes, summary = diff_schedules(BASE_SCHEDULE, copy.deepcopy(BASE_SCHEDULE))
    assert changes == []
    assert summary["students_affected"] == 0 and summary["proctors_affected"] == 0


def test_diff_detects_moved_sitting():
    new = copy.deepcopy(BASE_SCHEDULE)
    sitting = next(s for s in new["sittings"] if s["sitting_id"] == "MAT1099@2026-12-16_1")
    sitting.update(date="2026-12-17", sitting_id="MAT1099@2026-12-17_1")
    changes, summary = diff_schedules(BASE_SCHEDULE, new)
    assert len(changes) == 1
    assert changes[0]["kinds"] == ["time"]
    assert changes[0]["old"]["sitting_id"] == "MAT1099@2026-12-16_1"
    assert changes[0]["new"]["sitting_id"] == "MAT1099@2026-12-17_1"
    assert changes[0]["students_affected"] == sitting["num_students"]
    assert summary["sittings_moved"] == 1 and summary["sittings_removed"] == 0


def test_diff_proctor_swap_affects_only_two_proctors():
    new = copy.deepcopy(BASE_SCHEDULE)
    room = next(s for s in new["sittings"] if s["sitting_id"] == "MAT1099@2026-12-16_1")["rooms"][0]
    assert "GV04" in room["proctors"] and "GV01" not in room["proctors"]
    room["proctors"] = sorted(["GV01" if g == "GV04" else g for g in room["proctors"]])
    changes, summary = diff_schedules(BASE_SCHEDULE, new)
    assert [ch["kinds"] for ch in changes] == [["proctors"]]
    assert changes[0]["students_affected"] == 0
    assert summary["students_affected"] == 0 and summary["proctors_affected"] == 2


# ---------------------------------------------------------------- chẩn đoán vô nghiệm

def _variant(tmp_path, files):
    for name in os.listdir(TOY):
        if name.endswith(".csv"):
            shutil.copy(os.path.join(TOY, name), tmp_path / name)
    for name, text in files.items():
        (tmp_path / name).write_text(text, encoding="utf-8")
    loaded = load_instance(str(tmp_path), CONFIG)
    assert loaded.ok, [m.to_dict() for m in loaded.messages]
    loaded.config.update(time_limit_sec=30)
    return loaded


def _toy_text(name):
    with open(os.path.join(TOY, name), encoding="utf-8") as f:
        return f.read()


NO_BUSY = "resource_type,resource_id,date,period,note\n"


def _diagnosis(loaded):
    return [(m.code, m.message) for m in diagnose(loaded.instance, loaded.config) if m.code != "N05"]


def test_diagnose_lack_of_proctors(tmp_path):
    lecturers = _toy_text("lecturers.csv")
    for name in ("Cường", "Dung", "Em", "Phương"):
        lecturers = lecturers.replace(f"{name},1", f"{name},0")
    found = _diagnosis(_variant(tmp_path, {"lecturers.csv": lecturers}))
    assert [code for code, _ in found] == ["N01"]
    assert "giám thị" in found[0][1]


def test_diagnose_student_conflicts(tmp_path):
    slots = "date,period\n" + "".join(f"2026-12-14,{k}\n" for k in (1, 2, 3, 4)) + \
            "".join(f"2026-12-15,{k}\n" for k in (1, 2, 3))
    found = _diagnosis(_variant(tmp_path, {"slots.csv": slots, "unavailability.csv": NO_BUSY}))
    assert [code for code, _ in found] == ["N01"]
    assert "A-H2" in found[0][1]


def test_diagnose_busy_rooms(tmp_path):
    busy = _toy_text("unavailability.csv") + "".join(f"room,G2-LAB1,2026-12-{d},,\n" for d in (15, 16, 17))
    found = _diagnosis(_variant(tmp_path, {"unavailability.csv": busy}))
    assert [code for code, _ in found] == ["N01"]
    assert "A-H6" in found[0][1]


def test_diagnose_not_enough_rooms_or_slots(tmp_path):
    """Chỉ còn 2 ca: phòng máy duy nhất không đủ chỗ cho số lượt thi máy, dù bỏ cả ba nhóm."""
    loaded = _variant(tmp_path, {"slots.csv": "date,period\n2026-12-14,1\n2026-12-14,2\n",
                                 "unavailability.csv": NO_BUSY})
    assert [code for code, _ in _diagnosis(loaded)] == ["N03"]


def test_run_diagnoses_infeasible_data(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    _variant(data, {"slots.csv": "date,period\n2026-12-14,1\n2026-12-14,2\n", "unavailability.csv": NO_BUSY})
    schedule = run(str(data), CONFIG, str(tmp_path / "a.json"))
    assert schedule["status"] == "INFEASIBLE"
    assert {"N03", "N05"} <= {m["code"] for m in schedule["messages"]}
    schedule = run(str(data), CONFIG, str(tmp_path / "b.json"), diagnose=False)
    assert not any(m["code"].startswith("N") for m in schedule["messages"])


# ---------------------------------------------------------------- cấu hình

def test_reschedule_config(tmp_path):
    from src.config import load_config
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"reschedule": {"time_limit_sec": 20, "weights": {"A-R1": 5000, "A-R9": 1}}}),
                    encoding="utf-8")
    messages = []
    cfg = load_config(str(path), messages)
    assert cfg["reschedule"]["time_limit_sec"] == 20
    assert cfg["reschedule"]["weights"]["A-R1"] == 5000 and cfg["reschedule"]["weights"]["A-R2"] == 100
    assert [(m.code, m.level) for m in messages] == [("D12", "warning")]
    path.write_text(json.dumps({"reschedule": {"weights": {"A-R1": -1}}}), encoding="utf-8")
    messages = []
    load_config(str(path), messages)
    assert [(m.code, m.level) for m in messages] == [("D12", "error")]
