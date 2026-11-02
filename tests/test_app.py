"""Kiểm thử giao diện: xem kết quả (MANH-1) và nhập dữ liệu + xếp lịch (MANH-2)."""
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

from app.app import DEFAULT_PATH, KPI_NOTES, _run_summary, calendar_rows, export_excel

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
