"""Xếp lại lịch học bài toán B khi có sự cố (model_spec B.9, data_schema mục 9.11).

Cách chạy:
    py -3.12 -m src.reschedule_b --data data/toy_b --base tests/reference/toy_timetable.json \
        --incident room,G2-LAB1,6,4
    py -3.12 -m src.reschedule_b --data data/toy_b --base lich_cu.json --incident lecturer,GV02,4

Mỗi --incident có dạng loại,mã,thứ[,ca]; thứ là 2..7, bỏ ca nghĩa là bận cả ngày. Có thể ghi nhiều --incident.
Lớp mới: thêm lớp vào classes.csv (và class_groups.csv nếu là lớp bắt buộc) rồi xếp lại; lớp có trong dữ liệu mà
không có trong lịch cũ được coi là lớp mới. Khi gọi hàm, có thể truyền sự cố {"type": "add_class", "class": {...}}.
Kết quả mặc định ghi vào output/<tên bộ dữ liệu>/retimetable.json.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from typing import Optional, Union

from src.data_loader_b import load_instance_b
from src.instance import Message, SolveResult
from src.instance_b import ClassB, InstanceB, Session, SolutionB
from src.schedule import write_schedule
from src.timetable import build_timetable

PERIODS = (1, 2, 3, 4)
WEEKDAYS = (2, 3, 4, 5, 6, 7)
ID_RE = re.compile(r"^[A-Za-z0-9_.\-]{1,50}$")


def _is_int(x) -> bool:
    return isinstance(x, int) and not isinstance(x, bool)


# ---------------------------------------------------------------- sự cố

def _apply_unavailability(instance: InstanceB, inc: dict, where: str, messages: list[Message]) -> Optional[dict]:
    kind, rid = inc.get("resource_type"), inc.get("resource_id")
    if kind not in ("room", "lecturer"):
        messages.append(Message("I01", "error", f"{where}: resource_type phải là room hoặc lecturer, gặp {kind!r}"))
        return None
    target = instance.rooms if kind == "room" else instance.lecturers
    if rid not in target:
        label = "Phòng" if kind == "room" else "Giảng viên"
        messages.append(Message("I01", "error", f"{where}: {label} {rid!r} không có trong dữ liệu"))
        return None
    day = inc.get("weekday")
    if not (_is_int(day) and day in WEEKDAYS):
        messages.append(Message("I01", "error", f"{where}: weekday phải là 2–7, gặp {day!r}"))
        return None
    period = inc.get("period")
    if period in ("", None):
        period = None
    elif not (_is_int(period) and period in PERIODS):
        messages.append(Message("I01", "error", f"{where}: ca phải là 1–4 hoặc để trống (cả ngày), gặp {period!r}"))
        return None
    slots = set(instance.slots)
    hit = {(day, k) for k in ([period] if period else PERIODS) if (day, k) in slots}
    when = f"Thứ {day} ca {period}" if period else f"cả Thứ {day}"
    if not hit:
        messages.append(Message("I02", "warning", f"{where}: {when} không có trong lịch tuần, bỏ qua"))
    elif kind == "lecturer" and rid not in instance.teaching:
        messages.append(Message("I02", "warning", f"{where}: giảng viên {rid} không dạy lớp nào, sự cố không ảnh hưởng"))
    target[rid].busy |= hit
    if kind == "lecturer":
        target[rid].avoid -= target[rid].busy       # ca vừa bận vừa không muốn dạy thì coi là bận (mục 9.7)
    return {"resource_type": kind, "resource_id": rid, "weekday": day, "period": period}


def _apply_add_class(instance: InstanceB, inc: dict, where: str, messages: list[Message]) -> Optional[dict]:
    raw = inc.get("class")
    if not isinstance(raw, dict):
        messages.append(Message("I01", "error", f"{where}: thiếu thông tin lớp mới ('class')"))
        return None
    cid, lecturer = raw.get("class_id"), raw.get("lecturer_id")
    size, sessions, needs_lab = raw.get("size"), raw.get("sessions_per_week"), raw.get("needs_lab", False)
    groups = raw.get("groups", [])
    errors = []
    if not (isinstance(cid, str) and ID_RE.match(cid)):
        errors.append(f"mã lớp {cid!r} không hợp lệ")
    elif cid in instance.classes:
        errors.append(f"lớp {cid} đã có trong dữ liệu")
    if lecturer not in instance.lecturers:
        errors.append(f"giảng viên {lecturer!r} không có trong dữ liệu")
    if not (_is_int(size) and size >= 1):
        errors.append(f"sĩ số phải là số nguyên ≥ 1, gặp {size!r}")
    if not (_is_int(sessions) and sessions >= 1):
        errors.append(f"số buổi/tuần phải là số nguyên ≥ 1, gặp {sessions!r}")
    if not isinstance(needs_lab, bool):
        errors.append("needs_lab phải là true hoặc false")
    if not (isinstance(groups, list) and all(isinstance(g, str) and ID_RE.match(g) for g in groups)):
        errors.append("groups phải là danh sách mã nhóm")
    if errors:
        messages.append(Message("I01", "error", f"{where}: " + "; ".join(errors)))
        return None
    cls = ClassB(cid, needs_lab, size, sessions, lecturer, str(raw.get("class_name", "")),
                 str(raw.get("course_id", "")), set(groups))
    instance.classes[cid] = cls
    for g in groups:
        instance.groups[g] = sorted(set(instance.groups.get(g, [])) | {cid})
    if not instance.rooms_for(cid):
        kind = "phòng máy" if needs_lab else "phòng thường"
        messages.append(Message("PB1", "error", f"Lớp mới {cid} ({size} sinh viên) không có {kind} nào đủ chỗ"))
    return {"type": "add_class", "class": {"class_id": cid, "class_name": cls.name, "course_id": cls.course_id,
                                            "needs_lab": needs_lab, "size": size, "sessions_per_week": sessions,
                                            "lecturer_id": lecturer, "groups": sorted(groups)}}


def apply_incidents_b(instance: InstanceB, incidents: list[dict], messages: list[Message]) -> list[dict]:
    """Áp dụng sự cố vào instance và trả về danh sách sự cố đã chuẩn hóa.

    - Ca bận thêm: {"resource_type": "room" | "lecturer", "resource_id", "weekday": 2..7, "period": 1..4 | None},
      như một dòng của week_unavailability.csv. Có thể kèm "type": "unavailability".
    - Thêm lớp: {"type": "add_class", "class": {"class_id", "lecturer_id", "size", "sessions_per_week",
      "needs_lab", "groups", "class_name", "course_id"}}.
    Sự cố sai báo I01 (error), sự cố không ảnh hưởng gì báo I02 (warning).
    """
    applied = []
    for n, inc in enumerate(incidents, start=1):
        where = f"Sự cố {n}"
        if not isinstance(inc, dict):
            messages.append(Message("I01", "error", f"{where}: phải là một đối tượng"))
            continue
        kind = inc.get("type", "unavailability")
        if kind == "unavailability":
            item = _apply_unavailability(instance, inc, where, messages)
        elif kind == "add_class":
            item = _apply_add_class(instance, inc, where, messages)
        else:
            messages.append(Message("I01", "error", f"{where}: type phải là unavailability hoặc add_class, gặp {kind!r}"))
            item = None
        if item is not None:
            applied.append(item)
    return applied


def parse_incident_b(text: str) -> dict:
    """'room,G2-LAB1,6,4' hoặc 'lecturer,GV02,4' (cả Thứ 4) -> dict sự cố."""
    parts = [p.strip() for p in text.split(",")]
    if len(parts) not in (3, 4):
        raise ValueError(f"Sự cố {text!r} phải có dạng loại,mã,thứ[,ca]")
    if not parts[2].isdigit():
        raise ValueError(f"Thứ trong sự cố {text!r} phải là số 2–7")
    period = None
    if len(parts) == 4 and parts[3] != "":
        if not parts[3].isdigit():
            raise ValueError(f"Ca trong sự cố {text!r} phải là số 1–4")
        period = int(parts[3])
    return {"resource_type": parts[0], "resource_id": parts[1], "weekday": int(parts[2]), "period": period}


# ---------------------------------------------------------------- lịch cũ

def base_solution_b(instance: InstanceB, base: dict, messages: list[Message]) -> Optional[SolutionB]:
    """Dựng lại lời giải thô từ mảng sessions của timetable.json cũ. Lỗi báo I03."""
    sessions = base.get("sessions") if isinstance(base, dict) else None
    if not isinstance(sessions, list) or not sessions:
        status = base.get("status") if isinstance(base, dict) else None
        messages.append(Message("I03", "error", f"Lịch cũ không có buổi học nào (trạng thái {status})"))
        return None
    week, seen, result = set(instance.slots), set(), []
    for item in sessions:
        try:
            k, r, slot = item["class_id"], item["room_id"], (item["weekday"], item["period"])
            if not (isinstance(k, str) and isinstance(r, str) and _is_int(slot[0]) and _is_int(slot[1])):
                raise TypeError
        except (KeyError, TypeError):
            messages.append(Message("I03", "error", "Lịch cũ sai định dạng (data_schema mục 9.11)"))
            return None
        if k not in instance.classes:
            messages.append(Message("I03", "error", f"Lịch cũ có lớp {k} không có trong dữ liệu"))
            return None
        if r not in instance.rooms:
            messages.append(Message("I03", "error", f"Lịch cũ dùng phòng {r} không có trong dữ liệu"))
            return None
        if slot not in week:
            messages.append(Message("I03", "error", f"Lịch cũ có buổi {item.get('session_id')} ở ca không có trong "
                                                    "week_slots.csv"))
            return None
        if (k, slot) in seen:
            messages.append(Message("I03", "error", f"Lịch cũ có hai buổi của lớp {k} cùng ca"))
            return None
        seen.add((k, slot))
        result.append(Session(k, r, slot))
    return SolutionB(result)


# ---------------------------------------------------------------- phạm vi xếp lại

def affected_classes(instance: InstanceB, base: SolutionB) -> set[str]:
    """Lớp phải mở lại: có buổi cũ không còn hợp lệ sau sự cố (phòng hoặc giảng viên bận ở ca đó, phòng không còn
    phù hợp), số buổi cũ khác số buổi cần, hoặc lớp mới (có trong dữ liệu, không có trong lịch cũ)."""
    hit, count = set(), {}
    for s in base.sessions:
        count[s.class_id] = count.get(s.class_id, 0) + 1
        cls = instance.classes[s.class_id]
        if (s.slot in instance.rooms[s.room_id].busy or s.slot in instance.lecturers[cls.lecturer_id].busy
                or s.room_id not in instance.rooms_for(s.class_id)):
            hit.add(s.class_id)
    hit |= {k for k, cls in instance.classes.items() if count.get(k, 0) != cls.sessions}
    return hit


def reschedule_scopes_b(instance: InstanceB, base: SolutionB, incidents: list[dict]) -> list[tuple[str, set[str]]]:
    """Các phạm vi xếp lại từ hẹp đến rộng (model_spec B.9): lớp bị ảnh hưởng; thêm các lớp học cùng ngày với sự cố
    hoặc với buổi bị ảnh hưởng; toàn bộ lịch. Lớp ngoài phạm vi giữ nguyên như lịch cũ."""
    everything = set(instance.classes)
    touched = affected_classes(instance, base)
    days = {inc["weekday"] for inc in incidents if "weekday" in inc}
    days |= {s.slot[0] for s in base.sessions if s.class_id in touched}
    same_day = touched | {s.class_id for s in base.sessions if s.slot[0] in days}
    scopes, seen = [], []
    for label, free in (("các lớp bị sự cố ảnh hưởng", touched), ("các lớp học cùng ngày với sự cố", same_day),
                        ("toàn bộ lịch", everything)):
        if free not in seen:
            scopes.append((label, free))
            seen.append(free)
    return scopes


def _total_cost(result: SolveResult, weights: dict) -> int:
    """Hàm mục tiêu khi xếp lại (B.9): Z^B + gamma_1 R^B_1 + gamma_2 R^B_2."""
    return result.objective + sum(weights[k] * v for k, v in (result.change_penalties or {}).items())


def _solve_in_scopes(instance: InstanceB, config: dict, base: SolutionB, incidents: list[dict]) -> SolveResult:
    """Xếp lại hai bước trong cùng giới hạn reschedule.time_limit_sec, như A.14.

    Bước 1: giải từ phạm vi hẹp đến rộng, lớp ngoài phạm vi giữ nguyên, dừng ở phạm vi đầu tiên có lời giải.
    Bước 2: với thời gian còn lại, giải trên toàn lịch, lấy lời giải bước 1 làm gợi ý; chỉ dùng khi tổng chi phí thấp
    hơn. Chỉ lời giải trên toàn lịch mới được báo OPTIMAL hoặc INFEASIBLE."""
    from src.room_solver import solve

    weights = config["reschedule"]["weights"]
    started = time.monotonic()
    deadline = started + float(config["time_limit_sec"])
    everything = frozenset(instance.classes)
    notes, local = [], None
    for label, free in reschedule_scopes_b(instance, base, incidents):
        if free == everything:
            break
        local = solve(instance, config, base=base, change_weights=weights, frozen=everything - free,
                      _deadline=deadline)
        if local.status in ("OPTIMAL", "FEASIBLE"):
            notes.append(Message("I04", "info", f"Bước 1, xếp lại cục bộ trong phạm vi {label}: mở lại "
                                                f"{len(free)}/{len(everything)} lớp, tổng chi phí "
                                                f"{_total_cost(local, weights)}"))
            break
        notes.append(Message("I04", "info", f"Bước 1: phạm vi {label} ({len(free)} lớp) không xếp được "
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
        elif result is not None and result.status == "OPTIMAL":
            # Bước 2 chứng minh được tối ưu trên toàn lịch và lời giải cục bộ không tệ hơn: lời giải cục bộ cũng tối ưu
            notes.append(Message("I04", "info", "Bước 2, giải trên toàn lịch: lời giải cục bộ đã là tối ưu, "
                                                "giữ lời giải cục bộ"))
            local.status = "OPTIMAL"
            result = local
        else:
            notes.append(Message("I04", "info", "Bước 2, giải trên toàn lịch: không tìm được lời giải tốt hơn, "
                                                "giữ lời giải cục bộ"))
            local.status = "FEASIBLE"     # chỉ tối ưu trong phạm vi cục bộ
            result = local
    elif result is None:
        result = SolveResult(status="UNKNOWN", solve_time_sec=0.0)
        notes.append(Message("I04", "warning", "Hết thời gian xếp lại trước khi tìm được lời giải"))
    result.messages = notes + result.messages
    result.solve_time_sec = time.monotonic() - started
    return result


# ---------------------------------------------------------------- so sánh hai lịch

def _view(s: dict) -> dict:
    return {"session_id": s["session_id"], "weekday": s["weekday"], "period": s["period"], "room_id": s["room_id"]}


def diff_timetables(old: dict, new: dict) -> tuple[list[dict], dict]:
    """So sánh hai nội dung timetable.json theo từng lớp.

    Buổi cùng ca được ghép trước (khác phòng là "rooms", tức B-R2); các buổi còn lại ghép theo thứ tự thời gian
    ("time", tức B-R1). Buổi thừa ở lịch mới là "added", thừa ở lịch cũ là "removed". Buổi không đổi không có
    trong danh sách. Mỗi thay đổi có đúng một loại.
    """
    by_class: dict[str, tuple[list, list]] = {}
    for key, table in ((0, old), (1, new)):
        for s in table.get("sessions", []):
            by_class.setdefault(s["class_id"], ([], []))[key].append(s)
    lecturer_of = {s["class_id"]: s.get("lecturer_id") for t in (old, new) for s in t.get("sessions", [])}
    changes = []
    for k in sorted(by_class):
        olds, news = by_class[k]
        a = {(s["weekday"], s["period"]): s for s in olds}
        b = {(s["weekday"], s["period"]): s for s in news}
        for t in sorted(a.keys() & b.keys()):
            o, n = a.pop(t), b.pop(t)
            if o["room_id"] != n["room_id"]:
                changes.append({"class_id": k, "kinds": ["rooms"], "old": _view(o), "new": _view(n)})
        rest_old, rest_new = [a[t] for t in sorted(a)], [b[t] for t in sorted(b)]
        for o, n in zip(rest_old, rest_new):
            changes.append({"class_id": k, "kinds": ["time"], "old": _view(o), "new": _view(n)})
        for o in rest_old[len(rest_new):]:
            changes.append({"class_id": k, "kinds": ["removed"], "old": _view(o), "new": None})
        for n in rest_new[len(rest_old):]:
            changes.append({"class_id": k, "kinds": ["added"], "old": None, "new": _view(n)})

    def count(kind):
        return sum(kind in ch["kinds"] for ch in changes)

    classes = {ch["class_id"] for ch in changes}
    summary = {
        "sessions_moved": count("time"),
        "sessions_room_changed": count("rooms"),
        "sessions_added": count("added"),
        "sessions_removed": count("removed"),
        "classes_affected": len(classes),
        "lecturers_affected": len({lecturer_of[k] for k in classes if lecturer_of.get(k)}),
    }
    return changes, summary


# ---------------------------------------------------------------- xếp lại

def reschedule_b(data_dir: str, base: Union[str, dict], incidents: list[dict], config_path: Optional[str] = None,
                 out_path: Optional[str] = None) -> dict:
    """Xếp lại lịch học sau sự cố và trả về nội dung retimetable.json (data_schema mục 9.11).

    base là đường dẫn timetable.json của lịch cũ, hoặc chính nội dung đó (dict). Kết quả có thêm "changes" (các
    buổi bị đổi) và "reschedule" (tóm tắt).
    """
    from src.diagnose_b import diagnose_b

    dataset = os.path.basename(os.path.normpath(data_dir))
    loaded = load_instance_b(data_dir, config_path)
    messages = list(loaded.messages)
    config = dict(loaded.config, strategy="single")
    config["time_limit_sec"] = config["reschedule"]["time_limit_sec"]
    instance = loaded.instance
    base_name = os.path.basename(base) if isinstance(base, str) else "(lịch đang mở)"
    base_sol, applied, base_json = None, [], None
    if loaded.ok:
        if isinstance(base, dict):
            base_json = base
        else:
            try:
                with open(base, encoding="utf-8-sig") as f:
                    base_json = json.load(f)
            except (OSError, UnicodeError, json.JSONDecodeError) as e:
                messages.append(Message("I03", "error", f"Không đọc được lịch cũ: {e}"))
        if base_json is not None:
            base_sol = base_solution_b(instance, base_json, messages)
        applied = apply_incidents_b(instance, incidents, messages)
        if base_sol is not None:
            new_classes = sorted(set(instance.classes) - {s.class_id for s in base_sol.sessions})
            if new_classes:
                messages.append(Message("I04", "info", f"Lớp mới chưa có trong lịch cũ: {', '.join(new_classes)}"))
    has_error = any(m.level == "error" for m in messages)

    result = None
    if not has_error:
        result = _solve_in_scopes(instance, config, base_sol, applied)
        if result.status == "INFEASIBLE":
            result.messages += diagnose_b(instance, config)
    table = build_timetable(instance if not has_error else None, config, messages, result, dataset)

    changes, summary = [], None
    if base_json is not None and table["sessions"]:
        changes, summary = diff_timetables(base_json, table)
    weights = config["reschedule"]["weights"]
    change_penalties = result.change_penalties if result else None
    table["changes"] = changes
    table["reschedule"] = {
        "base_timetable": base_name,
        "incidents": applied,
        "change_penalties": change_penalties,
        "change_cost": (sum(weights[k] * v for k, v in change_penalties.items()) if change_penalties else None),
        "summary": summary,
    }
    out_path = out_path or os.path.join("output", dataset, "retimetable.json")
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    write_schedule(table, out_path)
    return table


_KIND_LABELS = {"time": "dời ca", "rooms": "đổi phòng", "added": "thêm buổi", "removed": "bỏ buổi"}


def _where(view: Optional[dict]) -> str:
    return "-" if view is None else f"Thứ {view['weekday']} ca {view['period']} ({view['room_id']})"


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="backslashreplace")
    parser = argparse.ArgumentParser(description="Xếp lại lịch học khi có sự cố (bài toán B)")
    parser.add_argument("--data", required=True, help="Thư mục bộ dữ liệu, ví dụ data/toy_b")
    parser.add_argument("--base", required=True, help="File timetable.json của lịch cũ")
    parser.add_argument("--incident", action="append", default=[], metavar="LOẠI,MÃ,THỨ[,CA]",
                        help="Ví dụ room,G2-LAB1,6,4 hoặc lecturer,GV02,4 (cả Thứ 4)")
    parser.add_argument("--config", default=None, help="Mặc định configs/problem_b.json nếu có")
    parser.add_argument("--out", default=None, help="Mặc định output/<tên bộ dữ liệu>/retimetable.json")
    args = parser.parse_args()
    try:
        incidents = [parse_incident_b(text) for text in args.incident]
    except ValueError as e:
        print(e)
        return 2
    config_path = args.config
    if config_path is None and os.path.exists("configs/problem_b.json"):
        config_path = "configs/problem_b.json"
    table = reschedule_b(args.data, args.base, incidents, config_path, args.out)
    for m in table["messages"]:
        print(f"[{m['level']}] {m['code']}: {m['message']}")
    print(f"Trạng thái: {table['status']}, mục tiêu: {table['objective']}, "
          f"thời gian xếp lại: {table['solve_time_sec']:.2f} giây, vi phạm: {len(table['violations'])}")
    info = table["reschedule"]
    if info["summary"]:
        s = info["summary"]
        print(f"Thay đổi: {s['sessions_moved']} buổi dời ca, {s['sessions_room_changed']} buổi đổi phòng, "
              f"{s['sessions_added']} buổi thêm; {s['classes_affected']} lớp, {s['lecturers_affected']} giảng viên "
              f"bị ảnh hưởng")
    for ch in table["changes"]:
        print(f"  {ch['class_id']}: {_KIND_LABELS[ch['kinds'][0]]}: {_where(ch['old'])} -> {_where(ch['new'])}")
    return 0 if table["status"] in ("OPTIMAL", "FEASIBLE") and not table["violations"] else 1


if __name__ == "__main__":
    sys.exit(main())
