"""Chạy toàn bộ quy trình bài toán A: đọc dữ liệu, giải, hậu xử lý, kiểm tra, ghi schedule.json.

Cách chạy:
    py -3.12 -m src.run --data data/toy
    py -3.12 -m src.run --data data/toy --solver pulp
    py -3.12 -m src.run --data data/medium --config configs/default.json --out output/medium/schedule.json
"""
from __future__ import annotations

import argparse
import importlib
import os
import sys

from src.data_loader import load_instance
from src.schedule import build_schedule, write_schedule

# Tên solver -> module có hàm solve(instance, config) -> SolveResult
SOLVERS = {
    "cp-sat": "src.exam_solver",
    "pulp": "src.exam_solver_pulp",
}


def run(data_dir: str, config_path: str | None, out_path: str | None, solver: str = "cp-sat") -> dict:
    if solver not in SOLVERS:
        raise ValueError(f"solver phải là một trong {sorted(SOLVERS)}, gặp {solver!r}")
    dataset = os.path.basename(os.path.normpath(data_dir))
    loaded = load_instance(data_dir, config_path)
    result = None
    if loaded.ok:
        solve = importlib.import_module(SOLVERS[solver]).solve
        result = solve(loaded.instance, loaded.config)
    schedule = build_schedule(loaded.instance, loaded.config, loaded.messages, result, dataset)
    out_path = out_path or os.path.join("output", dataset, "schedule.json")
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    write_schedule(schedule, out_path)
    return schedule


def main() -> int:
    parser = argparse.ArgumentParser(description="Xếp lịch thi (bài toán A)")
    parser.add_argument("--data", required=True, help="Thư mục bộ dữ liệu, ví dụ data/toy")
    parser.add_argument("--config", default="configs/default.json")
    parser.add_argument("--out", default=None, help="Mặc định output/<tên bộ dữ liệu>/schedule.json")
    parser.add_argument("--solver", choices=sorted(SOLVERS), default="cp-sat",
                        help="cp-sat (mặc định) hoặc pulp (solver đối chứng PuLP + CBC)")
    args = parser.parse_args()
    config_path = args.config if os.path.exists(args.config) else None

    try:
        schedule = run(args.data, config_path, args.out, solver=args.solver)
    except NotImplementedError as e:
        print(f"Chưa chạy được: {e}")
        return 2
    for m in schedule["messages"]:
        where = f" ({m['file']}" + (f", dòng {m['line']}" if m["line"] else "") + ")" if m["file"] else ""
        print(f"[{m['level']}] {m['code']}{where}: {m['message']}")
    print(f"Solver: {schedule['meta']['solver']}")
    print(f"Trạng thái: {schedule['status']}, mục tiêu: {schedule['objective']}, "
          f"thời gian: {schedule['solve_time_sec']} giây, số lượt: {len(schedule['sittings'])}, "
          f"vi phạm: {len(schedule['violations'])}")
    return 0 if schedule["status"] in ("OPTIMAL", "FEASIBLE") and not schedule["violations"] else 1


if __name__ == "__main__":
    sys.exit(main())
