"""Chẩn đoán khi bài toán B vô nghiệm (model_spec B.7, data_schema mục 9.10, mã N01–N05).

Cách làm giống bài A (src/diagnose.py): tạm bỏ từng nhóm ràng buộc cứng rồi thử tìm một lịch bất kỳ, không tối
ưu. Nhóm nào bỏ đi mà có lịch trở lại thì nhóm đó là nguyên nhân.
"""
from __future__ import annotations

import time

from src.instance import Message
from src.instance_b import InstanceB

# (nhóm, tên nhóm, gợi ý cách sửa dữ liệu), đúng bảng ở model_spec B.7
GROUPS = [
    ("B-H5", "giảng viên (B-H5, kể cả ca bận của giảng viên)",
     "giảng viên dạy quá nhiều lớp hoặc bận quá nhiều ca. Hãy chia bớt lớp cho giảng viên khác hoặc giảm ca bận "
     "trong week_unavailability.csv"),
    ("B-H7", "nhóm sinh viên (B-H7)",
     "một nhóm có quá nhiều buổi bắt buộc so với số ca, khi tính cả các ràng buộc khác. Hãy thêm ca vào "
     "week_slots.csv hoặc giảm số buổi của các lớp bắt buộc trong class_groups.csv"),
    ("B-H6", "lịch bận của phòng (B-H6)",
     "phòng bận quá nhiều ca. Hãy giảm ca bận của phòng trong week_unavailability.csv hoặc thêm phòng"),
]
DEFAULT_TIME_LIMIT = 30


def _feasible(instance: InstanceB, config: dict, relax, seconds: float) -> str:
    """Trả về "yes", "no" hoặc "unknown" (hết giờ mà chưa kết luận)."""
    from src.room_solver import solve
    cfg = dict(config, strategy="single", time_limit_sec=seconds)
    result = solve(instance, cfg, relax=frozenset(relax), optimize=False)
    if result.status in ("OPTIMAL", "FEASIBLE"):
        return "yes"
    return "no" if result.status == "INFEASIBLE" else "unknown"


def diagnose_b(instance: InstanceB, config: dict, time_limit: float | None = None) -> list[Message]:
    """Thử bỏ lần lượt từng nhóm ràng buộc và trả về các thông báo chẩn đoán.

    time_limit là giới hạn cho mỗi lần thử, mặc định min(30 giây, time_limit_sec của cấu hình).
    """
    seconds = time_limit if time_limit is not None else min(DEFAULT_TIME_LIMIT, float(config["time_limit_sec"]))
    started = time.monotonic()
    messages: list[Message] = []
    causes = []
    for group, label, hint in GROUPS:
        verdict = _feasible(instance, config, {group}, seconds)
        if verdict == "yes":
            causes.append(group)
            messages.append(Message("N01", "warning",
                                    f"Chẩn đoán: bỏ nhóm {label} thì xếp được lịch. Nguyên nhân có thể là {hint}."))
        elif verdict == "unknown":
            messages.append(Message("N04", "info",
                                    f"Chẩn đoán: lần thử bỏ nhóm {label} hết {seconds:g} giây mà chưa kết luận được."))
    if not causes and not any(m.code == "N04" for m in messages):
        verdict = _feasible(instance, config, {g for g, _, _ in GROUPS}, seconds)
        if verdict == "yes":
            messages.append(Message("N02", "warning",
                                    "Chẩn đoán: không nhóm nào riêng lẻ gây vô nghiệm, nhưng bỏ cả ba nhóm (giảng viên, "
                                    "nhóm sinh viên, phòng bận) thì xếp được lịch. Nhiều nguyên nhân cùng lúc: hãy nới "
                                    "dữ liệu ở nhiều phía (thêm ca, chia lại lớp cho giảng viên, giảm ca bận của phòng)."))
        elif verdict == "no":
            messages.append(Message("N03", "warning",
                                    "Chẩn đoán: bỏ cả ba nhóm (giảng viên, nhóm sinh viên, phòng bận) vẫn không xếp được "
                                    "lịch. Nguyên nhân nằm ở phòng (B-H1 đến B-H4): không đủ phòng đúng loại và đủ chỗ "
                                    "cho số buổi cần xếp. Hãy thêm phòng (nhất là phòng máy), thêm ca hoặc giảm số buổi."))
        else:
            messages.append(Message("N04", "info",
                                    f"Chẩn đoán: lần thử bỏ cả ba nhóm hết {seconds:g} giây mà chưa kết luận được."))
    messages.append(Message("N05", "info", f"Chẩn đoán xong trong {time.monotonic() - started:.1f} giây."))
    return messages
