"""Giải bài toán A (lịch thi) bằng OR-Tools CP-SAT, chiến lược single.

Triển khai các biến, ràng buộc và hàm mục tiêu tại docs/model_spec.md A.4–A.6.
Chỉ trích xuất lịch thô; chia sinh viên vào từng phòng và đánh giá KPI thuộc
src.schedule, src.validator, src.kpi.
"""

from __future__ import annotations

from collections import defaultdict
from importlib.metadata import PackageNotFoundError, version

from ortools.sat.python import cp_model

from src.instance import Instance, Sitting, Solution, SolveResult


def solve(instance: Instance, config: dict) -> SolveResult:
    if config["strategy"] == "two_phase":
        raise NotImplementedError("Chiến lược two_phase thuộc task KHOE-3")
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
    p1_terms = []
    # A-S1: a_(i,d) = max(E_(i,d)-1, 0).
    for i, cs in student_courses.items():
        for d in days:
            a = model.NewIntVar(0, max(len(cs) - 1, 0), f"a_{i}_{d}")
            model.AddMaxEquality(a, [exams_per_day[i, d] - 1, 0])
            p1_terms.append(a)
    p1 = sum(p1_terms)

    # A-S2: b_(i,d) = max(E_(i,d)+E_(i,d')-1, 0).
    p2_terms = []
    for i, cs in student_courses.items():
        for d, d2 in instance.day_pairs:
            b = model.NewIntVar(0, max(len(cs) - 1, 0), f"b_{i}_{d}_{d2}")
            model.AddMaxEquality(b, [exams_per_day[i, d] + exams_per_day[i, d2] - 1, 0])
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
    model.AddMaxEquality(max_load, loads)
    model.AddMinEquality(min_load, loads)
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
    solver.parameters.log_search_progress = True
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

    return SolveResult(
        **kwargs,
        objective=round(solver.ObjectiveValue()),
        best_bound=solver.BestObjectiveBound(),
        penalties={
            name: int(solver.Value(expr)) for name, expr in penalties_expr.items()
        },
        solution=Solution(sittings, proctoring),
    )
