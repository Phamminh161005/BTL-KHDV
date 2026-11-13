"""Nghiệm thu KHOE-5: đáp án chuẩn, B.12, deadline và chẩn đoán."""
import copy
import itertools
import random
import time
from pathlib import Path

import pytest

from src.data_loader_b import load_instance_b
from src.instance_b import ClassB, InstanceB, LecturerB, RoomB
from src.room_solver import solve
from src.timetable import build_timetable
from src.validator_b import compute_penalties_b, validate_b

ROOT = Path(__file__).resolve().parents[1]


def toy():
    loaded = load_instance_b(str(ROOT / "data" / "toy_b"))
    assert loaded.ok
    loaded.config.update(time_limit_sec=10, num_workers=1)
    return loaded.instance, loaded.config


def checked(inst, cfg, result):
    assert result.status in ("OPTIMAL", "FEASIBLE")
    table = build_timetable(inst, cfg, [], result, inst.name)
    assert not table["violations"]
    assert result.penalties == compute_penalties_b(inst, table, cfg["lab_reserve_ratio"])
    assert result.objective == sum(cfg["weights"][k] * v for k, v in result.penalties.items())
    return table


@pytest.mark.parametrize("seed", [0, 1, 2])
def test_reference(seed):
    inst, cfg = toy()
    cfg["random_seed"] = seed
    result = solve(inst, cfg)
    assert result.status == "OPTIMAL" and result.objective == 355
    assert result.best_bound == 355
    assert tuple(result.penalties.values()) == (75, 1, 2, 1)
    table = checked(inst, cfg, result)
    assert len(table["sessions"]) == 24
    assert table["kpi"]["room_utilization_lab"] == 9 / 40


def test_weight_tradeoff():
    inst, cfg = toy()
    cfg["weights"]["B-S2"] = 150
    res = solve(inst, cfg)
    checked(inst, cfg, res)
    assert res.status == "OPTIMAL"
    assert tuple(res.penalties.values()) == (75, 0, 3, 1)


@pytest.mark.parametrize("variant", range(6))
def test_b12_infeasible(variant):
    inst, cfg = toy()
    if variant == 0:
        inst.classes["INT2204-LT"].size = 70
    elif variant == 1:
        inst.classes["INT2204-TH1"].size = 25
    elif variant == 2:
        inst.lecturers["GV06"].busy = set(inst.slots) - {(6, 1)}
    elif variant == 3:
        inst.classes["EXTRA"] = ClassB("EXTRA", False, 10, 16, "GV07")
    elif variant == 4:
        inst.classes["EXTRA"] = ClassB("EXTRA", False, 10, 8, "GV03")
        inst.groups["K67-CN1"] += ["ELT2035", "EXTRA"]
    else:
        for i, g in enumerate(["GV01", "GV02", "GV03"]):
            inst.classes[f"L{i}"] = ClassB(f"L{i}", True, 10, 11, g)
    result = solve(inst, cfg)
    assert result.status == "INFEASIBLE"
    assert result.solution is None and result.objective is None


def test_diagnosis_b12_and_no_mutation():
    inst, cfg = toy()
    for k, n in [("ELT2035", 7), ("INT3306-TH", 6)]:
        cls = inst.classes[k]
        cls.sessions = n
        inst.lecturers[cls.lecturer_id].busy = {t for t in inst.slots if t[0] > 4}
    inst.groups["DIAG"] = ["ELT2035", "INT3306-TH"]
    before = copy.deepcopy(inst)
    assert solve(inst, cfg).status == "INFEASIBLE"
    for group, expected in [("B-H5", "FEASIBLE"), ("B-H7", "FEASIBLE"), ("B-H6", "INFEASIBLE")]:
        res = solve(inst, cfg, relax={group}, optimize=False)
        assert res.status == expected
        if res.solution:
            table = build_timetable(inst, cfg, [], res, "diag")
            assert {v["code"] for v in table["violations"]} <= {group}
    assert inst == before


def test_room_busy_can_be_relaxed():
    inst, cfg = toy()
    for room in inst.rooms.values():
        room.busy = set(inst.slots)
    assert solve(inst, cfg).status == "INFEASIBLE"
    assert solve(inst, cfg, relax={"B-H6"}, optimize=False).status == "FEASIBLE"


@pytest.mark.parametrize("budget", [0, 1e-8, 0.03])
def test_deadline_includes_build(budget):
    inst, cfg = toy()
    cfg["time_limit_sec"] = budget
    start = time.monotonic()
    res = solve(inst, cfg)
    elapsed = time.monotonic() - start
    assert elapsed < budget + 0.3  # tolérance d'ordonnancement de l'OS
    assert res.solve_time_sec <= elapsed
    if budget < 1e-6:
        assert res.status == "UNKNOWN" and res.solution is None


def test_slow_model_build_never_receives_fresh_budget(monkeypatch):
    inst, cfg = toy()
    cfg["time_limit_sec"] = 0.02
    original = inst.rooms_for
    def delayed(k):
        time.sleep(0.04)
        return original(k)
    monkeypatch.setattr(inst, "rooms_for", delayed)
    from ortools.sat.python import cp_model
    def forbidden(*a, **kw):
        pytest.fail("Không được bắt đầu search khi dựng model đã hết ngân sách")
    monkeypatch.setattr(cp_model.CpSolver, "solve", forbidden)
    res = solve(inst, cfg)
    assert res.status == "UNKNOWN" and res.solution is None


def test_feasibility_and_invalid_options():
    inst, cfg = toy()
    res = solve(inst, cfg, optimize=False)
    assert res.status == "FEASIBLE" and res.best_bound is None
    checked(inst, cfg, res)
    with pytest.raises(ValueError):
        solve(inst, cfg, relax={"typo"})
    with pytest.raises(ValueError):
        solve(inst, dict(cfg, strategy="two_phase"))


@pytest.mark.parametrize("seed", range(5))
def test_tiny_exhaustive_optimum(seed):
    """So với vét cạn độc lập: kiểm cả tương tác các ràng buộc, trọng số 0."""
    rng = random.Random(seed)
    slots = [(2, 1), (2, 2), (3, 1), (3, 2)]
    rooms = {"N": RoomB("N", "normal", 30), "L1": RoomB("L1", "lab", 20),
             "L2": RoomB("L2", "lab", 25, busy={(2, 1)})}
    lecturers = {g: LecturerB(g, avoid={rng.choice(slots)}) for g in ("G1", "G2")}
    classes = {"A": ClassB("A", True, 18, 2, "G1", groups={"H"}),
               "B": ClassB("B", True, 19, 1, "G2"),
               "C": ClassB("C", False, 25, 1, "G2", groups={"H"})}
    inst = InstanceB("tiny", slots, rooms, classes, lecturers, {"H": ["A", "C"]})
    _, cfg = toy()
    cfg["weights"]["B-S4"] = 0 if seed % 2 else 30
    choices = []
    for k, cls in classes.items():
        feasible = [(k, r, t) for r in inst.rooms_for(k) for t in inst.slots_for(k, r)]
        choices.append(list(itertools.combinations(feasible, cls.sessions)))
    optimum = None
    for combo in itertools.product(*choices):
        rows = [{"session_id": f"{k}@{r}@{t}", "class_id": k, "room_id": r,
                 "weekday": t[0], "period": t[1]} for options in combo for k, r, t in options]
        tt = {"sessions": rows}
        if validate_b(inst, tt):
            continue
        p = compute_penalties_b(inst, tt, cfg["lab_reserve_ratio"])
        cost = sum(cfg["weights"][k] * v for k, v in p.items())
        optimum = cost if optimum is None else min(optimum, cost)
    res = solve(inst, cfg)
    checked(inst, cfg, res)
    assert res.status == "OPTIMAL" and res.objective == optimum


def test_relaxed_busy_objective_and_bound_still_match():
    inst, cfg = toy()
    for r in inst.rooms.values():
        r.busy = set(inst.slots)
    res = solve(inst, cfg, relax={"B-H6"})
    assert res.status == "OPTIMAL"
    assert res.best_bound == res.objective
    tt = build_timetable(inst, cfg, [], res, "relaxed")
    assert {v["code"] for v in tt["violations"]} == {"B-H6"}
