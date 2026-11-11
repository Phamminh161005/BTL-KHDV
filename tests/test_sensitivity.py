"""Kiểm thử phần lập kế hoạch của experiments/sensitivity.py (không chạy solver)."""
from experiments.sensitivity import FIELDS, KEY, WEIGHT_FACTORS, plan, scaled_weights

DEFAULTS = {"A-S1": 100, "A-S2": 30, "A-S3": 50, "A-S4": 1, "A-S5": 20, "A-S6": 200}


def test_scaled_weights_are_integers_with_same_ratio():
    assert scaled_weights(DEFAULTS, "A-S1", 0)["A-S1"] == 0
    assert scaled_weights(DEFAULTS, "A-S1", 5)["A-S1"] == 500
    half = scaled_weights(DEFAULTS, "A-S4", 0.5)        # A-S4 = 1 không chia đôi được: nhân các trọng số khác với 2
    assert half == {"A-S1": 200, "A-S2": 60, "A-S3": 100, "A-S4": 1, "A-S5": 40, "A-S6": 400}
    assert all(isinstance(v, int) for factor in WEIGHT_FACTORS for v in scaled_weights(DEFAULTS, "A-S2", factor).values())


def test_plan_has_unique_keys_and_expected_size():
    runs = plan(["toy", "toy_gen", "medium"])
    keys = [r.key() for r in runs]
    assert len(keys) == len(set(keys))
    assert sum(r.experiment == "weight" for r in runs) == 6 * len(WEIGHT_FACTORS)
    assert {r.dataset for r in runs if r.experiment == "reschedule_weight"} == {"toy"}
    assert {r.seed for r in runs if r.dataset == "medium"} == {0, 1, 2}
    assert set(KEY) <= set(FIELDS)
