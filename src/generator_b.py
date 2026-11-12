"""Sinh medium_b/large_b theo schema 9.12, dùng nguyên file tài nguyên A.

Dựng lịch chứng kiến khả thi trước, rồi lấy ca bận ngoài lịch đó; lịch này
không được truyền làm hint cho solver. Seed chi phối toàn bộ việc sinh.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import csv
import hashlib
import json
from pathlib import Path
import random
import shutil


def generate_b(size, seed, out_dir, source_dir=None, force=False):
    from src.generator import _write_csv
    from src.data_loader_b import load_instance_b
    if size not in ("medium_b", "large_b"):
        raise ValueError("size phải là medium_b hoặc large_b")
    out = Path(out_dir)
    if out.name in ("toy", "toy_b") and not force:
        raise ValueError("Không ghi đè bộ tham chiếu toy/toy_b")
    source = Path(source_dir) if source_dir else Path(__file__).resolve().parents[1] / "data" / size[:-2]
    if out.resolve() == source.resolve():
        raise ValueError("Thư mục B phải khác thư mục nguồn A")
    def read(name):
        with (source / name).open(encoding="utf-8-sig", newline="") as f:
            return list(csv.DictReader(f))
    rooms, lecturers = read("rooms.csv"), read("lecturers.csv")
    room_caps = {r["room_id"]: int(r["num_computers"] if r["room_type"] == "lab" else r["seats"])
                 for r in rooms}
    lab_ids = [r["room_id"] for r in rooms if r["room_type"] == "lab" and room_caps[r["room_id"]] > 0]
    normal_ids = [r["room_id"] for r in rooms if r["room_type"] == "normal" and room_caps[r["room_id"]] > 0]
    if not lab_ids or not normal_ids or not lecturers:
        raise ValueError("Nguồn phải có phòng thường, phòng máy và giảng viên")
    rng = random.Random(f"{size}:{seed}")
    count, group_count = (60, 8) if size == "medium_b" else (120, 16)
    slots = [(d, p) for d in range(2, 8) for p in range(1, 5)]
    # Mỗi phòng bận 2/24 ca. Tải phòng máy mục tiêu 72% công suất còn lại.
    lab_target = round(0.72 * len(lab_ids) * 22)
    lab_count = count // 2
    if lab_target < lab_count or lab_target > 2 * lab_count:
        raise ValueError("Nguồn phòng không phù hợp quy mô: tải mục tiêu cần 1–2 buổi/lớp máy")
    lab_sessions = [1] * lab_count
    for i in rng.sample(range(lab_count), lab_target - lab_count):
        lab_sessions[i] += 1
    classes = []
    groups = []
    lab_index = 0
    # count/4 học phần có LT + TH1 + TH2; count/4 học phần chỉ LT.
    for i in range(count // 2):
        course = f"B{i + 1:03d}"
        pair = i % (group_count // 2)
        children = [f"K68-N{pair + 1:02d}-{j}" for j in (1, 2)]
        split = i < count // 4
        sizes = [rng.randint(12, min(room_caps[r] for r in lab_ids)) for _ in (1, 2)]
        # Một phần lớp lớn hơn phòng máy nhỏ nhất: dự phòng còn phụ thuộc đủ máy.
        if split and i % 4 == 0:
            sizes[0] = rng.randint(min(room_caps[r] for r in lab_ids), max(room_caps[r] for r in lab_ids))
        lt_size = sum(sizes) if split else rng.randint(35, min(90, max(room_caps[r] for r in normal_ids)))
        classes.append({"class_id": course + "-LT", "course_id": course,
                        "class_name": f"Học phần {i + 1} (lý thuyết)", "needs_lab": 0,
                        "size": lt_size, "sessions_per_week": 1 + (rng.random() < 0.4),
                        "groups": children})
        if split:
            for j in range(2):
                classes.append({"class_id": course + f"-TH{j + 1}", "course_id": course,
                                "class_name": f"Học phần {i + 1} (thực hành {j + 1})", "needs_lab": 1,
                                "size": sizes[j], "sessions_per_week": lab_sessions[lab_index],
                                "groups": [children[j]]})
                lab_index += 1
    # Đặt lớp khó trước, có thử lại toàn bộ để không phụ thuộc may rủi greedy.
    witness = None
    for attempt in range(100):
        room_used, teacher_used, group_used = defaultdict(set), defaultdict(set), defaultdict(set)
        load = Counter()
        assignments = {}
        candidate_order = sorted(classes, key=lambda c: (-c["needs_lab"], -c["size"], -c["sessions_per_week"], c["class_id"]))
        success = True
        for cls in candidate_order:
            suitable = [r for r in (lab_ids if cls["needs_lab"] else normal_ids) if room_caps[r] >= cls["size"]]
            teachers = [g["lecturer_id"] for g in lecturers]
            rng.shuffle(teachers)
            teachers.sort(key=lambda g: load[g])
            assigned = None
            for g in teachers:
                chosen = []
                days = set()
                options = [(r, t) for r in suitable for t in slots]
                rng.shuffle(options)
                options.sort(key=lambda rt: len(room_used[rt[0]]))
                for r, t in options:
                    if (t in room_used[r] or t in teacher_used[g] or
                            any(t in group_used[h] for h in cls["groups"]) or
                            t[0] in days):
                        continue
                    # Giữ ít nhất 2 ca chưa dùng ở mỗi phòng để sinh ca bảo trì.
                    if len(room_used[r]) + sum(rr == r for rr, _ in chosen) >= 22:
                        continue
                    chosen.append((r, t))
                    days.add(t[0])
                    if len(chosen) == cls["sessions_per_week"]:
                        assigned = (g, chosen)
                        break
                if assigned:
                    break
            if assigned is None:
                success = False
                break
            g, chosen = assigned
            cls["lecturer_id"] = g
            load[g] += len(chosen)
            assignments[cls["class_id"]] = chosen
            for r, t in chosen:
                room_used[r].add(t)
                teacher_used[g].add(t)
                for h in cls["groups"]:
                    group_used[h].add(t)
        if success:
            witness = assignments
            break
    if witness is None:
        raise RuntimeError("Không dựng được lịch chứng kiến sau 100 lần thử")
    busy_rows, pref_rows = [], []
    for kind, ids, used in (("room", sorted(room_caps), room_used),
                            ("lecturer", sorted(g["lecturer_id"] for g in lecturers), teacher_used)):
        for rid in ids:
            free = [t for t in slots if t not in used[rid]]
            busy = rng.sample(free, min(2, len(free)))
            for d, p in sorted(busy):
                busy_rows.append([kind, rid, d, p, "Bảo trì định kỳ" if kind == "room" else "Lịch công tác"])
            if kind == "lecturer":
                choices = [t for t in slots if t not in busy]
                for d, p in sorted(rng.sample(choices, min(3, len(choices)))):
                    pref_rows.append([rid, d, p, "Nguyện vọng giờ dạy"])
    out.mkdir(parents=True, exist_ok=True)
    for name in ("rooms.csv", "lecturers.csv"):
        shutil.copyfile(source / name, out / name)
    def write(name, header, rows):
        _write_csv(str(out / name), header, rows)
    write("week_slots.csv", ["weekday", "period"], slots)
    columns = ["class_id", "class_name", "course_id", "needs_lab", "size", "sessions_per_week", "lecturer_id"]
    write("classes.csv", columns, [[int(c[x]) if x == "sessions_per_week" else c[x] for x in columns]
                                   for c in sorted(classes, key=lambda c: c["class_id"])])
    for cls in classes:
        groups.extend((cls["class_id"], h) for h in cls["groups"])
    write("class_groups.csv", ["class_id", "group_id"], sorted(groups))
    write("week_unavailability.csv", ["resource_type", "resource_id", "weekday", "period", "note"], busy_rows)
    write("preferences.csv", ["lecturer_id", "weekday", "period", "note"], pref_rows)
    loaded = load_instance_b(str(out))
    if not loaded.ok:
        raise RuntimeError([m.to_dict() for m in loaded.messages])
    inst = loaded.instance
    utilization = sum(c.sessions for c in inst.classes.values() if c.needs_lab) / sum(inst.labs_available(t) for t in inst.slots)
    if not 0.60 <= utilization <= 0.85:
        raise RuntimeError(f"Tải phòng máy ngoài 60–85%: {utilization}")
    # Kiểm tra độc lập lịch chứng kiến, không đưa vào solver hoặc lưu trong data.
    from src.validator_b import validate_b
    table = {"sessions": [{"session_id": f"{k}@T{t[0]}_{t[1]}", "class_id": k,
                             "room_id": r, "weekday": t[0], "period": t[1]}
                            for k, choices in witness.items() for r, t in choices]}
    if validate_b(inst, table):
        raise RuntimeError("Lịch chứng kiến không hợp lệ")
    stats = {"size": size, "seed": seed, "classes": len(classes), "groups": group_count,
             "rooms": len(rooms), "lab_rooms": len(lab_ids), "lecturers": len(lecturers),
             "num_sessions": sum(c.sessions for c in inst.classes.values()),
             "lab_sessions": lab_target, "room_utilization_lab": utilization,
             "resource_sha256": {name: hashlib.sha256((source / name).read_bytes()).hexdigest()
                                 for name in ("rooms.csv", "lecturers.csv")},
             "pb_messages": [m.to_dict() for m in loaded.messages]}
    (out / "generation.json").write_text(json.dumps(stats, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return stats
