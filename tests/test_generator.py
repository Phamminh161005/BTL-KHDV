"""Kiểm thử src/generator.py (task KHOE-1)."""
import filecmp
import os

import pytest

from src.data_loader import load_instance
from src.generator import generate, students_outside_range

ROOT = os.path.join(os.path.dirname(__file__), "..")
FILES = ["slots.csv", "rooms.csv", "courses.csv", "enrollments.csv", "lecturers.csv", "teaching.csv",
         "unavailability.csv"]
COMMITTED = {"toy": "toy_gen", "medium": "medium", "large": "large"}  # cỡ -> thư mục trong data/


@pytest.mark.parametrize("size", ["toy", "medium", "large"])
def test_generated_data_is_valid(tmp_path, size):
    stats = generate(size, 1, str(tmp_path / "out"))
    result = load_instance(str(tmp_path / "out"))
    assert result.ok
    assert [m.to_dict() for m in result.messages if m.level in ("error", "warning")] == []
    assert students_outside_range(result.instance) == []          # mỗi SV học 4–6 môn
    assert stats["computer_courses"] == stats["courses"] // 3     # khoảng 1/3 số môn thi máy
    assert stats["long_courses"] >= 1                             # có môn 150–180 phút


def test_same_seed_same_data(tmp_path):
    generate("medium", 7, str(tmp_path / "a"))
    generate("medium", 7, str(tmp_path / "b"))
    match, mismatch, errors = filecmp.cmpfiles(tmp_path / "a", tmp_path / "b", FILES, shallow=False)
    assert mismatch == [] and errors == []


def test_different_seed_different_data(tmp_path):
    generate("medium", 1, str(tmp_path / "a"))
    generate("medium", 2, str(tmp_path / "b"))
    assert not filecmp.cmp(tmp_path / "a" / "enrollments.csv", tmp_path / "b" / "enrollments.csv", shallow=False)


@pytest.mark.parametrize("size,folder", COMMITTED.items())
def test_committed_data_matches_generator(tmp_path, size, folder):
    """Dữ liệu trong data/ phải đúng là kết quả của generator với seed 1; sửa generator thì phải sinh lại."""
    generate(size, 1, str(tmp_path / "out"))
    match, mismatch, errors = filecmp.cmpfiles(tmp_path / "out", os.path.join(ROOT, "data", folder), FILES,
                                               shallow=False)
    assert mismatch == [] and errors == [], (
        f"data/{folder} lệch với generator: chạy lại "
        f"python -m src.generator --size {size} --seed 1 --out data/{folder}")


def test_refuses_to_overwrite_reference_toy(tmp_path):
    with pytest.raises(SystemExit):
        generate("toy", 1, str(tmp_path / "toy"))
