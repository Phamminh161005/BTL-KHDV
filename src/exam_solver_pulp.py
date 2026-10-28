"""Solver đối chứng cho bài toán A: PuLP + CBC (nhánh và cận).

Người phụ trách: Minh (task MINH-2).

Cài đặt độc lập với src/exam_solver.py (CP-SAT), cùng mô hình docs/model_spec.md và cùng đầu vào/đầu ra.
Hai solver viết riêng mà cho cùng giá trị tối ưu là cách kiểm tra chéo; phần thực nghiệm so sánh thời gian
giữa quy hoạch ràng buộc (CP-SAT) và quy hoạch nguyên bằng nhánh và cận (CBC).

Chỉ hỗ trợ strategy "single". Dùng PuLP 3.x vì từ PuLP 4 bộ giải CBC không còn được đóng gói sẵn.

Các lựa chọn cài đặt (đều không làm thay đổi tập nghiệm, xem model_spec A.5 và A.11):
- A-H6 và phần "không coi vào ca bận" của A-H8: không tạo biến u, w cho phòng-ca, giám thị-ca bận.
- Biến w chỉ tạo cho các phòng-ca có thể được dùng (có ít nhất một biến u phủ tới).
- Sinh viên có cùng tập môn và không học môn chia lượt nào thì có cùng ràng buộc A-H2 và cùng điểm phạt
  A-S1, A-S2. Mỗi nhóm như vậy chỉ sinh một bộ ràng buộc và một bộ biến phạt, nhân hệ số bằng số sinh viên.
- Biến phụ a, b, Lambda khai báo liên tục: vì mục tiêu cực tiểu và các vế phải nguyên, tại nghiệm tối ưu
  chúng tự nhận giá trị nguyên (model_spec A.6). Điểm phạt trả về được đếm lại từ lời giải đã làm tròn.
"""
from __future__ import annotations

import threading
import time
import warnings
from collections import defaultdict

import pulp
from pulp.apis import coin_api

from src.instance import Instance, Message, Sitting, Solution, SolveResult, next_period

SOLVER_NAME = f"PuLP {pulp.__version__} + CBC"
PENALTY_KEYS = ["A-S1", "A-S2", "A-S3", "A-S4", "A-S5", "A-S6"]

# Mã sol_status của PuLP -> trạng thái theo model_spec A.7. Không dùng prob.status, vì khi CBC dừng do hết
# giờ mà đã có lời giải khả thi thì prob.status vẫn là "Optimal"; sol_status mới phân biệt được.
_STATUS = {
    pulp.LpSolutionOptimal: "OPTIMAL",
    pulp.LpSolutionIntegerFeasible: "FEASIBLE",
    pulp.LpSolutionInfeasible: "INFEASIBLE",
    pulp.LpSolutionNoSolutionFound: "UNKNOWN",
}


def solve(instance: Instance, config: dict) -> SolveResult:
    """Giải bài toán A bằng PuLP + CBC. Đầu vào, đầu ra giống src.exam_solver.solve."""
    if config["strategy"] != "single":
        raise NotImplementedError("solver PuLP chỉ hỗ trợ strategy 'single'")
    started = time.time()
    model = _Model(instance, config)
    # Không truyền threads: bản CBC 2.10.3 đóng gói trong PuLP cho Windows bị treo ngay khi bắt đầu nhánh và cận
    # nếu có tham số -threads (kể cả threads=1), và không còn tôn trọng giới hạn thời gian. Vì vậy CBC chạy một
    # luồng; num_workers trong cấu hình chỉ áp dụng cho CP-SAT.
    with warnings.catch_warnings():
        # PuLP 3.x báo PULP_CBC_CMD sẽ bị bỏ ở PuLP 4; đây chính là lý do giữ PuLP 3 (xem docstring đầu file).
        warnings.simplefilter("ignore", DeprecationWarning)
        cbc = pulp.PULP_CBC_CMD(
            msg=False,
            timeLimit=config["time_limit_sec"],
            gapRel=0,
            options=[f"randomCbcSeed {config['random_seed']}"] if config["random_seed"] > 0 else [],
        )
    deadline = hard_deadline(config["time_limit_sec"])
    try:
        timed_out = _solve_with_deadline(model.prob, cbc, deadline)
    except pulp.PulpSolverError as e:
        return SolveResult("UNKNOWN", time.time() - started, solver_name=SOLVER_NAME, messages=[
            Message("S02", "error", f"CBC thoát bất thường: {e}")])
    elapsed = time.time() - started
    if timed_out:
        return SolveResult("UNKNOWN", elapsed, solver_name=SOLVER_NAME, messages=[
            Message("S01", "warning",
                    f"CBC không tự dừng ở giới hạn {config['time_limit_sec']} giây nên bị dừng cưỡng bức sau "
                    f"{deadline:.0f} giây; lời giải tốt nhất lúc đó (nếu có) không lấy được")])

    status = _STATUS.get(model.prob.sol_status, "UNKNOWN")
    if status not in ("OPTIMAL", "FEASIBLE"):
        return SolveResult(status, elapsed, solver_name=SOLVER_NAME)
    solution = model.extract()
    penalties = _count_penalties(instance, solution)
    objective = sum(config["weights"][k] * penalties[k] for k in PENALTY_KEYS)
    # PuLP không trả cận dưới của CBC; chỉ biết cận bằng giá trị mục tiêu khi đã chứng minh tối ưu.
    best_bound = objective if status == "OPTIMAL" else None
    return SolveResult(status, elapsed, objective, best_bound, penalties, solution, solver_name=SOLVER_NAME)


def hard_deadline(time_limit: float) -> float:
    """Hạn cứng (giây) để dừng CBC: giới hạn trong cấu hình cộng phần dư cho CBC tự dừng và ghi lời giải."""
    return time_limit + max(30.0, 0.2 * time_limit)


_launch_lock = threading.Lock()


def _solve_with_deadline(prob: pulp.LpProblem, cbc, deadline: float) -> bool:
    """Gọi prob.solve(cbc); nếu CBC chạy quá deadline giây thì dừng tiến trình CBC. Trả về True nếu đã phải dừng.

    CBC chỉ kiểm tra giới hạn -sec giữa các bước, nên với mô hình lớn nó có thể chạy rất lâu ở bước tiền xử lý
    hoặc nút gốc mà không dừng. PuLP lại chờ CBC không giới hạn (Popen.wait()). Để giữ được tiến trình CBC mà không
    sửa thư viện, trong lúc giải ta thay mô-đun subprocess mà riêng pulp.apis.coin_api nhìn thấy bằng một lớp
    bọc ghi lại tiến trình được tạo ra. Khóa _launch_lock đảm bảo hai lần giải song song không chồng lên nhau.
    """
    real = coin_api.subprocess
    launched: list = []
    killed = threading.Event()

    class _Subprocess:
        def __getattr__(self, name):
            return getattr(real, name)

        @staticmethod
        def Popen(*args, **kwargs):  # noqa: N802 (giữ tên của subprocess)
            process = real.Popen(*args, **kwargs)
            launched.append(process)
            return process

    def stop():
        for process in launched:
            if process.poll() is None:
                killed.set()
                process.kill()

    timer = threading.Timer(deadline, stop)
    with _launch_lock:
        coin_api.subprocess = _Subprocess()
        timer.start()
        try:
            prob.solve(cbc)
        except pulp.PulpSolverError:
            if not killed.is_set():
                raise
        finally:
            timer.cancel()
            coin_api.subprocess = real
    return killed.is_set()


class _Model:
    """Dựng mô hình ILP theo model_spec A.4–A.6."""

    def __init__(self, inst: Instance, config: dict):
        self.inst = inst
        nu = config["proctors_per_room"]
        weights = config["weights"]
        self.prob = pulp.LpProblem("lich_thi", pulp.LpMinimize)
        slot_set = set(inst.slots)
        proctors = inst.proctors
        courses = inst.courses

        # Tập dẫn xuất S_c, Cov(c, s) và S_c(t) (spec A.3)
        self.starts = {c: inst.start_slots(c) for c in courses}
        cover = {(c, s): inst.covered(c, s) for c in courses for s in self.starts[c]}
        starts_at = defaultdict(list)                       # (c, t) -> các s thuộc S_c(t)
        for (c, s), slots in cover.items():
            for t in slots:
                starts_at[c, t].append(s)

        # Biến quyết định (spec A.4). Tên biến tự đánh số để PuLP không làm trùng tên khi đổi ký tự.
        counter = iter(range(10 ** 9))

        def binary(prefix):
            return self.prob.add_variable(f"{prefix}{next(counter)}", cat=pulp.LpBinary)

        def nonneg(prefix):
            return self.prob.add_variable(f"{prefix}{next(counter)}", lowBound=0)

        self.x = {(c, s): binary("x") for c in courses for s in self.starts[c]}
        self.u = {}
        for c in courses:
            for r in inst.rooms_for(c):
                busy = inst.rooms[r].busy
                for s in self.starts[c]:
                    if not any(t in busy for t in cover[c, s]):        # A-H6: không tạo biến cho phòng bận
                        self.u[c, r, s] = binary("u")
        self.split = [c for c in courses if courses[c].splittable]
        self.q = {(i, c, s): binary("q") for c in self.split for i in sorted(courses[c].students)
                  for s in self.starts[c]}

        occ = defaultdict(list)                             # (r, t) -> các u phủ tới phòng r ở ca t
        for (c, r, s), var in self.u.items():
            for t in cover[c, s]:
                occ[r, t].append(var)
        self.w = {(g, r, t): binary("w") for (r, t) in occ for g in proctors if t not in proctors[g].busy}

        def w_or_zero(g, r, t):
            return self.w.get((g, r, t), 0)

        def n_students(c, s):
            """N_{c,s}."""
            if courses[c].splittable:
                return pulp.lpSum(self.q[i, c, s] for i in courses[c].students)
            return len(courses[c].students) * self.x[c, s]

        add = self.prob.addConstraint

        # A-H1: mỗi môn từ 1 đến L_c lượt
        for c in courses:
            total = pulp.lpSum(self.x[c, s] for s in self.starts[c])
            add(total >= 1)
            add(total <= courses[c].max_sittings)

        # A-H9: mỗi sinh viên thi đúng một lượt của môn chia lượt; chỉ vào lượt có mở; không mở lượt rỗng
        for c in self.split:
            students = courses[c].students
            for i in students:
                add(pulp.lpSum(self.q[i, c, s] for s in self.starts[c]) == 1)
                for s in self.starts[c]:
                    add(self.q[i, c, s] <= self.x[c, s])
            for s in self.starts[c]:
                add(self.x[c, s] <= pulp.lpSum(self.q[i, c, s] for i in students))

        # A-H3: đủ chỗ cho mỗi lượt; chỉ lượt có mở mới giữ phòng (viết riêng từng phòng, không big-M)
        for c in courses:
            for s in self.starts[c]:
                rooms = [r for r in inst.rooms_for(c) if (c, r, s) in self.u]
                add(n_students(c, s) <= pulp.lpSum(inst.rooms[r].exam_capacity * self.u[c, r, s] for r in rooms))
                for r in rooms:
                    add(self.u[c, r, s] <= self.x[c, s])

        # A-H4: mỗi phòng mỗi ca tối đa một môn (A-H5 đảm bảo qua miền của u, A-H6 qua việc không tạo biến)
        for terms in occ.values():
            if len(terms) > 1:
                add(pulp.lpSum(terms) <= 1)

        # A-H7: đủ nu giám thị cho phòng đang dùng, không có giám thị ở phòng không dùng
        for (r, t), terms in occ.items():
            add(pulp.lpSum(w_or_zero(g, r, t) for g in proctors) == nu * pulp.lpSum(terms))
        # A-H7: lượt 2 ca giữ nguyên giám thị ở cả hai ca
        for r in inst.rooms:
            for s in inst.slots:
                s_next = next_period(s)
                if s_next not in slot_set:
                    continue
                m = [self.u[c, r, s] for c in courses if courses[c].num_periods == 2 and (c, r, s) in self.u]
                if not m:
                    continue
                for g in proctors:
                    a, b = w_or_zero(g, r, s), w_or_zero(g, r, s_next)
                    if isinstance(a, int) and isinstance(b, int):
                        continue
                    add(a - b <= 1 - pulp.lpSum(m))
                    add(b - a <= 1 - pulp.lpSum(m))

        # A-H8: giám thị không coi hai phòng cùng ca (ca bận: không tạo biến w)
        by_proctor_slot = defaultdict(list)
        for (g, r, t), var in self.w.items():
            by_proctor_slot[g, t].append(var)
        for terms in by_proctor_slot.values():
            if len(terms) > 1:
                add(pulp.lpSum(terms) <= 1)

        # A-H10 (tùy chọn): giám thị không coi môn mình dạy
        if config["forbid_own_course"]:
            for (g, r, t), var in self.w.items():
                own = [self.u[c, r, s] for c in proctors[g].teaches if c in courses
                       for s in starts_at[c, t] if (c, r, s) in self.u]
                if own:
                    add(var + pulp.lpSum(own) <= 1)

        # Ràng buộc bổ trợ: số phòng dùng mỗi ca không vượt số giám thị rảnh chia nu
        for t in inst.slots:
            terms = [v for r in inst.rooms for v in occ.get((r, t), [])]
            if terms:
                free = sum(1 for g in proctors if t not in proctors[g].busy)
                add(pulp.lpSum(terms) <= free // nu)

        # ---- Sinh viên: A-H2 và biểu thức E_{i,d} cho A-S1, A-S2 ----
        # Nhóm sinh viên chỉ học môn không chia lượt theo tập môn; sinh viên có môn chia lượt xét riêng.
        courses_of = defaultdict(set)
        for c, course in courses.items():
            for i in course.students:
                courses_of[i].add(c)
        units = defaultdict(int)                            # khóa nhóm -> số sinh viên
        for i, cs in courses_of.items():
            key = ("cohort", frozenset(cs)) if not any(courses[c].splittable for c in cs) else ("student", i)
            units[key] += 1

        def attend(key, c, s):
            """pi_{i,c,s} của một sinh viên đại diện cho nhóm."""
            if courses[c].splittable:
                return self.q[key[1], c, s]
            return self.x[c, s]

        def unit_courses(key):
            return key[1] if key[0] == "cohort" else courses_of[key[1]]

        # A-H2: không sinh viên nào thi hai lượt trùng ca
        for key in units:
            for t in inst.slots:
                terms = [attend(key, c, s) for c in unit_courses(key) for s in starts_at[c, t]]
                if len(terms) > 1:
                    add(pulp.lpSum(terms) <= 1)

        days = inst.days
        day_starts = {(c, d): [s for s in self.starts[c] if s[0] == d] for c in courses for d in days}

        def e(key, d):
            """E_{i,d}: số lượt sinh viên bắt đầu trong ngày d."""
            return pulp.lpSum(attend(key, c, s) for c in unit_courses(key) for s in day_starts[c, d])

        p1_terms, p2_terms = [], []
        for key, size in units.items():
            if len(unit_courses(key)) < 2:
                continue                                    # thi tối đa 1 lượt thì không bao giờ bị phạt
            for d in days:
                a = nonneg("a")                                         # A-S1
                add(a >= e(key, d) - 1)
                p1_terms.append(size * a)
            for d, d2 in inst.day_pairs:
                b = nonneg("b")                                         # A-S2
                add(b >= e(key, d) + e(key, d2) - 1)
                p2_terms.append(size * b)

        # A-S3, A-S4, A-S5, A-S6
        p3 = pulp.lpSum(self.u.values()) - pulp.lpSum(self.x.values())
        p4 = pulp.lpSum(courses[c].num_periods * (
            pulp.lpSum(inst.rooms[r].exam_capacity * self.u[c, r, s]
                       for r in inst.rooms_for(c) if (c, r, s) in self.u) - n_students(c, s))
            for c in courses for s in self.starts[c])
        lam_max = nonneg("lam_max")
        lam_min = nonneg("lam_min")
        load = defaultdict(list)
        for (g, r, t), var in self.w.items():
            load[g].append(var)
        for g in proctors:
            add(lam_max >= pulp.lpSum(load[g]))
            add(lam_min <= pulp.lpSum(load[g]))
        p5 = lam_max - lam_min
        p6 = pulp.lpSum(self.x.values()) - len(courses)

        self.prob.setObjective(
            weights["A-S1"] * pulp.lpSum(p1_terms) + weights["A-S2"] * pulp.lpSum(p2_terms)
            + weights["A-S3"] * p3 + weights["A-S4"] * p4 + weights["A-S5"] * p5 + weights["A-S6"] * p6)

    def extract(self) -> Solution:
        inst = self.inst

        def on(var):
            return var.varValue is not None and var.varValue > 0.5

        sittings = []
        for (c, s), var in self.x.items():
            if not on(var):
                continue
            rooms = [r for r in inst.rooms_for(c) if (c, r, s) in self.u and on(self.u[c, r, s])]
            if inst.courses[c].splittable:
                students = sorted(i for i in inst.courses[c].students if on(self.q[i, c, s]))
            else:
                students = sorted(inst.courses[c].students)
            sittings.append(Sitting(c, s, rooms, students))
        proctoring = defaultdict(list)
        for (g, r, t), var in self.w.items():
            if on(var):
                proctoring[r, t].append(g)
        return Solution(sittings, {k: sorted(v) for k, v in proctoring.items()})


def _count_penalties(inst: Instance, solution: Solution) -> dict[str, int]:
    """Đếm P_1..P_6 (spec A.6) trực tiếp từ lời giải đã làm tròn."""
    starts = defaultdict(int)                               # (sinh viên, ngày) -> số lượt bắt đầu
    for st in solution.sittings:
        for i in st.students:
            starts[i, st.start[0]] += 1
    students = {i for c in inst.courses.values() for i in c.students}
    p1 = sum(max(0, starts[i, d] - 1) for i in students for d in inst.days)
    p2 = sum(max(0, starts[i, d] + starts[i, d2] - 1) for i in students for d, d2 in inst.day_pairs)
    p3 = sum(len(st.rooms) - 1 for st in solution.sittings)
    p4 = sum(inst.courses[st.course_id].num_periods
             * (sum(inst.rooms[r].exam_capacity for r in st.rooms) - len(st.students))
             for st in solution.sittings)
    load = {g: 0 for g in inst.proctors}
    for names in solution.proctoring.values():
        for g in names:
            load[g] += 1
    p5 = max(load.values()) - min(load.values()) if load else 0
    p6 = len(solution.sittings) - len(inst.courses)
    return dict(zip(PENALTY_KEYS, (p1, p2, p3, p4, p5, p6)))
