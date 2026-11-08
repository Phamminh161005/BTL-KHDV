"""Đọc và kiểm tra file cấu hình (data_schema mục 6)."""
from __future__ import annotations

import copy
import json
from typing import Optional

from src.instance import Message

DEFAULT_CONFIG: dict = {
    "strategy": "single",
    "time_limit_sec": 300,
    "num_workers": 8,
    "random_seed": 0,
    "proctors_per_room": 2,
    "forbid_own_course": False,
    "written_capacity_ratio": 0.5,
    "default_max_sittings_computer": 3,
    "weights": {"A-S1": 100, "A-S2": 30, "A-S3": 50, "A-S4": 1, "A-S5": 20, "A-S6": 200},
    # Xếp lại khi có sự cố (model_spec A.14)
    "reschedule": {
        "time_limit_sec": 45,
        "weights": {"A-R1": 1000, "A-R2": 100, "A-R3": 50, "A-R4": 20},
    },
}


def _is_int(x) -> bool:
    return isinstance(x, int) and not isinstance(x, bool)


def _is_number(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool)


_VALIDATORS = {
    "strategy": lambda x: x in ("single", "two_phase"),
    "time_limit_sec": lambda x: _is_number(x) and x > 0,
    "num_workers": lambda x: _is_int(x) and x >= 1,
    "random_seed": lambda x: _is_int(x) and x >= 0,
    "proctors_per_room": lambda x: _is_int(x) and x >= 1,
    "forbid_own_course": lambda x: isinstance(x, bool),
    "written_capacity_ratio": lambda x: _is_number(x) and 0 < x <= 1,
    "default_max_sittings_computer": lambda x: _is_int(x) and x >= 1,
}


def load_config(path: Optional[str], messages: list[Message]) -> dict:
    """Trả về cấu hình đầy đủ (đã điền mặc định). Lỗi được ghi vào messages với mã D12."""
    cfg = copy.deepcopy(DEFAULT_CONFIG)
    if path is None:
        return cfg
    fname = "config.json"
    try:
        with open(path, encoding="utf-8-sig") as f:
            user = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        messages.append(Message("D12", "error", f"Không đọc được cấu hình: {e}", fname))
        return cfg
    if not isinstance(user, dict):
        messages.append(Message("D12", "error", "Cấu hình phải là một đối tượng JSON", fname))
        return cfg

    for key, value in user.items():
        if key not in DEFAULT_CONFIG:
            messages.append(Message("D12", "warning", f"Khóa cấu hình lạ '{key}', bị bỏ qua", fname))
        elif key == "weights":
            if not isinstance(value, dict):
                messages.append(Message("D12", "error", "'weights' phải là một đối tượng", fname))
                continue
            for wkey, wval in value.items():
                if wkey not in DEFAULT_CONFIG["weights"]:
                    messages.append(Message("D12", "warning", f"Trọng số lạ '{wkey}', bị bỏ qua", fname))
                elif not (_is_int(wval) and wval >= 0):
                    messages.append(Message("D12", "error", f"Trọng số {wkey} phải là số nguyên ≥ 0", fname))
                else:
                    cfg["weights"][wkey] = wval
        elif key == "reschedule":
            _load_reschedule(value, cfg["reschedule"], messages, fname)
        elif _VALIDATORS[key](value):
            cfg[key] = value
        else:
            messages.append(Message("D12", "error", f"Giá trị cấu hình '{key}' không hợp lệ: {value!r}", fname))
    return cfg


def _load_reschedule(value, target: dict, messages: list[Message], fname: str) -> None:
    """Khóa 'reschedule': {"time_limit_sec": số dương, "weights": {"A-R1".."A-R4": số nguyên ≥ 0}}."""
    if not isinstance(value, dict):
        messages.append(Message("D12", "error", "'reschedule' phải là một đối tượng", fname))
        return
    for key, val in value.items():
        if key == "time_limit_sec":
            if _is_number(val) and val > 0:
                target[key] = val
            else:
                messages.append(Message("D12", "error", f"reschedule.time_limit_sec không hợp lệ: {val!r}", fname))
        elif key == "weights" and isinstance(val, dict):
            for wkey, wval in val.items():
                if wkey not in target["weights"]:
                    messages.append(Message("D12", "warning", f"Trọng số xếp lại lạ '{wkey}', bị bỏ qua", fname))
                elif not (_is_int(wval) and wval >= 0):
                    messages.append(Message("D12", "error", f"Trọng số {wkey} phải là số nguyên ≥ 0", fname))
                else:
                    target["weights"][wkey] = wval
        elif key == "weights":
            messages.append(Message("D12", "error", "'reschedule.weights' phải là một đối tượng", fname))
        else:
            messages.append(Message("D12", "warning", f"Khóa cấu hình lạ 'reschedule.{key}', bị bỏ qua", fname))
