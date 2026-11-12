"""Independent KPI checks against the hand-specified toy_b reference timetable."""
import copy
import json
from pathlib import Path

import pytest

from src.data_loader_b import load_instance_b
from src.kpi_b import compute_kpi, compute_penalties
from src.validator_b import compute_penalties_b, validate_b

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT / "tests" / "reference" / "toy_timetable.json"


@pytest.fixture(scope="module")
def instance_and_config():
    result = load_instance_b(str(ROOT / "data" / "toy_b"), str(ROOT / "configs" / "default.json"))
    assert result.ok
    return result.instance, result.config


@pytest.fixture
def timetable():
    return json.loads(REFERENCE.read_text(encoding="utf-8"))


def test_reference_is_valid_and_optimal_by_independent_penalty_accounting(instance_and_config, timetable):
    instance, config = instance_and_config
    assert len(timetable["sessions"]) == 24
    assert validate_b(instance, timetable) == []
    expected = {"B-S1": 75, "B-S2": 1, "B-S3": 2, "B-S4": 1}
    assert compute_penalties(instance, timetable, config["lab_reserve_ratio"]) == expected
    assert compute_penalties_b(instance, timetable, config["lab_reserve_ratio"]) == expected
    assert timetable["penalties"] == expected
    assert sum(config["weights"][key] * value for key, value in expected.items()) == timetable["objective"] == 355


def test_reference_kpi_hand_calculated(instance_and_config, timetable):
    instance, _ = instance_and_config
    # 15 normal sessions / 43 available room-slots; 9 lab sessions / 40 available.
    # Scheduled class sizes sum to 765, total assigned capacity is 840.
    expected = {
        "hard_violations": 0,
        "room_utilization_normal": round(15 / 43, 4),
        "room_utilization_lab": 9 / 40,
        "lab_peak_utilization": 1.0,
        "slots_without_lab_reserve": 1,
        "seat_fill_rate": round(765 / 840, 4),
        "preference_violations": 1,
        "classes_same_day": 2,
        "group_max_sessions_per_day": 4,
        "solve_time_sec": 0.0,
    }
    assert compute_kpi(instance, timetable, len(validate_b(instance, timetable))) == expected
    assert timetable["kpi"] == expected


def test_duplicate_room_slot_only_counts_once_for_utilization(instance_and_config, timetable):
    instance, _ = instance_and_config
    timetable["sessions"].append(copy.deepcopy(timetable["sessions"][0]))
    kpi = compute_kpi(instance, timetable, 1)
    assert kpi["hard_violations"] == 1
    assert kpi["room_utilization_normal"] == round(15 / 43, 4)


def test_custom_reserve_ratio_and_empty_schedule(instance_and_config, timetable):
    instance, _ = instance_and_config
    timetable["meta"]["config"]["lab_reserve_ratio"] = 0.4
    assert compute_kpi(instance, timetable, 0)["slots_without_lab_reserve"] == 9
    assert compute_penalties(instance, timetable, 0.4)["B-S4"] == 9

    timetable["sessions"] = []
    kpi = compute_kpi(instance, timetable, 0)
    assert kpi["seat_fill_rate"] is None
    assert kpi["lab_peak_utilization"] == 0.0
    assert kpi["group_max_sessions_per_day"] == 0
    assert kpi["room_utilization_normal"] == 0.0
    assert kpi["slots_without_lab_reserve"] == 0
    assert compute_penalties(instance, timetable) == dict.fromkeys(("B-S1", "B-S2", "B-S3", "B-S4"), 0)


def test_null_denominators_and_no_groups(instance_and_config, timetable):
    instance, _ = instance_and_config
    instance = copy.deepcopy(instance)
    instance.slots = []
    instance.groups = {}
    instance.rooms = {}
    timetable["sessions"] = []
    kpi = compute_kpi(instance, timetable, 0)
    assert kpi["room_utilization_normal"] is None
    assert kpi["room_utilization_lab"] is None
    assert kpi["lab_peak_utilization"] is None
    assert kpi["group_max_sessions_per_day"] is None
    assert kpi["seat_fill_rate"] is None
