"""Trang chỉ đọc các CSV thực nghiệm bài toán B do experiments/perf_b.py (KHOE-5) ghi ra.

perf_b.csv: dataset, seed, time_limit_sec, status, objective, best_bound, gap, solve_time_sec, violations,
num_sessions. lab_reserve_b.csv: mỗi dòng là một lượt giải với trọng số B-S4 cho trước; trọng số 0 là tắt dự
phòng phòng máy, trọng số dương là bật. Ý nghĩa các cột: experiments/README.md mục "Giá trị của B-S4".
"""

import csv
import math
from pathlib import Path

import streamlit as st

SAMPLES_DIR = Path(__file__).resolve().parents[1] / "experiments" / "samples"
PERF_REQUIRED = ("dataset", "seed", "status", "solve_time_sec", "time_limit_sec")
LAB_REQUIRED = ("dataset", "seed", "b_s4_weight", "lab_sessions", "room_change_only", "must_move",
                "slots_without_lab_reserve")
LAB_COUNTS = ("lab_sessions", "room_change_only", "must_move", "slots_without_lab_reserve")
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
    if kind == "perf":
        row["status"] = row["status"].upper()
        if row["status"] not in STATUSES:
            raise ValueError(f"status không hợp lệ: {row['status']}")
        row["solve_time_sec"] = _number(row, "solve_time_sec")
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
        # perf_b.py chỉ ghi dòng khi lượt giải có lịch hợp lệ, nên mọi cột đếm đều bắt buộc
        row["b_s4_weight"] = _number(row, "b_s4_weight", integer=True)
        for field in LAB_COUNTS:
            row[field] = _number(row, field, integer=True)
        if row["room_change_only"] + row["must_move"] != row["lab_sessions"]:
            raise ValueError("room_change_only + must_move phải bằng lab_sessions")
        row["objective"] = _number(row, "objective", required=False)
        row["reserve_enabled"] = row["b_s4_weight"] > 0
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
                        key += (row["b_s4_weight"],)
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
              "time_limit_sec", "objective", "best_bound", "gap", "violations", "num_sessions"]
    fields = [f for f in fields if any(row.get(f) not in (None, "") for row in rows)]
    st.dataframe([{k: row.get(k) for k in fields} for row in rows], hide_index=True, width="stretch")
    st.caption("Objective và best_bound là số theo từng seed, không lấy trung bình; "
               "chỉ so objective khi cùng bài toán và cấu hình hàm mục tiêu.")


def _lab_view(rows):
    st.subheader("B - dự phòng phòng máy (B-S4 tắt / bật)")
    if not rows:
        st.info("Không có dòng dự phòng phòng máy B hợp lệ.")
        return
    # Ghép lượt tắt (trọng số 0) với lượt bật (trọng số dương) cùng bộ dữ liệu, seed, solver, strategy
    groups = {}
    for row in rows:
        key = tuple(row.get(field, "") for field in ("dataset", "seed", "solver", "strategy"))
        groups.setdefault(key, {}).setdefault(row["reserve_enabled"], []).append(row)
    pairs = [(group[False][0], on) for group in groups.values()
             if len(group.get(False, [])) == 1 for on in group.get(True, [])]
    st.metric("Cặp seed so sánh được (tắt / bật)", len(pairs))
    st.caption("Mỗi buổi máy được thử giả định phòng đang dùng hỏng đúng ca đó. \"Chỉ đổi phòng\" là còn phòng máy "
               "trống, đủ máy cùng ca; \"phải dời ca\" là không có. Bảng tổng hợp là trung bình theo bộ dữ liệu "
               "trên các cặp tắt/bật cùng seed.")
    if pairs:
        summary = []
        for dataset in sorted({off["dataset"] for off, _ in pairs}):
            chosen = [(off, on) for off, on in pairs if off["dataset"] == dataset]
            for field, label in (("must_move", "Buổi máy phải dời ca"),
                                 ("room_change_only", "Buổi máy chỉ cần đổi phòng"),
                                 ("slots_without_lab_reserve", "Ca vượt ngưỡng dự phòng")):
                off_avg = sum(off[field] for off, _ in chosen) / len(chosen)
                on_avg = sum(on[field] for _, on in chosen) / len(chosen)
                summary.append({"Bộ dữ liệu": dataset, "KPI": label, "Tắt (TB)": round(off_avg, 2),
                                "Bật (TB)": round(on_avg, 2), "Bật - tắt": round(on_avg - off_avg, 2),
                                "Số cặp": len(chosen)})
        st.dataframe(summary, hide_index=True, width="stretch")
    else:
        st.info("Chưa có cặp tắt/bật cùng bộ dữ liệu và seed để so sánh.")
    st.caption("Chi tiết từng lượt. Không so sánh objective giữa lượt tắt và bật vì hai hàm mục tiêu khác trọng số.")
    fields = ["dataset", "seed", "b_s4_weight", "lab_sessions", "room_change_only", "must_move",
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
