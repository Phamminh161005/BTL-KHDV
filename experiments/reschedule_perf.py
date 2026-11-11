"""Đo toàn bộ thời gian xếp lại khi có sự cố trên medium/large.

Chạy từ thư mục gốc: py experiments/reschedule_perf.py
Mặc định tái sử dụng lịch two_phase seed=0 do experiments/perf.py tạo
(output/perf/<dataset>/cp-sat_two_phase_seed0.json). Nếu không có, tự giải two_phase
để sinh lịch cũ và lưu vào output/ (không commit).

Cấu hình giải khi xếp lại do src/reschedule.py quyết định: strategy "single",
time_limit_sec = reschedule.time_limit_sec trong configs/default.json, num_workers và
random_seed lấy từ default.json.
Mỗi kịch bản đo một lần. objective_before và objective_after cùng thang đo (chỉ gồm Z; điểm phạt thay đổi
nằm riêng trong schedule["reschedule"]["change_cost"]).
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.data_loader import load_instance
from src.reschedule import reschedule
from src.schedule import build_schedule, write_schedule

DATASETS = ("medium", "large")
SCENARIOS = ("room_one_period", "lecturer_whole_day", "three_simultaneous")
SLA_SECONDS = 60
COLUMNS = (
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
RESULTS = ROOT / "experiments" / "results" / "reschedule.csv"


def room_occurrences(schedule):
    return sorted(
        {
            (s["date"], int(period), room["room_id"])
            for s in schedule["sittings"]
            for period in s["periods"]
            for room in s["rooms"]
            if room["room_id"] is not None
        }
    )


def lecturer_occurrences(schedule):
    return sorted(
        {
            (s["date"], g)
            for s in schedule["sittings"]
            for room in s["rooms"]
            for g in room["proctors"]
        }
    )


def choose_scenarios(base_schedule):
    """Sự cố THỰC SỰ chạm vào lịch cũ, chọn cố định theo thứ tự ngày/ca/mã.

    Ba sự cố đồng thời gồm 2 phòng khác nhau bị hỏng 1 ca và 1 giám thị bận cả ngày.
    """
    rooms = room_occurrences(base_schedule)
    lecturers = lecturer_occurrences(base_schedule)
    if not rooms or not lecturers:
        raise ValueError("Lịch cũ không có phòng/giám thị được phân công để tạo sự cố")
    d1, period1, room1 = rooms[0]
    d2, period2, room2 = next(
        ((d, p, r) for d, p, r in rooms if r != room1), (None, None, None)
    )
    if room2 is None:
        raise ValueError("Cần ít nhất 2 phòng có lượt thi để tạo 3 sự cố độc lập")
    gd, lecturer = lecturers[0]
    room_inc = {
        "resource_type": "room",
        "resource_id": room1,
        "date": d1,
        "period": period1,
    }
    lecturer_inc = {
        "resource_type": "lecturer",
        "resource_id": lecturer,
        "date": gd,
        "period": None,
    }
    room_inc_2 = {
        "resource_type": "room",
        "resource_id": room2,
        "date": d2,
        "period": period2,
    }
    return {
        "room_one_period": [room_inc],
        "lecturer_whole_day": [lecturer_inc],
        "three_simultaneous": [room_inc, lecturer_inc, room_inc_2],
    }


def describe_incidents(incidents):
    """Mã CSV loại:mã:ngày:ca; '*' thể hiện cả ngày."""
    return ";".join(
        f"{x['resource_type']}:{x['resource_id']}:{x['date']}:"
        f"{x['period'] if x['period'] is not None else '*'}"
        for x in incidents
    )


def ensure_results():
    RESULTS.parent.mkdir(parents=True, exist_ok=True)
    if not RESULTS.exists():
        with RESULTS.open("w", encoding="utf-8", newline="") as f:
            csv.writer(f).writerow(COLUMNS)
    with RESULTS.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        if tuple(reader.fieldnames or ()) != COLUMNS:
            raise ValueError("Header reschedule.csv không đúng yêu cầu")
        return {(r["dataset"], r["scenario"]) for r in reader}


def upsert(row):
    """Ghi (thay thế nếu đã có) một hàng qua file tạm."""
    key = (row["dataset"], row["scenario"])
    with RESULTS.open(encoding="utf-8", newline="") as f:
        records = [r for r in csv.DictReader(f) if (r["dataset"], r["scenario"]) != key]
    records.append(row)
    tmp = RESULTS.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(records)
    tmp.replace(RESULTS)


def baseline(dataset, regenerate=False):
    """Lấy lịch two_phase seed=0 của dữ liệu; thời gian tạo lịch không tính vào KPI xếp lại."""
    source = ROOT / "output" / "perf" / dataset / "cp-sat_two_phase_seed0.json"
    dest = ROOT / "output" / "reschedule_perf" / dataset / "base_two_phase.json"
    if regenerate or not source.exists():
        from src.exam_solver import solve

        loaded = load_instance(
            str(ROOT / "data" / dataset), str(ROOT / "configs" / "default.json")
        )
        if not loaded.ok:
            raise RuntimeError(f"Dữ liệu {dataset} không hợp lệ")
        cfg = dict(
            loaded.config,
            strategy="two_phase",
            time_limit_sec=300,
            random_seed=0,
            num_workers=8,
        )
        print(f"Tạo lịch cũ two_phase cho {dataset}...", flush=True)
        result = solve(loaded.instance, cfg)
        data = build_schedule(
            loaded.instance, cfg, list(loaded.messages), result, dataset
        )
        if result.solution is None or data["violations"]:
            raise RuntimeError(
                f"Không tạo được lịch cũ hợp lệ {dataset}: {result.status}"
            )
        dest.parent.mkdir(parents=True, exist_ok=True)
        write_schedule(data, str(dest))
        return dest, data
    data = json.loads(source.read_text(encoding="utf-8"))
    if (data.get("status") not in ("OPTIMAL", "FEASIBLE")
            or data.get("violations") or not data.get("sittings")
            or data.get("objective") is None):
        raise ValueError(f"Lịch cũ ở {source} không hợp lệ")
    meta = data.get("meta", {})
    if (
        meta.get("dataset") != dataset
        or meta.get("strategy") != "two_phase"
        or meta.get("config", {}).get("random_seed") != 0
        or meta.get("config", {}).get("time_limit_sec") != 300
        or meta.get("config", {}).get("num_workers") != 8
    ):
        raise ValueError(f"Metadata lịch cũ không đúng dữ liệu/strategy/seed: {source}")
    return source, data


def measure(dataset, scenario, incidents, base_path, base_schedule):
    out = ROOT / "output" / "reschedule_perf" / dataset / f"{scenario}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    schedule = reschedule(
        str(ROOT / "data" / dataset),
        str(base_path),
        incidents,
        str(ROOT / "configs" / "default.json"),
        str(out),
    )
    # Gồm đọc dữ liệu, dựng mô hình, giải, hậu xử lý và ghi JSON.
    total = time.perf_counter() - started
    summary = (schedule.get("reschedule") or {}).get("summary") or {}
    successful = (
        schedule["status"] in ("OPTIMAL", "FEASIBLE")
        and bool(schedule.get("sittings"))
        and not schedule.get("violations")
        and schedule.get("objective") is not None
    )
    return {
        "dataset": dataset,
        "scenario": scenario,
        "incidents": describe_incidents(incidents),
        "status": schedule["status"],
        "objective_before": base_schedule["objective"],
        "objective_after": schedule["objective"] if successful else "",
        "solve_time_sec": schedule["solve_time_sec"],
        "total_time_sec": round(total, 3),
        "sittings_changed": summary.get("sittings_changed", ""),
        "sittings_moved": summary.get("sittings_moved", ""),
        "students_affected": summary.get("students_affected", ""),
        "proctors_affected": summary.get("proctors_affected", ""),
        # Kể cả lịch có vi phạm, ghi số thật để không biến lỗi thành thiếu dữ liệu.
        "violations": (len(schedule.get("violations") or [])
                       if schedule.get("sittings") else ""),
    }


def main():
    ap = argparse.ArgumentParser(
        description="Đo thời gian xếp lại (đầy đủ, không chỉ solver)"
    )
    ap.add_argument("--datasets", nargs="+", choices=DATASETS, default=list(DATASETS))
    ap.add_argument(
        "--force", action="store_true", help="Đo lại và thay thế hàng CSV đã có"
    )
    ap.add_argument(
        "--regenerate-base",
        action="store_true",
        help="Tự sinh lại lịch cũ two_phase seed=0",
    )
    args = ap.parse_args()
    existing = ensure_results()
    failed = []
    for dataset in dict.fromkeys(args.datasets):
        if not args.force and all((dataset, s) in existing for s in SCENARIOS):
            print(f"Bỏ qua {dataset}: đủ 3 kịch bản", flush=True)
            continue
        try:
            base_path, base = baseline(dataset, args.regenerate_base)
            scenarios = choose_scenarios(base)
        except Exception as exc:
            traceback.print_exc()
            print(f"LỖI lịch cũ {dataset}: {exc}", flush=True)
            failed.append((dataset, "*"))
            continue
        for scenario, incidents in scenarios.items():
            key = dataset, scenario
            if key in existing and not args.force:
                print(f"Bỏ qua đã đo {key}", flush=True)
                continue
            print(f"Đang xếp lại {key}: {describe_incidents(incidents)}", flush=True)
            try:
                row = measure(dataset, scenario, incidents, base_path, base)
            except Exception as exc:
                traceback.print_exc()
                print(f"  -> LỖI {key}: {exc}", flush=True)
                failed.append(key)
                continue
            upsert(row)
            existing.add(key)
            success = (
                row["status"] in ("OPTIMAL", "FEASIBLE") and row["violations"] == 0
            )
            sla = (
                "ĐẠT"
                if success and row["total_time_sec"] < SLA_SECONDS
                else "KHÔNG ĐẠT"
            )
            print(
                f"  -> {row['status']}, tổng {row['total_time_sec']}s, "
                f"KPI <{SLA_SECONDS}s: {sla}; Z {row['objective_before']} -> "
                f"{row['objective_after']}, {row['sittings_changed']} lượt thay đổi, "
                f"{row['students_affected']} SV bị ảnh hưởng",
                flush=True,
            )
    print(f"Kết quả: {RESULTS}")
    if failed:
        print(f"CÓ lỗi ở: {failed} (chạy lại script để đo tiếp)")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
