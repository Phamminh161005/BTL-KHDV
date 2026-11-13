"""Hồi quy từ rà soát logic src: lỗi đầu vào, validator và ngân sách CBC."""
import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from types import SimpleNamespace

import pytest

from src.config import load_config
from src.data_loader import load_instance
from src.data_loader_b import load_instance_b
from src.reschedule import base_solution, reschedule
from src.room_solver import solve
from src.validator import validate

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("key", ["time_limit_sec", "reschedule"])
@pytest.mark.parametrize("value", [float("inf"), float("-inf"), float("nan")])
def test_nonfinite_budget_rejected(tmp_path, key, value):
    cfg = {key: {"time_limit_sec": value} if key == "reschedule" else value}
    p = tmp_path / "config.json"
    p.write_text(json.dumps(cfg), encoding="utf-8")
    messages = []
    load_config(str(p), messages)
    assert any(m.code == "D12" and m.level == "error" for m in messages)


@pytest.mark.parametrize("budget", [float("inf"), float("nan"), -1])
def test_room_solver_rejects_invalid_budget(budget):
    loaded = load_instance_b(str(ROOT / "data/toy_b"))
    with pytest.raises(ValueError, match="time_limit_sec"):
        solve(loaded.instance, dict(loaded.config, time_limit_sec=budget))


def test_bool_weight_not_an_integer_weight():
    loaded = load_instance_b(str(ROOT / "data/toy_b"))
    loaded.config["weights"]["B-S1"] = True
    with pytest.raises(ValueError):
        solve(loaded.instance, loaded.config)


@pytest.mark.parametrize("bad", [None, [], 123, {"sittings": []}, {"sittings": {"unexpected": 1}}])
def test_bad_base_file_returns_input_error(tmp_path, bad):
    p = tmp_path / "old.json"
    p.write_text(json.dumps(bad), encoding="utf-8")
    result = reschedule(str(ROOT / "data/toy"), str(p), [], out_path=str(tmp_path / "out.json"))
    assert result["status"] == "INPUT_ERROR"
    assert any(m["code"] == "I03" for m in result["messages"])


@pytest.mark.parametrize("rooms", [None, [None], [{"room_id": "G2-101", "students": None}],
                                    [{"room_id": "G2-101", "proctors": "GV01"}]])
def test_bad_nested_base_shape_reports_i03(rooms):
    loaded = load_instance(str(ROOT / "data/toy"))
    base = {"sittings": [{"course_id": "INT2204", "date": "2026-12-14", "start_period": 1,
                          "rooms": rooms}]}
    messages = []
    assert base_solution(loaded.instance, base, messages) is None
    assert any(m.code == "I03" for m in messages)


@pytest.mark.parametrize("field,value", [("course_id", "UNKNOWN"), ("start_period", 5),
                                         ("date", "bad-date")])
def test_validator_reports_bad_placement_instead_of_crashing(field, value):
    loaded = load_instance(str(ROOT / "data/toy"))
    table = json.loads((ROOT / "tests/reference/toy_schedule.json").read_text(encoding="utf-8"))
    table["sittings"][0][field] = value
    violations = validate(loaded.instance, table, loaded.config)
    assert any(v["code"] == "A-H1" for v in violations)


def test_duplicate_sitting_id_is_invalid():
    loaded = load_instance(str(ROOT / "data/toy"))
    table = json.loads((ROOT / "tests/reference/toy_schedule.json").read_text(encoding="utf-8"))
    table["sittings"].append(copy.deepcopy(table["sittings"][0]))
    assert any(v["code"] == "A-H1" for v in validate(loaded.instance, table, loaded.config))


@pytest.mark.parametrize("problem,folder", [("A", "toy"), ("B", "toy_b")])
@pytest.mark.parametrize("corruption", ["invalid_utf8", "duplicate_header"])
def test_shared_csv_reader_reports_errors(tmp_path, problem, folder, corruption):
    data = tmp_path / "data"
    shutil.copytree(ROOT / "data" / folder, data)
    p = data / "rooms.csv"
    if corruption == "invalid_utf8":
        p.write_bytes(b'room_id,room_type\nBAD,\xff\n')
        code = "D03"
    else:
        p.write_text('room_id,room_type,seats,seats\nR,normal,60,30\n', encoding="utf-8")
        code = "D02"
    loaded = load_instance_b(str(data)) if problem == "B" else load_instance(str(data))
    assert not loaded.ok
    assert any(m.code == code for m in loaded.messages)


def test_csv_open_failure_reports_d01(tmp_path):
    data = tmp_path / "data"
    shutil.copytree(ROOT / "data/toy_b", data)
    (data / "rooms.csv").unlink()
    (data / "rooms.csv").mkdir()
    loaded = load_instance_b(str(data))
    assert not loaded.ok and any(m.code == "D01" for m in loaded.messages)


def test_config_encoding_error_reports_d12(tmp_path):
    p = tmp_path / "bad.json"
    p.write_bytes(b'{"problem":"\xff"}')
    messages = []
    load_config(str(p), messages)
    assert any(m.code == "D12" for m in messages)


def test_missing_explicit_cli_config_is_not_silently_ignored(tmp_path):
    proc = subprocess.run([sys.executable, "-m", "src.run", "--problem", "B", "--data", "data/toy_b",
                           "--config", str(tmp_path / "does-not-exist.json"), "--out", str(tmp_path / "out.json")],
                          cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=15)
    assert proc.returncode == 1
    table = json.loads((tmp_path / "out.json").read_text(encoding="utf-8"))
    assert table["status"] == "INPUT_ERROR"
    assert any(m["code"] == "D12" for m in table["messages"])


def test_cli_unsupported_b_solver_reports_error_without_traceback(tmp_path):
    proc = subprocess.run([sys.executable, "-m", "src.run", "--problem", "B", "--data", "data/toy_b",
                           "--solver", "pulp", "--out", str(tmp_path / "out.json")],
                          cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=15)
    assert proc.returncode == 2 and "Traceback" not in proc.stderr


def test_cbc_exhausted_build_budget_never_starts_search(monkeypatch):
    from src import exam_solver_pulp as mod
    # Ngủ 0,05 giây nhưng chỉ đòi đo được ≥ 0,02 giây: đồng hồ của Windows có độ phân giải khoảng 15,6 ms,
    # nên đòi đúng bằng thời gian ngủ thì test lúc qua lúc lỗi.
    def slow_build(*args):
        time.sleep(0.05)
        return SimpleNamespace()
    def forbidden(*args, **kwargs):
        pytest.fail("CBC không được bắt đầu sau khi dựng model đã hết giờ")
    monkeypatch.setattr(mod, "_Model", slow_build)
    monkeypatch.setattr(mod, "_solve_with_deadline", forbidden)
    result = mod.solve(None, {"strategy": "single", "time_limit_sec": 0.001})
    assert result.status == "UNKNOWN" and result.solution is None
    assert result.solve_time_sec >= 0.02


def test_cbc_receives_only_remaining_build_budget(monkeypatch):
    from src import exam_solver_pulp as mod
    # Đồng hồ giả: build tốn đúng 12 giây trong ngân sách 300 giây.
    clock = iter([100, 112, 112, 112])
    monkeypatch.setattr(mod.time, "monotonic", lambda: next(clock))
    monkeypatch.setattr(mod, "_Model", lambda *a: SimpleNamespace(prob=SimpleNamespace(sol_status=0)))
    captured = {}
    def run(prob, cbc, deadline):
        captured.update(time_limit=cbc.timeLimit, hard_limit=deadline)
        return False
    monkeypatch.setattr(mod, "_solve_with_deadline", run)
    result = mod.solve(None, {"strategy": "single", "time_limit_sec": 300, "random_seed": 0})
    assert result.status == "UNKNOWN"
    assert captured == {"time_limit": 288, "hard_limit": 348}
    assert result.solve_time_sec == 12


def test_a_generator_also_protects_toy_b(tmp_path):
    from src.generator import generate
    with pytest.raises(SystemExit):
        generate("medium", 1, str(tmp_path / "toy_b"))


@pytest.mark.parametrize("case", ["missing_config", "unsupported_solver"])
def test_cli_with_cp1252_output_environment(tmp_path, case):
    """Tái hiện tiến trình con bị Windows gán stdout/stderr CP1252."""
    args = [sys.executable, "-m", "src.run", "--problem", "B", "--data", "data/toy_b",
            "--out", str(tmp_path / "out.json")]
    if case == "missing_config":
        args += ["--config", str(tmp_path / "missing.json")]
        expected_code = 1
    else:
        args += ["--solver", "pulp"]
        expected_code = 2
    environment = dict(os.environ, PYTHONIOENCODING="cp1252", PYTHONUTF8="0")
    proc = subprocess.run(args, cwd=ROOT, env=environment, capture_output=True,
                          text=True, encoding="utf-8", timeout=15)
    assert proc.returncode == expected_code, proc.stderr
    assert "Traceback" not in proc.stderr
    assert "UnicodeEncodeError" not in proc.stderr
    assert ("D12" in proc.stdout if case == "missing_config" else "Không chạy được" in proc.stdout)
