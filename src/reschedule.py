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
from src.instance import Instance, Message, Sitting, Solution
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
    if not sittings_json:
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
    messages = list(loaded.messages)
    config = dict(loaded.config, strategy="single")
    instance = loaded.instance
    base, applied, base_json = None, [], None
    if loaded.ok:
        try:
            with open(base_schedule_path, encoding="utf-8-sig") as f:
                base_json = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            messages.append(Message("I03", "error", f"Không đọc được lịch cũ: {e}"))
        if base_json is not None:
            base = base_solution(instance, base_json, messages)
        applied = apply_incidents(instance, incidents, messages)
    has_error = any(m.level == "error" for m in messages)

    result = None
    if not has_error:
        config["time_limit_sec"] = config["reschedule"]["time_limit_sec"]
        result = solve(instance, config, base=base, change_weights=config["reschedule"]["weights"])
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
