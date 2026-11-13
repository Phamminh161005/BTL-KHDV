"""Weekly timetable views and incident hand-off for problem B."""
import json
from collections import defaultdict
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
    """Match retained class/slot pairs before pairing moved sessions; IDs encode time."""
    before, after = defaultdict(list), defaultdict(list)
    for s in old["sessions"]:
        before[s["class_id"]].append(s)
    for s in new["sessions"]:
        after[s["class_id"]].append(s)
    changes = []
    for cid in sorted(before.keys() | after.keys()):
        a = {(s["weekday"], s["period"]): s for s in before[cid]}
        b = {(s["weekday"], s["period"]): s for s in after[cid]}
        pairs = [(a.pop(t), b.pop(t)) for t in sorted(a.keys() & b.keys())]
        rest_a, rest_b = [a[t] for t in sorted(a)], [b[t] for t in sorted(b)]
        pairs += [(rest_a[i] if i < len(rest_a) else None, rest_b[i] if i < len(rest_b) else None)
                  for i in range(max(len(rest_a), len(rest_b)))]
        for x, y in pairs:
            kinds = []
            if x is None:
                kinds = ["added"]
            elif y is None:
                kinds = ["removed"]
            elif (x["weekday"], x["period"]) != (y["weekday"], y["period"]):
                kinds = ["time"]
            elif x["room_id"] != y["room_id"]:
                kinds = ["rooms"]
            if kinds:
                describe = lambda s: f"Thứ {s['weekday']} ca {s['period']} / {s['room_id']}" if s else "—"
                changes.append({"Lớp": cid, "Thay đổi": ", ".join(kinds), "Lịch cũ": describe(x), "Lịch mới": describe(y)})
    return changes


def run_solver_b(data_dir, dataset, out_path):
    """Chạy toàn bộ quy trình bài B (đọc, kiểm tra, giải CP-SAT, hậu xử lý, validator) và ghi timetable.json."""
    from src.run import run

    config = ROOT / "configs" / "problem_b.json"
    return run(str(data_dir / dataset), str(config) if config.is_file() else None, str(out_path), problem="B")


def page_timetable_b(data_dir, output_dir):
    names = datasets_b(data_dir)
    if not names:
        st.info("Chưa có bộ dữ liệu B.")
        return
    dataset = st.selectbox("Bộ dữ liệu B", names, index=names.index("toy_b") if "toy_b" in names else 0,
                           key="b_dataset")
    source = st.radio("Nguồn lịch B", ["Kết quả đã lưu", "Mẫu toy_b tham chiếu"], key="b_source")
    st.session_state.pop("b_active", None)
    saved = output_dir / dataset / "timetable.json"
    if source == "Mẫu toy_b tham chiếu":
        if dataset != "toy_b":
            st.info("Lịch mẫu tham chiếu chỉ có cho bộ toy_b. Chọn toy_b, hoặc chọn \"Kết quả đã lưu\" rồi bấm chạy.")
            return
        st.caption("Lịch tối ưu tham chiếu của toy_b (Z = 355, model_spec B.12), không phải kết quả vừa chạy.")
    else:
        if st.button(f"Chạy xếp lịch B cho {dataset} (CP-SAT)", key="b_run_solver"):
            with st.spinner("Đang giải..."):
                try:
                    result = run_solver_b(data_dir, dataset, saved)
                except (OSError, ValueError) as exc:
                    st.error(f"Không chạy được: {exc}")
                else:
                    st.success(f"Đã giải: {result['status']}, mục tiêu {result['objective']}, "
                               f"{len(result['sessions'])} buổi, {result['solve_time_sec']:.2f} giây. "
                               f"Kết quả lưu ở {saved}.")
                    for m in result["messages"]:
                        if m["level"] in ("error", "warning"):
                            st.warning(f"{m['code']}: {m['message']}")
        elif not saved.is_file():
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
        loaded = load_instance_b(str(data_dir / dataset))
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
    st.session_state["b_active"] = {"timetable": {**timetable, "sessions": sessions}, "dataset": dataset}
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


def page_incident_b(data_dir):
    active = st.session_state.get("b_active")
    st.info("Chờ quy trình xếp lại B của Minh. Có thể khai báo/xuất sự cố và đối chiếu file kết quả; chưa chạy xếp lại.")
    if not active:
        st.caption("Mở một lịch B hợp lệ ở tab Lịch học tuần trước.")
        return
    loaded = load_instance_b(str(data_dir / active["dataset"]))
    instance = loaded.instance
    kind = st.selectbox("Loại sự cố B", ["Phòng bận", "Giảng viên bận", "Thêm lớp"], key="b_incident_kind")
    event = {}
    if kind != "Thêm lớp":
        resource_type = "room" if kind == "Phòng bận" else "lecturer"
        ids = sorted(instance.rooms if resource_type == "room" else instance.lecturers)
        resource = st.selectbox("Tài nguyên B", ids, key=f"b_resource_{resource_type}")
        slot = st.selectbox("Ca sự cố B", instance.slots, format_func=lambda t: f"Thứ {t[0]} ca {t[1]}", key="b_incident_slot")
        event = {"type": "unavailability", "resource_type": resource_type, "resource_id": resource, "weekday": slot[0], "period": slot[1]}
        affected = [s for s in active["timetable"]["sessions"] if s[f"{resource_type}_id"] == resource and (s["weekday"], s["period"]) == slot]
        st.write(f"Buổi bị tác động trực tiếp: {len(affected)}")
        if affected:
            st.dataframe(affected, hide_index=True)
    else:
        cid = st.text_input("Mã lớp mới B", key="b_new_class")
        name = st.text_input("Tên lớp mới B", key="b_new_name")
        lecturer = st.selectbox("Giảng viên lớp mới B", sorted(instance.lecturers), key="b_new_lecturer")
        size = st.number_input("Sĩ số B", min_value=1, value=15, step=1, key="b_new_size")
        count = st.number_input("Buổi/tuần B", min_value=1, max_value=len(instance.slots), value=1, step=1, key="b_new_count")
        lab = st.checkbox("Cần phòng máy B", key="b_new_lab")
        groups = st.multiselect("Nhóm bắt buộc B", sorted(instance.groups), key="b_new_groups")
        event = {"type": "add_class", "class": {"class_id": cid.strip(), "class_name": name, "lecturer_id": lecturer,
                 "size": size, "sessions_per_week": count, "needs_lab": lab, "groups": groups}}
    valid = kind != "Thêm lớp" or bool(event["class"]["class_id"] and event["class"]["class_id"] not in instance.classes)
    if not valid:
        st.warning("Mã lớp mới phải khác rỗng và chưa tồn tại.")
    st.download_button("Xuất khai báo sự cố B", json.dumps({"schema": "B-incident-draft-v1", "dataset": active["dataset"], "incidents": [event]}, ensure_ascii=False, indent=2),
                       file_name="incidents_b.json", key="b_export_incident", disabled=not valid)
    st.button("Xếp lại B (chờ backend)", disabled=True, key="b_run_incident")
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
        if kind != "Thêm lớp":
            from copy import deepcopy
            updated = deepcopy(instance)
            resources = updated.rooms if event["resource_type"] == "room" else updated.lecturers
            resources[event["resource_id"]].busy.add((event["weekday"], event["period"]))
            violations = validate_b(updated, new)
            if violations:
                st.warning("Lịch mới chưa hợp lệ với sự cố đang khai báo; bảng dưới chỉ là đối chiếu file.")
                st.dataframe(violations, hide_index=True)
            else:
                st.success("Lịch mới hợp lệ với ca bận đang khai báo.")
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
