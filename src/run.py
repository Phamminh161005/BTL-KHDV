"""Chạy quy trình bài toán A/B: đọc dữ liệu, giải, hậu xử lý, kiểm tra, ghi schedule.json.

Cách chạy:
    py -3.12 -m src.run --data data/toy
    py -3.12 -m src.run --problem B --data data/toy_b --config configs/problem_b.json
    py -3.12 -m src.run --data data/toy --solver pulp
    py -3.12 -m src.run --data data/toy --no-diagnose      # không chẩn đoán khi vô nghiệm
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
DEFAULT_CONFIG_PATH = "configs/default.json"


def run(data_dir: str, config_path: str | None, out_path: str | None, solver: str = "cp-sat",
        diagnose: bool = True, problem: str | None = None) -> dict:
    """diagnose: khi solver trả về INFEASIBLE, chạy chẩn đoán nguyên nhân (bài A: src/diagnose.py, bài B:
    src/diagnose_b.py; mã N01–N05)."""
    if problem not in (None, "A", "B"):
        raise ValueError("problem phải là A hoặc B")
    if solver not in SOLVERS:
        raise ValueError(f"solver phải là một trong {sorted(SOLVERS)}, gặp {solver!r}")
    dataset = os.path.basename(os.path.normpath(data_dir))
    if problem == "B":
        from src.data_loader_b import load_instance_b
        loaded = load_instance_b(data_dir, config_path)
    else:
        loaded = load_instance(data_dir, config_path)
    if problem == "A" and loaded.config["problem"] != "A":
        raise ValueError("--problem A không khớp problem trong cấu hình")
    if loaded.config["problem"] == "B":
        if solver != "cp-sat":
            raise ValueError("Bài toán B chỉ hỗ trợ solver cp-sat")
        from src.room_solver import solve as solve_b
        from src.timetable import build_timetable
        result = solve_b(loaded.instance, loaded.config) if loaded.ok else None
        if diagnose and result is not None and result.status == "INFEASIBLE":
            from src.diagnose_b import diagnose_b
            result.messages += diagnose_b(loaded.instance, loaded.config)
        timetable = build_timetable(loaded.instance, loaded.config, loaded.messages, result, dataset)
        out_path = out_path or os.path.join("output", dataset, "timetable.json")
        os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
        write_schedule(timetable, out_path)
        return timetable
    result = None
    if loaded.ok:
        solve = importlib.import_module(SOLVERS[solver]).solve
        result = solve(loaded.instance, loaded.config)
        if diagnose and result.status == "INFEASIBLE":
            from src.diagnose import diagnose as run_diagnosis
            result.messages += run_diagnosis(loaded.instance, loaded.config)
    schedule = build_schedule(loaded.instance, loaded.config, loaded.messages, result, dataset)
    out_path = out_path or os.path.join("output", dataset, "schedule.json")
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    write_schedule(schedule, out_path)
    return schedule


def main() -> int:
    # Giao thức CLI dùng UTF-8, kể cả khi stdout/stderr bị pipe trên Windows.
    # Chỉ đổi ở entry point, không tác động ứng dụng import hàm run().
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="backslashreplace")
    parser = argparse.ArgumentParser(description="Xếp lịch thi (A) hoặc lịch phòng học theo tuần (B)")
    parser.add_argument("--problem", choices=["A", "B"], default=None, help="Ghi đè chọn B; mặc định đọc cấu hình")
    parser.add_argument("--data", required=True, help="Thư mục bộ dữ liệu, ví dụ data/toy")
    parser.add_argument("--config", default=None,
                        help="Mặc định configs/default.json nếu có; truyền file không tồn tại thì báo D12")
    parser.add_argument("--out", default=None, help="Mặc định output/<bộ dữ liệu>/schedule.json (A), timetable.json (B)")
    parser.add_argument("--solver", choices=sorted(SOLVERS), default="cp-sat",
                        help="cp-sat (mặc định) hoặc pulp (solver đối chứng PuLP + CBC)")
    parser.add_argument("--no-diagnose", action="store_true",
                        help="Không chẩn đoán nguyên nhân khi vô nghiệm")
    args = parser.parse_args()
    config_path = args.config
    if config_path is None and os.path.exists(DEFAULT_CONFIG_PATH):
        config_path = DEFAULT_CONFIG_PATH

    try:
        schedule = run(args.data, config_path, args.out, solver=args.solver, diagnose=not args.no_diagnose, problem=args.problem)
    except (NotImplementedError, ValueError) as e:
        print(f"Không chạy được: {e}")
        return 2
    for m in schedule["messages"]:
        where = f" ({m['file']}" + (f", dòng {m['line']}" if m["line"] else "") + ")" if m["file"] else ""
        print(f"[{m['level']}] {m['code']}{where}: {m['message']}")
    print(f"Solver: {schedule['meta']['solver']}")
    print(f"Trạng thái: {schedule['status']}, mục tiêu: {schedule['objective']}, "
          f"thời gian: {schedule['solve_time_sec']} giây, số lượt: {len(schedule.get('sittings', schedule.get('sessions', [])))}, "
          f"vi phạm: {len(schedule['violations'])}")
    return 0 if schedule["status"] in ("OPTIMAL", "FEASIBLE") and not schedule["violations"] else 1


if __name__ == "__main__":
    sys.exit(main())
