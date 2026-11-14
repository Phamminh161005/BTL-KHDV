"""Giao diện bài toán B: tab Lịch học tuần B (chạy solver, xem lịch, KPI, xuất Excel) và tab Sự cố B (khai báo
sự cố, xếp lại theo model_spec B.9, so sánh hai lịch)."""
import copy
import hashlib
import json
import os
import shutil
import tempfile
from io import BytesIO
from pathlib import Path

import streamlit as st
from openpyxl import Workbook

from src.data_loader_b import load_instance_b
from src.kpi_b import compute_kpi
from src.validator_b import validate_b

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT / "tests" / "reference" / "toy_timetable.json"
PERIODS = {1: "07:00 - 09:30", 2: "09:40 - 12:10", 3: "13:00 - 15:30", 4: "15:40 - 18:10"}
KPI_NOTES_B = {
    "hard_violations": "Số vi phạm cứng; chỉ sử dụng lịch khi bằng 0.",
    "room_utilization_normal": "Mức khai thác phòng thường trên các ca không bận.",
    "room_utilization_lab": "Mức khai thác phòng máy cả tuần; đối chiếu mục tiêu 60-85%.",
    "lab_peak_utilization": "Mức tải phòng máy cao nhất theo ca, giúp nhận biết nút thắt.",
    "slots_without_lab_reserve": "Số ca vượt ngưỡng dự phòng, khó ứng phó sự cố phòng máy.",
    "seat_fill_rate": "Tổng sĩ số / tổng sức chứa các buổi; phản ánh mức lãng phí chỗ.",
    "preference_violations": "Số buổi vào ca giảng viên không muốn dạy.",
    "classes_same_day": "Số lớp có ngày học từ hai buổi; phản ánh mức dồn lịch.",
    "group_max_sessions_per_day": "Tải học bắt buộc lớn nhất của một nhóm trong ngày.",
    "solve_time_sec": "Thời gian solver; không phải thời gian đọc và hiển thị.",
}
RATIOS = {"room_utilization_normal", "room_utilization_lab", "lab_peak_utilization", "seat_fill_rate"}


def datasets_b(data_dir):
    return sorted(d.name for d in data_dir.iterdir()
                  if d.is_dir() and (d / "week_slots.csv").is_file() and (d / "classes.csv").is_file()) if data_dir.is_dir() else []


def read_timetable(path):
    with Path(path).open(encoding="utf-8-sig") as stream:
        result = json.load(stream)
    if not isinstance(result, dict) or not isinstance(result.get("meta"), dict) or result["meta"].get("problem") != "B":
        raise ValueError("Cần kết quả bài toán B (meta.problem = B).")
    if result.get("status") not in ("OPTIMAL", "FEASIBLE"):
        return result
    sessions = result.get("sessions")
    if not isinstance(sessions, list):
        raise ValueError("Thiếu mảng sessions.")
    ids = set()
    for s in sessions:
        if not isinstance(s, dict) or any(k not in s for k in ("session_id", "class_id", "room_id", "weekday", "period")):
            raise ValueError("Buổi học thiếu mã lớp, phòng, ca hoặc session_id.")
        if any(not isinstance(s[k], str) for k in ("class_id", "room_id")):
            raise ValueError("Mã lớp và mã phòng phải là chuỗi.")
        if type(s["weekday"]) is not int or type(s["period"]) is not int:
            raise ValueError("weekday và period phải là số nguyên.")
        if not isinstance(s["session_id"], str) or s["session_id"] in ids:
            raise ValueError("session_id phải là chuỗi duy nhất.")
        ids.add(s["session_id"])
    return result


def canonical_sessions(instance, timetable):
    rows = []
    for raw in timetable["sessions"]:
        cls = instance.classes[raw["class_id"]]
        room = instance.rooms[raw["room_id"]]
        rows.append({**raw, "class_name": cls.name, "course_id": cls.course_id,
                     "needs_lab": cls.needs_lab, "size": cls.size, "room_capacity": room.capacity,
                     "lecturer_id": cls.lecturer_id, "groups": sorted(cls.groups)})
    return sorted(rows, key=lambda s: (s["weekday"], s["period"], s["room_id"], s["class_id"]))


def weekly_rows(sessions, slots):
    return [{"Thứ": f"Thứ {day}", **{
        f"Ca {period} ({hours})": "\n".join(
            f"{s['class_id']} | {s['room_id']} | {s['lecturer_id']}"
            for s in sessions if s["weekday"] == day and s["period"] == period
        ) or ("—" if (day, period) in slots else "Không có ca")
        for period, hours in PERIODS.items()}}
        for day in sorted({d for d, _ in slots})]


def export_excel_b(sessions, slots, kpi):
    workbook = Workbook()
    workbook.remove(workbook.active)
    detail = [{**s, "groups": ", ".join(s["groups"])} for s in sessions]
    for name, rows, headers in (
        ("Lich tuan", weekly_rows(sessions, slots), ["Thứ", *[f"Ca {p} ({h})" for p, h in PERIODS.items()]]),
        ("Buoi hoc", detail, ["session_id", "class_id", "class_name", "weekday", "period", "room_id", "lecturer_id", "groups", "size", "room_capacity"]),
        ("KPI toan lich", [{"KPI": k, "Giá trị": v, "Ý nghĩa": KPI_NOTES_B[k]} for k, v in kpi.items()], ["KPI", "Giá trị", "Ý nghĩa"]),
    ):
        sheet = workbook.create_sheet(name)
        sheet.append(headers)
        for row in rows:
            sheet.append([row.get(h) for h in headers])
        for cells in sheet:
            for cell in cells:
                if isinstance(cell.value, str):
                    cell.data_type = "s"
        sheet.freeze_panes = "A2"
        sheet.auto_filter.ref = sheet.dimensions
    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def compare_timetables(old, new):
    """Bảng các buổi bị đổi giữa hai lịch, dùng đúng quy tắc ghép của src.reschedule_b.diff_timetables
    (data_schema mục 9.11): buổi cùng ca ghép trước, phần còn lại ghép theo thứ tự thời gian."""
    from src.reschedule_b import diff_timetables

    describe = lambda view: f"Thứ {view['weekday']} ca {view['period']} / {view['room_id']}" if view else "—"
    changes, _ = diff_timetables(old, new)
    return [{"Lớp": ch["class_id"], "Thay đổi": ", ".join(ch["kinds"]), "Lịch cũ": describe(ch["old"]),
             "Lịch mới": describe(ch["new"])} for ch in changes]


SOURCES = ["Kết quả đã lưu", "Tải CSV lên", "Mẫu toy_b tham chiếu"]
UPLOAD_NAME = "upload_b"
FILES_B = "week_slots.csv, rooms.csv, lecturers.csv, classes.csv (bắt buộc); class_groups.csv, " \
          "week_unavailability.csv, preferences.csv (tùy chọn)"


def run_solver_b(folder, out_path):
    """Chạy toàn bộ quy trình bài B (đọc, kiểm tra, giải CP-SAT, hậu xử lý, validator) và ghi timetable.json."""
    from src.run import run

    config = ROOT / "configs" / "problem_b.json"
    return run(str(folder), str(config) if config.is_file() else None, str(out_path), problem="B")


def _save_uploads_b(files):
    """Lưu các CSV tải lên vào <thư mục tạm>/upload_b, trả về (thư mục, khóa của bộ file).

    Streamlit chạy lại cả trang sau mỗi thao tác, nên dùng lại thư mục khi bộ file không đổi và xóa thư mục cũ khi
    người dùng tải bộ khác (như _save_uploaded_files của bài A). Tên thư mục con là upload_b để meta.dataset của
    kết quả khớp với tên đang hiển thị."""
    digest = hashlib.sha256()
    for f in sorted(files, key=lambda f: f.name):
        digest.update(f.name.encode("utf-8"))
        digest.update(f.getvalue())
    key = digest.hexdigest()
    previous = st.session_state.get("b_upload_dir")
    if st.session_state.get("b_upload_key") == key and previous and os.path.isdir(previous):
        return Path(previous), key
    if previous:
        shutil.rmtree(Path(previous).parent, ignore_errors=True)
    folder = Path(tempfile.mkdtemp(prefix="timetable_upload_")) / UPLOAD_NAME
    folder.mkdir()
    for f in files:
        (folder / f.name).write_bytes(f.getvalue())
    st.session_state["b_upload_key"] = key
    st.session_state["b_upload_dir"] = str(folder)
    return folder, key


def _show_load_messages(messages):
    for level, show in (("error", st.error), ("warning", st.warning)):
        for m in messages:
            if m.level == level:
                where = f" ({m.file}" + (f", dòng {m.line}" if m.line else "") + ")" if m.file else ""
                show(f"{m.code}{where}: {m.message}")


def _run_button(folder, dataset, saved):
    """Nút chạy solver; trả về True nếu vừa chạy xong."""
    if not st.button(f"Chạy xếp lịch B cho {dataset} (CP-SAT)", key="b_run_solver"):
        return False
    with st.spinner("Đang giải..."):
        try:
            result = run_solver_b(folder, saved)
        except (OSError, ValueError) as exc:
            st.error(f"Không chạy được: {exc}")
            return False
    st.success(f"Đã giải: {result['status']}, mục tiêu {result['objective']}, {len(result['sessions'])} buổi, "
               f"{result['solve_time_sec']:.2f} giây. Kết quả lưu ở {saved}.")
    for m in result["messages"]:
        if m["level"] in ("error", "warning") or m["code"].startswith("N"):
            st.warning(f"{m['code']}: {m['message']}")
    return True


def page_timetable_b(data_dir, output_dir):
    source = st.radio("Nguồn lịch B", SOURCES, key="b_source", horizontal=True)
    st.session_state.pop("b_active", None)
    if source == "Tải CSV lên":
        files = st.file_uploader("Tải các file CSV của bài B", type=["csv"], accept_multiple_files=True,
                                 key="b_upload", help=f"Định dạng theo data_schema mục 9: {FILES_B}.")
        if not files:
            st.info(f"Chọn các file CSV của một bộ dữ liệu B: {FILES_B}.")
            return
        folder, upload_key = _save_uploads_b(files)
        dataset = UPLOAD_NAME
        checked = load_instance_b(str(folder))
        _show_load_messages(checked.messages)
        if not checked.ok:
            st.error("Dữ liệu tải lên có lỗi, sửa file rồi tải lại.")
            return
        st.caption(f"Đọc được {len(checked.instance.classes)} lớp, {len(checked.instance.rooms)} phòng, "
                   f"{len(checked.instance.slots)} ca.")
    else:
        names = datasets_b(data_dir)
        if not names:
            st.info("Chưa có bộ dữ liệu B.")
            return
        dataset = st.selectbox("Bộ dữ liệu B", names, index=names.index("toy_b") if "toy_b" in names else 0,
                               key="b_dataset")
        folder = data_dir / dataset
    saved = output_dir / dataset / "timetable.json"
    if source == "Mẫu toy_b tham chiếu":
        if dataset != "toy_b":
            st.info("Lịch mẫu tham chiếu chỉ có cho bộ toy_b. Chọn toy_b, hoặc chọn \"Kết quả đã lưu\" rồi bấm chạy.")
            return
        st.caption("Lịch tối ưu tham chiếu của toy_b (Z = 355, model_spec B.12), không phải kết quả vừa chạy.")
    else:
        if _run_button(folder, dataset, saved) and source == "Tải CSV lên":
            st.session_state["b_upload_ran"] = upload_key
        # Với dữ liệu tải lên, chỉ hiện kết quả đã chạy cho đúng bộ file đang tải, không lấy kết quả của bộ trước
        fresh = source != "Tải CSV lên" or st.session_state.get("b_upload_ran") == upload_key
        if not saved.is_file() or not fresh:
            st.info(f"Chưa có kết quả cho {dataset}. Bấm nút trên để chạy solver.")
            return
    default = REFERENCE if source == "Mẫu toy_b tham chiếu" else saved
    path = st.text_input("Đường dẫn timetable.json", str(default), key=f"b_path_{source}_{dataset}")
    try:
        timetable = read_timetable(path)
        if timetable.get("meta", {}).get("dataset") != dataset:
            raise ValueError("Bộ dữ liệu trong lịch khác bộ đang chọn.")
        st.write(f"Trạng thái B: {timetable.get('status')}")
        if timetable.get("status") not in ("OPTIMAL", "FEASIBLE"):
            st.warning("Chưa có lời giải B hợp lệ để hiển thị.")
            return
        loaded = load_instance_b(str(folder))
        if not loaded.ok:
            raise ValueError("Dữ liệu B không hợp lệ: " + "; ".join(m.message for m in loaded.messages if m.level == "error"))
        violations = validate_b(loaded.instance, timetable)
        if violations:
            st.error("Lịch vi phạm ràng buộc cứng; không dùng lịch này.")
            st.dataframe(violations, hide_index=True)
            return
        sessions = canonical_sessions(loaded.instance, timetable)
        kpi = compute_kpi(loaded.instance, {**timetable, "sessions": sessions}, 0)
    except (OSError, UnicodeError, ValueError, KeyError, TypeError) as exc:
        st.warning(f"Không đọc được lịch B: {exc}")
        return
    st.session_state["b_active"] = {"timetable": {**timetable, "sessions": sessions}, "dataset": dataset,
                                    "data_dir": str(folder)}
    columns = st.columns(3)
    options = [sorted({s["room_id"] for s in sessions}), sorted({s["lecturer_id"] for s in sessions}), sorted(loaded.instance.groups)]
    filters = [columns[i].selectbox(label, ["Tất cả"] + values, key=key)
               for i, (label, key, values) in enumerate(zip(["Phòng B", "Giảng viên B", "Nhóm B"], ["b_room", "b_lecturer", "b_group"], options))]
    visible = [s for s in sessions if (filters[0] == "Tất cả" or s["room_id"] == filters[0])
               and (filters[1] == "Tất cả" or s["lecturer_id"] == filters[1])
               and (filters[2] == "Tất cả" or filters[2] in s["groups"])]
    st.metric("Buổi học đang hiển thị", len(visible))
    st.dataframe(weekly_rows(visible, loaded.instance.slots), hide_index=True, width="stretch")
    st.dataframe([{**s, "groups": ", ".join(s["groups"])} for s in visible], hide_index=True, width="stretch")
    st.caption("KPI tính trên toàn lịch; bộ lọc chỉ áp dụng lưới, danh sách và các buổi xuất Excel.")
    st.dataframe([{"KPI": k, "Giá trị": "Không áp dụng" if v is None else f"{v:.2%}" if k in RATIOS else str(v),
                   "Ý nghĩa dịch vụ": KPI_NOTES_B[k]} for k, v in kpi.items()], hide_index=True)
    st.download_button("Xuất Excel lịch B", export_excel_b(visible, loaded.instance.slots, kpi),
                       file_name="timetable.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key="b_excel")


def page_incident_b(data_dir, output_dir=None):
    output_dir = Path(output_dir) if output_dir is not None else ROOT / "output"
    active = st.session_state.get("b_active")
    st.caption("Khai báo sự cố rồi bấm \"Xếp lại B\" để xếp lại sao cho ít thay đổi nhất (model_spec B.9). "
               "Cũng có thể nhập đường dẫn một retimetable.json có sẵn để so sánh.")
    if not active:
        st.caption("Mở một lịch B hợp lệ ở tab Lịch học tuần trước.")
        return
    data_path = Path(active.get("data_dir") or data_dir / active["dataset"])
    instance = load_instance_b(str(data_path)).instance
    sessions = active["timetable"]["sessions"]
    # Ca cụ thể, hoặc (thứ, None) là cả ngày
    slot_options = list(instance.slots) + [(d, None) for d in instance.days]
    when = lambda t: f"Thứ {t[0]} ca {t[1]}" if t[1] is not None else f"Thứ {t[0]} cả ngày"
    # Sự cố đầu tiên giữ khóa không hậu tố để các lần mở lại trang không mất lựa chọn cũ
    key = lambda name, i: name if i == 0 else f"{name}_{i}"

    count = st.number_input("Số sự cố B", min_value=1, max_value=10, value=1, step=1, key="b_incident_count")
    events, problems, new_ids = [], [], set()
    for i in range(int(count)):
        st.markdown(f"Sự cố {i + 1}")
        kind = st.selectbox("Loại sự cố B", ["Phòng bận", "Giảng viên bận", "Thêm lớp"], key=key("b_incident_kind", i))
        if kind != "Thêm lớp":
            resource_type = "room" if kind == "Phòng bận" else "lecturer"
            ids = sorted(instance.rooms if resource_type == "room" else instance.lecturers)
            resource = st.selectbox("Tài nguyên B", ids, key=key(f"b_resource_{resource_type}", i))
            slot = st.selectbox("Ca sự cố B", slot_options, format_func=when, key=key("b_incident_slot", i))
            events.append({"type": "unavailability", "resource_type": resource_type, "resource_id": resource,
                           "weekday": slot[0], "period": slot[1]})
            affected = [s for s in sessions if s[f"{resource_type}_id"] == resource and s["weekday"] == slot[0]
                        and (slot[1] is None or s["period"] == slot[1])]
            st.write(f"Buổi bị tác động trực tiếp: {len(affected)}")
            if affected:
                st.dataframe(affected, hide_index=True)
        else:
            cid = st.text_input("Mã lớp mới B", key=key("b_new_class", i)).strip()
            name = st.text_input("Tên lớp mới B", key=key("b_new_name", i))
            lecturer = st.selectbox("Giảng viên lớp mới B", sorted(instance.lecturers), key=key("b_new_lecturer", i))
            size = st.number_input("Sĩ số B", min_value=1, value=15, step=1, key=key("b_new_size", i))
            per_week = st.number_input("Buổi/tuần B", min_value=1, max_value=len(instance.slots), value=1, step=1,
                                       key=key("b_new_count", i))
            lab = st.checkbox("Cần phòng máy B", key=key("b_new_lab", i))
            groups = st.multiselect("Nhóm bắt buộc B", sorted(instance.groups), key=key("b_new_groups", i))
            if not cid or cid in instance.classes:
                problems.append(f"Sự cố {i + 1}: Mã lớp mới phải khác rỗng và chưa tồn tại.")
            elif cid in new_ids:
                problems.append(f"Sự cố {i + 1}: Mã lớp mới {cid} trùng với một lớp mới khác.")
            new_ids.add(cid)
            events.append({"type": "add_class", "class": {"class_id": cid, "class_name": name, "lecturer_id": lecturer,
                                                          "size": int(size), "sessions_per_week": int(per_week),
                                                          "needs_lab": lab, "groups": groups}})
    for text in problems:
        st.warning(text)
    valid = not problems
    st.download_button("Xuất khai báo sự cố B",
                       json.dumps({"dataset": active["dataset"], "incidents": events}, ensure_ascii=False, indent=2),
                       file_name="incidents_b.json", key="b_export_incident", disabled=not valid)
    out_path = output_dir / active["dataset"] / "retimetable.json"
    if st.button("Xếp lại B", disabled=not valid, key="b_run_incident"):
        from src.reschedule_b import reschedule_b

        config = ROOT / "configs" / "problem_b.json"
        with st.spinner("Đang xếp lại..."):
            try:
                result = reschedule_b(str(data_path), active["timetable"], events,
                                      str(config) if config.is_file() else None, str(out_path))
            except (OSError, ValueError) as exc:
                st.error(f"Không xếp lại được: {exc}")
                return
        st.session_state["b_retimetable"] = str(out_path)
        info = result["reschedule"]
        if result["status"] in ("OPTIMAL", "FEASIBLE"):
            st.success(f"Đã xếp lại: {result['status']}, mục tiêu {result['objective']}, chi phí thay đổi "
                       f"{info['change_cost']}, {result['solve_time_sec']:.2f} giây. Kết quả lưu ở {out_path}.")
        else:
            st.error(f"Không xếp lại được: trạng thái {result['status']}.")
        for m in result["messages"]:
            if m["level"] in ("error", "warning") or m["code"].startswith(("N", "I04")):
                st.write(f"{m['code']}: {m['message']}")
        if result["status"] not in ("OPTIMAL", "FEASIBLE"):
            return
    path = st.text_input("Đường dẫn retimetable.json", key="b_retimetable")
    if not path:
        return
    try:
        new = read_timetable(path)
        if new.get("meta", {}).get("dataset") != active["dataset"]:
            raise ValueError("Không thể so sánh hai bộ dữ liệu khác nhau.")
        if new.get("status") not in ("OPTIMAL", "FEASIBLE"):
            st.warning("Xếp lại chưa có lời giải hợp lệ.")
            return
        if all(e["type"] == "unavailability" for e in events):
            # Soát lại lịch mới với dữ liệu cộng mọi ca bận đang khai báo
            updated = copy.deepcopy(instance)
            for e in events:
                resources = updated.rooms if e["resource_type"] == "room" else updated.lecturers
                resources[e["resource_id"]].busy |= {t for t in updated.slots if t[0] == e["weekday"]
                                                     and (e["period"] is None or t[1] == e["period"])}
            violations = validate_b(updated, new)
            if violations:
                st.warning("Lịch mới chưa hợp lệ với sự cố đang khai báo; bảng dưới chỉ là đối chiếu file.")
                st.dataframe(violations, hide_index=True)
            else:
                st.success("Lịch mới hợp lệ với ca bận đang khai báo.")
        elif "reschedule" in new and not new.get("violations"):
            st.success("Lịch mới hợp lệ: validator đã kiểm tra khi xếp lại, gồm cả lớp bổ sung.")
        else:
            st.caption("Đối chiếu file được cung cấp; chưa xác thực lịch mới với lớp bổ sung.")
        changes = compare_timetables(active["timetable"], new)
        st.metric("Buổi thay đổi B", len(changes))
        if changes:
            st.dataframe(changes, hide_index=True)
        else:
            st.success("Hai lịch B giống nhau.")
    except (OSError, UnicodeError, ValueError, KeyError, TypeError) as exc:
        st.warning(f"Không đọc được lịch xếp lại B: {exc}")
