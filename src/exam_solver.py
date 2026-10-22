"""Solver bài toán A (lịch thi) bằng OR-Tools CP-SAT.

Người phụ trách: TV2 (task T2: strategy "single"; task T3: strategy "two_phase").

Việc cần làm: cài đặt đúng mô hình trong docs/model_spec.md.
- Biến quyết định: mục A.4. Chỉ tạo biến trên đúng miền chỉ số (ví dụ u chỉ với r thuộc R_c).
- Ràng buộc cứng: mục A.5. Đặt chú thích mã ràng buộc (A-H1, A-H2, ...) ngay trên khối code tương ứng.
- Hàm mục tiêu và trọng số: mục A.6, trọng số lấy từ config["weights"].
- Chiến lược giải và trạng thái: mục A.7.
- Có thể thu nhỏ mô hình theo mục A.11, miễn không làm thay đổi tập nghiệm.

Các hàm có sẵn trong src.instance.Instance nên dùng lại: rooms_for (R_c), start_slots (S_c), covered (Cov),
proctors (G), days (D), day_pairs (Q).

Cách kiểm tra:
- pytest tests/test_exam_solver.py: solver phải đạt OPTIMAL trên data/toy với đúng giá trị mục tiêu tham chiếu.
- py -3.12 -m src.run --data data/toy: validator trong file kết quả phải không báo vi phạm nào.
"""
from __future__ import annotations

from src.instance import Instance, SolveResult


def solve(instance: Instance, config: dict) -> SolveResult:
    """Giải bài toán A.

    Đầu vào:
        instance: dữ liệu đã qua data_loader (đã loại môn P2, phòng P9).
        config: cấu hình đầy đủ (src.config.DEFAULT_CONFIG đã điền), dùng các khóa strategy, time_limit_sec,
            num_workers, random_seed, proctors_per_room, forbid_own_course, weights.

    Đầu ra: SolveResult với
        status: "OPTIMAL", "FEASIBLE", "INFEASIBLE" hoặc "UNKNOWN" (A.7).
        objective, best_bound: giá trị mục tiêu và cận dưới (None nếu không có lời giải).
        penalties: {"A-S1": P_1, ..., "A-S6": P_6}, giá trị chưa nhân trọng số.
        solution: Solution gồm danh sách Sitting (mỗi lượt có x = 1) và proctoring
            {(room_id, slot): [lecturer_id, ...]} cho mọi cặp phòng-ca có w = 1.
            Với lượt 2 ca, proctoring phải có mặt ở cả hai ca, cùng danh sách giám thị.
        solve_time_sec: thời gian giải.
        solver_name: ví dụ "OR-Tools CP-SAT 9.15.6755".
        messages: thông báo thêm nếu có (ví dụ gợi ý nguyên nhân khi INFEASIBLE, A.8).
    """
    raise NotImplementedError("T2: cài đặt solver theo docs/model_spec.md")
