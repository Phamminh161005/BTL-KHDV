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
LAB = ["dataset", "seed", "b_s4_weight", "lab_sessions", "room_change_only", "must_move",
       "slots_without_lab_reserve", "objective"]


def lab_row(seed, weight, change, move, over, objective=100):
    return dict(dataset="real", seed=seed, b_s4_weight=weight, lab_sessions=change + move,
                room_change_only=change, must_move=move, slots_without_lab_reserve=over, objective=objective)


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
        lab_row(0, 30, change=30, move=18, over=6),
        lab_row(0, 0, change=20, move=28, over=11),
        lab_row(1, 30, change=32, move=16, over=6),
        lab_row(1, 0, change=18, move=30, over=11),
        lab_row(2, 30, change=33, move=15, over=6)])       # seed 2 thiếu lượt tắt: không ghép
    app = run_page(tmp_path)
    assert not app.warning
    spec = json.loads(app.get("vega_lite_chart")[0].proto.spec)
    assert spec["layer"][1]["encoding"]["y"]["datum"] == 300
    assert spec["layer"][0]["encoding"]["color"]["field"] == "Trạng thái"
    perf = next(frame.value for frame in app.dataframe if "best_bound" in frame.value.columns)
    assert list(perf["status"]) == ["FEASIBLE", "OPTIMAL", "UNKNOWN"]
    summary = next(frame.value for frame in app.dataframe if "Bật - tắt" in frame.value.columns)
    # Thứ tự: phải dời ca, chỉ đổi phòng, ca vượt ngưỡng; trung bình 2 cặp (seed 0, 1)
    assert list(summary["Tắt (TB)"]) == pytest.approx([29, 19, 11])
    assert list(summary["Bật (TB)"]) == pytest.approx([17, 31, 6])
    assert list(summary["Bật - tắt"]) == pytest.approx([-12, 12, -5])
    assert any(metric.value == "2" for metric in app.metric)
    details = next(frame.value for frame in app.dataframe if "b_s4_weight" in frame.value.columns)
    assert len(details) == 5 and "objective" not in details.columns


def test_real_results_of_khoe5_render():
    """Đọc đúng experiments/results/ do experiments/perf_b.py ghi ra, không cảnh báo."""
    from pathlib import Path
    app = run_page(Path(__file__).resolve().parents[1] / "experiments" / "results")
    assert not app.warning
    summary = next(frame.value for frame in app.dataframe if "Bật - tắt" in frame.value.columns)
    assert set(summary["Bộ dữ liệu"]) == {"medium_b", "large_b"}
    assert any(metric.value == "6" for metric in app.metric)


def test_empty_and_extra_csv_fields_do_not_crash(tmp_path):
    (tmp_path / "perf_b.csv").write_text("", encoding="utf-8")
    (tmp_path / "lab_reserve_b.csv").write_text(
        ",".join(LAB) + "\nreal,0,30,10,8,2,1,100,unexpected\n",
        encoding="utf-8")
    app = run_page(tmp_path)
    assert any("thiếu cột" in w.value for w in app.warning)
    assert any("thừa ô" in w.value for w in app.warning)


def test_invalid_perf_isolated_from_lab_and_bad_rows_skipped(tmp_path):
    write_csv(tmp_path, "perf_b.csv", ["dataset", "seed"], [{"dataset": "bad", "seed": 0}])
    bad = lab_row(1, 30, change=8, move=2, over=1)
    bad["must_move"] = "nan"
    write_csv(tmp_path, "lab_reserve_b.csv", LAB, [lab_row(0, 0, change=8, move=2, over=1), bad])
    app = run_page(tmp_path)
    assert any("perf_b.csv" in w.value and "thiếu cột" in w.value for w in app.warning)
    assert any("lab_reserve_b.csv dòng 3" in w.value for w in app.warning)
    details = next(frame.value for frame in app.dataframe if "b_s4_weight" in frame.value.columns)
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


@pytest.mark.parametrize("field,value", [("b_s4_weight", "-1"), ("b_s4_weight", "x"),
                                          ("room_change_only", "nan"), ("slots_without_lab_reserve", "-1"),
                                          ("must_move", "5")])     # 8 + 5 ≠ 10 buổi máy
def test_invalid_lab_fields_warn_without_crashing(tmp_path, field, value):
    row = lab_row(0, 30, change=8, move=2, over=1)
    row[field] = value
    write_csv(tmp_path, "lab_reserve_b.csv", LAB, [row])
    app = run_page(tmp_path)
    assert any(field in w.value for w in app.warning)
    assert not app.dataframe
