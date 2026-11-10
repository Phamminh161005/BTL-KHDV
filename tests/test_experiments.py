"""Kiểm thử logic benchmark và sinh ra báo cáo không chạy 30 lần giải thật bài toán."""

import csv
import json
from pathlib import Path

import pytest

from experiments import perf, reschedule_perf as resch, update_report as report


def test_perf_combinations_and_config():
    jobs = list(perf.runs())
    assert len(jobs) == len(set(jobs)) == 30
    assert sum(solver == "cp-sat" for _, solver, _, _ in jobs) == 24
    assert sum(solver == "pulp" for _, solver, _, _ in jobs) == 6
    assert all(
        ds in {"toy", "toy_gen"} for ds, solver, _, _ in jobs if solver == "pulp"
    )
    assert {seed for *_, seed in jobs} == {0, 1, 2}
    assert perf.TIME_LIMIT_SEC == 300
    assert perf.NUM_WORKERS == 8


def test_csv_schemas_exactly_match_task():
    assert tuple(perf.COLUMNS) == tuple(report.PERF_COLUMNS)
    assert len(perf.COLUMNS) == 14
    assert tuple(resch.COLUMNS) == tuple(report.RESCHEDULE_COLUMNS)
    assert len(resch.COLUMNS) == 13


@pytest.mark.parametrize(
    "objective,bound,expected",
    [
        (100, 80, 0.2),
        (100, -20, 1.2),
        (None, 0, ""),
        (100, None, ""),
        (0, 0, ""),
        ("NaN", 0, ""),
        (100, float("inf"), ""),
    ],
)
def test_gap_value(objective, bound, expected):
    assert perf.gap_value(objective, bound) == expected


def _base_schedule():
    return {
        "sittings": [
            {
                "date": "2026-12-14",
                "periods": [1],
                "rooms": [{"room_id": "A", "proctors": ["G1", "G2"]}],
            },
            {
                "date": "2026-12-14",
                "periods": [3, 4],
                "rooms": [{"room_id": "B", "proctors": ["G3", "G4"]}],
            },
        ]
    }


def test_scenarios_use_occupied_resources_and_are_reproducible():
    first = resch.choose_scenarios(_base_schedule())
    assert first == resch.choose_scenarios(_base_schedule())
    assert set(first) == set(resch.SCENARIOS)
    assert [len(first[name]) for name in resch.SCENARIOS] == [1, 1, 3]
    assert first["room_one_period"][0]["resource_id"] == "A"
    assert first["lecturer_whole_day"][0]["period"] is None
    assert first["three_simultaneous"][2]["resource_id"] == "B"
    assert (
        resch.describe_incidents(first["lecturer_whole_day"])
        == "lecturer:G1:2026-12-14:*"
    )
    room_ids = [
        x["resource_id"]
        for x in first["three_simultaneous"]
        if x["resource_type"] == "room"
    ]
    assert len(set(room_ids)) == 2


def test_scenarios_reject_insufficient_resources():
    with pytest.raises(ValueError):
        resch.choose_scenarios({"sittings": []})
    with pytest.raises(ValueError):
        resch.choose_scenarios({"sittings": [_base_schedule()["sittings"][0]]})


def test_replace_only_report_section_and_reject_missing_marker(tmp_path):
    path = tmp_path / "model_spec.md"
    original = f"Start\n{report.START}\nold\n{report.END}\nOutside\n"
    path.write_text(original, encoding="utf-8")
    report.replace_section(path, "new")  # tương thích cách gọi cũ
    assert path.read_text(encoding="utf-8") == (
        f"Start\n{report.START}\nnew\n{report.END}\nOutside\n"
    )
    report.replace_section(path, report.START, report.END, "newer")
    assert "Outside" in path.read_text(encoding="utf-8")
    with pytest.raises(ValueError):
        report.replace_section(path, "<!-- MISSING -->", "<!-- END -->", "text")


def test_report_markers_match_readme():
    readme = Path(__file__).resolve().parents[1] / "experiments" / "README.md"
    raw = readme.read_text(encoding="utf-8")
    assert raw.count(report.R_START) == raw.count(report.R_END) == 1
    assert raw.count(report.M_START) == raw.count(report.M_END) == 1


def test_validity_requires_objective_time_and_zero_violations():
    row = {
        "status": "FEASIBLE",
        "objective": "2391",
        "solve_time_sec": "5.5",
        "violations": "0",
    }
    assert report.is_valid(row)
    for patch in (
        {"status": "UNKNOWN"},
        {"violations": "1"},
        {"objective": ""},
        {"solve_time_sec": "NaN"},
    ):
        assert not report.is_valid({**row, **patch})


def test_pick_winner_does_not_penalize_missing_gap():
    a = {"valid": 3, "z": 120, "gap": None, "time": 40}
    b = {"valid": 3, "z": 100, "gap": 0.2, "time": 50}
    assert report.pick_winner(a, b) == "two_phase"
    assert report.pick_winner({**a, "valid": 3}, {**b, "valid": 2}) == "single"
    assert report.pick_winner({**a, "z": 100, "time": 30}, b) == "single"


def test_fallback_detected_from_json(tmp_path, monkeypatch):
    monkeypatch.setattr(report, "PERF_OUTPUT", tmp_path)
    path = tmp_path / "medium" / "cp-sat_two_phase_seed0.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps({"messages": [{"code": "S04", "level": "warning"}]}),
        encoding="utf-8",
    )
    assert report.fallback_state("medium", "cp-sat", "two_phase", 0) is True
    assert report.fallback_state("medium", "cp-sat", "single", 0) is False
    assert report.fallback_state("medium", "cp-sat", "two_phase", 1) is None
    path.write_text(json.dumps({"messages": [{"code": "S05"}]}), encoding="utf-8")
    assert report.fallback_state("medium", "cp-sat", "two_phase", 0) is False


def _write_csv(path, columns, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def _perf_row(key, *, status="FEASIBLE", objective="100", violations="0"):
    ds, solver, strategy, seed = key
    return dict(
        dataset=ds,
        solver=solver,
        strategy=strategy,
        seed=seed,
        time_limit_sec=300,
        status=status,
        objective=objective,
        best_bound="80",
        gap="0.2",
        solve_time_sec="2",
        violations=violations,
        num_sittings="5",
        students_multi_exam_day="1",
        proctor_load_range="1",
    )


def _resch_row(ds, scenario, *, seconds=30, violations="0"):
    return dict(
        dataset=ds,
        scenario=scenario,
        incidents="room:A:2026-12-14:1",
        status="FEASIBLE",
        objective_before="100",
        objective_after="120",
        solve_time_sec="20",
        total_time_sec=str(seconds),
        sittings_changed="1",
        sittings_moved="1",
        students_affected="12",
        proctors_affected="2",
        violations=violations,
    )


def test_summary_reports_partial_data_without_inventing_conclusions(
    tmp_path, monkeypatch
):
    p, r = tmp_path / "perf.csv", tmp_path / "reschedule.csv"
    _write_csv(p, perf.COLUMNS, [_perf_row(("medium", "cp-sat", "single", 0))])
    _write_csv(r, resch.COLUMNS, [])
    monkeypatch.setattr(report, "PERF", p)
    monkeypatch.setattr(report, "RESCHEDULE", r)
    monkeypatch.setattr(report, "PERF_OUTPUT", tmp_path / "nonexistent_json")
    content, perf_ready, resch_ready, *_ = report.summary()
    assert not perf_ready and not resch_ready
    assert "1/30" in content and "0/6" in content
    assert "chưa đủ ba lần đo" in content
    assert "chưa đủ ba kịch bản" in content


def test_summary_complete_counts_and_reschedule_sla(tmp_path, monkeypatch):
    p, r = tmp_path / "perf.csv", tmp_path / "reschedule.csv"
    _write_csv(p, perf.COLUMNS, [_perf_row(k) for k in report.expected_perf_keys()])
    rows = [_resch_row(ds, sc) for ds in ("medium", "large") for sc in resch.SCENARIOS]
    # Một trường hợp vượt KPI đủ 60 giây dù có nghiệm hợp lệ.
    rows[-1]["total_time_sec"] = "60"
    _write_csv(r, resch.COLUMNS, rows)
    monkeypatch.setattr(report, "PERF", p)
    monkeypatch.setattr(report, "RESCHEDULE", r)
    monkeypatch.setattr(report, "PERF_OUTPUT", tmp_path / "no_json")
    content, perf_ready, resch_ready, *_ = report.summary()
    assert perf_ready and resch_ready
    assert "30/30" in content and "6/6" in content
    assert "KHÔNG ĐẠT" in content
    assert "chưa đạt KPI" in content
    # Khi tất cả trường hợp hợp lệ và dưới 60 giây, cả ba được ghi nhận đạt.
    rows[-1]["total_time_sec"] = "59.999"
    _write_csv(r, resch.COLUMNS, rows)
    content, *_ = report.summary()
    assert "đạt KPI dưới 60 giây" in content


def test_summary_rejects_duplicate_and_bad_header(tmp_path, monkeypatch):
    p, r = tmp_path / "perf.csv", tmp_path / "reschedule.csv"
    row = _perf_row(("medium", "cp-sat", "single", 0))
    _write_csv(p, perf.COLUMNS, [row, row])
    _write_csv(r, resch.COLUMNS, [])
    monkeypatch.setattr(report, "PERF", p)
    monkeypatch.setattr(report, "RESCHEDULE", r)
    with pytest.raises(ValueError, match="Trùng tổ hợp"):
        report.summary()
    p.write_text("dataset,seed\nmedium,0\n", encoding="utf-8")
    with pytest.raises(ValueError, match="sai định dạng"):
        report.summary()
