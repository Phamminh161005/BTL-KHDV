"""Thực nghiệm KHOE-5. Chạy từ gốc repo: python -m experiments.perf_b.

Dữ liệu cố định seed sinh 1; seed trong CSV là random_seed của CP-SAT.
Mỗi lượt 300 giây gồm dựng model; kết quả JSON lưu để kiểm tra lại.
"""
from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import json
from pathlib import Path
import platform
import time

import ortools

from src.data_loader_b import load_instance_b
from src.room_solver import solve
from src.schedule import write_schedule
from src.timetable import build_timetable
from src.validator_b import compute_penalties_b

ROOT = Path(__file__).resolve().parents[1]
PERF_COLUMNS = "dataset seed time_limit_sec status objective best_bound gap solve_time_sec violations num_sessions".split()
RESERVE_COLUMNS = "dataset seed b_s4_weight lab_sessions room_change_only must_move slots_without_lab_reserve objective".split()


def reserve_counts(instance, table):
    """Từng sự cố độc lập: chỉ chuyển một buổi, các buổi khác giữ nguyên.

    must_move nghĩa là không có cách đổi trực tiếp sang phòng trống cùng ca;
    không khẳng định bất khả thi nếu cho hoán đổi nhiều buổi cùng lúc.
    """
    occupied = {(s["room_id"], (s["weekday"], s["period"])) for s in table["sessions"]}
    labs = [s for s in table["sessions"] if instance.classes[s["class_id"]].needs_lab]
    change = 0
    for s in labs:
        slot = s["weekday"], s["period"]
        size = instance.classes[s["class_id"]].size
        if any(r != s["room_id"] and (r, slot) not in occupied and slot not in instance.rooms[r].busy
               and instance.rooms[r].capacity >= size for r in instance.lab_rooms):
            change += 1
    return {"lab_sessions": len(labs), "room_change_only": change, "must_move": len(labs) - change,
            "slots_without_lab_reserve": table["kpi"]["slots_without_lab_reserve"]}


def write_rows(path, columns, rows):
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=columns)
        w.writeheader()
        w.writerows(rows)


def run_experiment(out_dir, seeds=(0, 1, 2), time_limit=300, workers=8):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    runs = out / "runs_b"
    runs.mkdir(exist_ok=True)
    perf, reserves, cache = [], [], {}
    started = time.time()
    manifest = {"python": platform.python_version(), "platform": platform.platform(),
                "ortools": ortools.__version__, "num_workers": workers,
                "dataset_generation": {}, "solver_seeds": list(seeds), "time_limit_sec": time_limit,
                "started_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(started)),
                "input_sha256": {}, "runs": []}
    def execute(dataset, seed, weight):
        key = dataset, seed, weight
        if key in cache:
            return cache[key]
        loaded = load_instance_b(str(ROOT / "data" / dataset))
        if not loaded.ok:
            raise RuntimeError([m.to_dict() for m in loaded.messages])
        inst = loaded.instance
        cfg = copy.deepcopy(loaded.config)
        cfg.update(time_limit_sec=time_limit, random_seed=seed, num_workers=workers)
        cfg["weights"]["B-S4"] = weight
        res = solve(inst, cfg)
        table = build_timetable(inst, cfg, loaded.messages, res, dataset)
        path = runs / f"{dataset}_seed{seed}_s4_{weight}.json"
        write_schedule(table, str(path))
        if res.solution is None or table["violations"]:
            raise RuntimeError(f"Lượt {key} thất bại: {res.status}, {table['violations']}")
        independent = compute_penalties_b(inst, table, cfg["lab_reserve_ratio"])
        if independent != res.penalties or sum(cfg["weights"][k] * p for k, p in independent.items()) != res.objective:
            raise RuntimeError(f"Điểm phạt/mục tiêu không khớp: {key}")
        manifest["runs"].append({"dataset": dataset, "seed": seed, "b_s4_weight": weight,
                                 "result": str(path.relative_to(out)), "status": res.status,
                                 "solve_time_sec": res.solve_time_sec})
        (out / "manifest_b.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"{dataset} seed={seed} B-S4={weight}: {res.status} Z={res.objective} "
              f"bound={res.best_bound} time={res.solve_time_sec:.3f}s", flush=True)
        cache[key] = inst, res, table
        return cache[key]
    for dataset in ("toy_b", "medium_b", "large_b"):
        generation = ROOT / "data" / dataset / "generation.json"
        manifest["dataset_generation"][dataset] = (json.loads(generation.read_text(encoding="utf-8"))
                                                    if generation.exists() else {"kind": "handwritten"})
        manifest["input_sha256"][dataset] = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                                 for p in sorted((ROOT / "data" / dataset).glob("*.csv"))}
        for seed in seeds:
            inst, res, table = execute(dataset, seed, 30)
            gap = (max(0, res.objective - res.best_bound) / max(1, abs(res.objective))
                   if res.best_bound is not None else None)
            perf.append(dict(zip(PERF_COLUMNS, [dataset, seed, time_limit, res.status, res.objective,
                            res.best_bound, gap, res.solve_time_sec, len(table["violations"]), len(table["sessions"])])))
            write_rows(out / "perf_b.csv", PERF_COLUMNS, perf)
    for dataset in ("medium_b", "large_b"):
        for seed in seeds:
            for weight in (30, 0):
                inst, res, table = execute(dataset, seed, weight)
                reserves.append({"dataset": dataset, "seed": seed, "b_s4_weight": weight,
                                 **reserve_counts(inst, table), "objective": res.objective})
                write_rows(out / "lab_reserve_b.csv", RESERVE_COLUMNS, reserves)
    manifest["elapsed_sec"] = time.time() - started
    (out / "manifest_b.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return perf, reserves


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=str(ROOT / "experiments" / "results"))
    parser.add_argument("--seeds", nargs="+", type=int, default=[0, 1, 2])
    parser.add_argument("--time-limit", type=float, default=300)
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()
    if args.time_limit <= 0 or args.workers < 1:
        parser.error("time-limit phải > 0; workers phải >= 1")
    run_experiment(args.out, args.seeds, args.time_limit, args.workers)


if __name__ == "__main__":
    main()
