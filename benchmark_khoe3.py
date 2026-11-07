"""So sánh CP-SAT single/two_phase trên medium và large (không chỉnh sửa src/run.py).

Chạy tại thư mục gốc dự án: py benchmark_khoe3.py
Kết quả: benchmark_khoe3.csv và các file benchmark_schedules/*.json.
"""
from __future__ import annotations

import csv
from pathlib import Path

from src.data_loader import load_instance
from src.exam_solver import solve
from src.schedule import build_schedule, write_schedule

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "benchmark_schedules"
OUT.mkdir(exist_ok=True)
records = []
for size in ("medium", "large"):
    for strategy in ("single", "two_phase"):
        data_dir = ROOT / "data" / size
        loaded = load_instance(str(data_dir), str(ROOT / "configs" / "default.json"))
        if not loaded.ok:
            raise RuntimeError(f"Không thể đọc dữ liệu {size}: "
                               + str([m.to_dict() for m in loaded.messages]))
        cfg = loaded.config
        cfg.update(strategy=strategy, time_limit_sec=300)
        print(f"Đang đo {size} / {strategy} (limit=300s)", flush=True)
        result = solve(loaded.instance, cfg)
        schedule = build_schedule(loaded.instance, cfg, loaded.messages, result, size)
        write_schedule(schedule, str(OUT / f"{size}_{strategy}.json"))
        record = {
            "dataset": size,
            "strategy": strategy,
            "status": result.status,
            "objective": result.objective,
            "best_bound": result.best_bound,
            "solve_time_sec": round(result.solve_time_sec, 3),
            "has_solution": result.solution is not None,
            "violations": len(schedule["violations"]) if result.solution is not None else "N/A",
        }
        records.append(record)
        print(record, flush=True)
        if result.solution is not None and schedule["violations"]:
            raise AssertionError(f"Có vi phạm: {size}/{strategy}: {schedule['violations']}")

path = ROOT / "benchmark_khoe3.csv"
with path.open("w", encoding="utf-8-sig", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=list(records[0]))
    writer.writeheader()
    writer.writerows(records)
print(f"Đã lưu kết quả: {path}")
