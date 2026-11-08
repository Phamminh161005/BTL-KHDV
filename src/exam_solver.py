"""Giải bài toán A (lịch thi) bằng OR-Tools CP-SAT, single hoặc two_phase.

Triển khai các biến, ràng buộc và hàm mục tiêu tại docs/model_spec.md A.4–A.6.
Chỉ trích xuất lịch thô , chia sinh viên vào từng phòng và đánh giá KPI thuộc
src.schedule, src.validator, src.kpi.
"""

from __future__ import annotations

from collections import defaultdict
import time
from importlib.metadata import PackageNotFoundError, version

from ortools.sat.python import cp_model

from src.instance import Instance, Message, Sitting, Solution, SolveResult


def solve(instance: Instance, config: dict) -> SolveResult:
    if config["strategy"] == "two_phase":
        return _solve_two_phase(instance, config)
    if config["strategy"] != "single":
        raise ValueError(f"Chiến lược không hỗ trợ: {config['strategy']}")

    model = cp_model.CpModel()
    courses = instance.courses
    rooms = instance.rooms
    proctors = instance.proctors
    slots = instance.slots
    days = instance.days
    nu = config["proctors_per_room"]
    students_by_course = {c: sorted(course.students) for c, course in courses.items()}
    student_courses: dict[str, list[str]] = defaultdict(list)
    for c, ids in students_by_course.items():
        for i in ids:
            student_courses[i].append(c)
    for cs in student_courses.values():
        cs.sort()

    start = {c: instance.start_slots(c) for c in courses}
    suitable = {c: instance.rooms_for(c) for c in courses}
    cov = {(c, s): tuple(instance.covered(c, s)) for c in courses for s in start[c]}

    # A.4: x_(c,s), u_(c,r,s), q_(i,c,s), w_(g,r,t).
    # A-H5: miền r thuộc R_c tự bảo đảm đúng loại phòng.
    x = {
        (c, s): model.NewBoolVar(f"x_{c}_{s[0]}_{s[1]}")
        for c in courses
        for s in start[c]
    }
    u = {}
    # A-H6: không tạo u cho lượt có ca giao với lịch bận của phòng.
    for c in courses:
        for r in suitable[c]:
            busy = rooms[r].busy
            for s in start[c]:
                if all(t not in busy for t in cov[c, s]):
                    u[c, r, s] = model.NewBoolVar(f"u_{c}_{r}_{s[0]}_{s[1]}")
    q = {
        (i, c, s): model.NewBoolVar(f"q_{i}_{c}_{s[0]}_{s[1]}")
        for c, course in courses.items()
        if course.splittable
        for i in students_by_course[c]
        for s in start[c]
    }
    # A-H8: ca giảng viên bận không có biến w.
    w = {
        (g, r, t): model.NewBoolVar(f"w_{g}_{r}_{t[0]}_{t[1]}")
        for g in proctors
        for r in rooms
        for t in slots
        if t not in proctors[g].busy
    }

    starts_covering: dict[tuple[str, tuple], list] = defaultdict(list)
    for c in courses:
        for s in start[c]:
            for t in cov[c, s]:
                starts_covering[c, t].append(s)

    room_use: dict[tuple[str, tuple], list] = defaultdict(list)
    for (c, r, s), var in u.items():
        for t in cov[c, s]:
            room_use[r, t].append(var)

    # A-H1: mỗi môn mở từ một đến L_c lượt.
    for c, course in courses.items():
        model.Add(sum(x[c, s] for s in start[c]) >= 1)
        model.Add(sum(x[c, s] for s in start[c]) <= course.max_sittings)

    # A-H9: sinh viên thuộc môn chia lượt thi đúng một lần; không mở lượt rỗng.
    for c, course in courses.items():
        if not course.splittable:
            continue
        for i in students_by_course[c]:
            model.Add(sum(q[i, c, s] for s in start[c]) == 1)
            for s in start[c]:
                model.Add(q[i, c, s] <= x[c, s])
        for s in start[c]:
            model.Add(x[c, s] <= sum(q[i, c, s] for i in students_by_course[c]))

    def participation(i: str, c: str, s):
        return q[i, c, s] if courses[c].splittable else x[c, s]

    def sitting_size(c: str, s):
        if courses[c].splittable:
            return sum(q[i, c, s] for i in students_by_course[c])
        return len(students_by_course[c]) * x[c, s]

    # A-H2: một sinh viên không thi hai môn trùng ca; gộp nhóm ràng buộc giống nhau.
    # Gộp theo danh sách môn chỉ khi tất cả đều không chia lượt (A.11).
    seen_unsplit: set[tuple[str, ...]] = set()
    for i, cs in student_courses.items():
        if all(not courses[c].splittable for c in cs):
            key = tuple(cs)
            if key in seen_unsplit:
                continue
            seen_unsplit.add(key)
        for t in slots:
            terms = [
                participation(i, c, s)
                for c in cs
                for s in starts_covering.get((c, t), ())
            ]
            if len(terms) > 1:
                model.Add(sum(terms) <= 1)

    # A-H3: phòng giữ cho lượt phải đủ sức chứa; u <= x.
    for c in courses:
        for s in start[c]:
            assigned = [(r, u[c, r, s]) for r in suitable[c] if (c, r, s) in u]
            model.Add(
                sitting_size(c, s)
                <= sum(rooms[r].exam_capacity * v for r, v in assigned)
            )
            for _, v in assigned:
                model.Add(v <= x[c, s])

    # A-H4: mỗi phòng trong mỗi ca chỉ dùng tối đa một lượt.
    for r in rooms:
        for t in slots:
            model.Add(sum(room_use[r, t]) <= 1)

    # A-H7: phòng có lượt thi phải có đúng nu giám thị ở mọi ca.
    for r in rooms:
        for t in slots:
            model.Add(
                sum(w[g, r, t] for g in proctors if (g, r, t) in w)
                == nu * sum(room_use[r, t])
            )

    # A-H7: lượt hai ca phải giữ nguyên giám thị ở cả hai ca.
    # Khi có lượt hai ca bắt đầu tại s: |w_(g,r,s) - w_(g,r,s+)| = 0.
    for r in rooms:
        for s in slots:
            if s[1] not in (1, 3):
                continue
            nxt = (s[0], s[1] + 1)
            if nxt not in slots:
                continue
            long_starts = [
                u[c, r, s]
                for c in courses
                if courses[c].num_periods == 2 and (c, r, s) in u
            ]
            if not long_starts:
                continue
            active_long = sum(long_starts)
            for g in proctors:
                before = w.get((g, r, s), 0)
                after = w.get((g, r, nxt), 0)
                model.Add(before - after <= 1 - active_long)
                model.Add(after - before <= 1 - active_long)

    # A-H8: giám thị không coi nhiều phòng trong cùng ca; ca bận đã bỏ biến.
    for g in proctors:
        for t in slots:
            model.Add(sum(w[g, r, t] for r in rooms if (g, r, t) in w) <= 1)

    # A-H10 (tùy chọn): giảng viên không được coi môn mình đang dạy.
    if config["forbid_own_course"]:
        for g, lecturer in proctors.items():
            taught = lecturer.teaches & courses.keys()
            if not taught:
                continue
            for r in rooms:
                for t in slots:
                    own_room = [
                        v
                        for c in taught
                        for s in starts_covering.get((c, t), ())
                        if (v := u.get((c, r, s))) is not None
                    ]
                    if own_room:
                        model.Add(w.get((g, r, t), 0) + sum(own_room) <= 1)

    # A.5 bổ trợ: số phòng dùng <= số giám thị rảnh / nu tại từng ca.
    for t in slots:
        available = sum(t not in proctors[g].busy for g in proctors)
        model.Add(sum(v for r in rooms for v in room_use[r, t]) <= available // nu)

    # A-S1, A-S2: số lượt bắt đầu theo sinh viên/ngày E_(i,d).
    starts_by_day = {
        d: {c: [s for s in start[c] if s[0] == d] for c in courses} for d in days
    }
    exams_per_day = {
        (i, d): sum(participation(i, c, s) for c in cs for s in starts_by_day[d][c])
        for i, cs in student_courses.items()
        for d in days
    }
    # A-S1, A-S2, A-S5 viết bằng bất đẳng thức một chiều đúng như model_spec A.6, không dùng
    # AddMaxEquality/AddMinEquality: vì mục tiêu là cực tiểu, tại nghiệm tối ưu các biến phụ tự nhận đúng giá
    # trị max/min; dạng "bằng chính xác" làm mô hình khó chứng minh tối ưu hơn nhiều (toy: không chứng minh
    # được trong 300 giây, so với khoảng 20 giây ở dạng bất đẳng thức).
    p1_terms = []
    # A-S1: a_(i,d) >= E_(i,d) - 1, a >= 0.
    for i, cs in student_courses.items():
        for d in days:
            a = model.NewIntVar(0, max(len(cs) - 1, 0), f"a_{i}_{d}")
            model.Add(a >= exams_per_day[i, d] - 1)
            p1_terms.append(a)
    p1 = sum(p1_terms)

    # A-S2: b_(i,d) >= E_(i,d) + E_(i,d') - 1, b >= 0.
    p2_terms = []
    for i, cs in student_courses.items():
        for d, d2 in instance.day_pairs:
            b = model.NewIntVar(0, max(len(cs) - 1, 0), f"b_{i}_{d}_{d2}")
            model.Add(b >= exams_per_day[i, d] + exams_per_day[i, d2] - 1)
            p2_terms.append(b)
    p2 = sum(p2_terms)

    # A-S3: số phòng thêm so với phòng đầu tiên của mỗi lượt.
    p3 = sum(u.values()) - sum(x.values())

    # A-S4: tổng chỗ trống * số ca bị chiếm.
    p4 = sum(
        courses[c].num_periods * rooms[r].exam_capacity * var
        for (c, r, s), var in u.items()
    ) - sum(
        courses[c].num_periods * sitting_size(c, s) for c in courses for s in start[c]
    )

    # A-S5: chênh lệch giữa tải coi thi lớn nhất và nhỏ nhất.
    loads = []
    for g in proctors:
        load = model.NewIntVar(0, len(slots), f"load_{g}")
        model.Add(load == sum(var for (gg, r, t), var in w.items() if gg == g))
        loads.append(load)
    max_load = model.NewIntVar(0, len(slots), "max_proctor_load")
    min_load = model.NewIntVar(0, len(slots), "min_proctor_load")
    # A-S5: Lambda_max >= lambda_g, Lambda_min <= lambda_g với mọi giám thị g.
    for load in loads:
        model.Add(max_load >= load)
        model.Add(min_load <= load)
    p5 = max_load - min_load

    # A-S6: số lượt thi vượt mức một lượt cho mỗi môn.
    p6 = sum(x.values()) - len(courses)

    penalties_expr = {
        "A-S1": p1,
        "A-S2": p2,
        "A-S3": p3,
        "A-S4": p4,
        "A-S5": p5,
        "A-S6": p6,
    }
    # A.6: cực tiểu tổng điểm phạt có trọng số, cấu hình có thể tắt trọng số.
    model.Minimize(
        sum(config["weights"][name] * expr for name, expr in penalties_expr.items())
    )

    solver = cp_model.CpSolver()
    solver.parameters.log_search_progress = False
    solver.parameters.max_time_in_seconds = float(config["time_limit_sec"])
    solver.parameters.num_search_workers = int(config["num_workers"])
    solver.parameters.random_seed = int(config["random_seed"])
    result_status = solver.Solve(model)
    try:
        solver_name = f"OR-Tools CP-SAT {version('ortools')}"
    except PackageNotFoundError:
        solver_name = "OR-Tools CP-SAT"
    statuses = {
        cp_model.OPTIMAL: "OPTIMAL",
        cp_model.FEASIBLE: "FEASIBLE",
        cp_model.INFEASIBLE: "INFEASIBLE",
        cp_model.UNKNOWN: "UNKNOWN",
    }
    status = statuses.get(result_status, "UNKNOWN")
    kwargs = dict(
        status=status, solve_time_sec=solver.WallTime(), solver_name=solver_name
    )
    if result_status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return SolveResult(**kwargs)

    sittings = []
    for c in sorted(courses):
        for s in start[c]:
            if solver.Value(x[c, s]) == 0:
                continue
            used_rooms = [
                r for r in suitable[c] if (c, r, s) in u and solver.Value(u[c, r, s])
            ]
            assigned = (
                [i for i in students_by_course[c] if solver.Value(q[i, c, s])]
                if courses[c].splittable
                else students_by_course[c]
            )
            sittings.append(Sitting(c, s, used_rooms, assigned))
    sittings.sort(key=lambda item: (item.start, item.course_id))
    proctoring: dict = {}
    for (g, r, t), var in w.items():
        if solver.Value(var):
            proctoring.setdefault((r, t), []).append(g)
    for gs in proctoring.values():
        gs.sort()

    # Điểm phạt tính lại chính xác từ lời giải. Với lời giải FEASIBLE (hết giờ), các biến phụ a, b, max_load,
    # min_load chỉ bị chặn một phía nên có thể chưa về đúng max/min; đọc thẳng giá trị của chúng sẽ báo điểm
    # phạt cao hơn thực tế. P_3, P_4, P_6 không có biến phụ nên đọc thẳng là chính xác.
    exact_p1 = sum(
        max(0, solver.Value(exams_per_day[i, d]) - 1)
        for i in student_courses
        for d in days
    )
    exact_p2 = sum(
        max(
            0,
            solver.Value(exams_per_day[i, d]) + solver.Value(exams_per_day[i, d2]) - 1,
        )
        for i in student_courses
        for d, d2 in instance.day_pairs
    )
    load_values = [solver.Value(load) for load in loads]
    exact_p5 = max(load_values) - min(load_values) if load_values else 0
    penalties = {
        "A-S1": exact_p1,
        "A-S2": exact_p2,
        "A-S3": int(solver.Value(p3)),
        "A-S4": int(solver.Value(p4)),
        "A-S5": exact_p5,
        "A-S6": int(solver.Value(p6)),
    }
    return SolveResult(
        **kwargs,
        objective=sum(
            config["weights"][name] * value for name, value in penalties.items()
        ),
        best_bound=solver.BestObjectiveBound(),
        penalties=penalties,
        solution=Solution(sittings, proctoring),
    )


def _solve_two_phase(instance: Instance, config: dict) -> SolveResult:
    """Giải A.7: pha 1 xếp lịch/phòng/SV, pha 2 cố định lịch và phân giám thị.

    Giữ nguyên solver single ở trên. Cận dưới pha 1 hợp lệ cho toàn bài toán
    vì đã bỏ A-S5 (không âm, trọng số không âm) và nới lỏng A-H7/H8/H10.
    """
    started_at = time.monotonic()
    budget = float(config["time_limit_sec"])
    nu = int(config["proctors_per_room"])
    weights = config["weights"]
    courses, rooms, slots = instance.courses, instance.rooms, instance.slots
    proctors = instance.proctors
    days = instance.days

    try:
        solver_name = f"OR-Tools CP-SAT {version('ortools')} (two_phase)"
    except PackageNotFoundError:
        solver_name = "OR-Tools CP-SAT (two_phase)"
    messages: list[Message] = []

    def elapsed() -> float:
        return time.monotonic() - started_at

    def remaining() -> float:
        return max(0.0, budget - elapsed())

    def configure(solver: cp_model.CpSolver, seconds: float) -> None:
        solver.parameters.log_search_progress = False
        solver.parameters.max_time_in_seconds = max(0.001, float(seconds))
        solver.parameters.num_search_workers = int(config["num_workers"])
        solver.parameters.random_seed = int(config["random_seed"])

    statuses = {
        cp_model.OPTIMAL: "OPTIMAL",
        cp_model.FEASIBLE: "FEASIBLE",
        cp_model.INFEASIBLE: "INFEASIBLE",
        cp_model.UNKNOWN: "UNKNOWN",
    }

    # ---------------- PHA 1: mô hình x, u, q (A.7) ----------------
    model = cp_model.CpModel()
    students_by_course = {c: sorted(course.students) for c, course in courses.items()}
    student_courses: dict[str, list[str]] = defaultdict(list)
    for c, students in students_by_course.items():
        for i in students:
            student_courses[i].append(c)
    for cs in student_courses.values():
        cs.sort()

    start = {c: instance.start_slots(c) for c in courses}
    suitable = {c: instance.rooms_for(c) for c in courses}
    cov = {(c, s): tuple(instance.covered(c, s)) for c in courses for s in start[c]}

    # A.4, A-H5: chỉ tạo x_(c,s), u_(c,r,s), q_(i,c,s) đúng miền;
    # KHÔNG tạo w ở pha 1. Miền của u đảm bảo đúng loại phòng.
    x = {
        (c, s): model.NewBoolVar(f"x_{c}_{s[0]}_{s[1]}")
        for c in courses
        for s in start[c]
    }
    u = {}
    # A-H6: lược bỏ u nếu phòng bận ở bất kỳ ca nào của lượt thi.
    for c in courses:
        for r in suitable[c]:
            for s in start[c]:
                if all(t not in rooms[r].busy for t in cov[c, s]):
                    u[c, r, s] = model.NewBoolVar(f"u_{c}_{r}_{s[0]}_{s[1]}")
    q = {
        (i, c, s): model.NewBoolVar(f"q_{i}_{c}_{s[0]}_{s[1]}")
        for c, course in courses.items()
        if course.splittable
        for i in students_by_course[c]
        for s in start[c]
    }

    starts_covering = defaultdict(list)
    for c in courses:
        for s in start[c]:
            for t in cov[c, s]:
                starts_covering[c, t].append(s)
    room_use = defaultdict(list)
    for (c, r, s), var in u.items():
        for t in cov[c, s]:
            room_use[r, t].append(var)

    # A-H1: mỗi môn được mở từ một đến L_c lượt.
    for c, course in courses.items():
        model.Add(sum(x[c, s] for s in start[c]) >= 1)
        model.Add(sum(x[c, s] for s in start[c]) <= course.max_sittings)

    # A-H9: mỗi SV thi đúng một lượt của môn chia lượt; không có lượt rỗng.
    for c, course in courses.items():
        if not course.splittable:
            continue
        for i in students_by_course[c]:
            model.Add(sum(q[i, c, s] for s in start[c]) == 1)
            for s in start[c]:
                model.Add(q[i, c, s] <= x[c, s])
        for s in start[c]:
            model.Add(x[c, s] <= sum(q[i, c, s] for i in students_by_course[c]))

    def participates(i: str, c: str, s):
        return q[i, c, s] if courses[c].splittable else x[c, s]

    def sitting_size(c: str, s):
        if courses[c].splittable:
            return sum(q[i, c, s] for i in students_by_course[c])
        return len(students_by_course[c]) * x[c, s]

    # A-H2, A.11: SV không thi hai lượt cùng ca; gộp ràng buộc trùng nhau
    # cho các SV có cùng bộ môn và toàn bộ các môn đó không chia lượt.
    seen_unsplit: set[tuple[str, ...]] = set()
    for i, cs in student_courses.items():
        if all(not courses[c].splittable for c in cs):
            key = tuple(cs)
            if key in seen_unsplit:
                continue
            seen_unsplit.add(key)
        for t in slots:
            terms = [
                participates(i, c, s)
                for c in cs
                for s in starts_covering.get((c, t), ())
            ]
            if len(terms) > 1:
                model.Add(sum(terms) <= 1)

    # A-H3: đủ sức chứa của lượt và u_(c,r,s) <= x_(c,s).
    for c in courses:
        for s in start[c]:
            selected = [(r, u[c, r, s]) for r in suitable[c] if (c, r, s) in u]
            model.Add(
                sitting_size(c, s)
                <= sum(rooms[r].exam_capacity * var for r, var in selected)
            )
            for _, var in selected:
                model.Add(var <= x[c, s])

    # A-H4: một phòng tối đa một lượt ở mỗi ca, kể cả lượt chiếm hai ca.
    for r in rooms:
        for t in slots:
            model.Add(sum(room_use[r, t]) <= 1)

    # A.5 bổ trợ: số phòng sử dụng <= số giám thị rảnh chia nu.
    # CẦN GIỮ ở pha 1 dù chưa có w (A-H7/H8/H10 được dời sang pha 2).
    for t in slots:
        available = sum(t not in proctors[g].busy for g in proctors)
        model.Add(sum(var for r in rooms for var in room_use[r, t]) <= available // nu)

    # A-S1, A-S2: số lượt mỗi SV bắt đầu trong ngày (lượt hai ca tính một lần).
    starts_by_day = {
        d: {c: [s for s in start[c] if s[0] == d] for c in courses} for d in days
    }
    exams_per_day = {
        (i, d): sum(participates(i, c, s) for c in cs for s in starts_by_day[d][c])
        for i, cs in student_courses.items()
        for d in days
    }

    # A-S1: a_(i,d) >= E_(i,d) - 1, a >= 0 (bất đẳng thức như single trên main).
    a_terms = []
    for i, cs in student_courses.items():
        for d in days:
            a = model.NewIntVar(0, max(len(cs) - 1, 0), f"a_{i}_{d}")
            model.Add(a >= exams_per_day[i, d] - 1)
            a_terms.append(a)
    p1 = sum(a_terms)

    # A-S2: b_(i,d) >= E_(i,d) + E_(i,d') - 1, b >= 0.
    b_terms = []
    for i, cs in student_courses.items():
        for d, d2 in instance.day_pairs:
            b = model.NewIntVar(0, max(len(cs) - 1, 0), f"b_{i}_{d}_{d2}")
            model.Add(b >= exams_per_day[i, d] + exams_per_day[i, d2] - 1)
            b_terms.append(b)
    p2 = sum(b_terms)

    # A-S3: số phòng phụ trội (mỗi lượt trừ một phòng).
    p3 = sum(u.values()) - sum(x.values())

    # A-S4: số ghế trống nhân số ca mỗi lượt chiếm.
    p4 = sum(
        courses[c].num_periods * rooms[r].exam_capacity * var
        for (c, r, s), var in u.items()
    ) - sum(
        courses[c].num_periods * sitting_size(c, s) for c in courses for s in start[c]
    )

    # A-S6: số lượt thi vượt số môn.
    p6 = sum(x.values()) - len(courses)

    # A.6/A.7: mục tiêu pha 1 giữ A-S1,2,3,4,6 và BỎ A-S5.
    model.Minimize(
        weights["A-S1"] * p1
        + weights["A-S2"] * p2
        + weights["A-S3"] * p3
        + weights["A-S4"] * p4
        + weights["A-S6"] * p6
    )

    phase1 = cp_model.CpSolver()
    # A.7: tối đa 80% tổng budget cho pha 1 (bao gồm thời gian dựng mô hình).
    phase1_seconds = min(max(0.0, 0.8 * budget - elapsed()), remaining())
    if phase1_seconds <= 0:
        return SolveResult(
            "UNKNOWN",
            elapsed(),
            solver_name=solver_name,
            messages=[
                Message("K3-TIME", "warning", "Hết thời gian khi tạo mô hình pha 1")
            ],
        )
    configure(phase1, phase1_seconds)
    status1 = phase1.Solve(model)
    if status1 not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return SolveResult(
            statuses.get(status1, "UNKNOWN"),
            elapsed(),
            solver_name=solver_name,
            messages=messages,
        )
    # Phần mục tiêu pha 1 là nới lỏng của mục tiêu đầy đủ => cận dưới hợp lệ.
    phase1_bound = float(phase1.BestObjectiveBound())

    # A.7: cố định x, u, q bằng nghiệm pha 1; mỗi lượt đã chọn giữ phòng/SV cố định.
    sittings = []
    active: dict[tuple[str, tuple], str] = {}  # (phòng, ca) -> môn đang thi
    long_pairs: set[tuple[str, tuple, tuple]] = set()
    for c in sorted(courses):
        for s in start[c]:
            if not phase1.Value(x[c, s]):
                continue
            selected_rooms = [
                r for r in suitable[c] if (c, r, s) in u and phase1.Value(u[c, r, s])
            ]
            selected_students = (
                [i for i in students_by_course[c] if phase1.Value(q[i, c, s])]
                if courses[c].splittable
                else students_by_course[c]
            )
            sittings.append(Sitting(c, s, selected_rooms, selected_students))
            for r in selected_rooms:
                for t in cov[c, s]:
                    active[r, t] = c
                if courses[c].num_periods == 2:
                    long_pairs.add((r, s, cov[c, s][1]))
    sittings.sort(key=lambda sitting: (sitting.start, sitting.course_id))

    # ---------------- PHA 2: chỉ biến w, A-H7/H8/H10/A-S5 ----------------
    phase2_model = cp_model.CpModel()
    # A.4/A-H8: w chỉ tồn tại cho phòng-ca đang dùng và giám thị không bận.
    # A-H10: nếu bật forbid_own_course, loại luôn giám thị dạy môn đó.
    w = {}
    for (r, t), c in sorted(active.items()):
        for g, lecturer in proctors.items():
            if t in lecturer.busy:
                continue
            if config["forbid_own_course"] and c in lecturer.teaches:
                continue
            w[g, r, t] = phase2_model.NewBoolVar(f"w_{g}_{r}_{t[0]}_{t[1]}")

    # A-H7: mỗi phòng-ca đang dùng có đúng nu giám thị.
    for r, t in active:
        phase2_model.Add(sum(w[g, r, t] for g in proctors if (g, r, t) in w) == nu)

    # A-H7: lượt hai ca sử dụng đúng cùng danh sách giám thị tại cả hai ca.
    for r, s, nxt in sorted(long_pairs):
        for g in proctors:
            phase2_model.Add(w.get((g, r, s), 0) == w.get((g, r, nxt), 0))

    # A-H8: một giám thị không coi hai phòng cùng một ca; ca bận đã loại ở miền.
    for g in proctors:
        for t in slots:
            phase2_model.Add(sum(w[g, r, t] for r in rooms if (g, r, t) in w) <= 1)

    # A-S5: cân bằng số ca coi thi giữa giám thị, dạng bất đẳng thức như single.
    loads = []
    for g in proctors:
        load = phase2_model.NewIntVar(0, len(slots), f"load_{g}")
        phase2_model.Add(load == sum(var for (gg, r, t), var in w.items() if gg == g))
        loads.append(load)
    max_load = phase2_model.NewIntVar(0, len(slots), "max_proctor_load")
    min_load = phase2_model.NewIntVar(0, len(slots), "min_proctor_load")
    for load in loads:
        phase2_model.Add(max_load >= load)
        phase2_model.Add(min_load <= load)
    phase2_model.Minimize(weights["A-S5"] * (max_load - min_load))

    phase2 = cp_model.CpSolver()
    # A.7: pha 2 nhận toàn bộ thời gian còn lại (bao gồm phần pha 1 tiết kiệm).
    if remaining() <= 0:
        return SolveResult(
            "UNKNOWN",
            elapsed(),
            best_bound=phase1_bound,
            solver_name=solver_name,
            messages=[
                Message(
                    "K3-TIME", "warning", "Hết thời gian trước khi phân giám thị pha 2"
                )
            ],
        )
    configure(phase2, remaining())
    status2 = phase2.Solve(phase2_model)
    if status2 not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        reason = statuses.get(status2, "UNKNOWN")
        messages.append(
            Message(
                "K3-FALLBACK",
                "warning",
                f"Pha 2 {reason}; thử giải lại bằng single với thời gian còn lại",
            )
        )
        # A.7: nếu phân giám thị vô nghiệm trên lịch pha 1, chưa thể suy ra
        # toàn bài toán vô nghiệm, vì pha 1 chưa xét lịch bận theo từng giám thị.
        if remaining() > 0.05:
            fallback_cfg = dict(config, strategy="single", time_limit_sec=remaining())
            fallback = solve(instance, fallback_cfg)
            fallback.solve_time_sec = elapsed()
            fallback.messages = messages + fallback.messages
            return fallback
        messages.append(
            Message(
                "K3-TIME", "warning", "Không còn thời gian để chạy single sau pha 2"
            )
        )
        return SolveResult(
            "UNKNOWN",
            elapsed(),
            best_bound=phase1_bound,
            solver_name=solver_name,
            messages=messages,
        )

    proctoring: dict = {}
    for (g, r, t), var in w.items():
        if phase2.Value(var):
            proctoring.setdefault((r, t), []).append(g)
    for gs in proctoring.values():
        gs.sort()

    # A.6: tính lại CHÍNH XÁC sáu điểm phạt từ nghiệm x, u, q và w.
    # Không lấy thẳng a/b/max_load/min_load vì các biến phụ chỉ bị chặn một phía;
    # khi solver dừng ở FEASIBLE, chúng có thể chưa bằng giá trị phạt thực tế.
    exact_p1 = sum(
        max(0, phase1.Value(exams_per_day[i, d]) - 1)
        for i in student_courses
        for d in days
    )
    exact_p2 = sum(
        max(
            0,
            phase1.Value(exams_per_day[i, d]) + phase1.Value(exams_per_day[i, d2]) - 1,
        )
        for i in student_courses
        for d, d2 in instance.day_pairs
    )
    load_values = [phase2.Value(load) for load in loads]
    penalties = {
        "A-S1": int(exact_p1),
        "A-S2": int(exact_p2),
        "A-S3": int(phase1.Value(p3)),
        "A-S4": int(phase1.Value(p4)),
        "A-S5": max(load_values) - min(load_values) if load_values else 0,
        "A-S6": int(phase1.Value(p6)),
    }
    objective = sum(weights[name] * value for name, value in penalties.items())
    messages.append(
        Message(
            "K3-INFO",
            "info",
            f"Hai pha: pha 1 {statuses[status1]}, pha 2 {statuses[status2]}; "
            f"thời gian tổng {elapsed():.2f}s",
        )
    )
    # Dù hai pha đều OPTIMAL riêng lẻ cũng chưa chứng minh tối ưu toàn cục.
    return SolveResult(
        status="FEASIBLE",
        solve_time_sec=elapsed(),
        objective=int(objective),
        best_bound=phase1_bound,
        penalties=penalties,
        solution=Solution(sittings, proctoring),
        solver_name=solver_name,
        messages=messages,
    )
