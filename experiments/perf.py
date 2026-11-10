"""Đo hiệu năng CP-SAT single/two_phase và PuLP trên các bộ dữ liệu/seed.

Chạy từ thư mục gốc: py experiments/perf.py
Mỗi tổ hợp hoàn tất được ghi ngay vào experiments/results/perf.csv (có thể chạy tiếp
sau khi gián đoạn). Lịch JSON được lưu dưới output/perf/ (không commit).

Lưu ý: PuLP/CBC chạy 1 luồng và không dùng random_seed, nên ba seed của PuLP
thường cho kết quả gần như giống nhau (chỉ khác nhiễu thời gian).
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import platform
import subprocess
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.data_loader import load_instance
from src.schedule import build_schedule, write_schedule

DATASETS = ("toy", "toy_gen", "medium", "large")
SEEDS = (0, 1, 2)
TIME_LIMIT_SEC = 300
NUM_WORKERS = 8
COLUMNS = (
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
RESULTS = ROOT / "experiments" / "results" / "perf.csv"


def runs(datasets=DATASETS, seeds=SEEDS):
    """30 tổ hợp: 4 dataset × 2 CP-SAT × 3 seed, cộng 2 dataset × PuLP × 3 seed."""
    for dataset in datasets:
        for solver, strategy in (
            ("cp-sat", "single"),
            ("cp-sat", "two_phase"),
            ("pulp", "single"),
        ):
            if solver == "pulp" and dataset not in ("toy", "toy_gen"):
                continue
            for seed in seeds:
                yield dataset, solver, strategy, seed


def gap_value(objective, best_bound):
    """(objective - best_bound) / objective; để trống nếu thiếu một trong hai.

    Để trống khi objective bằng 0, không hữu hạn hoặc thiếu giá trị.
    Kẹp về >= 0 để tránh gap âm nhỏ do sai số số thực.
    """
    if objective in (None, "") or best_bound in (None, ""):
        return ""
    try:
        z = float(objective)
        bound = float(best_bound)
    except (ValueError, TypeError):
        return ""
    if not (math.isfinite(z) and math.isfinite(bound)) or z == 0:
        return ""
    # Sai số số thực rất nhỏ có thể khiến tỷ số âm gần 0.
    return max(0.0, round((z - bound) / z, 8))


def _cpu_name():
    """Tên CPU thật (không dùng platform.processor() vì trên Windows chỉ trả về family/model)."""
    try:
        if os.name == "nt":
            out = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    "(Get-CimInstance Win32_Processor | Select-Object -First 1).Name",
                ],
                capture_output=True,
                text=True,
                timeout=15,
            ).stdout.strip()
            if out:
                return out
        elif sys.platform == "darwin":
            out = subprocess.run(
                ["sysctl", "-n", "machdep.cpu.brand_string"],
                capture_output=True,
                text=True,
                timeout=10,
            ).stdout.strip()
            if out:
                return out
        else:
            with open("/proc/cpuinfo", encoding="utf-8") as f:
                for line in f:
                    if line.lower().startswith("model name"):
                        return line.split(":", 1)[1].strip()
    except (OSError, subprocess.SubprocessError):
        pass
    return platform.processor() or platform.uname().machine


def machine_info():
    """Metadata thô để điền cấu hình máy trong README; không suy đoán số lõi vật lý."""
    ram_bytes = None
    if os.name == "nt":
        try:
            import ctypes

            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]

            state = MEMORYSTATUSEX()
            state.dwLength = ctypes.sizeof(state)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(state)):
                ram_bytes = state.ullTotalPhys
        except (OSError, AttributeError, ValueError):
            pass
    else:
        try:
            ram_bytes = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
        except (OSError, ValueError, AttributeError):
            pass
    return {
        "cpu": _cpu_name(),
        "logical_cores": os.cpu_count(),
        "ram_gb": round(ram_bytes / (1024**3), 2) if ram_bytes else None,
        "os": platform.platform(),
        "python": platform.python_version(),
        "time_limit_sec": TIME_LIMIT_SEC,
        "num_workers_cp_sat": NUM_WORKERS,
        "note": "PuLP/CBC chạy 1 luồng, không dùng random_seed; có thể vượt 300s vì có hạn dừng cứng riêng.",
    }


def _key(r):
    return (r["dataset"], r["solver"], r["strategy"], int(r["seed"]))


def ensure_results(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        with path.open("w", encoding="utf-8", newline="") as f:
            csv.writer(f).writerow(COLUMNS)
    with path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        if tuple(reader.fieldnames or []) != COLUMNS:
            raise ValueError(f"Header {path} không đúng định dạng thực nghiệm")
        return {_key(r) for r in reader}


def upsert(path: Path, row: dict):
    """Ghi (thay thế nếu đã có) một hàng, ghi qua file tạm để không hỏng CSV khi bị ngắt."""
    key = _key(row)
    with path.open(encoding="utf-8", newline="") as f:
        records = [r for r in csv.DictReader(f) if _key(r) != key]
    records.append(row)
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(records)
    tmp.replace(path)


def measure(dataset: str, solver_name: str, strategy: str, seed: int):
    loaded = load_instance(
        str(ROOT / "data" / dataset), str(ROOT / "configs" / "default.json")
    )
    if not loaded.ok:
        raise RuntimeError(
            f"Dữ liệu {dataset} lỗi: {[m.to_dict() for m in loaded.messages]}"
        )
    cfg = dict(loaded.config)
    cfg.update(
        strategy=strategy,
        time_limit_sec=TIME_LIMIT_SEC,
        num_workers=NUM_WORKERS,
        random_seed=seed,
    )
    if solver_name == "pulp":
        from src.exam_solver_pulp import solve
    else:
        from src.exam_solver import solve
    result = solve(loaded.instance, cfg)
    schedule = build_schedule(
        loaded.instance, cfg, list(loaded.messages), result, dataset
    )
    destination = (
        ROOT / "output" / "perf" / dataset / f"{solver_name}_{strategy}_seed{seed}.json"
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    write_schedule(schedule, str(destination))
    has_solution = result.solution is not None
    n_violations = len(schedule["violations"]) if has_solution else ""
    if has_solution and n_violations:
        # Không dừng cả đợt đo: ghi số vi phạm thật; bảng tổng hợp tự loại hàng này.
        print(
            f"  !! CẢNH BÁO: {n_violations} vi phạm ở {dataset}/{solver_name}/"
            f"{strategy}/seed{seed}",
            flush=True,
        )
    kpi = schedule.get("kpi") or {}
    return {
        "dataset": dataset,
        "solver": solver_name,
        "strategy": strategy,
        "seed": seed,
        "time_limit_sec": TIME_LIMIT_SEC,
        "status": result.status,
        "objective": result.objective if has_solution else "",
        "best_bound": result.best_bound if result.best_bound is not None else "",
        "gap": gap_value(result.objective if has_solution else None, result.best_bound),
        "solve_time_sec": round(result.solve_time_sec, 3),
        "violations": n_violations,
        "num_sittings": kpi.get("num_sittings", ""),
        "students_multi_exam_day": kpi.get("students_multi_exam_day", ""),
        "proctor_load_range": kpi.get("proctor_load_range", ""),
    }


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Benchmark 30 tổ hợp; có thể chạy tiếp sau khi gián đoạn"
    )
    ap.add_argument("--datasets", nargs="+", choices=DATASETS, default=list(DATASETS))
    ap.add_argument("--seeds", nargs="+", type=int, default=list(SEEDS))
    ap.add_argument(
        "--force",
        action="store_true",
        help="Chạy lại các tổ hợp đã ghi (thay thế hàng cũ)",
    )
    args = ap.parse_args()
    if any(seed < 0 for seed in args.seeds):
        ap.error("seed phải >= 0")
    existing = ensure_results(RESULTS)

    # Ghi lại cấu hình máy hiện tại ở mỗi lần chạy (máy đo là máy đang chạy script này).
    machine_file = ROOT / "output" / "perf" / "machine.json"
    machine_file.parent.mkdir(parents=True, exist_ok=True)
    machine_file.write_text(
        json.dumps(machine_info(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    jobs = list(runs(dict.fromkeys(args.datasets), dict.fromkeys(args.seeds)))
    failed = []
    for idx, key in enumerate(jobs, 1):
        if key in existing and not args.force:
            print(f"[{idx}/{len(jobs)}] Bỏ qua đã đo: {key}", flush=True)
            continue
        print(
            f"[{idx}/{len(jobs)}] Đo {key} "
            f"(limit={TIME_LIMIT_SEC}s; CP-SAT workers={NUM_WORKERS})",
            flush=True,
        )
        try:
            row = measure(*key)
        except Exception as exc:  # một tổ hợp lỗi không làm mất cả đợt đo 2–3 giờ
            traceback.print_exc()
            print(f"  -> LỖI, bỏ qua {key}: {exc}", flush=True)
            failed.append(key)
            continue
        upsert(RESULTS, row)
        existing.add(key)
        print(
            f"  -> {row['status']}; Z={row['objective']}; t={row['solve_time_sec']}s; "
            f"vi phạm={row['violations']}",
            flush=True,
        )
    print(f"Kết quả: {RESULTS}")
    if failed:
        print(f"CÓ {len(failed)} tổ hợp lỗi (chạy lại script để đo tiếp): {failed}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
