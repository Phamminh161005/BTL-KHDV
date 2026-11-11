"""Tổng hợp CSV thực đo vào README và mục A.13 trong đặc tả.

Không tự suy diễn kết quả khi chưa đủ dữ liệu. Giữ nguyên các khối văn bản
ngoài dấu mốc HTML để phần nhận xét thủ công không bị ghi đè.
"""

from __future__ import annotations

import csv
import json
import math
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PERF = ROOT / "experiments" / "results" / "perf.csv"
RESCHEDULE = ROOT / "experiments" / "results" / "reschedule.csv"
CONFIG = ROOT / "configs" / "default.json"
PERF_OUTPUT = ROOT / "output" / "perf"

# Tương thích mục A.13 hiện tại trong docs/model_spec.md.
START, END = "<!-- RESULTS_BEGIN -->", "<!-- RESULTS_END -->"
# Đồng bộ trực tiếp với experiments/README.md mới.
R_START, R_END = "<!-- EXPERIMENT_RESULTS_BEGIN -->", "<!-- EXPERIMENT_RESULTS_END -->"
M_START, M_END = "<!-- EXPERIMENT_MACHINE_BEGIN -->", "<!-- EXPERIMENT_MACHINE_END -->"

DATASETS = ("toy", "toy_gen", "medium", "large")
SOLVERS = (("cp-sat", "single"), ("cp-sat", "two_phase"), ("pulp", "single"))
SCENARIOS = ("room_one_period", "lecturer_whole_day", "three_simultaneous")
SEEDS = (0, 1, 2)
SLA_SECONDS = 60
# Xếp lại phải giữ lịch gần lịch cũ: Z của lịch mới không được tăng quá 10% (ngưỡng nhóm tự chọn, xem README).
QUALITY_RATIO = 1.10
PERF_COLUMNS = (
    "dataset",
    "solver",
    "strategy",
    "seed",
    "time_limit_sec",
    "status",
    "objective",
    "best_bound",
    "gap",
    "solve_time_sec",
    "violations",
    "num_sittings",
    "students_multi_exam_day",
    "proctor_load_range",
)
RESCHEDULE_COLUMNS = (
    "dataset",
    "scenario",
    "incidents",
    "status",
    "objective_before",
    "objective_after",
    "solve_time_sec",
    "total_time_sec",
    "sittings_changed",
    "sittings_moved",
    "students_affected",
    "proctors_affected",
    "violations",
)


def read_csv(path: Path, columns: tuple[str, ...]):
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        if tuple(reader.fieldnames or ()) != columns:
            raise ValueError(f"CSV sai định dạng cột: {path}")
        return list(reader)


def numeric(value):
    if value in (None, ""):
        return None
    try:
        result = float(value)
    except (ValueError, TypeError):
        return None
    return result if math.isfinite(result) else None


def avg(values):
    vals = [v for v in values if v is not None]
    return statistics.mean(vals) if vals else None


def fmt(value, places=1):
    return f"{value:.{places}f}" if value is not None else "—"


def fmt_range(values):
    vals = [v for v in values if v is not None]
    return (
        f"{statistics.mean(vals):.1f} ({min(vals):.0f}–{max(vals):.0f})"
        if vals
        else "—"
    )


def is_valid(row):
    return (
        row.get("status") in ("FEASIBLE", "OPTIMAL")
        and row.get("violations") == "0"
        and numeric(row.get("objective")) is not None
        and numeric(row.get("solve_time_sec")) is not None
    )


def fallback_state(dataset, solver, strategy, seed):
    """True = có S04, False = không S04, None = thiếu/không đọc được JSON."""
    if solver != "cp-sat" or strategy != "two_phase":
        return False
    path = PERF_OUTPUT / dataset / f"{solver}_{strategy}_seed{seed}.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        messages = data.get("messages", [])
        return any(
            msg.get("code") == "S04" for msg in messages if isinstance(msg, dict)
        )
    except (OSError, ValueError, TypeError):
        return None


def pick_winner(a, b):
    """Ưu tiên số nghiệm hợp lệ, Z, gap (khi cả hai có), rồi thời gian.

    Thiếu gap không phải là lý do đánh giá một solver kém hơn.
    """
    if a["valid"] != b["valid"]:
        return "two_phase" if b["valid"] > a["valid"] else "single"
    for key in ("z", "gap", "time"):
        x, y = a[key], b[key]
        if x is None or y is None:
            continue
        tol = 1 if key == "time" else 1e-9
        if abs(x - y) > tol:
            return "two_phase" if y < x else "single"
    return "single"


def resch_time_ok(row):
    """KPI trong scope: có lịch hợp lệ và tổng thời gian xếp lại dưới 60 giây."""
    return (
        row.get("status") in ("OPTIMAL", "FEASIBLE")
        and row.get("violations") == "0"
        and numeric(row.get("objective_after")) is not None
        and numeric(row.get("total_time_sec")) is not None
        and numeric(row["total_time_sec"]) < SLA_SECONDS
    )


def resch_quality_ok(row):
    """Lịch mới hợp lệ và Z không tăng quá QUALITY_RATIO lần so với lịch cũ."""
    before, after = numeric(row.get("objective_before")), numeric(row.get("objective_after"))
    if not resch_time_ok(row) or before is None or after is None:
        return False
    return after <= QUALITY_RATIO * before


def expected_perf_keys():
    return [
        (d, solver, st, seed)
        for d in DATASETS
        for solver, st in SOLVERS
        if solver != "pulp" or d in ("toy", "toy_gen")
        for seed in SEEDS
    ]


def summary():
    perf = read_csv(PERF, PERF_COLUMNS)
    resch = read_csv(RESCHEDULE, RESCHEDULE_COLUMNS)
    by_perf = {}
    for row in perf:
        try:
            key = (row["dataset"], row["solver"], row["strategy"], int(row["seed"]))
        except (KeyError, ValueError, TypeError):
            raise ValueError(f"Hàng perf.csv không hợp lệ: {row}")
        if key in by_perf:
            raise ValueError(f"Trùng tổ hợp perf.csv: {key}")
        by_perf[key] = row
    by_resch = {}
    for row in resch:
        key = (row["dataset"], row["scenario"])
        if key in by_resch:
            raise ValueError(f"Trùng kịch bản reschedule.csv: {key}")
        by_resch[key] = row

    expected = expected_perf_keys()
    expected_resch = [(d, s) for d in ("medium", "large") for s in SCENARIOS]
    perf_complete = all(key in by_perf for key in expected)
    resch_complete = all(key in by_resch for key in expected_resch)

    lines = [
        f"Tiến độ: {sum(key in by_perf for key in expected)}/30 lượt giải; "
        f"{sum(key in by_resch for key in expected_resch)}/6 kịch bản xếp lại.",
        "",
        "| Bộ dữ liệu | Phương pháp | Nghiệm hợp lệ / lượt đo | OPTIMAL / lượt đo | Z TB (min–max) | Thời gian TB (s) | Gap TB |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    agg = {}
    fallback_notes = []
    for dataset in DATASETS:
        for solver, strategy in SOLVERS:
            if solver == "pulp" and dataset not in ("toy", "toy_gen"):
                continue
            group = [
                (seed, by_perf[dataset, solver, strategy, seed])
                for seed in SEEDS
                if (dataset, solver, strategy, seed) in by_perf
            ]
            valid = [r for _, r in group if is_valid(r)]
            zs = [numeric(r["objective"]) for r in valid]
            times = [numeric(r.get("solve_time_sec")) for _, r in group]
            gaps = [numeric(r["gap"]) for r in valid]
            record = {
                "n": len(group),
                "valid": len(valid),
                "z": avg(zs),
                "time": avg(times),
                "gap": avg(gaps),
            }
            agg[dataset, solver, strategy] = record
            lines.append(
                f"| {dataset} | {solver} / {strategy} | {len(valid)}/{len(group)} "
                f"| {sum(r['status'] == 'OPTIMAL' for r in valid)}/{len(group)} "
                f"| {fmt_range(zs)} | {fmt(record['time'])} | {fmt(record['gap'], 3)} |"
            )
            if solver == "cp-sat" and strategy == "two_phase":
                flags = [
                    fallback_state(dataset, solver, strategy, seed) for seed, _ in group
                ]
                n_fallback = sum(flag is True for flag in flags)
                unknown = sum(flag is None for flag in flags)
                fallback_notes.append(
                    f"- `{dataset}`: {n_fallback}/{len(group)} lượt có thông báo `S04`"
                    + (f"; {unknown} lượt chưa kiểm tra được JSON" if unknown else "")
                    + "."
                )

    lines.extend(
        [
            "",
            "Dấu «—» biểu thị thiếu giá trị để tính, không phải bằng 0. "
            "Thời gian trung bình tính trên các lượt đã ghi; Z/gap chỉ tính từ nghiệm hợp lệ. "
            "Cận dưới âm được kẹp về 0 vì Z không âm, nên gap = 1 nghĩa là chưa chứng minh được gì.",
            "",
            "### Fallback của `two_phase`",
            "",
            "`S04` ghi nhận pha 2 không tìm được nghiệm và đã thử chuyển sang `single`; "
            "không đồng nghĩa fallback đã tìm được nghiệm. Khi đánh giá hai pha thuần túy, "
            "cần tách riêng các lượt này.",
            "",
            *fallback_notes,
            "",
            "### Lựa chọn chiến lược",
            "",
        ]
    )
    decisions = {}
    for dataset in ("medium", "large"):
        a = agg[dataset, "cp-sat", "single"]
        b = agg[dataset, "cp-sat", "two_phase"]
        if a["n"] < 3 or b["n"] < 3:
            decision = "chưa đủ ba lần đo cho cả hai chiến lược"
        elif not a["valid"] and not b["valid"]:
            decision = "cả hai chiến lược chưa tìm được nghiệm hợp lệ"
        else:
            choice = pick_winner(a, b)
            decision = (
                f"đề xuất `{choice}` (single {a['valid']}/3 nghiệm hợp lệ, "
                f"two_phase {b['valid']}/3; Z TB {fmt(a['z'])} / {fmt(b['z'])}; "
                f"gap TB {fmt(a['gap'], 3)} / {fmt(b['gap'], 3)}; "
                f"thời gian TB {fmt(a['time'])}s / {fmt(b['time'])}s)"
            )
        decisions[dataset] = decision
        lines.append(f"- {dataset}: {decision}.")
    if not perf_complete:
        lines.append(
            "- CP-SAT/PuLP: chưa đo đủ tổ hợp để kết luận so sánh chính thức."
        )

    lines.extend(
        [
            "",
            "### Xếp lại khi có sự cố",
            "",
            "Hai tiêu chí được đánh giá riêng. Thời gian: có lịch hợp lệ và tổng thời gian dưới "
            f"{SLA_SECONDS} giây (KPI trong scope). Chất lượng: Z của lịch mới không tăng quá "
            f"{round((QUALITY_RATIO - 1) * 100)}% so với lịch cũ.",
            "",
            "| Bộ dữ liệu | Kịch bản | Trạng thái | Tổng thời gian (s) | Z trước → sau | Lượt thay đổi / dời ca "
            "| SV bị ảnh hưởng | Thời gian | Chất lượng |",
            "|---|---|---|---:|---:|---:|---:|---|---|",
        ]
    )

    for dataset, scenario in expected_resch:
        row = by_resch.get((dataset, scenario))
        if row is None:
            lines.append(f"| {dataset} | {scenario} | Chưa đo | — | — | — | — | Chưa đo | Chưa đo |")
            continue
        before, after = numeric(row.get("objective_before")), numeric(row.get("objective_after"))
        change = (
            f"{before:.0f} → {after:.0f} ({(after - before) / before:+.1%})"
            if before and after is not None
            else "—"
        )
        lines.append(
            f"| {dataset} | {scenario} | {row['status']} | "
            f"{fmt(numeric(row['total_time_sec']), 3)} | {change} | "
            f"{row['sittings_changed'] or '—'} / {row['sittings_moved'] or '—'} | "
            f"{row['students_affected'] or '—'} | "
            f"{'ĐẠT' if resch_time_ok(row) else 'KHÔNG ĐẠT'} | "
            f"{'ĐẠT' if resch_quality_ok(row) else 'KHÔNG ĐẠT'} |"
        )
    if all(("large", scenario) in by_resch for scenario in SCENARIOS):
        large = [by_resch["large", sc] for sc in SCENARIOS]
        time_part = (
            "đạt KPI dưới 60 giây trên cả ba kịch bản đã đo"
            if all(resch_time_ok(r) for r in large)
            else "chưa đạt KPI dưới 60 giây trên cả ba kịch bản"
        )
        bad = [r["scenario"] for r in large if not resch_quality_ok(r)]
        quality_part = (
            "giữ được chất lượng lịch ở cả ba kịch bản"
            if not bad
            else "chưa giữ được chất lượng lịch ở " + ", ".join(f"`{s}`" for s in bad)
        )
        conclusion = f"{time_part}; {quality_part}"
    else:
        conclusion = "chưa đủ ba kịch bản để đánh giá KPI dưới 60 giây"
    lines.extend(["", f"Kết luận xếp lại trên large: {conclusion}."])
    lines.extend(
        [
            "",
            "Giới hạn: mỗi cấu hình solver được đo với ba seed; mỗi kịch bản xếp lại "
            "chỉ đo một lần. Kết quả phụ thuộc môi trường máy và dữ liệu thực nghiệm.",
        ]
    )
    return "\n".join(lines), perf_complete, resch_complete, agg, decisions, conclusion


def replace_section(
    path: Path, begin: str, end: str | None = None, content: str | None = None
):
    """Thay đúng một khối; cũng hỗ trợ cú pháp cũ replace_section(path, content)."""
    if end is None and content is None:
        content, begin, end = begin, START, END
    if end is None or content is None:
        raise ValueError("Phải truyền đủ begin, end, content")
    raw = path.read_text(encoding="utf-8")
    if raw.count(begin) != 1 or raw.count(end) != 1:
        raise ValueError(f"Thiếu hoặc trùng dấu mốc {begin} … {end} trong {path}")
    prefix, rest = raw.split(begin, 1)
    _, suffix = rest.split(end, 1)
    path.write_text(
        prefix + begin + "\n" + content.rstrip() + "\n" + end + suffix, encoding="utf-8"
    )


def machine_description():
    path = PERF_OUTPUT / "machine.json"
    if not path.exists():
        return "Chưa có thông tin cấu hình máy thực nghiệm."
    info = json.loads(path.read_text(encoding="utf-8"))
    return (
        f"- CPU: {info.get('cpu') or 'chưa xác định'} "
        f"({info.get('logical_cores') or '?'} luồng logic)\n"
        f"- RAM: {info.get('ram_gb') or 'chưa xác định'} GB\n"
        f"- Hệ điều hành: {info.get('os') or 'chưa xác định'}; "
        f"Python: {info.get('python') or 'chưa xác định'}\n"
        f"- Giới hạn mỗi lượt: {info.get('time_limit_sec', 300)} giây; "
        f"CP-SAT {info.get('num_workers_cp_sat', 8)} workers; CBC một luồng."
    )


def main():
    content, perf_complete, resch_complete, agg, decisions, conclusion = summary()
    readme = ROOT / "experiments" / "README.md"
    spec = ROOT / "docs" / "model_spec.md"
    if not readme.is_file() or not spec.is_file():
        raise FileNotFoundError("Thiếu README hoặc docs/model_spec.md")
    # Kiểm tra đủ marker TRƯỚC khi sửa bất cứ file nào.
    for path, markers in (
        (readme, ((R_START, R_END), (M_START, M_END))),
        (spec, ((START, END),)),
    ):
        raw = path.read_text(encoding="utf-8")
        for begin, end in markers:
            if raw.count(begin) != 1 or raw.count(end) != 1:
                raise ValueError(f"Thiếu/trùng dấu mốc {begin} {end} trong {path}")

    replace_section(readme, R_START, R_END, content)
    replace_section(readme, M_START, M_END, machine_description())

    short = [
        "Kết quả dưới đây tổng hợp từ `experiments/results/perf.csv` và "
        "`experiments/results/reschedule.csv`. Chi tiết phương pháp và phân tích: "
        "[Báo cáo thực nghiệm](../experiments/README.md).",
        "",
        "| Dữ liệu | Chiến lược | Nghiệm hợp lệ / 3 | Z TB | Thời gian TB (s) | Gap TB |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for dataset in ("medium", "large"):
        for strategy in ("single", "two_phase"):
            row = agg[dataset, "cp-sat", strategy]
            short.append(
                f"| `{dataset}` | `{strategy}` | {row['valid']}/{row['n']} "
                f"| {fmt(row['z'])} | {fmt(row['time'])} | {fmt(row['gap'], 3)} |"
            )
    short.extend(
        [
            "",
            "Dấu «—» là thiếu giá trị, không phải 0. Cận dưới âm được kẹp về 0 vì Z không âm, "
            "nên gap = 1 nghĩa là chưa chứng minh được gì.",
            "",
            f"- Medium: {decisions['medium']}.",
            f"- Large: {decisions['large']}.",
            f"- Xếp lại trên large: {conclusion}.",
        ]
    )
    if not perf_complete or not resch_complete:
        short.append(
            "\nChưa hoàn thành đầy đủ phép đo; các nhận xét trên chưa phải kết luận cuối cùng."
        )
    replace_section(spec, START, END, "\n".join(short))
    print("Đã cập nhật experiments/README.md và docs/model_spec.md (A.13).")
    if not perf_complete or not resch_complete:
        print("Chưa đủ 30 lượt giải và 6 kịch bản xếp lại.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
