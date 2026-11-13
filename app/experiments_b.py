"""Standalone, read-only dashboard for provisional B experiment CSVs."""

import csv
import math
from pathlib import Path

import streamlit as st

SAMPLES_DIR = Path(__file__).resolve().parents[1] / "experiments" / "samples"
PERF_REQUIRED = ("dataset", "seed", "status", "solve_time_sec", "time_limit_sec")
LAB_REQUIRED = ("dataset", "seed", "reserve_enabled", "lab_reserve_ratio", "status",
                "solve_time_sec", "room_utilization_lab", "lab_peak_utilization",
                "slots_without_lab_reserve")
SOLVED = {"FEASIBLE", "OPTIMAL"}
STATUSES = SOLVED | {"INFEASIBLE", "UNKNOWN", "INPUT_ERROR"}


def _number(row, field, *, required=True, integer=False, ratio=False):
    raw = (row.get(field) or "").strip()
    if not raw:
        if required:
            raise ValueError(f"{field} trống")
        return None
    try:
        value = float(raw)
    except ValueError as exc:
        raise ValueError(f"{field} không phải số: {raw}") from exc
    if not math.isfinite(value) or value < 0 or (ratio and value > 1) or (integer and not value.is_integer()):
        raise ValueError(f"{field} không hợp lệ: {raw}")
    return int(value) if integer else value


def _parse_row(raw, kind):
    row = {key: (value or "").strip() for key, value in raw.items() if key is not None}
    if not row["dataset"]:
        raise ValueError("dataset trống")
    row["seed"] = _number(row, "seed", integer=True)
    row["status"] = row["status"].upper()
    if row["status"] not in STATUSES:
        raise ValueError(f"status không hợp lệ: {row['status']}")
    row["solve_time_sec"] = _number(row, "solve_time_sec")
    if kind == "perf":
        row["time_limit_sec"] = _number(row, "time_limit_sec")
        if row["time_limit_sec"] <= 0:
            raise ValueError("time_limit_sec phải lớn hơn 0")
        row["objective"] = _number(row, "objective", required=False)
        row["best_bound"] = _number(row, "best_bound", required=False)
        if row["status"] in SOLVED and row["objective"] is None:
            raise ValueError("objective bắt buộc khi có nghiệm")
        if row["status"] not in SOLVED and row["objective"] is not None:
            raise ValueError("objective chỉ có khi có nghiệm")
    else:
        flag = row["reserve_enabled"].lower()
        if flag not in ("true", "false"):
            raise ValueError("reserve_enabled phải là true hoặc false")
        row["reserve_enabled"] = flag == "true"
        row["lab_reserve_ratio"] = _number(row, "lab_reserve_ratio", ratio=True)
        for field in ("room_utilization_lab", "lab_peak_utilization"):
            row[field] = _number(row, field, required=row["status"] in SOLVED, ratio=True)
        row["slots_without_lab_reserve"] = _number(
            row, "slots_without_lab_reserve", required=row["status"] in SOLVED, integer=True)
    return row


def _read_csv(folder, filename, kind):
    path = folder / filename
    if not path.is_file():
        st.info(f"Chưa có {filename} trong {folder}.")
        return []
    rows = []
    required = PERF_REQUIRED if kind == "perf" else LAB_REQUIRED
    try:
        with path.open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream, strict=True)
            headers = reader.fieldnames or []
            missing = set(required) - set(headers)
            if missing or len(set(headers)) != len(headers) or any(not header or not header.strip() for header in headers):
                raise ValueError(f"thiếu cột: {', '.join(sorted(missing))}" if missing else "cột tiêu đề trùng hoặc trống")
            seen = set()
            for raw in reader:
                try:
                    if None in raw:
                        raise ValueError("thừa ô so với tiêu đề")
                    row = _parse_row(raw, kind)
                    key = (row["dataset"], row["seed"], row.get("solver", ""), row.get("strategy", ""))
                    if kind == "lab":
                        key += (row["lab_reserve_ratio"], row["reserve_enabled"])
                    if key in seen:
                        raise ValueError("trùng cấu hình và seed")
                    seen.add(key)
                    rows.append(row)
                except ValueError as exc:
                    st.warning(f"{filename} dòng {reader.line_num}: {exc}; bỏ qua dòng.")
    except (OSError, UnicodeError, csv.Error, ValueError) as exc:
        st.warning(f"Không đọc được {filename}: {exc}")
    return rows


def _perf_view(rows):
    st.subheader("B - hiệu năng giải lịch")
    if not rows:
        st.info("Không có dòng hiệu năng B hợp lệ.")
        return
    chart = [{"Bộ dữ liệu / seed": f"{r['dataset']} / {r['seed']}",
              "Giây": r["solve_time_sec"], "Trạng thái": r["status"]}
             for r in rows if r["status"] in SOLVED]
    if chart:
        st.vega_lite_chart({"data": {"values": chart}, "layer": [
            {"mark": "bar", "encoding": {
                "x": {"field": "Bộ dữ liệu / seed", "type": "nominal"},
                "y": {"field": "Giây", "type": "quantitative"},
                "color": {"field": "Trạng thái", "type": "nominal"},
                "tooltip": [{"field": "Trạng thái"}, {"field": "Giây"}]}},
            {"mark": {"type": "rule", "color": "#c0392b", "strokeDash": [6, 4]},
             "encoding": {"y": {"datum": 300}}},
        ]}, width="stretch")
    st.caption("Đường đỏ: mốc 300 giây (5 phút), không phải giới hạn của mọi lượt chạy. "
               "FEASIBLE là lịch hợp lệ chưa chứng minh tối ưu; OPTIMAL đã chứng minh tối ưu. "
               "Chỉ vẽ thời gian lượt có nghiệm; các trạng thái khác vẫn có trong bảng.")
    fields = ["dataset", "solver", "strategy", "seed", "status", "solve_time_sec",
              "time_limit_sec", "objective", "best_bound"]
    st.dataframe([{k: row.get(k) for k in fields} for row in rows], hide_index=True, width="stretch")
    st.caption("Objective và best_bound là số theo từng seed, không lấy trung bình; "
               "chỉ so objective khi cùng bài toán và cấu hình hàm mục tiêu.")


def _lab_view(rows):
    st.subheader("B - dự trữ phòng máy (bật / tắt)")
    if not rows:
        st.info("Không có dòng dự trữ phòng máy B hợp lệ.")
        return
    keys = ("dataset", "seed", "lab_reserve_ratio", "solver", "strategy")
    groups = {}
    for row in rows:
        key = tuple(row.get(field, "") for field in keys)
        groups.setdefault(key, {})[row["reserve_enabled"]] = row
    pairs = [(off, on) for group in groups.values() if (off := group.get(False)) is not None
             and (on := group.get(True)) is not None and off["status"] in SOLVED and on["status"] in SOLVED]
    st.metric("Cặp seed có nghiệm (tắt / bật)", len(pairs))
    st.caption("Chỉ ghép cùng dataset, seed, tỷ lệ dự trữ, solver và strategy; "
               "hai phía phải là FEASIBLE hoặc OPTIMAL. KPI dưới đây là trung bình các cặp đủ điều kiện, "
               "không tính lượt chưa có nghiệm.")
    if pairs:
        summary = []
        for field, label in (("room_utilization_lab", "Sử dụng phòng máy"),
                             ("lab_peak_utilization", "Sử dụng đỉnh"),
                             ("slots_without_lab_reserve", "Ca không có phòng máy dự trữ"),
                             ("solve_time_sec", "Thời gian giải (giây)")):
            off_avg = sum(off[field] for off, _ in pairs) / len(pairs)
            on_avg = sum(on[field] for _, on in pairs) / len(pairs)
            summary.append({"KPI": label, "Tắt (TB)": off_avg, "Bật (TB)": on_avg,
                            "Bật - tắt": on_avg - off_avg})
        st.dataframe(summary, hide_index=True, width="stretch")
    else:
        st.info("Chưa có cặp tắt/bật cùng cấu hình và seed có nghiệm để so sánh.")
    st.caption("Chi tiết từng seed (tỷ lệ 0-1); không hiển thị hoặc so sánh objective giữa các cấu hình dự trữ.")
    fields = ["dataset", "seed", "solver", "strategy", "reserve_enabled", "lab_reserve_ratio",
              "status", "solve_time_sec", "room_utilization_lab", "lab_peak_utilization",
              "slots_without_lab_reserve"]
    st.dataframe([{k: row.get(k) for k in fields} for row in rows], hide_index=True, width="stretch")


def page_experiments_b(results_dir: Path):
    """Render B results from the caller's directory, or explicitly selected synthetic samples."""
    st.header("Thực nghiệm bài toán B")
    samples = st.checkbox("Dùng dữ liệu mẫu tổng hợp (synthetic, không phải kết quả solver B)",
                          key="experiments_b_samples")
    source = SAMPLES_DIR if samples else Path(results_dir)
    st.caption(f"Nguồn: {source} " + ("- DỮ LIỆU TỔNG HỢP, chỉ để xem giao diện." if samples
                                      else "- chỉ đọc CSV thực trong thư mục được truyền vào."))
    _perf_view(_read_csv(source, "perf_b.csv", "perf"))
    st.divider()
    _lab_view(_read_csv(source, "lab_reserve_b.csv", "lab"))
