"""Sinh dữ liệu giả lập cho bài toán A theo docs/data_schema.md.

Người phụ trách: Khỏe (task KHOE-1).

Cách chạy dự kiến:
    py -3.12 -m src.generator --size medium --seed 1 --out data/medium

Yêu cầu (chi tiết trong mô tả task KHOE-1 trên CoReach):
- Quy mô theo docs/scope.md mục 3: toy (5 môn, 3 phòng, ~50 SV), medium (30 môn, 10 phòng, ~500 SV),
  large (60 môn, 15 phòng, ~1.000 SV).
- Dữ liệu giống thực tế: mỗi SV học 4–6 môn; SV chia theo khóa/ngành, SV cùng khóa học nhiều môn giống nhau;
  khoảng 1/3 số môn thi máy; thời lượng chủ yếu 60/90/120 phút, vài môn 150–180 phút; mỗi môn 1–2 giảng viên;
  khoảng 10% ca bận của phòng và giảng viên; có 1 ca nghỉ lễ.
- Cùng seed thì sinh ra đúng cùng một bộ dữ liệu.
- Ghi đủ các file: slots, rooms, courses, enrollments, lecturers, teaching, unavailability.

Hoàn thành khi: cả ba bộ dữ liệu qua src.data_loader.load_instance mà không có thông báo mức "error".
Lưu ý: data/toy hiện có là bộ dữ liệu tham chiếu viết tay, dùng cho kiểm thử; không ghi đè lên nó.
"""
from __future__ import annotations

import argparse


def generate(size: str, seed: int, out_dir: str) -> None:
    """Sinh một bộ dữ liệu cỡ size ("toy", "medium", "large") vào thư mục out_dir."""
    raise NotImplementedError("KHOE-1: cài đặt script sinh dữ liệu")


def main() -> None:
    parser = argparse.ArgumentParser(description="Sinh dữ liệu giả lập cho bài toán lịch thi")
    parser.add_argument("--size", choices=["toy", "medium", "large"], required=True)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    generate(args.size, args.seed, args.out)


if __name__ == "__main__":
    main()
