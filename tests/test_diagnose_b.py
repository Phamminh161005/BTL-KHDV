"""Kiểm thử chẩn đoán bài toán B (src/diagnose_b.py) và việc run.py tự chẩn đoán khi vô nghiệm.

Hai bộ dữ liệu nhỏ dựng riêng, đều vượt qua kiểm tra PB1–PB7 nhưng không có lịch.
"""
import json

from src.data_loader_b import load_instance_b
from src.diagnose_b import diagnose_b
from src.run import run

ROOMS = "room_id,room_type,seats,num_computers\nR1,normal,60,\nR2,normal,40,\n"
LECTURERS = "lecturer_id\nGV01\nGV02\n"
SLOTS = "weekday,period\n2,1\n2,2\n2,3\n2,4\n"


def write(folder, files):
    folder.mkdir(exist_ok=True)
    for name, text in files.items():
        (folder / name).write_text(text, encoding="utf-8", newline="")
    return folder


def lecturer_and_group(tmp_path):
    """Nhóm H cần 4 buổi trong 4 ca, nhưng ca (2,1) cả hai giảng viên đều bận: còn 3 ca cho 4 buổi.
    Bỏ B-H5 (gồm ca bận) hoặc bỏ B-H7 thì xếp được; bỏ B-H6 thì không."""
    return write(tmp_path / "gv_nhom", {
        "week_slots.csv": SLOTS, "rooms.csv": ROOMS, "lecturers.csv": LECTURERS,
        "classes.csv": "class_id,needs_lab,size,sessions_per_week,lecturer_id\nA,0,30,3,GV01\nB,0,30,1,GV02\n",
        "class_groups.csv": "class_id,group_id\nA,H\nB,H\n",
        "week_unavailability.csv": "resource_type,resource_id,weekday,period\nlecturer,GV01,2,1\nlecturer,GV02,2,1\n",
    })


def room_shortage(tmp_path):
    """Hai lớp 50 sinh viên chỉ vào được R1 (60 ghế), cần 3 + 2 = 5 buổi nhưng R1 chỉ có 4 ca. PB5 không phát hiện vì
    tính cả R2. Bỏ cả ba nhóm vẫn vô nghiệm: N03."""
    return write(tmp_path / "phong", {
        "week_slots.csv": SLOTS, "rooms.csv": ROOMS, "lecturers.csv": LECTURERS,
        "classes.csv": "class_id,needs_lab,size,sessions_per_week,lecturer_id\nA,0,50,3,GV01\nB,0,50,2,GV02\n",
    })


def codes(messages):
    return [m.code for m in messages]


def test_lecturer_and_group_causes(tmp_path):
    loaded = load_instance_b(str(lecturer_and_group(tmp_path)))
    assert loaded.ok
    messages = diagnose_b(loaded.instance, loaded.config, time_limit=10)
    found = [m.message for m in messages if m.code == "N01"]
    assert len(found) == 2
    assert any("B-H5" in m for m in found) and any("B-H7" in m for m in found)
    assert not any("B-H6" in m for m in found)
    assert codes(messages)[-1] == "N05"


def test_room_shortage_is_n03(tmp_path):
    loaded = load_instance_b(str(room_shortage(tmp_path)))
    assert loaded.ok
    messages = diagnose_b(loaded.instance, loaded.config, time_limit=10)
    assert codes(messages) == ["N03", "N05"]


def test_run_b_diagnoses_when_infeasible(tmp_path):
    folder = lecturer_and_group(tmp_path)
    out = tmp_path / "timetable.json"
    table = run(str(folder), None, str(out), problem="B")
    assert table["status"] == "INFEASIBLE" and table["sessions"] == []
    assert codes_of(table).count("N01") == 2 and "N05" in codes_of(table)
    assert json.loads(out.read_text(encoding="utf-8"))["status"] == "INFEASIBLE"
    table = run(str(folder), None, str(out), problem="B", diagnose=False)
    assert not [c for c in codes_of(table) if c.startswith("N")]


def codes_of(table):
    return [m["code"] for m in table["messages"]]
