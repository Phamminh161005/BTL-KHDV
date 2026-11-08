"""Kiểm thử giao diện: xem kết quả (MANH-1), nhập dữ liệu + xếp lịch (MANH-2), so sánh + sự cố (MANH-3)."""
import copy
import json
import shutil
import subprocess
import sys
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

import pytest
from openpyxl import load_workbook
from streamlit.testing.v1 import AppTest

from app.app import DEFAULT_PATH, KPI_NOTES, _run_summary, calendar_rows, compare_schedules, export_excel

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app" / "app.py"


def open_result(path):
    app = AppTest.from_file(str(APP), default_timeout=15).run()
    app.text_input[0].set_value(str(path)).run()
    assert not app.exception
    return app


@pytest.fixture
def toy():
    return json.loads(DEFAULT_PATH.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# MANH-1: Kiểm thử trang xem kết quả
# ---------------------------------------------------------------------------

def test_toy_app_and_lookups(toy):
    app = AppTest.from_file(str(APP), default_timeout=15).run()
    assert not app.exception
    # Tab "Xem kết quả" là tab đầu tiên nên metric[0] là "Trạng thái"
    assert app.metric[0].value == "OPTIMAL"
    assert len(app.tabs) >= 4
    assert set(app.dataframe[1].value["Chỉ số"]) == set(KPI_NOTES)
    assert len(app.dataframe[0].value) == 6
    room = toy["sittings"][0]["rooms"][0]
    app.selectbox[0].select(room["room_id"]).run()
    assert set(app.dataframe[3].value["Phòng"]) == {room["room_id"]}
    student = room["students"][0]
    app.text_input[1].set_value(student).run()
    expected = sum(student in r["students"] for s in toy["sittings"] for r in s["rooms"])
    assert len(app.dataframe[4].value) == expected
    lecturer = room["proctors"][0]
    app.selectbox[1].select(lecturer).run()
    assert all(lecturer in value.split(", ") for value in app.dataframe[5].value["Giám thị"])
    app.text_input[1].set_value("KHONG_TON_TAI").run()
    assert any("Không tìm thấy" in info.value for info in app.info)
    assert not app.exception


def test_upload_takes_priority_over_path(toy):
    toy["status"] = "FEASIBLE"
    toy["kpi"]["avg_gap_days"] = None
    upload = BytesIO(json.dumps(toy).encode("utf-8"))
    with patch("streamlit.file_uploader", return_value=upload):
        app = AppTest.from_file(str(APP), default_timeout=15).run()
        app.text_input[0].set_value("missing.json").run()
    assert not app.exception
    assert app.metric[0].value == "FEASIBLE"
    assert not app.error
    assert "Không áp dụng" in app.dataframe[1].value.loc[2, "Giá trị"]


def test_calendar_has_four_periods_and_repeats_two_period_exam(toy):
    sitting = next(s for s in toy["sittings"] if len(s["periods"]) == 2)
    rows = calendar_rows(toy["sittings"])
    row = next(row for row in rows if row["Ngày"] == sitting["date"])
    assert len(row) == 5
    for period in sitting["periods"]:
        key = next(key for key in row if key.startswith(f"Ca {period} "))
        assert sitting["course_id"] in row[key]
        assert all(r["room_id"] in row[key] for r in sitting["rooms"])


def test_excel_contains_room_assignments_and_students(toy):
    workbook = load_workbook(BytesIO(export_excel(toy["sittings"])))
    assert workbook.sheetnames == ["Lịch tổng", "Sinh viên theo phòng"]
    rooms = [r for s in toy["sittings"] for r in s["rooms"]]
    assert workbook.worksheets[0].max_row == len(rooms) + 1
    assert workbook.worksheets[1].max_row == sum(len(r["students"]) for r in rooms) + 1
    assert workbook.worksheets[1].cell(2, 10).value == rooms[0]["students"][0]
    toy["sittings"][0]["course_name"] = "=1+1"
    workbook = load_workbook(BytesIO(export_excel(toy["sittings"])))
    assert workbook.worksheets[0].cell(2, 3).data_type == "s"


@pytest.mark.parametrize("status", ["INPUT_ERROR", "INFEASIBLE", "UNKNOWN"])
def test_no_schedule_for_unsolved_status(tmp_path, toy, status):
    toy.update(status=status, objective=None, penalties=None, kpi=None)
    # Kể cả file có lượt thi cũ, không vẽ lịch nếu trạng thái không có lời giải.
    toy["messages"] = [{"level": "error", "code": "D01", "message": "Dữ liệu không hợp lệ", "file": "rooms.csv", "line": 2}]
    path = tmp_path / "result.json"
    path.write_text(json.dumps(toy), encoding="utf-8")
    app = open_result(path)
    assert app.metric[0].value == status
    assert app.error


def test_real_input_error_from_cli(tmp_path):
    data = tmp_path / "bad_data"
    shutil.copytree(ROOT / "data" / "toy", data)
    rooms = data / "rooms.csv"
    rooms.write_text(rooms.read_text(encoding="utf-8").replace("normal,60", "normal,-1"), encoding="utf-8")
    result_path = tmp_path / "loi.json"
    result = subprocess.run(
        [sys.executable, "-m", "src.run", "--data", str(data), "--out", str(result_path)],
        cwd=ROOT, capture_output=True, check=False,
    )
    assert result.returncode == 1, result.stderr
    assert json.loads(result_path.read_text(encoding="utf-8"))["status"] == "INPUT_ERROR"
    app = open_result(result_path)
    assert app.metric[0].value == "INPUT_ERROR"
    assert app.error


def test_messages_and_violations(tmp_path, toy):
    toy["messages"] = [{"level": level, "code": level, "message": f"Thông báo {level}"}
                       for level in ("error", "warning", "info")]
    toy["violations"] = [{"code": "A-H2", "message": "Trùng ca", "refs": {"student_id": "22020001"}}]
    path = tmp_path / "violations.json"
    path.write_text(json.dumps(toy), encoding="utf-8")
    app = open_result(path)
    assert any("A-H2" in message.value for message in app.error)
    assert any("warning" in message.value for message in app.warning)
    assert any("info" in message.value for message in app.info)


@pytest.mark.parametrize("content", ["{", "[]", '{"status": "INVALID"}', '{"status": "INPUT_ERROR", "messages": [1]}'])
def test_bad_json_is_reported(tmp_path, content):
    path = tmp_path / "bad.json"
    path.write_text(content, encoding="utf-8")
    assert open_result(path).error


def test_missing_file_is_reported(tmp_path):
    assert open_result(tmp_path / "missing.json").error


# ---------------------------------------------------------------------------
# MANH-2: Kiểm thử giao diện nhập dữ liệu và xếp lịch
# ---------------------------------------------------------------------------

def _run_input_app(timeout=15):
    """Khởi động app."""
    return AppTest.from_file(str(APP), default_timeout=timeout).run()


def test_toy_data_has_only_info_and_run_enabled():
    """Chọn data/toy: chỉ có thông báo P7 (info), nút xếp lịch bật."""
    app = _run_input_app()
    assert not app.exception

    # Tab nhập là tab thứ hai, chọn "Bộ dữ liệu có sẵn" rồi chọn "toy"
    app.radio[0].set_value("Bộ dữ liệu có sẵn").run()
    # selectbox từ tab nhập là sau các selectbox của tab xem (phòng, giảng viên)
    # Tìm selectbox có nhãn "Chọn bộ dữ liệu"
    ds_box = next(sb for sb in app.selectbox if sb.label == "Chọn bộ dữ liệu")
    ds_box.select("toy").run()
    assert not app.exception

    # Thông báo P7 (info) phải xuất hiện
    has_p7 = any("P7" in info.value for info in app.info)
    assert has_p7, "Bộ toy phải có thông báo P7 (info) cho môn thi viết chia lượt"

    # Không có lỗi D (error) từ kiểm tra dữ liệu
    data_errors = [e for e in app.error if any(
        code in e.value for code in ["[D0", "[D1", "[P1", "[P2", "[P3", "[P4", "[P5", "[P6"]
    )]
    assert not data_errors, f"Bộ toy không được có lỗi dữ liệu: {[e.value for e in data_errors]}"

    # Nút "Xếp lịch" phải bật
    buttons = [b for b in app.button if b.label == "Xếp lịch"]
    assert buttons, "Phải có nút 'Xếp lịch'"
    assert not buttons[0].disabled, "Nút 'Xếp lịch' phải bật khi dữ liệu toy hợp lệ"


@pytest.fixture
def app_dirs(tmp_path, monkeypatch):
    """Thư mục data/ và output/ riêng cho giao diện trong lúc kiểm thử, để không ghi vào repo."""
    data_dir, output_dir = tmp_path / "data", tmp_path / "output"
    shutil.copytree(ROOT / "data" / "toy", data_dir / "toy")
    output_dir.mkdir()
    monkeypatch.setenv("EXAM_APP_DATA_DIR", str(data_dir))
    monkeypatch.setenv("EXAM_APP_OUTPUT_DIR", str(output_dir))
    return data_dir, output_dir


def _select_dataset(app, name):
    app.radio[0].set_value("Bộ dữ liệu có sẵn").run()
    next(sb for sb in app.selectbox if sb.label == "Chọn bộ dữ liệu").select(name).run()
    assert not app.exception
    return app


def _run_button(app):
    return next(b for b in app.button if b.label == "Xếp lịch")


def test_bad_data_shows_error_and_disables_run(app_dirs):
    """Sao chép toy rồi làm sai: hiện lỗi D và nút chạy tắt."""
    data_dir, _ = app_dirs
    bad = data_dir / "bad_toy"
    shutil.copytree(data_dir / "toy", bad)
    # Đổi tên cột bắt buộc room_type để tạo lỗi D02
    rooms_path = bad / "rooms.csv"
    rooms_path.write_text(rooms_path.read_text(encoding="utf-8").replace("room_type", "wrong_col"),
                          encoding="utf-8")

    app = _select_dataset(_run_input_app(), "bad_toy")
    assert any(any(code in e.value for code in ["[D0", "[D1"]) for e in app.error), \
        "Bộ dữ liệu lỗi phải hiện lỗi mã D"
    assert _run_button(app).disabled, "Nút 'Xếp lịch' phải tắt khi dữ liệu có lỗi"


def test_forbid_own_course_without_teaching_disables_run(app_dirs):
    """Bật forbid_own_course với bộ dữ liệu thiếu teaching.csv: báo D11 và khóa nút ngay, không chờ chạy."""
    data_dir, _ = app_dirs
    shutil.copytree(data_dir / "toy", data_dir / "no_teaching")
    (data_dir / "no_teaching" / "teaching.csv").unlink()

    app = _select_dataset(_run_input_app(), "no_teaching")
    assert not _run_button(app).disabled
    next(c for c in app.checkbox if "forbid_own_course" in c.label).check().run()
    assert any("D11" in e.value for e in app.error)
    assert _run_button(app).disabled


def test_run_shows_new_result_immediately_and_can_open_other_file(app_dirs):
    """Bấm Xếp lịch: tab Xem kết quả hiện ngay kết quả mới (lỗi A); sau đó vẫn mở được file khác (lỗi B)."""
    _, output_dir = app_dirs
    app = _select_dataset(_run_input_app(timeout=120), "toy")
    next(n for n in app.number_input if n.label.startswith("time_limit_sec")).set_value(15).run()
    _run_button(app).click().run()
    assert not app.exception

    result = json.loads((output_dir / "toy" / "schedule.json").read_text(encoding="utf-8"))
    assert result["status"] in ("OPTIMAL", "FEASIBLE") and result["violations"] == []
    # Tab "Xem kết quả" (vẽ trước) đã hiện đúng kết quả vừa chạy, không phải file cũ
    assert any("kết quả vừa chạy" in i.value for i in app.info)
    assert app.metric[0].value == result["status"]
    assert app.metric[3].value == str(result["solve_time_sec"])
    # Thông báo sau khi chạy theo đúng trạng thái
    assert any(f"Đã xếp xong ({result['status']})" in m.value for m in list(app.success) + list(app.warning))

    next(b for b in app.button if b.label == "Mở file khác").click().run()
    assert any(t.label == "Đường dẫn file kết quả" for t in app.text_input)
    assert not any("kết quả vừa chạy" in i.value for i in app.info)


@pytest.mark.parametrize("status", ["INPUT_ERROR", "INFEASIBLE", "UNKNOWN"])
def test_run_summary_never_reports_success_without_schedule(toy, status):
    """Lỗi C: kết quả không có lịch thì không được báo 'Đã xếp xong'."""
    toy.update(status=status, sittings=[], violations=[],
               messages=[{"level": "error", "code": "D11", "message": "Thiếu teaching.csv"}])
    kind, text = _run_summary(toy, "out.json")
    assert kind == "error" and "Đã xếp xong" not in text
    if status == "INPUT_ERROR":
        assert "Thiếu teaching.csv" in text


def test_run_summary_reports_violations_as_error(toy):
    toy["violations"] = [{"code": "A-H2", "message": "Trùng ca"}]
    kind, text = _run_summary(toy, "out.json")
    assert kind == "error" and "1 vi phạm" in text


# ---------------------------------------------------------------------------
# MANH-3: Kiểm thử so sánh hai lịch
# ---------------------------------------------------------------------------

def _move_first_sitting(schedule):
    """Dời lượt đầu tiên sang ca khác như khi xếp lại thật: sitting_id đổi theo ca mới."""
    target = schedule["sittings"][0]
    target["start_period"] = 1 if target["start_period"] != 1 else 2
    target["periods"] = [target["start_period"]]
    target["sitting_id"] = f"{target['course_id']}@{target['date']}_{target['start_period']}"
    return target


def test_compare_identical_schedules(toy):
    """So sánh hai lịch giống hệt nhau: không có lượt thay đổi."""
    changed, summary = compare_schedules(toy, toy)
    assert changed == []
    assert summary["students_affected"] == 0
    assert summary["proctors_affected"] == 0


def test_compare_with_moved_sitting(toy):
    """Dời một lượt thi sang ca khác: bảng thay đổi có đúng một dòng "Dời ca", không phải "Đã xóa" + "Thêm mới"."""
    modified = copy.deepcopy(toy)
    target = _move_first_sitting(modified)

    changed, summary = compare_schedules(toy, modified)
    assert len(changed) == 1
    assert changed[0]["Mã môn"] == target["course_id"]
    assert changed[0]["Thay đổi"] == "Dời ca"
    assert summary["sittings_moved"] == 1
    assert summary["sittings_removed"] == 0 and summary["sittings_added"] == 0
    # Mọi sinh viên của lượt bị dời đều bị ảnh hưởng, và chỉ họ
    assert summary["students_affected"] == target["num_students"]
    assert changed[0]["Sinh viên bị ảnh hưởng"] == target["num_students"]


def test_compare_with_changed_proctors(toy):
    """Chỉ đổi giám thị một phòng: không sinh viên nào bị ảnh hưởng, chỉ giám thị cũ và mới."""
    modified = copy.deepcopy(toy)
    room = modified["sittings"][0]["rooms"][0]
    old_proctors = room["proctors"]
    room["proctors"] = ["GV98", "GV99"]

    changed, summary = compare_schedules(toy, modified)
    assert len(changed) == 1
    assert changed[0]["Thay đổi"] == "Đổi giám thị"
    assert changed[0]["Sinh viên bị ảnh hưởng"] == 0
    assert summary["students_affected"] == 0
    assert summary["proctors_affected"] == len(old_proctors) + 2


def test_compare_with_removed_sitting(toy):
    """Xóa một lượt: bảng thay đổi báo đã xóa."""
    modified = copy.deepcopy(toy)
    removed = modified["sittings"].pop(0)

    changed, summary = compare_schedules(toy, modified)
    assert [c["Thay đổi"] for c in changed] == ["Đã xóa"]
    assert changed[0]["Mã môn"] == removed["course_id"]
    assert summary["students_affected"] == removed["num_students"]


def test_compare_tab_ui_identical(toy, tmp_path):
    """Kiểm tra giao diện tab So sánh hai lịch khi hai lịch giống nhau."""
    app = AppTest.from_file(str(APP), default_timeout=15).run()
    assert not app.exception

    # Tìm ô nhập đường dẫn Lịch A và Lịch B
    path_a = next(t for t in app.text_input if t.label == "Đường dẫn lịch A")
    path_b = next(t for t in app.text_input if t.label == "Đường dẫn lịch B")

    path_a.set_value(str(DEFAULT_PATH)).run()
    path_b.set_value(str(DEFAULT_PATH)).run()
    assert not app.exception

    assert any("Không có lượt thi nào thay đổi giữa hai lịch" in i.value for i in app.info)


def test_compare_tab_ui_with_diff(toy, tmp_path):
    """Kiểm tra giao diện tab So sánh hai lịch khi có lượt thi bị thay đổi."""
    modified = copy.deepcopy(toy)
    _move_first_sitting(modified)

    mod_path = tmp_path / "modified.json"
    mod_path.write_text(json.dumps(modified), encoding="utf-8")

    app = AppTest.from_file(str(APP), default_timeout=15).run()
    path_a = next(t for t in app.text_input if t.label == "Đường dẫn lịch A")
    path_b = next(t for t in app.text_input if t.label == "Đường dẫn lịch B")

    path_a.set_value(str(DEFAULT_PATH)).run()
    path_b.set_value(str(mod_path)).run()
    assert not app.exception

    metrics = {m.label: m.value for m in app.metric}
    assert metrics["Số lượt dời ca"] == "1"
    assert metrics["Số sinh viên bị ảnh hưởng"] == str(modified["sittings"][0]["num_students"])
    # Giám thị của lượt bị dời cũng phải coi vào giờ khác
    moved_proctors = {g for r in modified["sittings"][0]["rooms"] for g in r["proctors"]}
    assert metrics["Số giám thị bị ảnh hưởng"] == str(len(moved_proctors))


def _incident_app(app_dirs):
    """Mở tab sự cố trên bản sao toy; chưa có output/toy/schedule.json nên lịch gốc mặc định là file tham chiếu."""
    app = _run_input_app(timeout=120)
    base_input = next(t for t in app.text_input if t.label == "Đường dẫn lịch gốc")
    assert base_input.value == str(DEFAULT_PATH)
    return app


def _declare_incidents(app, incidents):
    next(n for n in app.number_input if n.key == "num_incidents").set_value(len(incidents)).run()
    for i, (kind, resource_id, date, period) in enumerate(incidents):
        next(s for s in app.selectbox if s.key == f"inc_rtype_{i}").select(kind).run()
        next(s for s in app.selectbox if s.key == f"inc_rid_{i}").select(resource_id).run()
        next(s for s in app.selectbox if s.key == f"inc_date_{i}").select(date).run()
        next(s for s in app.selectbox if s.key == f"inc_period_{i}").select(period).run()
    next(b for b in app.button if b.label == "Xếp lại").click().run()
    assert not app.exception


def test_incident_tab_reschedules_and_compares(app_dirs):
    """Phòng máy G2-LAB1 hỏng ca 3 ngày 15/12: xếp lại thành công, chỉ INT3306 bị dời ca, có bảng so sánh."""
    _, output_dir = app_dirs
    app = _incident_app(app_dirs)
    _declare_incidents(app, [("Phòng", "G2-LAB1", "2026-12-15", "Ca 3")])

    result = json.loads((output_dir / "toy" / "reschedule.json").read_text(encoding="utf-8"))
    assert result["status"] in ("OPTIMAL", "FEASIBLE") and result["violations"] == []
    assert [c["course_id"] for c in result["changes"] if "time" in c["kinds"]] == ["INT3306"]
    assert any(m.value.startswith("Đã xếp lại xong") for m in list(app.success) + list(app.warning))
    assert {m.label: m.value for m in app.metric}["Số lượt dời ca"] == "1"
    # Kết quả còn hiện sau khi thao tác khác trên trang (lưu trong session)
    app.run()
    assert any(m.value.startswith("Đã xếp lại xong") for m in list(app.success) + list(app.warning))


def test_incident_tab_reports_failure(app_dirs):
    """Lỗi 3 của MANH-3: xếp lại thất bại thì không được báo thành công."""
    # Phòng máy duy nhất hỏng từ 15/12 đến 17/12: không đủ ca phòng máy cho các môn thi máy, vô nghiệm
    app = _incident_app(app_dirs)
    _declare_incidents(app, [("Phòng", "G2-LAB1", f"2026-12-{d}", "Cả ngày") for d in (15, 16, 17)])
    assert not any("Đã xếp lại xong" in m.value for m in list(app.success) + list(app.warning))
    assert any(e.value.startswith("Không xếp lại được (INFEASIBLE)") for e in app.error)
    # Chẩn đoán chỉ ra nguyên nhân là lịch bận của phòng (A-H6)
    assert any("[N01]" in w.value and "A-H6" in w.value for w in app.warning)
    assert not any(m.label == "Số lượt dời ca" for m in app.metric)


def test_solver_selection_options():
    """Kiểm tra tab Nhập dữ liệu có tùy chọn solver CP-SAT và PuLP."""
    app = _run_input_app()
    solver_radio = next(r for r in app.radio if r.label == "Solver")
    assert "CP-SAT (mặc định)" in solver_radio.options
    assert "PuLP" in solver_radio.options
    assert solver_radio.value == "CP-SAT (mặc định)"
