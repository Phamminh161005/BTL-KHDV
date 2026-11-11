"""MINH-4: thực nghiệm độ nhạy trọng số và đường cong đánh đổi (model_spec A.6, A.14; câu hỏi thứ 5 của Daskin).

Cách chạy, từ thư mục gốc của repo:
    py -3.12 -m experiments.sensitivity                       # chạy tất cả 65 lần (khoảng 2 giờ 30 phút)
    py -3.12 -m experiments.sensitivity --only weight noise   # chỉ chạy một số thí nghiệm
    py -3.12 -m experiments.sensitivity --dataset toy_gen     # chỉ chạy trên một bộ dữ liệu
    py -3.12 -m experiments.sensitivity --list                # in danh sách các lần chạy, không chạy

Mỗi lần chạy ghi ngay một dòng vào experiments/results/sensitivity.csv. Chạy lại thì bỏ qua các lần đã có trong
file (khóa: experiment, parameter, value, dataset, seed), nên bị ngắt giữa chừng thì chỉ cần chạy lại lệnh cũ.
Lần chạy nào có vi phạm ràng buộc cứng hoặc điểm phạt không khớp với lịch thì script dừng ngay, không ghi số sai.

Thiết kế và kết quả: experiments/README.md, mục "Độ nhạy trọng số".
- toy quá chật (một phòng máy buộc mọi cách xếp đều cần 3 lượt thêm) nên gần như không phản ứng với trọng số;
  chỉ dùng cho thí nghiệm trọng số xếp lại.
- toy_gen giải được tối ưu trong vài chục giây, nên khác biệt giữa các cấu hình là do trọng số: dùng cho độ nhạy.
- medium chỉ đạt FEASIBLE trong 300 giây và dao động 2-35% giữa các seed: chạy 3 seed, chỉ dùng các giá trị cách
  xa nhau và chỉ kết luận xu hướng mà mọi seed cùng đồng ý.
"""
from __future__ import annotations

import argparse
import copy
import csv
import json
import os
import sys
import tempfile
import time
from dataclasses import dataclass, field

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from src.data_loader import load_instance  # noqa: E402
from src.kpi import compute_penalties  # noqa: E402
from src.schedule import build_schedule  # noqa: E402

CONFIG = os.path.join(ROOT, "configs", "default.json")
OUT = os.path.join(ROOT, "experiments", "results", "sensitivity.csv")
TOY_BASE = os.path.join(ROOT, "tests", "reference", "toy_schedule.json")
TOY_INCIDENT = {"resource_type": "room", "resource_id": "G2-LAB1", "date": "2026-12-15", "period": 3}

SOFT = ("A-S1", "A-S2", "A-S3", "A-S4", "A-S5", "A-S6")
CHANGE = ("A-R1", "A-R2", "A-R3", "A-R4")
# Với reschedule_weight, `objective` là tổng phạt mềm của lịch mới; hàm mục tiêu thực khi xếp lại là change_cost.
FIELDS = ["experiment", "parameter", "value", "dataset", "strategy", "seed", "status", "objective",
          *SOFT, "students_multi_exam_day", "avg_gap_days", "proctor_load_range", "num_sittings",
          "seat_fill_rate", "solve_time_sec", "sittings_moved", "students_affected", "change_cost", *CHANGE]
KEY = ("experiment", "parameter", "value", "dataset", "seed")

# Bộ dữ liệu -> (strategy, các seed). time_limit_sec = 300 cho mọi lần chạy.
DATASETS = {"toy_gen": ("single", (0,)), "medium": ("two_phase", (0, 1, 2))}
TIME_LIMIT = 300
WEIGHT_FACTORS = (0, 0.5, 2, 5)
TRADEOFF_A_S6 = {"toy_gen": (0, 50, 100, 200, 400, 800), "medium": (0, 200, 800, 1600)}
RESCHEDULE_WEIGHTS = {"A-R1": (200, 1000, 5000), "A-R3": (10, 50, 200)}


@dataclass
class Run:
    experiment: str        # noise, weight, tradeoff, param, time_limit, reschedule_weight
    parameter: str         # tên trọng số hoặc tham số, "random_seed" hoặc "default"
    value: object          # giá trị đã dùng (với weight: hệ số nhân)
    dataset: str
    seed: int
    overrides: dict = field(default_factory=dict)   # thay đổi so với configs/default.json

    def key(self) -> tuple:
        return (self.experiment, self.parameter, str(self.value), self.dataset, str(self.seed))


def scaled_weights(defaults: dict, name: str, factor: float) -> dict:
    """Trọng số khi nhân `name` với `factor`. CP-SAT chỉ nhận số nguyên, nên với hệ số nhỏ hơn 1 thì nhân các
    trọng số còn lại với 1/factor (cùng tỷ lệ, cùng lời giải tối ưu), ví dụ A-S4 = 1 nhân 0,5."""
    weights = dict(defaults)
    if factor == 0 or factor >= 1:
        weights[name] = int(round(defaults[name] * factor))
        return weights
    inverse = round(1 / factor)
    if abs(inverse * factor - 1) > 1e-9:
        raise ValueError(f"Hệ số {factor} không có nghịch đảo nguyên")
    return {k: (v if k == name else v * inverse) for k, v in defaults.items()}


def plan(datasets: list[str]) -> list[Run]:
    """Danh sách mọi lần chạy, theo thứ tự chạy."""
    with open(CONFIG, encoding="utf-8") as f:
        defaults = json.load(f)["weights"]
    runs: list[Run] = []
    for ds in datasets:
        if ds not in DATASETS:
            continue
        _, seeds = DATASETS[ds]
        noise_seeds = (0, 1, 2) if ds == "toy_gen" else seeds
        for seed in noise_seeds:
            runs.append(Run("noise", "random_seed", seed, ds, seed))
        if ds == "toy_gen":
            for name in SOFT:
                for factor in WEIGHT_FACTORS:
                    runs.append(Run("weight", name, factor, ds, 0,
                                    {"weights": scaled_weights(defaults, name, factor)}))
        for value in TRADEOFF_A_S6[ds]:
            for seed in seeds:
                runs.append(Run("tradeoff", "A-S6", value, ds, seed, {"weights": dict(defaults, **{"A-S6": value})}))
        for seed in seeds:
            runs.append(Run("param", "forbid_own_course", True, ds, seed, {"forbid_own_course": True}))
            runs.append(Run("param", "proctors_per_room", 3, ds, seed, {"proctors_per_room": 3}))
        if ds == "medium":
            # Cho solver thời gian gấp 3 có làm các seed ổn định hơn không (so với noise ở 300 giây)
            for seed in seeds:
                runs.append(Run("time_limit", "time_limit_sec", 900, ds, seed, {"time_limit_sec": 900}))
    if "toy" in datasets:
        for name, values in RESCHEDULE_WEIGHTS.items():
            for value in values:
                runs.append(Run("reschedule_weight", name, value, "toy", 0, {"reschedule": {"weights": {name: value}}}))
    return runs


def _config_for(run: Run) -> dict:
    with open(CONFIG, encoding="utf-8") as f:
        cfg = json.load(f)
    if run.experiment != "reschedule_weight":
        strategy, _ = DATASETS[run.dataset]
        cfg.update(strategy=strategy, time_limit_sec=TIME_LIMIT)
    cfg["random_seed"] = run.seed
    for key, value in run.overrides.items():
        if key == "reschedule":
            cfg["reschedule"]["weights"].update(value["weights"])
        else:
            cfg[key] = copy.deepcopy(value)
    return cfg


def _row(run: Run, strategy: str, schedule: dict, extra: dict | None = None) -> dict:
    kpi = schedule.get("kpi") or {}
    penalties = schedule.get("penalties") or {}
    row = {"experiment": run.experiment, "parameter": run.parameter, "value": run.value, "dataset": run.dataset,
           "strategy": strategy, "seed": run.seed, "status": schedule["status"], "objective": schedule["objective"],
           **{k: penalties.get(k) for k in SOFT},
           **{k: kpi.get(k) for k in ("students_multi_exam_day", "avg_gap_days", "proctor_load_range",
                                      "num_sittings", "seat_fill_rate")},
           "solve_time_sec": schedule["solve_time_sec"], "sittings_moved": None, "students_affected": None}
    row.update(extra or {})
    return row


def _check(run: Run, instance, schedule: dict) -> None:
    if schedule["status"] not in ("OPTIMAL", "FEASIBLE"):
        return
    if schedule["violations"]:
        raise RuntimeError(f"{run.key()}: có {len(schedule['violations'])} vi phạm: {schedule['violations'][:3]}")
    if compute_penalties(instance, schedule) != schedule["penalties"]:
        raise RuntimeError(f"{run.key()}: điểm phạt của solver không khớp với lịch")


def execute(run: Run) -> dict:
    """Chạy một lần và trả về dòng CSV."""
    cfg = _config_for(run)
    with tempfile.TemporaryDirectory() as tmp:
        cfg_path = os.path.join(tmp, "config.json")
        with open(cfg_path, "w", encoding="utf-8") as f:
            json.dump(cfg, f)
        data_dir = os.path.join(ROOT, "data", run.dataset)
        if run.experiment == "reschedule_weight":
            from src.reschedule import reschedule
            schedule = reschedule(data_dir, TOY_BASE, [TOY_INCIDENT], cfg_path, os.path.join(tmp, "out.json"))
            info = schedule["reschedule"]
            summary = info["summary"] or {}
            changes = info.get("change_penalties") or {}
            loaded = load_instance(data_dir, cfg_path)
            from src.reschedule import apply_incidents
            apply_incidents(loaded.instance, [TOY_INCIDENT], [])
            _check(run, loaded.instance, schedule)
            return _row(run, "single", schedule, {"sittings_moved": summary.get("sittings_moved"),
                                                  "students_affected": summary.get("students_affected"),
                                                  "change_cost": info.get("change_cost"),
                                                  **{k: changes.get(k) for k in CHANGE}})
        loaded = load_instance(data_dir, cfg_path)
        if not loaded.ok:
            raise RuntimeError(f"{run.key()}: dữ liệu lỗi: {[m.to_dict() for m in loaded.messages]}")
        from src.exam_solver import solve
        result = solve(loaded.instance, loaded.config)
        schedule = build_schedule(loaded.instance, loaded.config, loaded.messages, result, run.dataset)
        _check(run, loaded.instance, schedule)
        return _row(run, loaded.config["strategy"], schedule)


def _done(path: str) -> set[tuple]:
    if not os.path.exists(path):
        return set()
    with open(path, encoding="utf-8-sig", newline="") as f:
        return {tuple(row[k] for k in KEY) for row in csv.DictReader(f)}


def main() -> int:
    parser = argparse.ArgumentParser(description="MINH-4: độ nhạy trọng số và đường cong đánh đổi")
    parser.add_argument("--only", nargs="*",
                        choices=["noise", "weight", "tradeoff", "param", "time_limit", "reschedule_weight"])
    parser.add_argument("--dataset", nargs="*", choices=["toy", "toy_gen", "medium"],
                        default=["toy", "toy_gen", "medium"])
    parser.add_argument("--out", default=OUT)
    parser.add_argument("--list", action="store_true", help="chỉ in danh sách các lần chạy")
    args = parser.parse_args()

    runs = [r for r in plan(args.dataset) if not args.only or r.experiment in args.only]
    done = _done(args.out)
    todo = [r for r in runs if r.key() not in done]
    print(f"{len(runs)} lần chạy, đã có {len(runs) - len(todo)}, còn {len(todo)}", flush=True)
    if args.list:
        for r in todo:
            print("  ", r.key())
        return 0
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    new_file = not os.path.exists(args.out)
    with open(args.out, "a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        if new_file:
            writer.writeheader()
        # Cấu hình trùng nhau (ví dụ A-S6 = 200 chính là mặc định) chỉ giải một lần trong một lần chạy script
        cache: dict[str, dict] = {}
        for n, run in enumerate(todo, 1):
            started = time.monotonic()
            signature = json.dumps([run.experiment == "reschedule_weight", run.dataset, _config_for(run)],
                                   sort_keys=True, default=str)
            if signature in cache:
                row = dict(cache[signature], experiment=run.experiment, parameter=run.parameter, value=run.value)
            else:
                row = cache[signature] = execute(run)
            writer.writerow(row)
            f.flush()
            print(f"[{n}/{len(todo)}] {run.key()} -> {row['status']} {row['objective']} "
                  f"({time.monotonic() - started:.0f} giây)", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
