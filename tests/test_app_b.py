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
    assert not {"toy_b", "medium_b", "large_b"} & set(_available_datasets())
    app = open_b()
    assert set(app.selectbox(key="b_dataset").options) == {"toy_b", "medium_b", "large_b"}
    assert app.selectbox(key="b_dataset").value == "toy_b"          # mặc định toy_b
    assert {t.label for t in app.tabs} >= {"Lịch học tuần B", "Sự cố B", "Thực nghiệm B"}


def test_reference_only_for_toy_b():
    app = open_b()
    app.selectbox(key="b_dataset").select("medium_b").run()
    assert not app.exception
    assert any("chỉ có cho bộ toy_b" in m.value for m in app.info)
    assert not any(m.label == "Buổi học đang hiển thị" for m in app.metric)


def test_run_solver_from_ui_writes_and_shows_timetable(tmp_path, monkeypatch):
    """Nút chạy giải toy_b bằng CP-SAT, ghi timetable.json vào thư mục kết quả rồi hiển thị ngay."""
    monkeypatch.setenv("EXAM_APP_OUTPUT_DIR", str(tmp_path))
    app = AppTest.from_file(str(APP), default_timeout=120).run()
    assert any("Chưa có kết quả cho toy_b" in m.value for m in app.info)
    app.button(key="b_run_solver").click().run()
    assert not app.exception
    assert any("OPTIMAL, mục tiêu 355" in s.value for s in app.success)
    saved = json.loads((tmp_path / "toy_b" / "timetable.json").read_text(encoding="utf-8"))
    assert saved["status"] == "OPTIMAL" and saved["objective"] == 355 and saved["violations"] == []
    assert next(m for m in app.metric if m.label == "Buổi học đang hiển thị").value == "24"


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
    assert not app.button(key="b_run_incident").disabled
    app.selectbox(key="b_incident_kind").select("Giảng viên bận").run()
    assert not app.exception
    app.selectbox(key="b_incident_kind").select("Thêm lớp").run()
    assert any("Mã lớp mới" in w.value for w in app.warning)
    app.text_input(key="b_new_class").set_value("NEW-CLASS").run()
    assert not app.exception


def test_reschedule_button_runs_b9(tmp_path, monkeypatch):
    """G2-LAB1 hỏng Thứ 6 ca 4: bấm "Xếp lại B" thì chỉ INT3505-TH bị dời ca, kết quả ghi vào thư mục kết quả."""
    monkeypatch.setenv("EXAM_APP_OUTPUT_DIR", str(tmp_path))
    app = AppTest.from_file(str(APP), default_timeout=120).run()
    app.radio(key="b_source").set_value("Mẫu toy_b tham chiếu").run()
    app.selectbox(key="b_resource_room").select("G2-LAB1").run()
    app.selectbox(key="b_incident_slot").select((6, 4)).run()
    app.button(key="b_run_incident").click().run()
    assert not app.exception
    assert any("Đã xếp lại" in s.value for s in app.success)
    saved = json.loads((tmp_path / "toy_b" / "retimetable.json").read_text(encoding="utf-8"))
    assert saved["reschedule"]["change_penalties"] == {"B-R1": 1, "B-R2": 0}
    changes = next(d.value for d in app.dataframe if "Thay đổi" in d.value.columns)
    assert list(changes["Lớp"]) == ["INT3505-TH"] and list(changes["Thay đổi"]) == ["time"]


def test_reschedule_button_adds_class(tmp_path, monkeypatch):
    monkeypatch.setenv("EXAM_APP_OUTPUT_DIR", str(tmp_path))
    app = AppTest.from_file(str(APP), default_timeout=120).run()
    app.radio(key="b_source").set_value("Mẫu toy_b tham chiếu").run()
    app.selectbox(key="b_incident_kind").select("Thêm lớp").run()
    app.text_input(key="b_new_class").set_value("NEW-LT").run()
    app.button(key="b_run_incident").click().run()
    assert not app.exception
    assert any("Đã xếp lại" in s.value for s in app.success)
    assert any("validator đã kiểm tra" in s.value for s in app.success)
    changes = next(d.value for d in app.dataframe if "Thay đổi" in d.value.columns)
    assert list(changes["Thay đổi"]) == ["added"]


UPLOAD_SCRIPT = """
import json
from pathlib import Path
import streamlit as st

class Upload:
    def __init__(self, path):
        self.name, self._data = path.name, path.read_bytes()
    def getvalue(self):
        return self._data

# AppTest chưa hỗ trợ chọn file: thay file_uploader bằng danh sách file ghi trong control.json
control = json.loads(Path({control!r}).read_text(encoding="utf-8"))
original = st.file_uploader
st.file_uploader = lambda *args, **kwargs: [Upload(Path(p)) for p in control]
try:
    from app.timetable_b import page_timetable_b
    page_timetable_b(Path({data!r}), Path({out!r}))
finally:
    st.file_uploader = original     # trả lại hàm thật để không ảnh hưởng các test khác cùng tiến trình
"""


def upload_app(tmp_path, files):
    control = tmp_path / "control.json"
    control.write_text(json.dumps([str(f) for f in files]), encoding="utf-8")
    script = UPLOAD_SCRIPT.format(control=str(control), data=str(ROOT / "data"), out=str(tmp_path / "out"))
    app = AppTest.from_string(script, default_timeout=120).run()
    app.radio(key="b_source").set_value("Tải CSV lên").run()
    assert not app.exception
    return app, control


def test_upload_csv_then_run_solver(tmp_path):
    files = sorted((ROOT / "data" / "toy_b").glob("*.csv"))
    app, control = upload_app(tmp_path, files)
    assert any("Đọc được 10 lớp" in c.value for c in app.caption)
    assert any("Chưa có kết quả cho upload_b" in m.value for m in app.info)
    app.button(key="b_run_solver").click().run()
    assert not app.exception
    assert any("OPTIMAL, mục tiêu 355" in s.value for s in app.success)
    assert next(m for m in app.metric if m.label == "Buổi học đang hiển thị").value == "24"
    assert json.loads((tmp_path / "out" / "upload_b" / "timetable.json").read_text(encoding="utf-8"))["objective"] == 355
    # Tải bộ file khác (bỏ preferences.csv): không hiện kết quả của bộ trước, phải chạy lại
    control.write_text(json.dumps([str(f) for f in files if f.name != "preferences.csv"]), encoding="utf-8")
    app.run()
    assert any("Chưa có kết quả cho upload_b" in m.value for m in app.info)
    assert not any(m.label == "Buổi học đang hiển thị" for m in app.metric)


def test_upload_with_missing_file_shows_error(tmp_path):
    files = [f for f in sorted((ROOT / "data" / "toy_b").glob("*.csv")) if f.name != "classes.csv"]
    app, _ = upload_app(tmp_path, files)
    assert any("D01" in e.value and "classes.csv" in e.value for e in app.error)
    assert not any(b.key == "b_run_solver" for b in app.button)


def test_several_incidents_at_once(tmp_path, monkeypatch):
    """Hai sự cố cùng lúc: G2-LAB1 hỏng Thứ 6 ca 4 và GV02 bận cả Thứ 4. Hai buổi phải dời ca."""
    monkeypatch.setenv("EXAM_APP_OUTPUT_DIR", str(tmp_path))
    app = AppTest.from_file(str(APP), default_timeout=120).run()
    app.radio(key="b_source").set_value("Mẫu toy_b tham chiếu").run()
    app.number_input(key="b_incident_count").set_value(2).run()
    app.selectbox(key="b_resource_room").select("G2-LAB1").run()
    app.selectbox(key="b_incident_slot").select((6, 4)).run()
    app.selectbox(key="b_incident_kind_1").select("Giảng viên bận").run()
    app.selectbox(key="b_resource_lecturer_1").select("GV02").run()
    app.selectbox(key="b_incident_slot_1").select((4, None)).run()
    assert not app.exception
    assert any("Buổi bị tác động trực tiếp: 1" in m.value for m in app.markdown)
    app.button(key="b_run_incident").click().run()
    assert not app.exception
    saved = json.loads((tmp_path / "toy_b" / "retimetable.json").read_text(encoding="utf-8"))
    assert len(saved["reschedule"]["incidents"]) == 2
    assert saved["reschedule"]["change_penalties"]["B-R1"] == 2 and saved["violations"] == []
    changes = next(d.value for d in app.dataframe if "Thay đổi" in d.value.columns)
    assert sorted(changes["Lớp"]) == ["INT2211-LT", "INT3505-TH"]
    assert any("Lịch mới hợp lệ với ca bận" in s.value for s in app.success)


def test_duplicate_new_class_ids_block_reschedule():
    app = open_b()
    app.number_input(key="b_incident_count").set_value(2).run()
    for i, suffix in enumerate(["", "_1"]):
        app.selectbox(key=f"b_incident_kind{suffix}").select("Thêm lớp").run()
        app.text_input(key=f"b_new_class{suffix}").set_value("NEW-LT").run()
    assert any("trùng" in w.value for w in app.warning)
    assert app.button(key="b_run_incident").disabled


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
