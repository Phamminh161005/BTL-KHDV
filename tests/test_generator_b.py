"""Kiểm tra dữ liệu sinh, CLI, phép đếm đổi phòng và thực nghiệm B."""
from pathlib import Path
import json
import pytest

from src.generator import generate, check
from src.generator_b import generate_b
from src.data_loader_b import load_instance_b
from src.room_solver import solve
from src.timetable import build_timetable
from src.run import run
from experiments.perf_b import reserve_counts

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("size,n,groups", [("medium_b", 60, 8), ("large_b", 120, 16)])
@pytest.mark.parametrize("seed", [0, 1, 2])
def test_generated_b_valid_and_reproducible(tmp_path, size, n, groups, seed):
    a, b = tmp_path / "a", tmp_path / "b"
    generate(size, seed, str(a))
    generate(size, seed, str(b))
    assert {p.name: p.read_bytes() for p in a.iterdir()} == {p.name: p.read_bytes() for p in b.iterdir()}
    for name in ("rooms.csv", "lecturers.csv"):
        assert (a / name).read_bytes() == (ROOT / "data" / size[:-2] / name).read_bytes()
    loaded = load_instance_b(str(a))
    assert loaded.ok and check(str(a))
    assert not [m for m in loaded.messages if m.code.startswith("PB")]
    assert len(loaded.instance.classes) == n and len(loaded.instance.groups) == groups
    stats = json.loads((a / "generation.json").read_text(encoding="utf-8"))
    assert 0.6 <= stats["room_utilization_lab"] <= 0.85
    assert all(not g.busy & g.avoid for g in loaded.instance.lecturers.values())
    if seed == 1:
        for name in ("classes.csv", "class_groups.csv", "week_slots.csv", "week_unavailability.csv", "preferences.csv"):
            assert (a / name).read_bytes() == (ROOT / "data" / size / name).read_bytes()
    # Lịch khả thi trong 10s trên cả seed sinh khác, không chỉ bộ đã commit.
    loaded.config.update(time_limit_sec=10, num_workers=1)
    result = solve(loaded.instance, loaded.config, optimize=False)
    assert result.solution is not None
    assert not build_timetable(loaded.instance, loaded.config, [], result, size)["violations"]


def test_different_seed_changes_data(tmp_path):
    generate("medium_b", 1, str(tmp_path / "a"))
    generate("medium_b", 2, str(tmp_path / "b"))
    assert (tmp_path / "a/classes.csv").read_bytes() != (tmp_path / "b/classes.csv").read_bytes()


def test_reference_data_protected(tmp_path):
    with pytest.raises(ValueError):
        generate_b("medium_b", 1, str(tmp_path / "toy_b"))


def test_run_b_exports_schema(tmp_path):
    out = tmp_path / "timetable.json"
    tt = run(str(ROOT / "data/toy_b"), str(ROOT / "configs/problem_b.json"), str(out))
    assert tt["status"] == "OPTIMAL" and tt["objective"] == 355
    assert not tt["violations"] and tt["meta"]["problem"] == "B"
    assert json.loads(out.read_text(encoding="utf-8")) == tt


def test_reserve_counter_requires_capacity_availability_and_free_slot():
    from src.instance_b import InstanceB, RoomB, ClassB, LecturerB
    rooms = {"L1": RoomB("L1", "lab", 30), "L2": RoomB("L2", "lab", 20),
             "L3": RoomB("L3", "lab", 30, busy={(2, 1)})}
    classes = {"A": ClassB("A", True, 25, 1, "G")}
    inst = InstanceB("test", [(2, 1)], rooms, classes, {"G": LecturerB("G")}, {})
    tt = {"sessions": [{"class_id": "A", "room_id": "L1", "weekday": 2, "period": 1}],
          "kpi": {"slots_without_lab_reserve": 0}}
    assert reserve_counts(inst, tt)["must_move"] == 1  # L2 thiếu máy, L3 bận
    rooms["L3"].busy.clear()
    assert reserve_counts(inst, tt)["room_change_only"] == 1
    tt["sessions"].append({"class_id": "A", "room_id": "L3", "weekday": 2, "period": 1})
    assert reserve_counts(inst, tt)["must_move"] == 2  # L3 đã có buổi khác
