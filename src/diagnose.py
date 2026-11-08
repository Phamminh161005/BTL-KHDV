"""Chẩn đoán khi solver trả về INFEASIBLE (model_spec A.8, data_schema mục 5, mã N01–N05).

Cách làm giống loại trừ: tạm bỏ từng nhóm ràng buộc cứng rồi thử tìm một lịch bất kỳ (không tối ưu). Nhóm nào
bỏ đi mà có lịch trở lại thì nhóm đó là nguyên nhân. Chẩn đoán luôn dùng CP-SAT, kể cả khi lần giải chính dùng
PuLP + CBC.
"""
from __future__ import annotations

import time

from src.instance import Instance, Message

# (nhóm, tên nhóm, gợi ý cách sửa dữ liệu)
GROUPS = [
    ("proctors", "phần giám thị (A-H7, A-H8, A-H10)",
     "không đủ giám thị rảnh để coi thi. Hãy thêm giảng viên coi thi (is_proctor = 1), giảm lịch bận của "
     "giảng viên, giảm proctors_per_room hoặc tắt forbid_own_course"),
    ("A-H2", "không trùng lịch sinh viên (A-H2)",
     "quá ít ca so với số môn mà một số sinh viên phải thi. Hãy thêm ca thi vào slots.csv"),
    ("A-H6", "lịch bận của phòng (A-H6)",
     "phòng bận quá nhiều ca. Hãy giảm lịch bận của phòng trong unavailability.csv hoặc thêm phòng"),
]
DEFAULT_TIME_LIMIT = 30


def _feasible(instance: Instance, config: dict, relax, seconds: float) -> str:
    """Trả về "yes", "no" hoặc "unknown" (hết giờ mà chưa kết luận)."""
    from src.exam_solver import solve
    cfg = dict(config, strategy="single", time_limit_sec=seconds)
    result = solve(instance, cfg, relax=frozenset(relax), optimize=False)
    if result.status in ("OPTIMAL", "FEASIBLE"):
        return "yes"
    return "no" if result.status == "INFEASIBLE" else "unknown"


def diagnose(instance: Instance, config: dict, time_limit: float | None = None) -> list[Message]:
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
                                    "Chẩn đoán: không nhóm nào riêng lẻ gây vô nghiệm, nhưng bỏ cả ba nhóm (giám thị, "
                                    "A-H2, A-H6) thì xếp được lịch. Nhiều nguyên nhân cùng lúc: hãy nới dữ liệu ở "
                                    "nhiều phía (thêm ca, thêm giám thị, giảm lịch bận của phòng)."))
        elif verdict == "no":
            messages.append(Message("N03", "warning",
                                    "Chẩn đoán: bỏ cả ba nhóm (giám thị, A-H2, A-H6) vẫn không xếp được lịch. Nguyên "
                                    "nhân nằm ở phòng và số lượt (A-H1, A-H3, A-H4, A-H5): không đủ phòng phù hợp "
                                    "hoặc không đủ ca để mở đủ số lượt cần thiết cho các môn. Hãy thêm ca, thêm phòng "
                                    "(nhất là phòng máy) hoặc tăng max_sittings."))
        else:
            messages.append(Message("N04", "info",
                                    f"Chẩn đoán: lần thử bỏ cả ba nhóm hết {seconds:g} giây mà chưa kết luận được."))
    messages.append(Message("N05", "info", f"Chẩn đoán xong trong {time.monotonic() - started:.1f} giây."))
    return messages
