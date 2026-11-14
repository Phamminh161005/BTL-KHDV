"""Xếp lại lịch thi khi có sự cố: phòng hỏng, giảng viên bận đột xuất (model_spec A.14).

Cách chạy:
    py -3.12 -m src.reschedule --data data/toy --base tests/reference/toy_schedule.json \
        --incident room,G2-LAB1,2026-12-15,3
    py -3.12 -m src.reschedule --data data/toy --base lich_cu.json --incident lecturer,GV02,2026-12-15

Mỗi --incident có dạng loại,mã,ngày[,ca]; bỏ ca nghĩa là bận cả ngày. Có thể ghi nhiều --incident.
Kết quả mặc định ghi vào output/<tên bộ dữ liệu>/reschedule.json.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from typing import Optional

from src.data_loader import load_instance
from src.instance import Instance, Message, Sitting, Solution, SolveResult
from src.schedule import build_schedule, write_schedule

PERIODS = (1, 2, 3, 4)


# ---------------------------------------------------------------- sự cố

def apply_incidents(instance: Instance, incidents: list[dict], messages: list[Message]) -> list[dict]:
    """Kiểm tra từng sự cố, thêm vào lịch bận của phòng hoặc giảng viên (như một dòng của unavailability.csv).

    Trả về danh sách sự cố đã chuẩn hóa. Sự cố sai được báo I01 (error); sự cố không ảnh hưởng gì báo I02.
    """
    applied = []
    slot_set = set(instance.slots)
    for n, inc in enumerate(incidents, start=1):
        where = f"Sự cố {n}"
        if not isinstance(inc, dict):
            messages.append(Message("I01", "error", f"{where}: phải là một đối tượng"))
            continue
        kind = inc.get("resource_type")
        rid = inc.get("resource_id")
        if kind not in ("room", "lecturer"):
            messages.append(Message("I01", "error", f"{where}: resource_type phải là room hoặc lecturer, gặp {kind!r}"))
            continue
        target = instance.rooms if kind == "room" else instance.lecturers
        if rid not in target:
            label = "Phòng" if kind == "room" else "Giảng viên"
            messages.append(Message("I01", "error", f"{where}: {label} {rid!r} không có trong dữ liệu"))
            continue
        try:
            day = dt.date.fromisoformat(str(inc.get("date")))
        except ValueError:
            messages.append(Message("I01", "error", f"{where}: ngày {inc.get('date')!r} không đúng dạng YYYY-MM-DD"))
            continue
        period = inc.get("period")
        if period in ("", None):
            period = None
        elif not (isinstance(period, int) and not isinstance(period, bool) and period in PERIODS):
            messages.append(Message("I01", "error", f"{where}: ca phải là 1–4 hoặc để trống (cả ngày), gặp {period!r}"))
            continue
        hit = {(day, k) for k in ([period] if period else PERIODS) if (day, k) in slot_set}
        when = f"ca {period} ngày {day}" if period else f"cả ngày {day}"
        if not hit:
            messages.append(Message("I02", "warning", f"{where}: {when} không có trong lịch thi, bỏ qua"))
        elif kind == "lecturer" and not instance.lecturers[rid].is_proctor:
            messages.append(Message("I02", "warning", f"{where}: giảng viên {rid} không coi thi, sự cố không ảnh hưởng"))
        target[rid].busy |= hit
        applied.append({"resource_type": kind, "resource_id": rid, "date": day.isoformat(), "period": period})
    return applied


def parse_incident(text: str) -> dict:
    """'room,G2-LAB1,2026-12-15,3' hoặc 'lecturer,GV02,2026-12-15' (cả ngày) -> dict sự cố."""
    parts = [p.strip() for p in text.split(",")]
    if len(parts) not in (3, 4):
        raise ValueError(f"Sự cố {text!r} phải có dạng loại,mã,ngày[,ca]")
    period = None
    if len(parts) == 4 and parts[3] != "":
        if not parts[3].isdigit():
            raise ValueError(f"Ca trong sự cố {text!r} phải là số 1–4")
        period = int(parts[3])
    return {"resource_type": parts[0], "resource_id": parts[1], "date": parts[2], "period": period}


# ---------------------------------------------------------------- lịch cũ

def base_solution(instance: Instance, base: dict, messages: list[Message]) -> Optional[Solution]:
    """Dựng lại lời giải thô (x, u, q, w) từ nội dung schedule.json của lịch cũ. Lỗi báo I03."""
    sittings_json = base.get("sittings") if isinstance(base, dict) else None
    if not isinstance(sittings_json, list) or not sittings_json:
        messages.append(Message("I03", "error", "Lịch cũ không có lượt thi nào (trạng thái "
                                f"{base.get('status') if isinstance(base, dict) else None})"))
        return None
    slot_set = set(instance.slots)
    sittings, proctoring = [], {}
    seen_students: dict[str, set] = {c: set() for c in instance.courses}
    for item in sittings_json:
        try:
            c = item["course_id"]
            start = (dt.date.fromisoformat(item["date"]), int(item["start_period"]))
            room_entries = item["rooms"]
            if not isinstance(room_entries, list):
                raise ValueError("rooms phải là danh sách")
            for entry in room_entries:
                if not isinstance(entry, dict):
                    raise ValueError("Mỗi phòng phải là đối tượng")
                for field in ("students", "proctors"):
                    values = entry.get(field, [])
                    if not isinstance(values, list) or not all(isinstance(x, str) for x in values):
                        raise ValueError(f"{field} phải là danh sách mã")
                if entry.get("room_id") is not None and not isinstance(entry["room_id"], str):
                    raise ValueError("room_id phải là chuỗi")
            if not isinstance(c, str):
                raise ValueError("course_id phải là chuỗi")
        except (KeyError, TypeError, ValueError):
            messages.append(Message("I03", "error", "Lịch cũ sai định dạng (data_schema mục 7.3)"))
            return None
        if c not in instance.courses:
            messages.append(Message("I03", "error", f"Lịch cũ có môn {c} không có trong dữ liệu"))
            return None
        if start not in slot_set:
            messages.append(Message("I03", "error", f"Lịch cũ có lượt {item.get('sitting_id')} ở ca không có trong "
                                                    "slots.csv"))
            return None
        rooms, students = [], []
        for entry in room_entries:
            r = entry.get("room_id")
            if r is not None and r not in instance.rooms:
                messages.append(Message("I03", "error", f"Lịch cũ dùng phòng {r} không có trong dữ liệu"))
                return None
            if r is not None:
                rooms.append(r)
                for t in instance.covered(c, start):
                    if t in slot_set:
                        proctoring.setdefault((r, t), []).extend(entry.get("proctors", []))
            students.extend(entry.get("students", []))
        seen_students[c].update(students)
        sittings.append(Sitting(c, start, rooms, sorted(students)))
    for c, course in instance.courses.items():
        if seen_students[c] != course.students:
            messages.append(Message("I03", "error", f"Danh sách sinh viên môn {c} trong lịch cũ khác với "
                                                    "enrollments.csv; lịch cũ không thuộc bộ dữ liệu này"))
            return None
    return Solution(sittings, proctoring)


# ---------------------------------------------------------------- phạm vi xếp lại

def conflicting_courses(instance: Instance, base: Solution) -> set[str]:
    """Các môn có lượt trong lịch cũ không còn hợp lệ sau sự cố: dùng phòng đang bận, hoặc có giám thị đang bận,
    ở một ca mà lượt đó chiếm. Lịch bận lúc này đã gồm cả sự cố (apply_incidents)."""
    hit = set()
    for st in base.sittings:
        cells = [(r, t) for r in st.rooms for t in instance.covered(st.course_id, st.start)]
        if any(t in instance.rooms[r].busy for r, t in cells):
            hit.add(st.course_id)
        elif any(t in instance.lecturers[g].busy for r, t in cells for g in base.proctoring.get((r, t), [])):
            hit.add(st.course_id)
    return hit


def reschedule_scopes(instance: Instance, base: Solution, incidents: list[dict]) -> list[tuple[str, set[str]]]:
    """Các phạm vi xếp lại, từ hẹp đến rộng (model_spec A.14). Mỗi phạm vi là tập môn được thay đổi; các môn còn
    lại giữ nguyên như lịch cũ. Phạm vi hẹp vô nghiệm thì mới mở rộng.

    1. Các môn bị sự cố chạm vào.
    2. Thêm mọi môn có lượt thi vào ngày có sự cố hoặc ngày của các lượt bị chạm vào.
    3. Toàn bộ lịch.
    """
    everything = set(instance.courses)
    touched = conflicting_courses(instance, base)
    days = {dt.date.fromisoformat(inc["date"]) for inc in incidents}
    days |= {st.start[0] for st in base.sittings if st.course_id in touched}
    same_day = touched | {st.course_id for st in base.sittings if st.start[0] in days}
    scopes, seen = [], []
    for label, free in (("các môn bị sự cố chạm vào", touched), ("các môn thi cùng ngày với sự cố", same_day),
                        ("toàn bộ lịch", everything)):
        if free not in seen:
            scopes.append((label, free))
            seen.append(free)
    return scopes


# ---------------------------------------------------------------- so sánh hai lịch

def _placements(schedule: dict):
    """Vị trí từng sinh viên ((môn, sinh viên) -> (ngày, ca, phòng)) và các ca coi thi của từng giám thị."""
    student_at, duties = {}, {}
    for st in schedule.get("sittings", []):
        for room in st["rooms"]:
            for i in room["students"]:
                student_at[st["course_id"], i] = (st["date"], st["start_period"], room["room_id"])
            for g in room["proctors"]:
                for k in st["periods"]:
                    duties.setdefault(g, set()).add((st["date"], k, room["room_id"]))
    return student_at, duties


def _view(st: dict) -> dict:
    return {"sitting_id": st["sitting_id"], "date": st["date"], "start_period": st["start_period"],
            "rooms": [r["room_id"] for r in st["rooms"]],
            "proctors": {r["room_id"]: r["proctors"] for r in st["rooms"]}}


def diff_schedules(old: dict, new: dict) -> tuple[list[dict], dict]:
    """So sánh hai nội dung schedule.json theo từng môn, không theo sitting_id.

    Lượt của cùng một môn được ghép theo ca bắt đầu; lượt còn lại ghép theo số sinh viên chung nhiều nhất, nên
    một lượt bị dời sang ca khác hiện là "time" thay vì một lượt bị xóa và một lượt mới.
    Trả về (danh sách thay đổi, tóm tắt). Mỗi thay đổi có "kinds" là tập con của:
    time (dời ca), rooms (đổi phòng), proctors (đổi giám thị), students (đổi sinh viên giữa các phòng/lượt),
    removed (bỏ lượt), added (thêm lượt).
    """
    old_at, old_duties = _placements(old)
    new_at, new_duties = _placements(new)
    by_course: dict[str, tuple[list, list]] = {}
    for key, schedule in ((0, old), (1, new)):
        for st in schedule.get("sittings", []):
            by_course.setdefault(st["course_id"], ([], []))[key].append(st)

    def students(st):
        return {i for r in st["rooms"] for i in r["students"]}

    changes = []
    for c in sorted(by_course):
        olds, news = by_course[c]
        pairs = []
        rest_new = list(news)
        rest_old = []
        for o in olds:
            same = next((n for n in rest_new if (n["date"], n["start_period"]) == (o["date"], o["start_period"])), None)
            if same is not None:
                pairs.append((o, same))
                rest_new.remove(same)
            else:
                rest_old.append(o)
        for o in sorted(rest_old, key=lambda s: -len(students(s))):
            if not rest_new:
                break
            best = max(rest_new, key=lambda n: (len(students(o) & students(n)), -rest_new.index(n)))
            pairs.append((o, best))
            rest_new.remove(best)
        paired_old = {id(o) for o, _ in pairs}
        for o, n in pairs:
            kinds = []
            if (o["date"], o["start_period"]) != (n["date"], n["start_period"]):
                kinds.append("time")
            if sorted(r["room_id"] for r in o["rooms"]) != sorted(r["room_id"] for r in n["rooms"]):
                kinds.append("rooms")
            if ({(r["room_id"], g) for r in o["rooms"] for g in r["proctors"]}
                    != {(r["room_id"], g) for r in n["rooms"] for g in r["proctors"]}):
                kinds.append("proctors")
            moved = {i for i in students(o) | students(n) if old_at.get((c, i)) != new_at.get((c, i))}
            if moved and not {"time", "rooms"} & set(kinds):
                kinds.append("students")
            if kinds:
                changes.append({"course_id": c, "kinds": kinds, "old": _view(o), "new": _view(n),
                                "students_affected": len(moved)})
        for o in olds:
            if id(o) not in paired_old:
                changes.append({"course_id": c, "kinds": ["removed"], "old": _view(o), "new": None,
                                "students_affected": len(students(o))})
        for n in rest_new:
            changes.append({"course_id": c, "kinds": ["added"], "old": None, "new": _view(n),
                            "students_affected": len({i for i in students(n) if old_at.get((c, i)) != new_at.get((c, i))})})

    def count(kind):
        return sum(kind in ch["kinds"] for ch in changes)

    summary = {
        "sittings_changed": len(changes),
        "sittings_moved": count("time"),
        "sittings_room_changed": count("rooms"),
        "sittings_proctor_changed": count("proctors"),
        "sittings_removed": count("removed"),
        "sittings_added": count("added"),
        "students_affected": len({i for (c, i) in set(old_at) | set(new_at) if old_at.get((c, i)) != new_at.get((c, i))}),
        "proctors_affected": len({g for g in set(old_duties) | set(new_duties)
                                  if old_duties.get(g, set()) != new_duties.get(g, set())}),
    }
    return changes, summary


# ---------------------------------------------------------------- xếp lại

def _total_cost(result, weights: dict) -> int:
    """Hàm mục tiêu khi xếp lại (A.14): Z cộng chi phí thay đổi."""
    return result.objective + sum(weights[k] * v for k, v in (result.change_penalties or {}).items())


def _solve_in_scopes(instance: Instance, config: dict, base: Solution, incidents: list[dict], solve):
    """Xếp lại hai bước trong cùng giới hạn reschedule.time_limit_sec (model_spec A.14).

    Bước 1, xếp lại cục bộ: giải lần lượt từ phạm vi hẹp đến rộng, các môn ngoài phạm vi giữ nguyên như lịch cũ,
    dừng ở phạm vi đầu tiên có lời giải. Bước này nhỏ nên nhanh, và bảo đảm không xáo trộn phần lịch không liên quan.
    Bước 2: với thời gian còn lại, giải trên toàn lịch, lấy lời giải bước 1 làm gợi ý; giữ lời giải bước 2 chỉ khi
    tổng Z + chi phí thay đổi thấp hơn. Chỉ lời giải trên toàn lịch mới được báo OPTIMAL hoặc INFEASIBLE."""
    import time

    weights = config["reschedule"]["weights"]
    started = time.monotonic()
    deadline = started + float(config["time_limit_sec"])
    scopes = reschedule_scopes(instance, base, incidents)
    everything = frozenset(instance.courses)
    notes, local, label, free = [], None, None, set()
    for label, free in scopes:
        if free == everything:
            break
        local = solve(instance, config, base=base, change_weights=weights, frozen=everything - free,
                      _deadline=deadline)
        if local.status in ("OPTIMAL", "FEASIBLE"):
            notes.append(Message("I04", "info", f"Bước 1, xếp lại cục bộ trong phạm vi {label}: mở lại "
                                                f"{len(free)}/{len(everything)} môn, tổng chi phí "
                                                f"{_total_cost(local, weights)}"))
            break
        notes.append(Message("I04", "info", f"Bước 1: phạm vi {label} ({len(free)} môn) không xếp được "
                                            f"({local.status}); mở rộng phạm vi"))
        local = None
        if time.monotonic() >= deadline:
            break

    result = None
    if time.monotonic() < deadline:
        result = solve(instance, config, base=base, change_weights=weights,
                       hint=local.solution if local else None, _deadline=deadline)
    if local is not None:
        if result is not None and result.status in ("OPTIMAL", "FEASIBLE") \
                and _total_cost(result, weights) < _total_cost(local, weights):
            notes.append(Message("I04", "info", f"Bước 2, giải trên toàn lịch: tổng chi phí giảm xuống "
                                                f"{_total_cost(result, weights)}, dùng lời giải này"))
        else:
            notes.append(Message("I04", "info", "Bước 2, giải trên toàn lịch: không tìm được lời giải tốt hơn, "
                                                "giữ lời giải cục bộ"))
            local.status = "FEASIBLE"     # chỉ tối ưu trong phạm vi cục bộ
            result = local
    elif result is None:
        # Hết thời gian trước khi giải được trên toàn lịch; phạm vi hẹp vô nghiệm không chứng minh được gì.
        result = SolveResult(status="UNKNOWN", solve_time_sec=0.0)
        notes.append(Message("I04", "warning", "Hết thời gian xếp lại trước khi tìm được lời giải"))
    result.messages = notes + result.messages
    result.solve_time_sec = time.monotonic() - started
    return result


def reschedule(data_dir: str, base_schedule_path: str, incidents: list[dict], config_path: Optional[str] = None,
               out_path: Optional[str] = None) -> dict:
    """Xếp lại lịch cũ sau sự cố và trả về nội dung schedule.json của lịch mới (data_schema mục 7.6).

    incidents: danh sách {"resource_type": "room" | "lecturer", "resource_id", "date": "YYYY-MM-DD",
    "period": 1..4 hoặc None (cả ngày)}. Kết quả có thêm "changes" (các lượt bị đổi) và "reschedule" (tóm tắt).
    """
    from src.diagnose import diagnose
    from src.exam_solver import solve

    dataset = os.path.basename(os.path.normpath(data_dir))
    loaded = load_instance(data_dir, config_path)
    if loaded.config["problem"] != "A":
        raise ValueError("src.reschedule chỉ hỗ trợ bài A; bài B cần bộ xếp lại riêng theo B.9")
    messages = list(loaded.messages)
    config = dict(loaded.config, strategy="single")
    instance = loaded.instance
    base, applied, base_json = None, [], None
    if loaded.ok:
        try:
            with open(base_schedule_path, encoding="utf-8-sig") as f:
                base_json = json.load(f)
        except (OSError, UnicodeError, json.JSONDecodeError) as e:
            messages.append(Message("I03", "error", f"Không đọc được lịch cũ: {e}"))
        else:
            base = base_solution(instance, base_json, messages)
        applied = apply_incidents(instance, incidents, messages)
    has_error = any(m.level == "error" for m in messages)

    result = None
    if not has_error:
        config["time_limit_sec"] = config["reschedule"]["time_limit_sec"]
        result = _solve_in_scopes(instance, config, base, applied, solve)
        if result.status == "INFEASIBLE":
            result.messages += diagnose(instance, config)
    schedule = build_schedule(instance if not has_error else None, config, messages, result, dataset)

    changes, summary = ([], None)
    if base_json is not None and schedule["sittings"]:
        changes, summary = diff_schedules(base_json, schedule)
    weights = config["reschedule"]["weights"]
    change_penalties = result.change_penalties if result else None
    schedule["changes"] = changes
    schedule["reschedule"] = {
        "base_schedule": os.path.basename(base_schedule_path),
        "incidents": applied,
        "change_penalties": change_penalties,
        "change_cost": (sum(weights[k] * v for k, v in change_penalties.items()) if change_penalties else None),
        "summary": summary,
    }
    out_path = out_path or os.path.join("output", dataset, "reschedule.json")
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    write_schedule(schedule, out_path)
    return schedule


_KIND_LABELS = {"time": "dời ca", "rooms": "đổi phòng", "proctors": "đổi giám thị", "students": "đổi sinh viên",
                "removed": "bỏ lượt", "added": "thêm lượt"}


def _where(view: Optional[dict]) -> str:
    if view is None:
        return "-"
    return f"ca {view['start_period']} ngày {view['date']} ({', '.join(view['rooms'])})"


def main() -> int:
    parser = argparse.ArgumentParser(description="Xếp lại lịch thi khi có sự cố (bài toán A)")
    parser.add_argument("--data", required=True, help="Thư mục bộ dữ liệu, ví dụ data/toy")
    parser.add_argument("--base", required=True, help="File schedule.json của lịch cũ")
    parser.add_argument("--incident", action="append", default=[], metavar="LOẠI,MÃ,NGÀY[,CA]",
                        help="Ví dụ room,G2-LAB1,2026-12-15,3 hoặc lecturer,GV02,2026-12-15 (cả ngày)")
    parser.add_argument("--config", default="configs/default.json")
    parser.add_argument("--out", default=None, help="Mặc định output/<tên bộ dữ liệu>/reschedule.json")
    args = parser.parse_args()
    try:
        incidents = [parse_incident(text) for text in args.incident]
    except ValueError as e:
        print(e)
        return 2
    config_path = args.config if os.path.exists(args.config) else None
    schedule = reschedule(args.data, args.base, incidents, config_path, args.out)
    for m in schedule["messages"]:
        print(f"[{m['level']}] {m['code']}: {m['message']}")
    info = schedule["reschedule"]
    print(f"Trạng thái: {schedule['status']}, mục tiêu: {schedule['objective']}, "
          f"thời gian xếp lại: {schedule['solve_time_sec']} giây, vi phạm: {len(schedule['violations'])}")
    if info["summary"]:
        s = info["summary"]
        print(f"Thay đổi: {s['sittings_changed']} lượt ({s['sittings_moved']} dời ca), "
              f"{s['students_affected']} sinh viên và {s['proctors_affected']} giám thị bị ảnh hưởng")
    for ch in schedule["changes"]:
        kinds = ", ".join(_KIND_LABELS[k] for k in ch["kinds"])
        print(f"  {ch['course_id']}: {kinds}: {_where(ch['old'])} -> {_where(ch['new'])}")
    return 0 if schedule["status"] in ("OPTIMAL", "FEASIBLE") and not schedule["violations"] else 1


if __name__ == "__main__":
    sys.exit(main())
