"""Kiểm thử src/data_loader.py theo docs/data_schema.md.

Mỗi ca kiểm thử lấy bộ data/toy, làm hỏng đúng một chỗ, rồi kiểm tra bộ đọc báo đúng mã thông báo.
"""
import json
import os

import pytest

from src.data_loader import load_instance

TOY = os.path.join(os.path.dirname(__file__), "..", "data", "toy")
FILES = ["slots.csv", "rooms.csv", "courses.csv", "enrollments.csv", "lecturers.csv", "teaching.csv",
         "unavailability.csv"]
BASE = {f: open(os.path.join(TOY, f), encoding="utf-8").read() for f in FILES}


def make(tmp_path, patch=None, drop=(), config=None):
    """Tạo bộ dữ liệu trong tmp_path từ data/toy, thay nội dung một số file, bỏ một số file."""
    for f in FILES:
        if f in drop:
            continue
        text = (patch or {}).get(f, BASE[f])
        (tmp_path / f).write_text(text, encoding="utf-8", newline="")
    cfg_path = None
    if config is not None:
        cfg_path = tmp_path / "config.json"
        cfg_path.write_text(config if isinstance(config, str) else json.dumps(config), encoding="utf-8")
    return load_instance(str(tmp_path), str(cfg_path) if cfg_path else None)


def add(f, line):
    return BASE[f] + line + "\n"


def repl(f, old, new):
    assert old in BASE[f], f"'{old}' không có trong {f}"
    return BASE[f].replace(old, new, 1)


def codes(result):
    return {m.code for m in result.messages}


def test_toy_loads_cleanly(tmp_path):
    r = make(tmp_path)
    assert r.ok
    assert codes(r) == {"P7"}            # INT3505 là môn thi viết được phép chia lượt
    inst = r.instance
    assert len(inst.slots) == 15 and len(inst.rooms) == 3 and len(inst.courses) == 5
    assert inst.rooms["G2-101"].exam_capacity == 30       # floor(60 × 0,5)
    assert inst.rooms["G2-LAB1"].exam_capacity == 12      # ghi đè
    assert inst.courses["INT2211"].max_sittings == 3      # mặc định môn thi máy
    assert inst.courses["MAT1099"].num_periods == 2
    assert "22020001" in inst.courses["INT2204"].students
    assert "GV07" not in inst.proctors                    # is_proctor = 0
    # 15/12 không có ca 2 nên môn 2 ca không được bắt đầu ở ca 1 ngày 15/12
    assert all(not (d.day == 15 and k == 1) for d, k in inst.start_slots("MAT1099"))


def test_student_id_keeps_leading_zero(tmp_path):
    r = make(tmp_path, {"enrollments.csv": add("enrollments.csv", "0123,INT2204")})
    assert "0123" in r.instance.courses["INT2204"].students


def test_bom_and_uppercase_header(tmp_path):
    r = make(tmp_path, {"slots.csv": "﻿" + BASE["slots.csv"].replace("date,period", "Date,PERIOD", 1)})
    assert r.ok and len(r.instance.slots) == 15


ERROR_CASES = [
    ("D01", "thiếu lecturers.csv", dict(drop=["lecturers.csv"])),
    ("D02", "thiếu cột duration_min", dict(patch={"courses.csv": "course_id,exam_type\nINT2204,written\n"})),
    ("D03", "period = 5", dict(patch={"slots.csv": add("slots.csv", "2026-12-18,5")})),
    ("D03", "exam_type = oral", dict(patch={"courses.csv": repl("courses.csv", "đối tượng,written",
                                                                "đối tượng,oral")})),
    ("D03", "duration_min = 0", dict(patch={"courses.csv": repl("courses.csv", "written,90", "written,0")})),
    ("D03", "seats = 60.5", dict(patch={"rooms.csv": repl("rooms.csv", "normal,60", "normal,60.5")})),
    ("D03", "ngày sai dạng", dict(patch={"slots.csv": add("slots.csv", "14/12/2026,1")})),
    ("D03", "is_proctor = yes", dict(patch={"lecturers.csv": repl("lecturers.csv", "Văn An,1", "Văn An,yes")})),
    ("D03", "max_sittings = 0", dict(patch={"courses.csv": repl("courses.csv", "computer,150,2", "computer,150,0")})),
    ("D04", "trùng course_id", dict(patch={"courses.csv": add("courses.csv", "INT2204,Trùng,written,60,")})),
    ("D04", "trùng ca", dict(patch={"slots.csv": add("slots.csv", "2026-12-14,1")})),
    ("D05", "đăng ký môn không có", dict(patch={"enrollments.csv": add("enrollments.csv", "22020001,INT9999")})),
    ("D05", "ca bận của phòng không có", dict(patch={"unavailability.csv": add("unavailability.csv",
                                                                              "room,X-999,2026-12-14,1,")})),
    ("D06", "mã có dấu tiếng Việt", dict(patch={"courses.csv": add("courses.csv", "Toán1,Toán,written,60,")})),
    ("D07", "Chủ nhật", dict(patch={"slots.csv": add("slots.csv", "2026-12-20,1")})),
    ("D08", "phòng máy thiếu num_computers", dict(patch={"rooms.csv": add("rooms.csv", "LAB9,,G2,lab,30,,")})),
    ("D08", "phòng thường thiếu sức chứa", dict(patch={"rooms.csv": add("rooms.csv", "P9,,G2,normal,,,")})),
    ("D11", "bật forbid_own_course, thiếu teaching", dict(drop=["teaching.csv"], config={"forbid_own_course": True})),
    ("D12", "strategy sai", dict(config={"strategy": "fast"})),
    ("D12", "trọng số âm", dict(config={"weights": {"A-S1": -5}})),
    ("D12", "file cấu hình hỏng", dict(config="{không phải json")),
    ("D15", "không ai đăng ký", dict(patch={"enrollments.csv": "student_id,course_id\n"})),
    ("P1", "môn thi 300 phút", dict(patch={"courses.csv": add("courses.csv", "C9,Dài,written,300,")})),
    ("P3", "không còn phòng máy", dict(patch={"rooms.csv": repl("rooms.csv", "lab,,15,12", "lab,,15,0")})),
    ("P4", "không có cặp ca liền", dict(patch={"slots.csv": "date,period\n2026-12-14,1\n2026-12-14,3\n"
                                                             "2026-12-15,2\n2026-12-15,4\n"})),
    ("P5", "thi máy quá đông so với số lượt", dict(patch={"courses.csv": repl("courses.csv", "computer,60,",
                                                                              "computer,60,1")})),
    ("P6", "chỉ 1 giám thị", dict(patch={"lecturers.csv": "lecturer_id,is_proctor\nGV01,1\nGV02,0\nGV03,0\n"
                                                           "GV04,0\nGV05,0\nGV06,0\nGV07,0\n"})),
]


@pytest.mark.parametrize("code,name,kwargs", ERROR_CASES, ids=[f"{c}-{n}" for c, n, _ in ERROR_CASES])
def test_error_cases(tmp_path, code, name, kwargs):
    r = make(tmp_path, **kwargs)
    assert not r.ok, f"{name}: lẽ ra phải dừng"
    assert code in codes(r), f"{name}: báo {sorted(codes(r))}, cần {code}"


WARNING_CASES = [
    ("D09", "cột thừa", dict(patch={"rooms.csv": BASE["rooms.csv"].replace("exam_capacity\n", "exam_capacity,floor\n",
                                                                           1)})),
    ("D10", "ca bận ngoài lịch thi", dict(patch={"unavailability.csv": add("unavailability.csv",
                                                                           "lecturer,GV02,2026-12-30,,")})),
    ("D12", "khóa cấu hình lạ", dict(config={"timelimit": 10})),
    ("D13", "exam_capacity > num_computers", dict(patch={"rooms.csv": add("rooms.csv", "LAB2,,G2,lab,,20,25")})),
    ("D14", "phòng thường có num_computers", dict(patch={"rooms.csv": add("rooms.csv", "P3,,G2,normal,30,5,")})),
    ("D16", "dấu chấm phẩy", dict(patch={"teaching.csv": BASE["teaching.csv"].replace(",", ";")})),
    ("P2", "môn không ai đăng ký", dict(patch={"courses.csv": add("courses.csv", "C9,Trống,written,60,")})),
    ("P7", "môn thi viết cho chia lượt", dict()),
    ("P8", "đăng ký lặp", dict(patch={"enrollments.csv": add("enrollments.csv", "22020001,INT2204")})),
    ("P9", "phòng sức chứa 0", dict(patch={"rooms.csv": add("rooms.csv", "P0,,G2,normal,1,,")})),
]


@pytest.mark.parametrize("code,name,kwargs", WARNING_CASES, ids=[f"{c}-{n}" for c, n, _ in WARNING_CASES])
def test_warning_cases(tmp_path, code, name, kwargs):
    r = make(tmp_path, **kwargs)
    assert r.ok, f"{name}: cảnh báo không được làm dừng, nhưng báo {[m.to_dict() for m in r.messages]}"
    assert code in codes(r)


def test_no_cascading_d05(tmp_path):
    """Môn có dòng lỗi không kéo theo D05 ở các file tham chiếu tới nó (data_schema mục 5)."""
    r = make(tmp_path, {"courses.csv": repl("courses.csv", "written,90", "written,abc")})
    assert "D03" in codes(r) and "D05" not in codes(r)


def test_no_d08_after_bad_number(tmp_path):
    r = make(tmp_path, {"rooms.csv": repl("rooms.csv", "normal,60", "normal,60.5")})
    assert "D03" in codes(r) and "D08" not in codes(r)


def test_line_numbers_count_header(tmp_path):
    r = make(tmp_path, {"slots.csv": add("slots.csv", "2026-12-18,5")})
    msg = next(m for m in r.messages if m.code == "D03")
    assert msg.file == "slots.csv" and msg.line == 17      # tiêu đề + 15 dòng dữ liệu + dòng lỗi
