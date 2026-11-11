"""Kiểm thử src/data_loader_b.py theo docs/data_schema.md mục 9 và model_spec B.7.

Mỗi ca kiểm thử lấy bộ data/toy_b, làm hỏng đúng một chỗ, rồi kiểm tra bộ đọc báo đúng mã thông báo.
"""
import json
import os

import pytest

from src.data_loader import load_instance
from src.data_loader_b import load_instance_b

TOY_B = os.path.join(os.path.dirname(__file__), "..", "data", "toy_b")
FILES = ["week_slots.csv", "rooms.csv", "lecturers.csv", "classes.csv", "class_groups.csv",
         "week_unavailability.csv", "preferences.csv"]
BASE = {f: open(os.path.join(TOY_B, f), encoding="utf-8").read() for f in FILES}


def make(tmp_path, patch=None, drop=(), config=None):
    """Tạo bộ dữ liệu trong tmp_path từ data/toy_b, thay nội dung một số file, bỏ một số file."""
    for f in FILES:
        if f in drop:
            continue
        text = (patch or {}).get(f, BASE[f])
        (tmp_path / f).write_text(text, encoding="utf-8", newline="")
    cfg_path = None
    if config is not None:
        cfg_path = tmp_path / "config.json"
        cfg_path.write_text(config if isinstance(config, str) else json.dumps(config), encoding="utf-8")
    return load_instance_b(str(tmp_path), str(cfg_path) if cfg_path else None)


def add(f, line):
    return BASE[f] + line + "\n"


def repl(f, old, new):
    assert old in BASE[f], f"'{old}' không có trong {f}"
    return BASE[f].replace(old, new, 1)


def codes(result):
    return {m.code for m in result.messages}


def test_toy_b_loads_cleanly(tmp_path):
    r = make(tmp_path)
    assert r.ok
    assert codes(r) == {"PB6"}            # ELT2035 có 7 buổi trong 6 ngày học
    inst = r.instance
    assert len(inst.slots) == 22 and inst.days == [2, 3, 4, 5, 6, 7]
    assert inst.slots_on(7) == [(7, 1), (7, 2)]
    assert len(inst.rooms) == 4 and len(inst.classes) == 10
    assert inst.rooms["G2-101"].capacity == 60           # seats, không chia written_capacity_ratio
    assert inst.rooms["G2-LAB1"].capacity == 15          # num_computers, bỏ qua exam_capacity = 12
    assert inst.lab_rooms == ["G2-LAB1", "G2-LAB2"]
    assert inst.groups["K67-KHMT"] == ["INT2211-LT", "INT2211-TH", "INT3306-TH", "MAT1099"]
    assert inst.classes["INT2204-LT"].groups == {"K67-CN1", "K67-CN2"}
    assert inst.classes["INT3505"].groups == set()       # lớp tự chọn
    assert inst.teaching["GV04"] == ["INT2204-TH1", "INT2204-TH2"]
    assert "GV07" in inst.teaching


def test_toy_b_derived_sets(tmp_path):
    inst = make(tmp_path).instance
    assert inst.rooms_for("INT2204-LT") == ["G2-101"]        # 55 sinh viên, G2-102 chỉ 40 ghế
    assert inst.rooms_for("INT2204-TH1") == ["G2-LAB2"]      # 18 sinh viên, G2-LAB1 chỉ 15 máy
    assert inst.rooms_for("INT3505-TH") == ["G2-LAB1", "G2-LAB2"]
    assert inst.rooms_for("INT3505") == ["G2-101", "G2-102"]  # lớp lý thuyết không vào phòng máy
    # GV06 chỉ rảnh Thứ 6, G2-LAB2 bảo trì cả Thứ 6
    assert inst.slots_for("INT3505-TH", "G2-LAB1") == [(6, 1), (6, 2), (6, 3), (6, 4)]
    assert inst.slots_for("INT3505-TH", "G2-LAB2") == []
    assert (2, 1) not in inst.slots_for("INT3505", "G2-101") and (2, 1) not in inst.slots_for("MAT1099", "G2-101")
    assert inst.labs_available((6, 1)) == 1 and inst.lab_limit((6, 1), 0.85) == 0
    assert inst.labs_available((2, 1)) == 2 and inst.lab_limit((2, 1), 0.85) == 1
    assert inst.lecturers["GV01"].busy == {(3, 1), (3, 2), (3, 3), (3, 4)}
    assert inst.lecturers["GV01"].avoid == {(7, 1), (7, 2)}   # Thứ 7 chỉ có 2 ca
    assert inst.lecturers["GV05"].avoid == {(2, 1), (2, 2), (2, 3), (2, 4)}


def test_load_instance_dispatches_on_problem_key(tmp_path):
    make(tmp_path)
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps({"problem": "B"}), encoding="utf-8")
    r = load_instance(str(tmp_path), str(cfg))
    assert r.ok and r.config["problem"] == "B" and len(r.instance.classes) == 10


def test_default_config_has_b_keys(tmp_path):
    cfg = make(tmp_path).config
    assert cfg["lab_reserve_ratio"] == 0.85
    assert {k: cfg["weights"][k] for k in ("B-S1", "B-S2", "B-S3", "B-S4")} == \
        {"B-S1": 1, "B-S2": 50, "B-S3": 100, "B-S4": 30}
    assert cfg["reschedule"]["weights"]["B-R1"] == 100 and cfg["reschedule"]["weights"]["B-R2"] == 20


@pytest.mark.parametrize("config, code", [
    ({"strategy": "two_phase"}, "D12"),
    ({"lab_reserve_ratio": 1.5}, "D12"),
    ({"lab_reserve_ratio": 0}, "D12"),
    ({"problem": "C"}, "D12"),
])
def test_bad_config(tmp_path, config, code):
    r = make(tmp_path, config=config)
    assert not r.ok and code in codes(r)


@pytest.mark.parametrize("patch, drop, code", [
    (None, ("classes.csv",), "D01"),
    (None, ("week_slots.csv",), "D01"),
    ({"classes.csv": repl("classes.csv", "needs_lab", "lab")}, (), "D02"),
    ({"week_slots.csv": add("week_slots.csv", "8,1")}, (), "D03"),
    ({"week_slots.csv": add("week_slots.csv", "7,5")}, (), "D03"),
    ({"classes.csv": repl("classes.csv", "INT2204,0,55", "INT2204,2,55")}, (), "D03"),
    ({"classes.csv": repl("classes.csv", "0,30,1,GV06", "0,30,0,GV06")}, (), "D03"),
    ({"classes.csv": repl("classes.csv", "0,40,7,GV07", "0,0,7,GV07")}, (), "D03"),
    ({"week_slots.csv": add("week_slots.csv", "2,1")}, (), "D04"),
    ({"classes.csv": add("classes.csv", "INT3505,Trùng,INT3505,0,30,1,GV06")}, (), "D04"),
    ({"classes.csv": repl("classes.csv", "GV07", "GV99")}, (), "D05"),
    ({"class_groups.csv": add("class_groups.csv", "INT9999,K67-CN1")}, (), "D05"),
    ({"week_unavailability.csv": add("week_unavailability.csv", "room,G9-999,2,1,")}, (), "D05"),
    ({"preferences.csv": add("preferences.csv", "GV99,2,1,")}, (), "D05"),
    ({"classes.csv": repl("classes.csv", "INT3505,Khoa", "INT 3505,Khoa")}, (), "D06"),
    ({"rooms.csv": repl("rooms.csv", "normal,40,,", "normal,,,30")}, (), "D08"),
    ({"rooms.csv": repl("rooms.csv", "lab,,20,", "lab,,,20")}, (), "D08"),
])
def test_format_errors(tmp_path, patch, drop, code):
    r = make(tmp_path, patch, drop)
    assert not r.ok
    assert code in codes(r)


def test_no_cascade_d05_when_lecturer_row_is_broken(tmp_path):
    """GV07 có trong lecturers.csv nhưng dòng bị lỗi D03: classes.csv không báo thêm D05."""
    r = make(tmp_path, {"lecturers.csv": repl("lecturers.csv", "Đỗ Văn Giang,0", "Đỗ Văn Giang,x")})
    assert not r.ok
    assert codes(r) == {"D03"}


@pytest.mark.parametrize("patch, code", [
    ({"week_unavailability.csv": add("week_unavailability.csv", "room,G2-102,7,4,")}, "D10"),
    ({"preferences.csv": add("preferences.csv", "GV02,7,3,")}, "D10"),
    ({"rooms.csv": repl("rooms.csv", "normal,40,,", "normal,40,25,")}, "D14"),
    ({"class_groups.csv": repl("class_groups.csv", "class_id,group_id", "class_id,group_id,ghi_chu")}, "D09"),
])
def test_warnings_still_load(tmp_path, patch, code):
    r = make(tmp_path, patch)
    assert r.ok
    assert code in codes(r)


def test_room_with_zero_capacity_is_dropped(tmp_path):
    r = make(tmp_path, {"rooms.csv": add("rooms.csv", "G2-LAB3,Phòng máy 3,G2,lab,,0,")})
    assert r.ok and "P9" in codes(r)
    assert "G2-LAB3" not in r.instance.rooms


def test_preference_inside_busy_slot_is_dropped(tmp_path):
    """GV01 bận cả Thứ 3; thêm nguyện vọng không dạy Thứ 3 ca 1 thì coi là bận, không báo."""
    r = make(tmp_path, {"preferences.csv": add("preferences.csv", "GV01,3,1,")})
    assert r.ok and codes(r) == {"PB6"}
    assert (3, 1) not in r.instance.lecturers["GV01"].avoid


def test_duplicate_group_row_is_silently_merged(tmp_path):
    r = make(tmp_path, {"class_groups.csv": add("class_groups.csv", "MAT1099,K67-CN1")})
    assert r.ok and codes(r) == {"PB6"}
    assert r.instance.groups["K67-CN1"].count("MAT1099") == 1


@pytest.mark.parametrize("patch, code", [
    # PB1: lớp lý thuyết 70 sinh viên, phòng thường lớn nhất 60 ghế
    ({"classes.csv": add("classes.csv", "BIG,Lớp đông,,0,70,1,GV07")}, "PB1"),
    # PB1: lớp thực hành 25 sinh viên, phòng máy lớn nhất 20 máy
    ({"classes.csv": add("classes.csv", "BIGLAB,Lớp đông,,1,25,1,GV07")}, "PB1"),
    # PB2: GV06 chỉ rảnh 4 ca Thứ 6
    ({"classes.csv": repl("classes.csv", "0,30,1,GV06", "0,30,5,GV06")}, "PB2"),
    # PB3: GV07 dạy 7 + 16 = 23 buổi, tuần chỉ có 22 ca
    ({"classes.csv": add("classes.csv", "EXTRA,Lớp thêm,,0,10,16,GV07")}, "PB3"),
    # PB4: nhóm K67-CN1 có 2+1+2+3 = 8 buổi; thêm ELT2035 (7) và lớp 8 buổi thành 23 > 22
    ({"classes.csv": add("classes.csv", "EXTRA,Lớp thêm,,0,10,8,GV03"),
      "class_groups.csv": add("class_groups.csv", "ELT2035,K67-CN1\nEXTRA,K67-CN1")}, "PB4"),
    # PB5: 9 buổi phòng máy có sẵn, thêm 3 lớp x 11 buổi thành 42 > 40 cặp (phòng máy, ca)
    ({"classes.csv": add("classes.csv", "L1,,,1,10,11,GV01\nL2,,,1,10,11,GV02\nL3,,,1,10,11,GV03")}, "PB5"),
])
def test_precheck_errors(tmp_path, patch, code):
    r = make(tmp_path, patch)
    assert not r.ok
    assert code in codes(r)


def test_pb7_warning_when_ratio_too_low(tmp_path):
    """9 buổi phòng máy trên 40 cặp (phòng máy, ca) không bận: 22,5% > 20%."""
    r = make(tmp_path, config={"lab_reserve_ratio": 0.2})
    assert r.ok and "PB7" in codes(r)
    r = make(tmp_path, config={"lab_reserve_ratio": 0.25})
    assert r.ok and "PB7" not in codes(r)
