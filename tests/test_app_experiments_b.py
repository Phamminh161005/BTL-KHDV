"""Focused AppTest coverage for the standalone B experiment dashboard."""
import csv
import json

import pytest
from streamlit.testing.v1 import AppTest


def run_page(folder):
    script = f"from pathlib import Path\nfrom app.experiments_b import page_experiments_b\npage_experiments_b(Path({str(folder)!r}))"
    app = AppTest.from_string(script, default_timeout=15).run()
    assert not app.exception
    return app


def write_csv(folder, filename, columns, rows):
    with (folder / filename).open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


PERF = ["dataset", "seed", "status", "solve_time_sec", "time_limit_sec", "objective", "best_bound"]
LAB = ["dataset", "seed", "reserve_enabled", "lab_reserve_ratio", "status", "solve_time_sec",
       "room_utilization_lab", "lab_peak_utilization", "slots_without_lab_reserve"]


def test_missing_real_files_never_auto_load_samples(tmp_path):
    app = run_page(tmp_path)
    assert all(any(name in message.value for message in app.info)
               for name in ("perf_b.csv", "lab_reserve_b.csv"))
    assert not app.dataframe
    assert "synthetic" in app.checkbox[0].label
    app.checkbox[0].check().run()
    assert not app.exception
    assert any("TỔNG HỢP" in caption.value for caption in app.caption)
    assert len(app.dataframe) >= 3
    assert any("synthetic_small" in frame.value["dataset"].values
               for frame in app.dataframe if "dataset" in frame.value.columns)
    app.checkbox[0].uncheck().run()
    assert not app.dataframe


def test_real_files_chart_status_and_paired_kpis(tmp_path):
    write_csv(tmp_path, "perf_b.csv", PERF, [
        dict(dataset="real", seed=0, status="FEASIBLE", solve_time_sec=301,
             time_limit_sec=300, objective=13, best_bound=11),
        dict(dataset="real", seed=1, status="OPTIMAL", solve_time_sec=3,
             time_limit_sec=300, objective=12, best_bound=12),
        dict(dataset="real", seed=2, status="UNKNOWN", solve_time_sec=300, time_limit_sec=300)])
    write_csv(tmp_path, "lab_reserve_b.csv", LAB, [
        dict(dataset="real", seed=0, reserve_enabled="false", lab_reserve_ratio=.2,
             status="OPTIMAL", solve_time_sec=10, room_utilization_lab=.8,
             lab_peak_utilization=.9, slots_without_lab_reserve=1),
        dict(dataset="real", seed=0, reserve_enabled="true", lab_reserve_ratio=.2,
             status="FEASIBLE", solve_time_sec=14, room_utilization_lab=.6,
             lab_peak_utilization=.7, slots_without_lab_reserve=3),
        dict(dataset="real", seed=1, reserve_enabled="true", lab_reserve_ratio=.2,
             status="UNKNOWN", solve_time_sec=300)])
    app = run_page(tmp_path)
    assert not app.warning
    spec = json.loads(app.get("vega_lite_chart")[0].proto.spec)
    assert spec["layer"][1]["encoding"]["y"]["datum"] == 300
    assert spec["layer"][0]["encoding"]["color"]["field"] == "Trạng thái"
    perf = next(frame.value for frame in app.dataframe if "objective" in frame.value.columns)
    assert list(perf["status"]) == ["FEASIBLE", "OPTIMAL", "UNKNOWN"]
    summary = next(frame.value for frame in app.dataframe if "Bật - tắt" in frame.value.columns)
    assert list(summary["Bật - tắt"]) == pytest.approx([-.2, -.2, 2, 4])
    assert any(metric.value == "1" for metric in app.metric)
    assert not any("objective" in frame.value.columns for frame in app.dataframe if "reserve_enabled" in frame.value.columns)


def test_empty_and_extra_csv_fields_do_not_crash(tmp_path):
    (tmp_path / "perf_b.csv").write_text("", encoding="utf-8")
    (tmp_path / "lab_reserve_b.csv").write_text(
        ",".join(LAB) + "\nreal,0,true,0.2,FEASIBLE,2,0.7,0.8,1,unexpected\n",
        encoding="utf-8")
    app = run_page(tmp_path)
    assert any("thiếu cột" in w.value for w in app.warning)
    assert any("thừa ô" in w.value for w in app.warning)


def test_invalid_perf_isolated_from_lab_and_bad_rows_skipped(tmp_path):
    write_csv(tmp_path, "perf_b.csv", ["dataset", "seed"], [{"dataset": "bad", "seed": 0}])
    write_csv(tmp_path, "lab_reserve_b.csv", LAB, [
        dict(dataset="real", seed=0, reserve_enabled="false", lab_reserve_ratio=.2,
             status="FEASIBLE", solve_time_sec=10, room_utilization_lab=.8,
             lab_peak_utilization=.9, slots_without_lab_reserve=1),
        dict(dataset="real", seed=1, reserve_enabled="true", lab_reserve_ratio=.2,
             status="FEASIBLE", solve_time_sec="nan", room_utilization_lab=.7,
             lab_peak_utilization=.8, slots_without_lab_reserve=2)])
    app = run_page(tmp_path)
    assert any("perf_b.csv" in w.value and "thiếu cột" in w.value for w in app.warning)
    assert any("lab_reserve_b.csv dòng 3" in w.value for w in app.warning)
    details = next(frame.value for frame in app.dataframe if "reserve_enabled" in frame.value.columns)
    assert len(details) == 1


@pytest.mark.parametrize("field,value", [("solve_time_sec", "-1"), ("time_limit_sec", "0"),
                                          ("objective", "inf"), ("seed", "1.5")])
def test_invalid_perf_numbers_warn_without_crashing(tmp_path, field, value):
    row = dict(dataset="real", seed=0, status="OPTIMAL", solve_time_sec=1, time_limit_sec=300)
    row[field] = value
    write_csv(tmp_path, "perf_b.csv", PERF, [row])
    app = run_page(tmp_path)
    assert any(field in w.value for w in app.warning)
    assert not app.dataframe


@pytest.mark.parametrize("field,value", [("reserve_enabled", "maybe"), ("lab_reserve_ratio", "1.5"),
                                          ("room_utilization_lab", "nan"),
                                          ("slots_without_lab_reserve", "-1")])
def test_invalid_lab_fields_warn_without_crashing(tmp_path, field, value):
    row = dict(dataset="real", seed=0, reserve_enabled="true", lab_reserve_ratio=.2,
               status="FEASIBLE", solve_time_sec=2, room_utilization_lab=.7,
               lab_peak_utilization=.9, slots_without_lab_reserve=1)
    row[field] = value
    write_csv(tmp_path, "lab_reserve_b.csv", LAB, [row])
    app = run_page(tmp_path)
    assert any(field in w.value for w in app.warning)
    assert not app.dataframe
