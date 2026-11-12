"""Focused weekly timetable and incident hand-off UI tests."""
import copy
import json
import subprocess
import sys
from io import BytesIO
from pathlib import Path

from openpyxl import load_workbook
from streamlit.testing.v1 import AppTest

from app.app import _available_datasets
from app.timetable_b import REFERENCE, compare_timetables, export_excel_b
from src.data_loader_b import load_instance_b

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app" / "app.py"


def open_b():
    app = AppTest.from_file(str(APP), default_timeout=30).run()
    app.radio(key="b_source").set_value("Mẫu toy_b tham chiếu").run()
    assert not app.exception
    return app


def test_streamlit_entrypoint_imports_with_script_directory_first():
    code = (
        "import runpy, sys; "
        "sys.path.insert(0, sys.argv[1]); "
        "runpy.run_path(sys.argv[2], run_name='entrypoint_test'); "
        "from app.timetable_b import page_timetable_b; "
        "from app.experiments_b import page_experiments_b"
    )
    result = subprocess.run([sys.executable, "-c", code, str(ROOT / "app"), str(APP)],
                            cwd=ROOT, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr


def test_dataset_lists_do_not_mix_problems():
    assert "toy" in _available_datasets()
    assert "toy_b" not in _available_datasets()
    app = open_b()
    assert app.selectbox(key="b_dataset").options == ["toy_b"]
    assert {t.label for t in app.tabs} >= {"Lịch học tuần B", "Sự cố B", "Thực nghiệm B"}


def test_weekly_timetable_and_required_group_filter():
    app = open_b()
    assert next(m for m in app.metric if m.label == "Buổi học đang hiển thị").value == "24"
    app.selectbox(key="b_group").select("K67-KHMT").run()
    assert not app.exception
    frame = next(d.value for d in app.dataframe if "session_id" in d.value.columns)
    expected = load_instance_b(str(ROOT / "data" / "toy_b")).instance.groups["K67-KHMT"]
    assert set(frame.class_id) == set(expected)
    assert all("K67-KHMT" in groups for groups in frame.groups)
    app.selectbox(key="b_room").select("G2-101").run()
    frame = next(d.value for d in app.dataframe if "session_id" in d.value.columns)
    assert set(frame.room_id) <= {"G2-101"}
    assert not app.exception


def test_excel_filtered_sessions_and_formula_safety():
    timetable = json.loads(REFERENCE.read_text(encoding="utf-8"))
    session = copy.deepcopy(timetable["sessions"][0])
    session["class_name"] = "=1+1"
    book = load_workbook(BytesIO(export_excel_b([session], [(2, 1)], {})))
    sheet = book["Buoi hoc"]
    assert sheet.max_row == 2
    assert sheet.cell(2, 3).value == "=1+1"
    assert sheet.cell(2, 3).data_type == "s"
    assert len(book["Lich tuan"][1]) == 5


def test_incident_room_change_file_comparison(tmp_path):
    app = open_b()
    old = json.loads(REFERENCE.read_text(encoding="utf-8"))
    new = copy.deepcopy(old)
    instance = load_instance_b(str(ROOT / "data" / "toy_b")).instance
    target = next(s for s in new["sessions"] if s["needs_lab"] and s["size"] <= 15
                  and any(r != s["room_id"] and (s["weekday"], s["period"]) not in instance.rooms[r].busy
                          and not any(t["room_id"] == r and (t["weekday"], t["period"]) == (s["weekday"], s["period"])
                                      for t in new["sessions"])
                          for r in instance.lab_rooms))
    room = target["room_id"]
    app.selectbox(key="b_resource_room").select(room).run()
    slot = (target["weekday"], target["period"])
    app.selectbox(key="b_incident_slot").select(slot).run()
    assert any("Buổi bị tác động trực tiếp: 1" in m.value for m in app.markdown)
    target["room_id"] = next(r for r in instance.lab_rooms if r != room)
    target["room_capacity"] = instance.rooms[target["room_id"]].capacity
    path = tmp_path / "retimetable.json"
    path.write_text(json.dumps(new), encoding="utf-8")
    app.text_input(key="b_retimetable").set_value(str(path)).run()
    assert not app.exception
    changes = next(d.value for d in app.dataframe if "Thay đổi" in d.value.columns)
    assert len(changes) == 1
    assert changes.iloc[0]["Thay đổi"] == "rooms"
    assert any("Lịch mới hợp lệ với ca bận" in s.value for s in app.success)
    assert app.button(key="b_run_incident").disabled
    app.selectbox(key="b_incident_kind").select("Giảng viên bận").run()
    assert not app.exception
    app.selectbox(key="b_incident_kind").select("Thêm lớp").run()
    assert any("Mã lớp mới" in w.value for w in app.warning)
    app.text_input(key="b_new_class").set_value("NEW-CLASS").run()
    assert not app.exception


def test_compare_matches_class_slot_before_moved_session():
    old = {"sessions": [dict(class_id="K", weekday=2, period=1, room_id="R"),
                        dict(class_id="K", weekday=3, period=1, room_id="R")]}
    new = copy.deepcopy(old)
    new["sessions"][0]["weekday"] = 4
    changes = compare_timetables(old, new)
    assert len(changes) == 1
    assert changes[0]["Thay đổi"] == "time"


def test_bad_result_does_not_leave_stale_incident_state(tmp_path):
    app = open_b()
    path = tmp_path / "bad.json"
    path.write_text('{"meta":{"problem":"B","dataset":"toy_b"},"status":"OPTIMAL","sessions":42}', encoding="utf-8")
    app.text_input(key="b_path_Mẫu toy_b tham chiếu_toy_b").set_value(str(path)).run()
    assert not app.exception
    assert any("Không đọc được lịch B" in w.value for w in app.warning)
    assert not any(b.key == "b_run_incident" for b in app.button)
