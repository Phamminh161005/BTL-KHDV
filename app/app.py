"""Giao diện nhập dữ liệu, kiểm tra, cấu hình, xếp lịch thi, so sánh và xếp lại khi sự cố (MANH-2, MANH-3).

Chạy: streamlit run app/app.py

Biến môi trường (dùng cho kiểm thử, để không ghi vào data/ và output/ của repo):
    EXAM_APP_DATA_DIR    thư mục chứa các bộ dữ liệu, mặc định data/
    EXAM_APP_OUTPUT_DIR  thư mục ghi kết quả, mặc định output/
"""
import hashlib
import json
import os
import shutil
import sys
import tempfile
from io import BytesIO
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st
from openpyxl import Workbook

from src.config import load_config
DEFAULT_RESULT_PATH = ROOT / "tests" / "reference" / "toy_schedule.json"
DATA_DIR = Path(os.environ.get("EXAM_APP_DATA_DIR", ROOT / "data"))
CONFIGS_DIR = ROOT / "configs"
OUTPUT_DIR = Path(os.environ.get("EXAM_APP_OUTPUT_DIR", ROOT / "output"))

# Giữ DEFAULT_PATH cho khả năng tương thích với test cũ
DEFAULT_PATH = DEFAULT_RESULT_PATH

PERIODS = {
    1: "07:00 - 09:30",
    2: "09:40 - 12:10",
    3: "13:00 - 15:30",
    4: "15:40 - 18:10",
}
STATUS_NOTES = {
    "OPTIMAL": "Đã tìm được lịch tối ưu theo hàm mục tiêu.",
    "FEASIBLE": "Đã có lịch hợp lệ, nhưng chưa chứng minh được tối ưu trong thời gian cho phép.",
    "INPUT_ERROR": "Dữ liệu đầu vào có lỗi; solver chưa chạy. Hãy sửa các lỗi được liệt kê rồi chạy lại.",
    "INFEASIBLE": "Không có lịch thỏa tất cả ràng buộc cứng. Hãy kiểm tra số phòng, ca trống và giám thị.",
    "UNKNOWN": "Hết thời gian nhưng chưa tìm được lịch hợp lệ. Có thể tăng thời gian giải rồi chạy lại.",
}
PENALTY_NOTES = {
    "A-S1": "Hạn chế sinh viên thi từ hai môn trong một ngày.",
    "A-S2": "Giãn cách các môn thi của cùng sinh viên.",
    "A-S3": "Hạn chế chia một môn ra nhiều phòng.",
    "A-S4": "Hạn chế chỗ trống trong phòng thi.",
    "A-S5": "Chia đều tải coi thi giữa các giám thị.",
    "A-S6": "Hạn chế số lượt thi, tức số đề phải chuẩn bị.",
}
KPI_NOTES = {
    "hard_violations": "Số vi phạm ràng buộc cứng; lịch đúng phải bằng 0.",
    "students_multi_exam_day": "Số sinh viên có ít nhất một ngày bắt đầu từ hai lượt thi.",
    "avg_gap_days": "Khoảng cách ngày giữa các lượt liên tiếp: tính trung bình từng sinh viên rồi trung bình đều trên các sinh viên thi từ hai lượt.",
    "min_gap_days": "Khoảng cách ngày nhỏ nhất giữa hai lượt liên tiếp; cùng ngày tính là 0.",
    "proctor_load_min": "Số ca coi thi ít nhất trên toàn bộ giảng viên; lượt hai ca tính hai ca.",
    "proctor_load_max": "Số ca coi thi nhiều nhất trên toàn bộ giảng viên; lượt hai ca tính hai ca.",
    "proctor_load_range": "Chênh lệch giữa số ca coi thi nhiều nhất và ít nhất.",
    "num_sittings": "Tổng số lượt thi, cũng là số đề cần chuẩn bị.",
    "room_utilization_normal": "Tỷ lệ cặp (phòng thường, ca) được dùng trên các cặp không bận.",
    "room_utilization_lab": "Tỷ lệ cặp (phòng máy, ca) được dùng trên các cặp không bận.",
    "seat_fill_rate": "Tổng (số sinh viên × số ca) chia tổng (sức chứa phòng dùng × số ca).",
    "solve_time_sec": "Thời gian giải tính bằng giây, không gồm thời gian đọc dữ liệu.",
}
REQUIRED_CSV = ["slots.csv", "rooms.csv", "courses.csv", "enrollments.csv", "lecturers.csv"]
OPTIONAL_CSV = ["teaching.csv", "unavailability.csv"]
ALL_CSV = REQUIRED_CSV + OPTIONAL_CSV


# ---------------------------------------------------------------------------
# Hàm tiện ích hiển thị
# ---------------------------------------------------------------------------

def format_value(value, ratio=False):
    if value is None:
        return "Không áp dụng / chưa có"
    return f"{value:.2%}" if ratio else str(value)


def calendar_rows(sittings):
    rows = []
    for date in sorted({s["date"] for s in sittings}):
        row = {"Ngày": date}
        for period, hours in PERIODS.items():
            entries = [
                f"{s['course_id']} - {s['course_name']} | Phòng: "
                + ", ".join(r["room_id"] for r in s["rooms"])
                for s in sittings if s["date"] == date and period in s["periods"]
            ]
            row[f"Ca {period} ({hours})"] = "\n".join(entries) or "—"
        rows.append(row)
    return rows


def room_rows(sittings):
    return [
        {
            "Lượt thi": s["sitting_id"],
            "Mã môn": s["course_id"],
            "Môn": s["course_name"],
            "Ngày": s["date"],
            "Ca": ", ".join(map(str, s["periods"])),
            "Giờ": f"{s['start_time']} - {s['end_time']}",
            "Phòng": r["room_id"],
            "Số SV": r["num_students"],
            "Giám thị": ", ".join(r["proctors"]),
        }
        for s in sittings for r in s["rooms"]
    ]


def export_excel(sittings):
    workbook = Workbook()
    workbook.remove(workbook.active)
    summary = room_rows(sittings)
    students = [
        {**row, "Mã sinh viên": student}
        for row, room in zip(summary, (r for s in sittings for r in s["rooms"]))
        for student in room["students"]
    ]
    headers = ["Lượt thi", "Mã môn", "Môn", "Ngày", "Ca", "Giờ", "Phòng", "Số SV", "Giám thị"]
    for name, rows, columns in (
        ("Lịch tổng", summary, headers),
        ("Sinh viên theo phòng", students, headers + ["Mã sinh viên"]),
    ):
        sheet = workbook.create_sheet(name)
        sheet.append(columns)
        for row in rows:
            sheet.append([row[column] for column in columns])
        # Giữ mã có số 0 đầu và không diễn giải dữ liệu JSON thành công thức Excel.
        for cells in sheet.iter_rows():
            for cell in cells:
                if isinstance(cell.value, str):
                    cell.data_type = "s"
        sheet.freeze_panes = "A2"
        sheet.auto_filter.ref = sheet.dimensions
        for column in sheet.columns:
            sheet.column_dimensions[column[0].column_letter].width = min(
                55, max(len(str(cell.value or "")) for cell in column) + 2
            )
    output = BytesIO()
    workbook.save(output)
    return output.getvalue()


# ---------------------------------------------------------------------------
# Phần 1: Nhập dữ liệu, kiểm tra, cấu hình, chạy xếp lịch
# ---------------------------------------------------------------------------

def _available_datasets():
    """Liệt kê thư mục con trong data/ có chứa ít nhất một file CSV bắt buộc."""
    datasets = []
    if DATA_DIR.is_dir():
        for d in sorted(DATA_DIR.iterdir()):
            if d.is_dir() and any((d / f).exists() for f in REQUIRED_CSV):
                datasets.append(d.name)
    return datasets


def _save_uploaded_files(uploaded_files):
    """Lưu file tải lên vào thư mục tạm, trả về đường dẫn thư mục.

    Streamlit chạy lại toàn bộ trang sau mỗi thao tác, nên thư mục tạm được dùng lại khi các file tải lên không
    đổi, và thư mục cũ bị xóa khi người dùng tải bộ file khác.
    """
    digest = hashlib.sha256()
    for uploaded in sorted(uploaded_files, key=lambda f: f.name):
        digest.update(uploaded.name.encode("utf-8"))
        digest.update(uploaded.getvalue())
    key = digest.hexdigest()
    previous = st.session_state.get("upload_dir")
    if st.session_state.get("upload_key") == key and previous and os.path.isdir(previous):
        return previous
    if previous:
        shutil.rmtree(previous, ignore_errors=True)
    tmp = tempfile.mkdtemp(prefix="exam_upload_")
    for uploaded in uploaded_files:
        target = os.path.join(tmp, uploaded.name)
        with open(target, "wb") as f:
            f.write(uploaded.getvalue())
    st.session_state["upload_key"] = key
    st.session_state["upload_dir"] = tmp
    return tmp


def _show_messages_from_load(messages):
    """Hiện thông báo theo mức error/warning/info kèm tên file và số dòng."""
    for level, label, display in (
        ("error", "Lỗi", st.error),
        ("warning", "Cảnh báo", st.warning),
        ("info", "Thông tin", st.info),
    ):
        level_msgs = [m for m in messages if m.level == level]
        if level_msgs:
            st.markdown(f"**{label} ({len(level_msgs)})**")
        for m in level_msgs:
            location = m.file or ""
            if m.line is not None:
                location += f", dòng {m.line}"
            display(f"[{m.code}] {m.message}" + (f" ({location})" if location else ""))


def _show_data_preview(load_result):
    """Hiện xem trước dữ liệu: thống kê và bảng môn thi, bảng phòng."""
    instance = load_result.instance
    if instance is None:
        return

    # Thống kê tổng quan
    num_courses = len(instance.courses)
    num_rooms = len(instance.rooms)
    all_students = set()
    for c in instance.courses.values():
        all_students |= c.students
    num_students = len(all_students)
    num_slots = len(instance.slots)
    num_proctors = len(instance.proctors)

    st.subheader("Xem trước dữ liệu")
    cols = st.columns(5)
    cols[0].metric("Số môn", num_courses)
    cols[1].metric("Số phòng", num_rooms)
    cols[2].metric("Số sinh viên", num_students)
    cols[3].metric("Số ca", num_slots)
    cols[4].metric("Số giám thị", num_proctors)

    # Bảng môn thi
    st.markdown("Bảng môn thi")
    course_data = []
    for c in instance.courses.values():
        course_data.append({
            "Mã môn": c.course_id,
            "Tên môn": c.name,
            "Hình thức": "Thi viết" if c.exam_type == "written" else "Thi máy",
            "Thời lượng (phút)": c.duration_min,
            "Số SV": len(c.students),
            "Số lượt tối đa": c.max_sittings,
        })
    st.dataframe(course_data, hide_index=True, width="stretch")

    # Bảng phòng
    st.markdown("Bảng phòng")
    room_data = []
    for r in instance.rooms.values():
        room_data.append({
            "Mã phòng": r.room_id,
            "Tên phòng": r.name,
            "Loại": "Phòng thường" if r.room_type == "normal" else "Phòng máy",
            "Sức chứa khi thi": r.exam_capacity,
        })
    st.dataframe(room_data, hide_index=True, width="stretch")


def _config_form():
    """Hiển thị form cấu hình, trả về (config_dict, config_valid)."""
    st.subheader("Cấu hình")
    # Giá trị mặc định lấy từ configs/default.json (khóa thiếu được điền theo src.config.DEFAULT_CONFIG)
    config_file = CONFIGS_DIR / "default.json"
    defaults = load_config(str(config_file) if config_file.exists() else None, [])

    valid = True
    cfg = {}

    col1, col2 = st.columns(2)
    with col1:
        time_limit = st.number_input(
            "time_limit_sec (giới hạn thời gian giải, giây)",
            min_value=1, value=defaults["time_limit_sec"], step=10,
            help="Số dương. Với chiến lược two_phase là tổng thời gian cả hai pha.",
        )
        cfg["time_limit_sec"] = time_limit

        forbid = st.checkbox(
            "forbid_own_course (cấm coi thi môn mình dạy)",
            value=defaults["forbid_own_course"],
            help="Bật ràng buộc A-H10: giám thị không được coi thi môn mình dạy.",
        )
        cfg["forbid_own_course"] = forbid

    with col2:
        st.markdown("Trọng số ràng buộc mềm (số nguyên ≥ 0)")
        weights = {}
        for key in ["A-S1", "A-S2", "A-S3", "A-S4", "A-S5", "A-S6"]:
            default_w = defaults["weights"][key]
            w = st.number_input(
                f"{key}", min_value=0, value=default_w, step=1,
                help=PENALTY_NOTES.get(key, ""), key=f"weight_{key}",
            )
            if not isinstance(w, int) or w < 0:
                valid = False
            weights[key] = w
        cfg["weights"] = weights

    # Các giá trị cố định lấy mặc định
    for key in ["strategy", "num_workers", "random_seed", "proctors_per_room",
                 "written_capacity_ratio", "default_max_sittings_computer"]:
        cfg[key] = defaults[key]

    return cfg, valid


def _write_temp_config(cfg):
    """Ghi cấu hình ra file tạm và trả về đường dẫn."""
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8")
    json.dump(cfg, tmp, ensure_ascii=False)
    tmp.close()
    return tmp.name


def page_input():
    """Trang nhập dữ liệu và chạy xếp lịch."""
    st.header("Nhập dữ liệu và xếp lịch")

    # Bước 1: Chọn dữ liệu
    st.subheader("Chọn dữ liệu")
    source = st.radio(
        "Nguồn dữ liệu",
        ["Bộ dữ liệu có sẵn", "Tải lên file CSV"],
        horizontal=True,
    )

    data_dir = None
    dataset_name = None

    if source == "Bộ dữ liệu có sẵn":
        datasets = _available_datasets()
        if not datasets:
            st.warning("Không tìm thấy bộ dữ liệu nào trong thư mục data/.")
            return
        dataset_name = st.selectbox("Chọn bộ dữ liệu", datasets)
        if dataset_name:
            data_dir = str(DATA_DIR / dataset_name)
    else:
        uploaded_files = st.file_uploader(
            "Chọn các file CSV",
            type=["csv"],
            accept_multiple_files=True,
            help=f"Bắt buộc: {', '.join(REQUIRED_CSV)}. Tùy chọn: {', '.join(OPTIONAL_CSV)}.",
        )
        if uploaded_files:
            data_dir = _save_uploaded_files(uploaded_files)
            dataset_name = "upload"
        else:
            st.info(f"Vui lòng tải lên ít nhất các file: {', '.join(REQUIRED_CSV)}")
            return

    if data_dir is None:
        return

    # Bước 2: Kiểm tra dữ liệu
    st.subheader("Kiểm tra dữ liệu")
    from src.data_loader import load_instance
    config_path = str(CONFIGS_DIR / "default.json")
    if not os.path.exists(config_path):
        config_path = None
    load_result = load_instance(data_dir, config_path)

    _show_messages_from_load(load_result.messages)

    has_error = any(m.level == "error" for m in load_result.messages)
    if has_error:
        st.error("Dữ liệu có lỗi. Hãy sửa các lỗi trên rồi thử lại.")

    # Bước 3: Xem trước dữ liệu
    _show_data_preview(load_result)

    # Bước 4: Cấu hình
    cfg, config_valid = _config_form()

    # Bước 4b: Chọn solver
    solver_choice = st.radio(
        "Solver",
        ["CP-SAT (mặc định)", "PuLP"],
        horizontal=True,
        help="CP-SAT (Google OR-Tools) hoặc PuLP (CBC). Phần chọn solver để dành cho task sau.",
    )
    solver = "cp-sat" if solver_choice.startswith("CP-SAT") else "pulp"

    # Bước 5: Nút xếp lịch
    # Bật forbid_own_course mà thiếu teaching.csv thì bộ đọc dữ liệu sẽ báo lỗi D11 khi chạy: chặn ngay từ đây.
    missing_teaching = cfg["forbid_own_course"] and not os.path.exists(os.path.join(data_dir, "teaching.csv"))
    if missing_teaching:
        st.error("Đã bật forbid_own_course nhưng bộ dữ liệu không có teaching.csv (lỗi D11). "
                 "Hãy bổ sung teaching.csv hoặc tắt tùy chọn này.")
    can_run = load_result.ok and config_valid and not missing_teaching
    run_clicked = st.button("Xếp lịch", disabled=not can_run, type="primary")

    if not config_valid:
        st.info("Cấu hình không hợp lệ. Hãy kiểm tra lại các giá trị.")

    if run_clicked:
        config_path_tmp = _write_temp_config(cfg)
        out_path = os.path.join(str(OUTPUT_DIR / dataset_name), "schedule.json")

        try:
            with st.spinner("Đang xếp lịch, vui lòng chờ..."):
                from src.run import run
                schedule = run(data_dir=data_dir, config_path=config_path_tmp, out_path=out_path, solver=solver)
        except NotImplementedError as e:
            st.warning(
                f"Solver chưa được cài đặt: {e}\n\n"
                "Phần này sẽ hoạt động khi solver (CP-SAT hoặc PuLP) được triển khai ở task tiếp theo."
            )
            return
        finally:
            os.unlink(config_path_tmp)

        st.session_state["schedule_result"] = schedule
        st.session_state["schedule_path"] = out_path
        st.session_state["run_summary"] = _run_summary(schedule, out_path)
        st.session_state["run_data_dir"] = data_dir
        # Vẽ lại cả trang: tab "Xem kết quả" được vẽ trước tab này, nên phải chạy lại thì mới hiện kết quả mới.
        st.rerun()

    # Chỉ nhắc lại kết quả khi bộ dữ liệu đang chọn đúng là bộ vừa chạy
    if "run_summary" in st.session_state and st.session_state.get("run_data_dir") == data_dir:
        kind, text = st.session_state["run_summary"]
        {"success": st.success, "warning": st.warning, "error": st.error}[kind](text)


def _run_summary(schedule, out_path):
    """Thông báo sau khi chạy, theo đúng trạng thái kết quả: trả về (loại thông báo, nội dung)."""
    status = schedule["status"]
    violations = schedule.get("violations") or []
    where = f"Kết quả lưu tại {out_path}; xem chi tiết ở tab Xem kết quả."
    if status in ("OPTIMAL", "FEASIBLE") and not violations:
        kind = "success" if status == "OPTIMAL" else "warning"
        return kind, f"Đã xếp xong ({status}). {STATUS_NOTES[status]} {where}"
    if violations:
        return "error", f"Lịch tìm được có {len(violations)} vi phạm ràng buộc cứng, không được dùng. {where}"
    errors = [m["message"] for m in schedule.get("messages", []) if m.get("level") == "error"]
    reason = (" Nguyên nhân: " + "; ".join(errors[:3])) if errors else ""
    return "error", f"Không xếp được lịch ({status}). {STATUS_NOTES[status]}{reason} {where}"


# ---------------------------------------------------------------------------
# Phần 2: Xem kết quả (giống MANH-1)
# ---------------------------------------------------------------------------

def show_messages(schedule):
    st.subheader("Thông báo và vi phạm")
    for level, label, display in (
        ("error", "Lỗi", st.error),
        ("warning", "Cảnh báo", st.warning),
        ("info", "Thông tin", st.info),
    ):
        messages = [m for m in schedule.get("messages", []) if m.get("level") == level]
        if messages:
            st.markdown(f"**{label} ({len(messages)})**")
        for message in messages:
            location = message.get("file") or ""
            if message.get("line") is not None:
                location += f", dòng {message['line']}"
            display(f"[{message.get('code', level)}] {message.get('message', '')}"
                    + (f" ({location})" if location else ""))
    violations = schedule.get("violations", [])
    if violations:
        st.error(f"PHÁT HIỆN {len(violations)} VI PHẠM RÀNG BUỘC CỨNG — không sử dụng lịch trước khi sửa lỗi.")
        for violation in violations:
            st.error(f"[{violation.get('code', '')}] {violation.get('message', '')}")
            if violation.get("refs"):
                st.json(violation["refs"])
    elif not schedule.get("messages"):
        st.info("Không có thông báo hoặc vi phạm được ghi trong file.")


def show_schedule(schedule):
    """Hiển thị kết quả lịch thi (các màn hình MANH-1)."""
    status = schedule["status"]
    cols = st.columns(4)
    cols[0].metric("Trạng thái", status, help=STATUS_NOTES[status])
    cols[1].metric("Giá trị mục tiêu", format_value(schedule.get("objective")), help="Tổng điểm phạt đã nhân trọng số; càng nhỏ càng tốt.")
    cols[2].metric("Cận dưới tốt nhất", format_value(schedule.get("best_bound")), help="Cận dưới solver chứng minh được; bằng mục tiêu khi tối ưu.")
    cols[3].metric("Thời gian giải (giây)", format_value(schedule.get("solve_time_sec")), help=KPI_NOTES["solve_time_sec"])
    (st.success if status == "OPTIMAL" else st.info if status == "FEASIBLE" else st.error)(STATUS_NOTES[status])
    show_messages(schedule)
    if status not in ("OPTIMAL", "FEASIBLE"):
        return

    st.subheader("Điểm phạt A-S1 đến A-S6")
    penalties = schedule.get("penalties") or {}
    st.caption("Điểm phạt chưa nhân trọng số; không phải phần đóng góp trực tiếp vào giá trị mục tiêu.")
    st.dataframe([{"Chỉ số": key, "Giá trị": format_value(penalties.get(key)), "Ghi chú": note}
                  for key, note in PENALTY_NOTES.items()], hide_index=True, width="stretch")
    st.subheader("Toàn bộ KPI")
    kpi = schedule.get("kpi") or {}
    st.dataframe([{"Chỉ số": key, "Giá trị": format_value(kpi.get(key), key in ("room_utilization_normal", "room_utilization_lab", "seat_fill_rate")), "Ghi chú": note}
                  for key, note in KPI_NOTES.items()], hide_index=True, width="stretch")
    st.caption("Không áp dụng / chưa có: giá trị null hoặc thiếu trong file; không được coi là 0.")

    sittings = schedule.get("sittings") or []
    if not sittings:
        st.info("File không có lượt thi để hiển thị.")
        return
    sittings = sorted(sittings, key=lambda s: (s["date"], s["start_period"], s["course_id"]))
    rows = room_rows(sittings)
    calendar, rooms, students, proctors = st.tabs(["Lịch ngày × ca", "Theo phòng", "Sinh viên", "Giám thị"])
    with calendar:
        st.subheader("Lịch ngày × ca")
        st.caption("Lượt thi hai ca xuất hiện ở cả hai ô. Giờ hiển thị là khung giữ phòng, không phải giờ nộp bài.")
        st.dataframe(calendar_rows(sittings), hide_index=True, width="stretch", row_height=140)
    with rooms:
        room_id = st.selectbox("Chọn phòng", sorted({row["Phòng"] for row in rows}))
        if room_id is not None:
            st.dataframe([row for row in rows if row["Phòng"] == room_id], hide_index=True, width="stretch")
    with students:
        student_id = st.text_input("Mã sinh viên").strip()
        if student_id:
            matches = [row for row, room in zip(rows, (r for s in sittings for r in s["rooms"])) if student_id in room["students"]]
            if matches:
                st.dataframe(matches, hide_index=True, width="stretch")
            else:
                st.info("Không tìm thấy lịch thi của sinh viên này trong file.")
    with proctors:
        lecturer = st.selectbox("Chọn giảng viên", sorted({g for s in sittings for r in s["rooms"] for g in r["proctors"]}))
        if lecturer is not None:
            matches = [row for row, room in zip(rows, (r for s in sittings for r in s["rooms"])) if lecturer in room["proctors"]]
            st.dataframe(matches, hide_index=True, width="stretch")
        st.caption("File kết quả chỉ có mã giảng viên được phân công, không có tên hoặc danh sách giảng viên không được phân công.")
    st.download_button("Xuất Excel", data=export_excel(sittings), file_name="lich_thi.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


def page_view():
    """Trang xem file kết quả (giữ chức năng gốc MANH-1)."""
    st.header("Xem kết quả")

    # Xem từ session state nếu vừa chạy xong; nút "Mở file khác" quay lại chế độ chọn file
    if "schedule_result" in st.session_state:
        st.info(f"Đang hiển thị kết quả vừa chạy ({st.session_state.get('schedule_path', '')}).")
        if st.button("Mở file khác", key="close_latest_result"):
            for key in ("schedule_result", "schedule_path", "run_summary", "run_data_dir"):
                st.session_state.pop(key, None)
            st.rerun()
        show_schedule(st.session_state["schedule_result"])
        return

    uploaded = st.file_uploader("Tải file kết quả schedule.json", type=["json"])
    path = st.text_input("Đường dẫn file kết quả", str(DEFAULT_RESULT_PATH))
    st.caption("File tải lên được ưu tiên; nếu chưa tải, mở đường dẫn trên (mặc định là bộ toy).")
    try:
        content = uploaded.getvalue() if uploaded is not None else Path(path).read_bytes()
        schedule = json.loads(content.decode("utf-8-sig"))
        if not isinstance(schedule, dict) or schedule.get("status") not in STATUS_NOTES:
            raise ValueError("Thiếu trạng thái hợp lệ theo schema mục 7.")
        if not isinstance(schedule.get("messages", []), list) or not isinstance(schedule.get("violations", []), list):
            raise ValueError("messages và violations phải là mảng.")
        if any(not isinstance(item, dict) for key in ("messages", "violations") for item in schedule.get(key, [])):
            raise ValueError("Mỗi thông báo và vi phạm phải là một đối tượng.")
    except (OSError, UnicodeError, ValueError) as exc:
        st.error(f"Không đọc được file kết quả: {exc}")
        return

    show_schedule(schedule)


# ---------------------------------------------------------------------------
# Phần 3: So sánh hai lịch (MANH-3)
# ---------------------------------------------------------------------------

def _load_schedule_file(label, key):
    """Đọc file schedule.json từ file tải lên hoặc đường dẫn, trả về dict hoặc None."""
    uploaded = st.file_uploader(f"Tải {label}", type=["json"], key=f"cmp_upload_{key}")
    default_path = str(DEFAULT_RESULT_PATH) if key == "a" else ""
    path = st.text_input(f"Đường dẫn {label}", value=default_path, key=f"cmp_path_{key}")
    try:
        if uploaded is not None:
            raw = uploaded.getvalue()
        elif path:
            raw = Path(path).read_bytes()
        else:
            return None
        schedule = json.loads(raw.decode("utf-8-sig"))
        if not isinstance(schedule, dict) or schedule.get("status") not in STATUS_NOTES:
            raise ValueError("Thiếu trạng thái hợp lệ.")
        return schedule
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
        st.error(f"Không đọc được {label}: {exc}")
        return None


def compare_schedules(old, new):
    """So sánh hai lịch thi, trả về (changed_sittings, affected_students, affected_proctors).

    changed_sittings: danh sách dict mô tả các lượt thay đổi (dời ca, đổi phòng, đổi giám thị).
    affected_students: tập mã sinh viên bị ảnh hưởng bởi thay đổi.
    affected_proctors: tập mã giám thị bị ảnh hưởng bởi thay đổi.
    """
    old_sittings = {s["sitting_id"]: s for s in old.get("sittings", [])}
    new_sittings = {s["sitting_id"]: s for s in new.get("sittings", [])}

    all_ids = sorted(set(old_sittings) | set(new_sittings))
    changed = []
    affected_students = set()
    affected_proctors = set()

    for sid in all_ids:
        o = old_sittings.get(sid)
        n = new_sittings.get(sid)

        if o is None and n is not None:
            # Lượt mới thêm
            changed.append({
                "Lượt thi": sid,
                "Mã môn": n["course_id"],
                "Thay đổi": "Thêm mới",
                "Cũ": "—",
                "Mới": f"{n['date']} ca {n['start_period']}, phòng " + ", ".join(r["room_id"] for r in n["rooms"]),
            })
            for r in n["rooms"]:
                affected_students.update(r.get("students", []))
                affected_proctors.update(r.get("proctors", []))
            continue

        if n is None and o is not None:
            # Lượt bị xóa
            changed.append({
                "Lượt thi": sid,
                "Mã môn": o["course_id"],
                "Thay đổi": "Đã xóa",
                "Cũ": f"{o['date']} ca {o['start_period']}, phòng " + ", ".join(r["room_id"] for r in o["rooms"]),
                "Mới": "—",
            })
            for r in o["rooms"]:
                affected_students.update(r.get("students", []))
                affected_proctors.update(r.get("proctors", []))
            continue

        # Cả hai đều có: kiểm tra thay đổi
        diffs = []
        if o["date"] != n["date"] or o["start_period"] != n["start_period"]:
            diffs.append("Dời ca")
        old_rooms = sorted(r["room_id"] for r in o["rooms"])
        new_rooms = sorted(r["room_id"] for r in n["rooms"])
        if old_rooms != new_rooms:
            diffs.append("Đổi phòng")
        old_proctors = sorted(p for r in o["rooms"] for p in r.get("proctors", []))
        new_proctors = sorted(p for r in n["rooms"] for p in r.get("proctors", []))
        if old_proctors != new_proctors:
            diffs.append("Đổi giám thị")

        if diffs:
            changed.append({
                "Lượt thi": sid,
                "Mã môn": o["course_id"],
                "Thay đổi": ", ".join(diffs),
                "Cũ": f"{o['date']} ca {o['start_period']}, phòng " + ", ".join(r["room_id"] for r in o["rooms"]),
                "Mới": f"{n['date']} ca {n['start_period']}, phòng " + ", ".join(r["room_id"] for r in n["rooms"]),
            })
            # Sinh viên và giám thị bị ảnh hưởng: lấy từ cả hai phía
            for r in o["rooms"] + n["rooms"]:
                affected_students.update(r.get("students", []))
                affected_proctors.update(r.get("proctors", []))

    return changed, affected_students, affected_proctors


def _show_comparison(old, new):
    """Hiển thị so sánh KPI, điểm phạt và các lượt thay đổi giữa hai lịch."""
    # Bảng KPI cạnh nhau
    st.subheader("So sánh KPI")
    old_kpi = old.get("kpi") or {}
    new_kpi = new.get("kpi") or {}
    ratio_keys = ("room_utilization_normal", "room_utilization_lab", "seat_fill_rate")
    kpi_rows = []
    for key, note in KPI_NOTES.items():
        ov = old_kpi.get(key)
        nv = new_kpi.get(key)
        is_ratio = key in ratio_keys
        diff = ""
        if ov is not None and nv is not None:
            d = nv - ov
            diff = f"{d:+.2%}" if is_ratio else f"{d:+g}"
        kpi_rows.append({
            "Chỉ số": key,
            "Lịch A": format_value(ov, is_ratio),
            "Lịch B": format_value(nv, is_ratio),
            "Chênh lệch": diff,
        })
    st.dataframe(kpi_rows, hide_index=True, width="stretch")

    # Bảng điểm phạt cạnh nhau
    st.subheader("So sánh điểm phạt")
    old_pen = old.get("penalties") or {}
    new_pen = new.get("penalties") or {}
    pen_rows = []
    for key, note in PENALTY_NOTES.items():
        ov = old_pen.get(key)
        nv = new_pen.get(key)
        diff = ""
        if ov is not None and nv is not None:
            d = nv - ov
            diff = f"{d:+g}"
        pen_rows.append({
            "Chỉ số": key,
            "Lịch A": format_value(ov),
            "Lịch B": format_value(nv),
            "Chênh lệch": diff,
            "Ghi chú": note,
        })
    st.dataframe(pen_rows, hide_index=True, width="stretch")

    # Bảng lượt thi thay đổi
    st.subheader("Các lượt thi thay đổi")
    changed, affected_students, affected_proctors = compare_schedules(old, new)
    if not changed:
        st.info("Không có lượt thi nào thay đổi giữa hai lịch.")
    else:
        st.dataframe(changed, hide_index=True, width="stretch")
        cols = st.columns(2)
        cols[0].metric("Số sinh viên bị ảnh hưởng", len(affected_students))
        cols[1].metric("Số giám thị bị ảnh hưởng", len(affected_proctors))


def page_compare():
    """Trang so sánh hai lịch thi."""
    st.header("So sánh hai lịch")

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Lịch A")
        sched_a = _load_schedule_file("lịch A", "a")
    with col2:
        st.subheader("Lịch B")
        sched_b = _load_schedule_file("lịch B", "b")

    if sched_a is None or sched_b is None:
        st.info("Vui lòng chọn cả hai file lịch để so sánh.")
        return

    _show_comparison(sched_a, sched_b)


# ---------------------------------------------------------------------------
# Phần 4: Sự cố và xếp lại (MANH-3)
# ---------------------------------------------------------------------------

def page_incident():
    """Trang khai báo sự cố và xếp lại lịch."""
    st.header("Sự cố và xếp lại")

    # Bước 1: Chọn bộ dữ liệu và lịch gốc
    st.subheader("Chọn dữ liệu và lịch gốc")
    datasets = _available_datasets()
    if not datasets:
        st.warning("Không tìm thấy bộ dữ liệu nào trong thư mục data/.")
        return
    dataset_name = st.selectbox("Bộ dữ liệu", datasets, key="incident_dataset")
    data_dir = str(DATA_DIR / dataset_name)

    base_upload = st.file_uploader("Tải lịch gốc (schedule.json)", type=["json"], key="incident_base_upload")
    default_base = str(OUTPUT_DIR / dataset_name / "schedule.json")
    base_path = st.text_input("Đường dẫn lịch gốc", default_base, key="incident_base_path")
    try:
        if base_upload is not None:
            base_raw = base_upload.getvalue()
        elif base_path:
            base_raw = Path(base_path).read_bytes()
        else:
            st.info("Vui lòng chọn file lịch gốc.")
            return
        base_schedule = json.loads(base_raw.decode("utf-8-sig"))
        if base_schedule.get("status") not in ("OPTIMAL", "FEASIBLE"):
            st.error("Lịch gốc phải có trạng thái OPTIMAL hoặc FEASIBLE.")
            return
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        st.error(f"Không đọc được lịch gốc: {exc}")
        return

    sittings = base_schedule.get("sittings", [])
    if not sittings:
        st.error("Lịch gốc không có lượt thi nào.")
        return

    # Thu thập danh sách phòng, giảng viên, ngày từ bộ dữ liệu và lịch gốc
    from src.data_loader import load_instance
    load_res = load_instance(data_dir)
    if load_res.instance:
        all_rooms = sorted(load_res.instance.rooms.keys())
        all_proctors = sorted(load_res.instance.proctors.keys())
        all_dates = sorted({d.isoformat() for d in load_res.instance.days})
    else:
        all_rooms = sorted({r["room_id"] for s in sittings for r in s["rooms"]})
        all_proctors = sorted({p for s in sittings for r in s["rooms"] for p in r.get("proctors", [])})
        all_dates = sorted({s["date"] for s in sittings})

    # Bước 2: Khai báo sự cố
    st.subheader("Khai báo sự cố")
    num_incidents = st.number_input("Số sự cố", min_value=1, max_value=20, value=1, step=1, key="num_incidents")

    incidents = []
    valid_incidents = True
    for i in range(int(num_incidents)):
        st.markdown(f"Sự cố {i + 1}")
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            rtype_label = st.selectbox("Loại", ["Phòng", "Giảng viên"], key=f"inc_rtype_{i}")
        with c2:
            target_ids = all_rooms if rtype_label == "Phòng" else all_proctors
            rid = st.selectbox("Đối tượng", target_ids, key=f"inc_rid_{i}")
        with c3:
            date = st.selectbox("Ngày", all_dates, key=f"inc_date_{i}")
        with c4:
            period_choice = st.selectbox("Ca", ["Cả ngày", "Ca 1", "Ca 2", "Ca 3", "Ca 4"], key=f"inc_period_{i}")

        if rid and date:
            period = None if period_choice == "Cả ngày" else int(period_choice[-1])
            incidents.append({
                "resource_type": "room" if rtype_label == "Phòng" else "lecturer",
                "resource_id": rid,
                "date": date,
                "period": period,
            })

    if not incidents:
        valid_incidents = False

    # Bước 3: Xếp lại
    can_reschedule = valid_incidents and len(incidents) > 0
    resched_clicked = st.button("Xếp lại", disabled=not can_reschedule, type="primary", key="btn_reschedule")

    if resched_clicked:
        # Lưu lịch gốc ra file tạm nếu cần
        base_tmp = tempfile.NamedTemporaryFile(mode="wb", suffix=".json", delete=False)
        base_tmp.write(base_raw)
        base_tmp.close()

        out_path = os.path.join(str(OUTPUT_DIR / dataset_name), "schedule_resched.json")

        try:
            from src.reschedule import reschedule
        except (ImportError, ModuleNotFoundError):
            st.warning(
                "Chức năng xếp lại khi sự cố chưa sẵn sàng (thiếu src/reschedule.py, task MINH-3).\n\n"
                "Phần này sẽ hoạt động khi module reschedule được triển khai và gộp vào main."
            )
            os.unlink(base_tmp.name)
            return

        try:
            with st.spinner("Đang xếp lại lịch, vui lòng chờ..."):
                new_schedule = reschedule(
                    data_dir=data_dir,
                    base_schedule_path=base_tmp.name,
                    incidents=incidents,
                    config_path=None,
                    out_path=out_path,
                )
        except NotImplementedError as e:
            st.warning(f"Chức năng xếp lại chưa hoàn chỉnh: {e}")
            return
        finally:
            os.unlink(base_tmp.name)

        solve_time = new_schedule.get("solve_time_sec", 0)
        st.success(f"Đã xếp lại xong trong {solve_time} giây. Kết quả lưu tại {out_path}")
        _show_comparison(base_schedule, new_schedule)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    st.set_page_config(page_title="Lịch thi", layout="wide")
    st.title("Lịch thi cuối kỳ")

    tab_view, tab_input, tab_compare, tab_incident = st.tabs([
        "Xem kết quả",
        "Nhập dữ liệu và xếp lịch",
        "So sánh hai lịch",
        "Sự cố và xếp lại",
    ])
    with tab_view:
        page_view()
    with tab_input:
        page_input()
    with tab_compare:
        page_compare()
    with tab_incident:
        page_incident()


if __name__ == "__main__":
    main()
