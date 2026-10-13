"""Turn a solved timetable into things people actually use: a console summary,
flat CSV, and a printable, interactive HTML routine with Master Routine and Teacher Search."""

from __future__ import annotations

import csv
import html
import re
from collections import defaultdict
from pathlib import Path

from .models import Problem, Teacher
from .scheduler import Solution

# ----------------------------------------------------------------- Light Theme Palette
# Standard, elegant academic light theme colors
BG_PAGE = "#F8FAFC"
BG_CARD = "#FFFFFF"
BG_HEADER = "#F1F5F9"
BG_HEADER_ALT = "#E2E8F0"
BORDER = "#CBD5E1"
BORDER_DARK = "#94A3B8"
TEXT_MAIN = "#0F172A"
TEXT_MUTED = "#334155"
TEXT_DIM = "#64748B"
PRIMARY = "#1D4ED8"           # KUET academic royal blue
PRIMARY_HOVER = "#1E40AF"
PRIMARY_LIGHT = "#EFF6FF"
PRIMARY_BORDER = "#93C5FD"
LAB_BG = "#FEF9C3"            # Standard academic soft warm tint for sessionals / labs
LAB_BORDER = "#D97706"        # Amber accent line
LAB_TEXT = "#92400E"
THEORY_BG = "#FFFFFF"
BREAK_BG = "#F8FAFC"
BREAK_STRIPE = "rgba(148, 163, 184, 0.25)"
BREAK_TEXT = "#64748B"

CURRICULUM_ORDER = ["1-1", "1-2", "2-1", "2-2", "3-1", "3-2", "4-1", "4-2"]


def _curriculum_key(batch_id: str) -> int:
    try:
        return CURRICULUM_ORDER.index(batch_id)
    except ValueError:
        return 99


def format_display_group(group: str | None, section: str = "") -> str:
    """Format group label for display in KUET routines.

    In KUET routines, groups are designated by section letter followed by group number:
    - Section A: A1, A2, A1/A2
    - Section B: B1, B2, B1/B2
    instead of generic G1, G2, G1/G2.
    """
    if not group:
        return ""
    g = str(group).strip()
    if not section:
        return g
    sec = section.strip().upper()
    return re.sub(r"\bG(\d+)\b", rf"{sec}\1", g)


# ----------------------------------------------------------------- console


def console_summary(problem: Problem, solution: Solution) -> str:
    grid = problem.grid
    lines = [
        f"status        : {solution.status}",
        f"objective     : {solution.objective}  (lower bound {solution.best_bound})",
        f"solve time    : {solution.wall_seconds:.1f}s",
        f"events placed : {len(solution.assignments)} / {len(problem.events)}",
        "",
        "penalty breakdown",
    ]
    if not solution.penalties:
        lines.append("  (no soft constraints active)")
    for name, value in sorted(solution.penalties.items()):
        weight = problem.options["weights"].get(name, 0)
        lines.append(f"  {name:<24} {value:>5}  x{weight} = {value * weight}")

    if solution.unsynced_courses:
        lines += [
            "",
            "labs auto-staggered (not enough rooms of that kind to sync both groups):",
        ]
        for c in solution.unsynced_courses:
            lines.append(f"  {c}")

    # Where the week actually sits.
    per_day = defaultdict(int)
    for a in solution.assignments:
        per_day[grid.day_of(a.start)] += a.event.length
    lines += ["", "teaching load by day (period-slots)"]
    for d, day in enumerate(grid.days):
        lines.append(f"  {day:<10} {per_day[d]}")

    return "\n".join(lines)


# --------------------------------------------------------------------- CSV


def write_csv(problem: Problem, solution: Solution, path: str | Path) -> Path:
    grid = problem.grid
    path = Path(path)
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(
            [
                "day", "start_period", "start_time", "end_time", "periods",
                "batch", "section", "group", "course_code", "course_title",
                "kind", "room", "teachers",
            ]
        )
        rows = sorted(
            solution.assignments,
            key=lambda a: (
                _curriculum_key(a.event.batch_id),
                a.start,
                a.event.section,
                a.event.group or "",
            ),
        )
        for a in rows:
            ev = a.event
            d, p = grid.day_of(a.start), grid.period_of(a.start)
            end_p = p + ev.length - 1
            clean_code = ev.course.code.replace(" ", "").upper()
            is_project = clean_code in ("CSE3200", "CSE4000") or clean_code.startswith("CSE4000")
            if is_project:
                t_str = ""
                room_str = ""
                disp_code = "CSE 3200" if "3200" in clean_code else "CSE 4000"
            elif ev.is_shared:
                t_str = "/".join(problem.teachers[t].name for t in ev.teacher_ids if t in problem.teachers)
                room_str = problem.rooms[a.room_id].name
                disp_code = ev.course.code
            elif ev.is_lab:
                t_str = " + ".join(problem.teachers[t].name for t in ev.teacher_ids if t in problem.teachers)
                room_str = problem.rooms[a.room_id].name
                disp_code = ev.course.code
            else:
                t_str = ", ".join(problem.teachers[t].name for t in ev.teacher_ids if t in problem.teachers)
                room_str = problem.rooms[a.room_id].name
                disp_code = ev.course.code

            grp = format_display_group(ev.group, ev.section)
            if ev.paired_event_id is not None:
                grp = f"{grp} (0.75cr alt)" if grp else "(0.75cr alt)"

            w.writerow(
                [
                    grid.days[d],
                    grid.periods[p].name,
                    grid.periods[p].start,
                    grid.periods[end_p].end,
                    ev.length,
                    ev.batch_id,
                    ev.section,
                    grp,
                    disp_code,
                    ev.course.title,
                    ev.course.kind,
                    room_str,
                    t_str,
                ]
            )
    return path


# -------------------------------------------------------------------- HTML Grid Helpers


def _section_grid(problem: Problem, solution: Solution, batch_id: str, section: str):
    """cells[day][period] -> None | {'span': n, 'entries': [...]}, plus 'skip'."""
    grid = problem.grid
    cells: list[list] = [[None] * grid.n_periods for _ in range(grid.n_days)]

    relevant = [
        a
        for a in solution.assignments
        if a.event.batch_id == batch_id and a.event.section == section
    ]
    merged: dict[tuple, dict] = {}
    for a in relevant:
        ev = a.event
        d, p = grid.day_of(a.start), grid.period_of(a.start)
        clean_code = ev.course.code.replace(" ", "").upper()
        is_project = clean_code in ("CSE3200", "CSE4000") or clean_code.startswith("CSE4000")

        if ev.paired_event_id is not None:
            key = (d, p, "paired_075_lab")
        elif is_project:
            key = (d, p, "project", ev.eid)
        elif ev.is_lab:
            key = (d, p, ev.course.code)
        else:
            key = (d, p, ev.course.code, ev.eid)

        bucket = merged.setdefault(
            key,
            {"day": d, "period": p, "span": ev.length, "lab": ev.is_lab, "entries": []},
        )
        if is_project:
            disp_code = "CSE 3200" if "3200" in clean_code else "CSE 4000"
            bucket["entries"].append(
                {
                    "code": disp_code,
                    "group": "",
                    "room": "",
                    "teachers": "",
                    "is_project": True,
                }
            )
            continue

        if ev.is_shared:
            t_str = "/".join(problem.teachers[t].short for t in ev.teacher_ids if t in problem.teachers)
        elif ev.is_lab:
            t_str = "+".join(problem.teachers[t].short for t in ev.teacher_ids if t in problem.teachers)
        else:
            t_str = ", ".join(problem.teachers[t].short for t in ev.teacher_ids if t in problem.teachers)

        grp_label = format_display_group(ev.group, ev.section)
        if ev.paired_event_id is not None:
            grp_label = f"{grp_label} (0.75cr alt)" if grp_label else "(0.75cr alt)"

        bucket["entries"].append(
            {
                "code": ev.course.code,
                "group": grp_label,
                "room": problem.rooms[a.room_id].name,
                "teachers": t_str,
            }
        )

    for bucket in merged.values():
        if bucket["lab"] and len(bucket["entries"]) > 1:
            first = bucket["entries"][0]
            if all(e["code"] == first["code"] and e["room"] == first["room"] for e in bucket["entries"]):
                all_t = []
                for e in bucket["entries"]:
                    for t in e["teachers"].split("+"):
                        t_clean = t.strip()
                        if t_clean and t_clean not in all_t:
                            all_t.append(t_clean)
                first["teachers"] = "+".join(all_t)
                first["group"] = ""
                bucket["entries"] = [first]

        d, p = bucket["day"], bucket["period"]
        cells[d][p] = bucket
        for k in range(1, bucket["span"]):
            cells[d][p + k] = "skip"
    return cells


def _teacher_grid(problem: Problem, solution: Solution, teacher_id: str):
    grid = problem.grid
    cells: list[list] = [[None] * grid.n_periods for _ in range(grid.n_days)]
    for a in solution.assignments:
        if teacher_id not in a.event.teacher_ids:
            continue
        ev = a.event
        d, p = grid.day_of(a.start), grid.period_of(a.start)
        disp_grp = format_display_group(ev.group, ev.section)
        if disp_grp:
            grp_tag = f"{ev.batch_id} {disp_grp}" if disp_grp.startswith(ev.section) else f"{ev.batch_id} {ev.section}{disp_grp}"
        else:
            grp_tag = f"{ev.batch_id} {ev.section}"
        cells[d][p] = {
            "day": d,
            "period": p,
            "span": ev.length,
            "lab": ev.is_lab,
            "entries": [
                {
                    "code": ev.course.code,
                    "group": grp_tag,
                    "room": problem.rooms[a.room_id].name,
                    "teachers": "",
                }
            ],
        }
        for k in range(1, ev.length):
            cells[d][p + k] = "skip"
    return cells


def _render_table(problem: Problem, cells) -> str:
    grid = problem.grid
    break_after = {grid.period_index(b.after_period): b for b in problem.grid.breaks}

    head = ["<tr><th class='corner'>Day</th>"]
    for i, per in enumerate(grid.periods):
        head.append(
            f"<th><span class='pname'>{per.name}</span>"
            f"<span class='ptime'>{html.escape(per.label)}</span></th>"
        )
        if i in break_after:
            br = break_after[i]
            head.append(
                f"<th class='brk'><span>{html.escape(br.name)}</span>"
                f"<span class='ptime'>{br.start}-{br.end}</span></th>"
            )
    head.append("</tr>")

    body = []
    for d, day in enumerate(grid.days):
        row = [f"<tr><th class='day'>{html.escape(day)}</th>"]
        for p in range(grid.n_periods):
            cell = cells[d][p]
            if cell != "skip":
                if cell is None:
                    row.append("<td class='free'></td>")
                else:
                    span = cell["span"]
                    klass = "lab" if cell["lab"] else "theory"
                    inner = []
                    for e in cell["entries"]:
                        tag = f"<b>{html.escape(e['code'])}</b>"
                        if e.get("is_project"):
                            inner.append(f"<div class='ent'>{tag}</div>")
                            continue
                        if e["group"]:
                            grp_str = f"({e['group']})" if not e["group"].startswith("(") else e["group"]
                            tag += f" <span class='grp'>{html.escape(grp_str)}</span>"
                        meta = " · ".join(x for x in (e["room"], e["teachers"]) if x)
                        inner.append(
                            f"<div class='ent'>{tag}<span class='meta'>"
                            f"{html.escape(meta)}</span></div>"
                        )
                    row.append(
                        f"<td class='{klass}' colspan='{span}'>{''.join(inner)}</td>"
                    )
            if p in break_after:
                row.append("<td class='brk'></td>")
        row.append("</tr>")
        body.append("".join(row))

    return (
        "<table class='routine'><thead>"
        + "".join(head)
        + "</thead><tbody>"
        + "".join(body)
        + "</tbody></table>"
    )


# ----------------------------------------------------------------- Master Routine Tables


# Known KUET CSE faculty seniority order matching sample routine Image 1
CSE_SENIORITY_ORDER = [
    "mma_hashem",
    "km_azharul_hasan",
    "kazi_md_rokibul_alam",
    "muhammad_sheikh_sadi",
    "muhammad_aminul_haque",
    "sk_md_masudul_ahsan",
    "al_mahmud",
    "sk_imran_hossain",
    "md_abdus_salim_mollah",
    "md_abdul_awal",
    "md_milon_islam",
    "dola_das",
    "kazi_saeed_alam",
    "md_repon_islam",
    "md_sakhawat_hossain",
    "md_nazirulhasan_shawon",
    "md_badiuzzaman_shuvo",
    "kaniz_fatema_isha",
    "safin_ahmmed",
    "md_tajmilur_rahman",
    "nabil_faiyaz_sadi",
    "subah_nawar",
    "waliul_islam_sumon",
    "sadia_islam",
    "ehsanul_karim",
    "md_mubtashim_abrar_nihal",
    "lamisa_bintee_mizan_deya",
]


def _get_sorted_teachers(problem: Problem, busy_teacher_ids: set[str]) -> list[Teacher]:
    """Sort teachers with CSE faculty first in seniority order, followed by other departments."""
    dept_order = {"CSE": 0, "ECE": 1, "EEE": 2, "ME": 3, "MATH": 4, "PHY": 5, "HUM": 6}
    cse_rank = {tid: idx for idx, tid in enumerate(CSE_SENIORITY_ORDER)}

    def sort_key(t: Teacher):
        d_val = dept_order.get(t.department, 99)
        if t.department == "CSE":
            c_val = cse_rank.get(t.id, 500)
            return (0, c_val, t.name)
        return (1, d_val, t.name)

    teachers = [problem.teachers[tid] for tid in busy_teacher_ids if tid in problem.teachers]
    teachers.sort(key=sort_key)
    return teachers


def _render_master_teachers_table(problem: Problem, solution: Solution, teachers: list[Teacher]) -> str:
    """Render comprehensive Master Routine table matching Image 1:
    SL No., Teacher Name, and for each Day: Periods 1-9 with precise times."""
    grid = problem.grid

    # Pre-build teacher grids: t_grid[teacher_id][day][period] -> cell
    t_grids = {t.id: [[None] * grid.n_periods for _ in range(grid.n_days)] for t in teachers}
    for a in solution.assignments:
        ev = a.event
        d, p = grid.day_of(a.start), grid.period_of(a.start)
        disp_grp = format_display_group(ev.group, ev.section)
        for tid in ev.teacher_ids:
            if tid in t_grids:
                t_grids[tid][d][p] = {
                    "span": ev.length,
                    "code": ev.course.code,
                    "batch": ev.batch_id,
                    "section": ev.section,
                    "group": disp_grp,
                    "room": problem.rooms[a.room_id].name,
                    "lab": ev.is_lab,
                }
                for k in range(1, ev.length):
                    if p + k < grid.n_periods:
                        t_grids[tid][d][p + k] = "skip"

    # Header Row 1: SL No, Teacher Name, Days (SUNDAY, MONDAY, TUESDAY, WEDNESDAY, THURSDAY)
    head_r1 = [
        "<tr>",
        "<th rowspan='2' class='m-th-sl'>SL<br>No.</th>",
        "<th rowspan='2' class='m-th-teacher'>Teacher Name</th>",
    ]
    for day in grid.days:
        head_r1.append(f"<th colspan='{grid.n_periods}' class='m-th-day'>{html.escape(day.upper())}</th>")
    head_r1.append("</tr>")

    # Header Row 2: Periods 1 to 9 with times
    head_r2 = ["<tr>"]
    for day_idx, day in enumerate(grid.days):
        for p, per in enumerate(grid.periods):
            # Mark divider line after P3 and P6
            border_cls = " brk-sep" if p in (2, 5) else ""
            head_r2.append(
                f"<th class='m-th-per{border_cls}'>"
                f"<span class='m-pnum'>{p + 1}</span>"
                f"<span class='m-ptime'>{per.start} to {per.end}</span>"
                f"</th>"
            )
    head_r2.append("</tr>")

    # Body: 1 row per teacher
    body = []
    for sl, t in enumerate(teachers, start=1):
        dept_cls = f"badge-{t.department.lower()}"
        row = [
            f"<tr data-teacher-id='{html.escape(t.id)}' data-dept='{html.escape(t.department)}' data-name='{html.escape(t.name.lower())}'>",
            f"<td class='m-td-sl'>{sl}</td>",
            f"<td class='m-td-teacher'>"
            f"<div class='m-tname'>{html.escape(t.name)}</div>"
            f"<div class='m-tmeta'><span class='m-tcode'>{html.escape(t.short)}</span> <span class='badge {dept_cls}'>{html.escape(t.department)}</span></div>"
            f"</td>",
        ]

        for d in range(grid.n_days):
            p = 0
            while p < grid.n_periods:
                cell = t_grids[t.id][d][p]
                if cell == "skip":
                    p += 1
                    continue
                elif cell is None:
                    border_cls = " brk-sep" if p in (2, 5) else ""
                    row.append(f"<td class='m-free{border_cls}'></td>")
                    p += 1
                else:
                    span = cell["span"]
                    end_p = p + span - 1
                    border_cls = " brk-sep" if end_p in (2, 5) else ""
                    klass = "m-cell-lab" if cell["lab"] else "m-cell-theory"
                    grp = cell["group"]
                    if grp:
                        tag_meta = f"{cell['batch']} {grp}" if grp.startswith(cell["section"]) else f"{cell['batch']} {cell['section']} ({grp})"
                    else:
                        tag_meta = f"{cell['batch']} {cell['section']}"

                    row.append(
                        f"<td class='{klass}{border_cls}' colspan='{span}'>"
                        f"<div class='m-code'>{html.escape(cell['code'])}</div>"
                        f"<div class='m-meta'>{html.escape(tag_meta)}</div>"
                        f"</td>"
                    )
                    p += span
        row.append("</tr>")
        body.append("".join(row))

    return (
        "<div class='master-table-scroll'>"
        "<table class='master-table' id='table-master-teachers'><thead>"
        + "".join(head_r1)
        + "".join(head_r2)
        + "</thead><tbody>"
        + "".join(body)
        + "</tbody></table>"
        "</div>"
    )


def _render_master_labs_table(problem: Problem, solution: Solution) -> str:
    """Render Labs Master Routine table matching Image 2 upper section."""
    grid = problem.grid

    # Collect lab rooms
    lab_rooms = [
        r for r in problem.rooms.values()
        if r.kind != "theory" or "lab" in r.id.lower() or "103" in r.id or "201" in r.id or "202" in r.id or "305" in r.id
    ]
    # Sort CSE labs first, then others
    lab_rooms.sort(key=lambda r: (0 if "cse" in r.id.lower() or "305" in r.id or "201" in r.id or "202" in r.id or "107" in r.id or "103" in r.id or "104" in r.id else 1, r.name))

    # Pre-index room assignments
    r_grids = {r.id: [[None] * grid.n_periods for _ in range(grid.n_days)] for r in lab_rooms}
    for a in solution.assignments:
        if a.room_id in r_grids:
            ev = a.event
            d, p = grid.day_of(a.start), grid.period_of(a.start)
            t_str = "+".join(problem.teachers[t].short for t in ev.teacher_ids if t in problem.teachers)
            disp_grp = format_display_group(ev.group, ev.section)
            r_grids[a.room_id][d][p] = {
                "span": ev.length,
                "code": ev.course.code,
                "batch": ev.batch_id,
                "section": ev.section,
                "group": disp_grp,
                "teachers": t_str,
            }
            for k in range(1, ev.length):
                if p + k < grid.n_periods:
                    r_grids[a.room_id][d][p + k] = "skip"

    head_r1 = [
        "<tr>",
        "<th rowspan='2' class='m-th-teacher' style='min-width: 220px;'>Laboratory / Facility</th>",
    ]
    for day in grid.days:
        head_r1.append(f"<th colspan='{grid.n_periods}' class='m-th-day'>{html.escape(day.upper())}</th>")
    head_r1.append("</tr>")

    head_r2 = ["<tr>"]
    for day in grid.days:
        for p, per in enumerate(grid.periods):
            border_cls = " brk-sep" if p in (2, 5) else ""
            head_r2.append(
                f"<th class='m-th-per{border_cls}'>"
                f"<span class='m-pnum'>{p + 1}</span>"
                f"<span class='m-ptime'>{per.start}-{per.end}</span>"
                f"</th>"
            )
    head_r2.append("</tr>")

    body = []
    for r in lab_rooms:
        row = [
            f"<tr data-room-id='{html.escape(r.id)}'>",
            f"<td class='m-td-teacher' style='font-weight: 700; color: #1E293B;'>{html.escape(r.name)}</td>",
        ]
        for d in range(grid.n_days):
            p = 0
            while p < grid.n_periods:
                cell = r_grids[r.id][d][p]
                if cell == "skip":
                    p += 1
                    continue
                elif cell is None:
                    border_cls = " brk-sep" if p in (2, 5) else ""
                    row.append(f"<td class='m-free{border_cls}'></td>")
                    p += 1
                else:
                    span = cell["span"]
                    end_p = p + span - 1
                    border_cls = " brk-sep" if end_p in (2, 5) else ""
                    grp_txt = f" ({cell['group']})" if cell["group"] else ""
                    row.append(
                        f"<td class='m-cell-lab{border_cls}' colspan='{span}'>"
                        f"<div class='m-code'>{html.escape(cell['code'])}</div>"
                        f"<div class='m-meta'>{html.escape(cell['batch'])} {html.escape(cell['section'])}{html.escape(grp_txt)} · {html.escape(cell['teachers'])}</div>"
                        f"</td>"
                    )
                    p += span
        row.append("</tr>")
        body.append("".join(row))

    return (
        "<div class='master-table-scroll'>"
        "<table class='master-table' id='table-master-labs'><thead>"
        + "".join(head_r1)
        + "".join(head_r2)
        + "</thead><tbody>"
        + "".join(body)
        + "</tbody></table>"
        "</div>"
    )


def _render_master_batches_table(problem: Problem, solution: Solution) -> str:
    """Render Batches / Sections Master Routine table matching Image 2 lower section."""
    grid = problem.grid

    # All batch sections strictly in CURRICULUM_ORDER
    batch_sections = []
    sorted_batches = sorted(problem.batches.values(), key=lambda b: _curriculum_key(b.id))
    for batch in sorted_batches:
        for sec in batch.sections:
            batch_sections.append((batch.id, batch.name, sec))

    # Pre-build grids
    b_grids = {}
    for bid, bname, sec in batch_sections:
        b_grids[(bid, sec)] = _section_grid(problem, solution, bid, sec)

    head_r1 = [
        "<tr>",
        "<th rowspan='2' class='m-th-teacher' style='min-width: 220px;'>Academic Term & Section</th>",
    ]
    for day in grid.days:
        head_r1.append(f"<th colspan='{grid.n_periods}' class='m-th-day'>{html.escape(day.upper())}</th>")
    head_r1.append("</tr>")

    head_r2 = ["<tr>"]
    for day in grid.days:
        for p, per in enumerate(grid.periods):
            border_cls = " brk-sep" if p in (2, 5) else ""
            head_r2.append(
                f"<th class='m-th-per{border_cls}'>"
                f"<span class='m-pnum'>{p + 1}</span>"
                f"<span class='m-ptime'>{per.start}-{per.end}</span>"
                f"</th>"
            )
    head_r2.append("</tr>")

    body = []
    for bid, bname, sec in batch_sections:
        row = [
            f"<tr data-batch-id='{html.escape(bid)}' data-sec='{html.escape(sec)}'>",
            f"<td class='m-td-teacher'><div style='font-weight: 700; color: #1E293B;'>{html.escape(bname)}</div><div style='font-size: 0.75rem; color: #64748B;'>Section {html.escape(sec)} ({bid})</div></td>",
        ]
        grid_cells = b_grids[(bid, sec)]
        for d in range(grid.n_days):
            p = 0
            while p < grid.n_periods:
                cell = grid_cells[d][p]
                if cell == "skip":
                    p += 1
                    continue
                elif cell is None:
                    border_cls = " brk-sep" if p in (2, 5) else ""
                    row.append(f"<td class='m-free{border_cls}'></td>")
                    p += 1
                else:
                    span = cell["span"]
                    end_p = p + span - 1
                    border_cls = " brk-sep" if end_p in (2, 5) else ""
                    klass = "m-cell-lab" if cell["lab"] else "m-cell-theory"
                    entries_html = []
                    for e in cell["entries"]:
                        if e.get("is_project"):
                            entries_html.append(f"<div class='m-code'>{html.escape(e['code'])}</div>")
                            continue
                        grp_txt = f" ({e['group']})" if e["group"] and not e["group"].startswith("(") else (f" {e['group']}" if e["group"] else "")
                        meta_txt = " · ".join(x for x in (e["room"], e["teachers"]) if x)
                        entries_html.append(
                            f"<div class='m-code'>{html.escape(e['code'])}{html.escape(grp_txt)}</div>"
                            f"<div class='m-meta'>{html.escape(meta_txt)}</div>"
                        )
                    row.append(
                        f"<td class='{klass}{border_cls}' colspan='{span}'>"
                        f"{''.join(entries_html)}"
                        f"</td>"
                    )
                    p += span
        row.append("</tr>")
        body.append("".join(row))

    return (
        "<div class='master-table-scroll'>"
        "<table class='master-table' id='table-master-batches'><thead>"
        + "".join(head_r1)
        + "".join(head_r2)
        + "</thead><tbody>"
        + "".join(body)
        + "</tbody></table>"
        "</div>"
    )


# ----------------------------------------------------------------- CSS & JS


CSS = f"""
:root {{
  --bg-page: {BG_PAGE};
  --bg-card: {BG_CARD};
  --bg-header: {BG_HEADER};
  --bg-header-alt: {BG_HEADER_ALT};
  --border: {BORDER};
  --border-dark: {BORDER_DARK};
  --text-main: {TEXT_MAIN};
  --text-muted: {TEXT_MUTED};
  --text-dim: {TEXT_DIM};
  --primary: {PRIMARY};
  --primary-hover: {PRIMARY_HOVER};
  --primary-light: {PRIMARY_LIGHT};
  --primary-border: {PRIMARY_BORDER};
  --lab-bg: {LAB_BG};
  --lab-border: {LAB_BORDER};
  --lab-text: {LAB_TEXT};
  --theory-bg: {THEORY_BG};
  --break-bg: {BREAK_BG};
  --break-text: {BREAK_TEXT};
}}

* {{ box-sizing: border-box; }}

body {{
  margin: 0;
  padding: 1.5rem 1rem 3.5rem;
  background: var(--bg-page);
  color: var(--text-main);
  font-family: "Source Sans 3", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, system-ui, sans-serif;
  font-size: 14px;
  line-height: 1.5;
}}

.wrap {{
  max-width: 1750px;
  margin: 0 auto;
  background: var(--bg-card);
  border: 1px solid #E2E8F0;
  border-radius: 10px;
  box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05), 0 2px 4px -1px rgba(0, 0, 0, 0.03);
  padding: 1.75rem 2rem 3rem;
}}

/* Header */
header.app-masthead {{
  border-bottom: 2px solid var(--primary);
  padding-bottom: 1.25rem;
  margin-bottom: 1.5rem;
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 1.25rem;
}}

.masthead-titles h1 {{
  font-family: "Source Serif 4", Georgia, serif;
  font-weight: 700;
  font-size: 1.85rem;
  margin: 0 0 0.25rem;
  color: var(--text-main);
  letter-spacing: -0.015em;
}}

.masthead-titles .sub {{
  color: var(--text-dim);
  margin: 0;
  font-size: 0.95rem;
  font-weight: 500;
}}

.stats {{
  display: flex;
  flex-wrap: wrap;
  gap: 0.75rem;
}}

.stat {{
  background: var(--bg-page);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 0.45rem 0.85rem;
  text-align: center;
  min-width: 80px;
}}

.stat b {{
  display: block;
  font-size: 1.35rem;
  color: var(--primary);
  font-weight: 700;
  line-height: 1.1;
}}

.stat span {{
  color: var(--text-dim);
  font-size: 0.72rem;
  text-transform: uppercase;
  font-weight: 600;
}}

/* Top Navigation Tabs */
nav.primary-nav {{
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.4rem;
  margin-bottom: 1.5rem;
  background: var(--bg-header);
  padding: 0.35rem;
  border-radius: 8px;
  border: 1px solid var(--border);
}}

nav.primary-nav button {{
  background: transparent;
  color: var(--text-muted);
  border: 1px solid transparent;
  padding: 0.5rem 1.1rem;
  border-radius: 6px;
  cursor: pointer;
  font: inherit;
  font-size: 0.875rem;
  font-weight: 600;
  transition: all 0.15s ease;
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
}}

nav.primary-nav button:hover {{
  color: var(--primary);
  background: rgba(255, 255, 255, 0.8);
}}

nav.primary-nav button[aria-selected="true"] {{
  background: var(--primary);
  color: #FFFFFF;
  border-color: var(--primary);
  font-weight: 700;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.12);
}}

nav.primary-nav button:focus-visible {{
  outline: 2px solid var(--primary);
  outline-offset: 2px;
}}

section[hidden] {{ display: none; }}

/* Badges */
.badge {{
  display: inline-flex;
  align-items: center;
  padding: 0.15rem 0.45rem;
  border-radius: 4px;
  font-size: 0.7rem;
  font-weight: 700;
  line-height: 1;
}}
.badge-dept {{
  display: inline-block;
  padding: 0.15rem 0.4rem;
  border-radius: 3px;
  font-size: 0.68rem;
  font-weight: 700;
}}
.badge-cse {{ background: #E0E7FF; color: #3730A3; }}
.badge-ece {{ background: #EDE9FE; color: #5B21B6; }}
.badge-eee {{ background: #FEF3C7; color: #92400E; }}
.badge-me {{ background: #FFEDD5; color: #9A3412; }}
.badge-math {{ background: #CFFAFE; color: #155E75; }}
.badge-phy {{ background: #CCFBF1; color: #115E59; }}
.badge-hum {{ background: #FCE7F3; color: #9D174D; }}

/* ------------------------------------------------------------- Master Routine Layout */
.master-header {{
  text-align: center;
  padding: 1.25rem 1rem 1rem;
  margin-bottom: 1.5rem;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: #FFFFFF;
}}

.master-header .univ {{
  font-size: 1.05rem;
  font-weight: 600;
  color: var(--text-muted);
  margin-bottom: 0.15rem;
}}

.master-header .dept {{
  font-size: 1.4rem;
  font-weight: 800;
  color: var(--text-main);
  letter-spacing: -0.01em;
}}

.master-header .doc-title {{
  font-size: 1.25rem;
  font-weight: 800;
  color: var(--primary);
  letter-spacing: 0.04em;
  text-transform: uppercase;
  margin-top: 0.25rem;
}}

.master-subnav-toolbar {{
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 1rem;
  margin-bottom: 1.25rem;
  background: var(--bg-header);
  padding: 0.75rem 1rem;
  border-radius: 8px;
  border: 1px solid var(--border);
}}

.master-subtabs {{
  display: flex;
  gap: 0.4rem;
  flex-wrap: wrap;
}}

.master-subtab {{
  padding: 0.45rem 0.95rem;
  border-radius: 6px;
  border: 1px solid var(--border);
  background: #FFFFFF;
  color: var(--text-muted);
  font-size: 0.85rem;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.15s ease;
}}

.master-subtab:hover {{
  border-color: var(--primary);
  color: var(--primary);
}}

.master-subtab.active {{
  background: var(--primary);
  color: #FFFFFF;
  border-color: var(--primary);
  font-weight: 700;
}}

.master-controls {{
  display: flex;
  align-items: center;
  gap: 0.75rem;
  flex-wrap: wrap;
}}

.search-box input {{
  padding: 0.45rem 0.85rem;
  font-size: 0.85rem;
  border: 1px solid var(--border);
  border-radius: 6px;
  min-width: 250px;
  background: #FFFFFF;
  color: var(--text-main);
  outline: none;
}}

.search-box input:focus {{
  border-color: var(--primary);
  box-shadow: 0 0 0 3px rgba(29, 78, 216, 0.15);
}}

.btn-action-icon {{
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  padding: 0.45rem 0.85rem;
  border-radius: 6px;
  border: 1px solid var(--border);
  background: #FFFFFF;
  font-size: 0.85rem;
  font-weight: 600;
  color: var(--text-main);
  cursor: pointer;
}}

.btn-action-icon:hover {{
  background: var(--bg-header);
}}

/* Master Table Design (Matching Sample Image 1 & 2) */
.master-table-scroll {{
  overflow-x: auto;
  border: 1px solid #94A3B8;
  border-radius: 6px;
  background: #FFFFFF;
  box-shadow: 0 1px 3px rgba(0,0,0,0.05);
}}

table.master-table {{
  border-collapse: collapse;
  width: 100%;
  min-width: 1400px;
  background: #FFFFFF;
  font-size: 0.76rem;
}}

table.master-table th, table.master-table td {{
  border: 1px solid #94A3B8;
  padding: 0.25rem 0.35rem;
  vertical-align: middle;
  text-align: center;
}}

table.master-table thead th {{
  background: #F1F5F9;
  color: #0F172A;
  font-weight: 700;
  border: 1px solid #64748B;
}}

th.m-th-sl {{
  width: 38px;
  background: #E2E8F0 !important;
}}

th.m-th-teacher {{
  width: 200px;
  text-align: left;
  padding-left: 0.6rem;
  background: #E2E8F0 !important;
}}

th.m-th-day {{
  background: #E2E8F0 !important;
  color: #0F172A;
  font-weight: 800;
  font-size: 0.82rem;
  letter-spacing: 0.05em;
  padding: 0.4rem;
  border-left: 2px solid #334155 !important;
}}

th.m-th-per {{
  font-size: 0.7rem;
  padding: 0.2rem 0.25rem;
  background: #F8FAFC;
  white-space: nowrap;
}}

.m-pnum {{
  display: block;
  font-weight: 800;
  font-size: 0.75rem;
  color: #0F172A;
}}

.m-ptime {{
  display: block;
  font-size: 0.64rem;
  color: #475569;
  font-weight: 500;
}}

/* Break column right divider */
.brk-sep {{
  border-right: 2px solid #475569 !important;
}}

/* Cells */
td.m-td-sl {{
  font-weight: 700;
  background: #F8FAFC;
  color: #475569;
}}

td.m-td-teacher {{
  text-align: left;
  padding: 0.35rem 0.6rem;
  white-space: nowrap;
  background: #F8FAFC;
}}

.m-tname {{
  font-weight: 700;
  color: #0F172A;
  font-size: 0.78rem;
}}

.m-tmeta {{
  font-size: 0.7rem;
  color: #64748B;
  display: flex;
  align-items: center;
  gap: 0.4rem;
  margin-top: 0.1rem;
}}

.m-tcode {{
  font-weight: 700;
  color: var(--primary);
}}

td.m-free {{
  background: #FFFFFF;
}}

td.m-cell-theory {{
  background: #FFFFFF;
  color: #0F172A;
  text-align: center;
}}

td.m-cell-lab {{
  background: var(--lab-bg);
  border-top: 1px solid #D97706 !important;
  border-bottom: 1px solid #D97706 !important;
  border-left: 2px solid #D97706 !important;
  border-right: 2px solid #D97706 !important;
  color: #92400E;
  text-align: center;
}}

.m-code {{
  font-weight: 800;
  font-size: 0.78rem;
  color: #0F172A;
  line-height: 1.2;
}}

.m-meta {{
  font-size: 0.68rem;
  color: #475569;
  font-weight: 600;
  margin-top: 0.15rem;
}}

/* ------------------------------------------------------------- Teachers Section (Dropdown & Filter) */
.teacher-filter-toolbar {{
  background: #FFFFFF;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 1rem 1.25rem;
  margin-bottom: 1.5rem;
  box-shadow: 0 1px 3px rgba(0,0,0,0.04);
}}

.teacher-filter-row {{
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 1rem;
}}

.filter-controls-left {{
  display: flex;
  align-items: center;
  gap: 1rem;
  flex-wrap: wrap;
}}

.filter-item {{
  display: flex;
  align-items: center;
  gap: 0.5rem;
}}

.filter-item label {{
  font-weight: 700;
  font-size: 0.85rem;
  color: var(--text-main);
}}

select.teacher-dropdown {{
  padding: 0.5rem 0.85rem;
  font-size: 0.875rem;
  font-weight: 600;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: #FFFFFF;
  color: var(--text-main);
  min-width: 280px;
  outline: none;
}}

select.teacher-dropdown:focus {{
  border-color: var(--primary);
  box-shadow: 0 0 0 3px rgba(29, 78, 216, 0.15);
}}

input.teacher-search-input {{
  padding: 0.5rem 0.85rem;
  font-size: 0.875rem;
  border: 1px solid var(--border);
  border-radius: 6px;
  min-width: 240px;
  outline: none;
}}

input.teacher-search-input:focus {{
  border-color: var(--primary);
  box-shadow: 0 0 0 3px rgba(29, 78, 216, 0.15);
}}

.dept-pill-group {{
  display: flex;
  align-items: center;
  gap: 0.3rem;
  flex-wrap: wrap;
}}

.dept-pill {{
  padding: 0.25rem 0.6rem;
  border-radius: 9999px;
  font-size: 0.75rem;
  font-weight: 700;
  border: 1px solid var(--border);
  background: #FFFFFF;
  color: var(--text-muted);
  cursor: pointer;
  transition: all 0.15s ease;
}}

.dept-pill:hover {{
  border-color: var(--primary);
  color: var(--primary);
}}

.dept-pill.active {{
  background: var(--primary);
  color: #FFFFFF;
  border-color: var(--primary);
}}

.teacher-filter-status {{
  margin-top: 0.75rem;
  padding-top: 0.75rem;
  border-top: 1px solid var(--bg-header-alt);
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 0.5rem;
}}

.teacher-card {{
  margin-bottom: 2rem;
  border: 1px solid var(--border);
  border-radius: 8px;
  overflow: hidden;
  background: #FFFFFF;
  box-shadow: 0 1px 3px rgba(0,0,0,0.03);
}}

.teacher-card-header {{
  padding: 0.85rem 1.25rem;
  background: var(--bg-header);
  border-bottom: 1px solid var(--border);
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 0.75rem;
}}

.teacher-card-title {{
  display: flex;
  align-items: center;
  gap: 0.6rem;
  flex-wrap: wrap;
}}

.teacher-card-title h3 {{
  margin: 0;
  font-size: 1.15rem;
  font-weight: 700;
  color: var(--text-main);
}}

.teacher-card-load {{
  font-size: 0.85rem;
  font-weight: 600;
  color: var(--primary);
  background: var(--primary-light);
  padding: 0.25rem 0.65rem;
  border-radius: 9999px;
  border: 1px solid var(--primary-border);
}}

/* ------------------------------------------------------------- Section / Batch Routines */
h2 {{
  font-family: "Source Serif 4", Georgia, serif;
  font-weight: 700;
  font-size: 1.25rem;
  margin: 1.75rem 0 0.65rem;
  color: var(--text-main);
}}

h2:first-of-type {{ margin-top: 0; }}

.scroll {{
  overflow-x: auto;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: #FFFFFF;
}}

table.routine {{
  border-collapse: collapse;
  width: 100%;
  min-width: 920px;
}}

table.routine th, table.routine td {{
  border: 1px solid var(--border);
  padding: 0.45rem 0.6rem;
  vertical-align: top;
  text-align: left;
}}

table.routine thead th {{
  background: var(--bg-header);
  color: var(--text-main);
  font-weight: 700;
  font-size: 0.8rem;
  white-space: nowrap;
}}

.pname {{ display: block; }}
.ptime {{ display: block; color: var(--text-dim); font-weight: 500; font-size: 0.72rem; }}

th.corner, th.day {{
  background: var(--bg-header-alt);
  width: 110px;
  font-size: 0.85rem;
  font-weight: 700;
}}

td.free {{
  background: #FFFFFF;
}}

td.theory {{
  background: #FFFFFF;
}}

td.lab {{
  background: var(--lab-bg);
  border-left: 3px solid var(--lab-border);
}}

.ent {{ font-size: 0.82rem; }}
.ent + .ent {{
  margin-top: 0.35rem;
  padding-top: 0.35rem;
  border-top: 1px dashed var(--border);
}}

.grp {{
  color: var(--lab-text);
  font-size: 0.76rem;
  font-weight: 600;
}}

.meta {{
  display: block;
  color: var(--text-dim);
  font-size: 0.74rem;
  margin-top: 0.15rem;
}}

.brk {{
  background: repeating-linear-gradient(135deg, rgba(203, 213, 225, 0.4) 0 5px, #F8FAFC 5px 10px);
  width: 44px;
  font-size: 0.68rem;
  color: var(--break-text);
  text-align: center;
}}

.brk span {{ writing-mode: vertical-rl; font-weight: 600; }}

footer {{
  margin-top: 3rem;
  color: var(--text-dim);
  font-size: 0.85rem;
  border-top: 1px solid var(--border);
  padding-top: 1.25rem;
  text-align: center;
}}

/* ------------------------------------------------------------- Routine Download Bar */
.routine-download-bar {{
  margin-top: 1.25rem;
  margin-bottom: 2rem;
  padding: 0.9rem 1.25rem;
  background: #F8FAFC;
  border: 1px solid var(--border);
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 1rem;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);
}}

.download-bar-info {{
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
}}

.download-bar-title {{
  font-weight: 700;
  font-size: 0.95rem;
  color: var(--text-main);
  display: flex;
  align-items: center;
  gap: 0.4rem;
}}

.download-bar-subtitle {{
  font-size: 0.8rem;
  color: var(--text-muted);
}}

.download-bar-actions {{
  display: flex;
  align-items: center;
  gap: 0.65rem;
  flex-wrap: wrap;
}}

.btn-download-pdf {{
  display: inline-flex;
  align-items: center;
  gap: 0.45rem;
  background: var(--primary);
  color: #FFFFFF;
  border: none;
  padding: 0.55rem 1.15rem;
  font-size: 0.85rem;
  font-weight: 700;
  border-radius: 6px;
  cursor: pointer;
  box-shadow: 0 2px 4px rgba(15, 23, 42, 0.12);
  transition: all 0.15s ease;
}}

.btn-download-pdf:hover {{
  background: #1E293B;
  transform: translateY(-1px);
  box-shadow: 0 4px 8px rgba(15, 23, 42, 0.18);
}}

.btn-download-pdf:disabled {{
  opacity: 0.7;
  cursor: not-allowed;
  transform: none;
}}

.btn-print-routine {{
  display: inline-flex;
  align-items: center;
  gap: 0.45rem;
  background: #FFFFFF;
  color: var(--text-main);
  border: 1px solid var(--border);
  padding: 0.55rem 1rem;
  font-size: 0.85rem;
  font-weight: 600;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.15s ease;
}}

.btn-print-routine:hover {{
  background: #F1F5F9;
  border-color: #94A3B8;
}}

/* ------------------------------------------------------------- Term Legend / Reference Card */
.term-legend-card {{
  margin-top: 1.5rem;
  margin-bottom: 1.5rem;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 8px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
  overflow: hidden;
  page-break-inside: avoid;
}}

.term-legend-card-header {{
  background: #F1F5F9;
  border-bottom: 1px solid var(--border);
  padding: 0.65rem 1.25rem;
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 0.5rem;
}}

.term-legend-card-title {{
  font-weight: 700;
  font-size: 0.95rem;
  color: var(--primary);
  display: flex;
  align-items: center;
  gap: 0.4rem;
}}

.term-legend-card-subtitle {{
  font-size: 0.8rem;
  color: var(--text-dim);
  font-weight: 500;
}}

.term-legend-grid {{
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1.5rem;
  padding: 1.25rem;
}}

@media (max-width: 850px) {{
  .term-legend-grid {{
    grid-template-columns: 1fr;
    gap: 1rem;
  }}
}}

.term-legend-col {{
  background: #F8FAFC;
  border: 1px solid #E2E8F0;
  border-radius: 6px;
  padding: 1rem 1.15rem;
  display: flex;
  flex-direction: column;
}}

.term-legend-col-header {{
  display: flex;
  align-items: center;
  gap: 0.5rem;
  border-bottom: 2px solid var(--primary-border);
  padding-bottom: 0.5rem;
  margin-bottom: 0.75rem;
}}

.term-legend-col-header h4 {{
  margin: 0;
  font-size: 0.95rem;
  font-weight: 700;
  color: var(--text-main);
}}

.term-legend-icon {{
  font-size: 1.1rem;
}}

.term-legend-subheading {{
  font-size: 0.78rem;
  font-weight: 800;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: #475569;
  margin-bottom: 0.45rem;
  padding-left: 0.2rem;
  border-left: 3px solid var(--primary);
}}

.term-legend-list {{
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}}

.term-legend-row {{
  display: flex;
  align-items: baseline;
  padding: 0.25rem 0.35rem;
  border-radius: 4px;
  font-size: 0.85rem;
  transition: background 0.1s ease;
  line-height: 1.45;
}}

.term-legend-row:hover {{
  background: #EDF2F7;
}}

.term-legend-code {{
  font-weight: 700;
  color: #1E3A8A;
  min-width: 88px;
  flex-shrink: 0;
}}

.term-legend-code.sessional-code {{
  color: #B45309;
}}

.term-legend-code.teacher-code {{
  font-weight: 800;
  color: #0369A1;
  min-width: 58px;
  flex-shrink: 0;
  font-family: monospace;
  font-size: 0.9rem;
}}

.term-legend-sep {{
  color: #94A3B8;
  margin: 0 0.5rem 0 0.25rem;
  font-weight: 700;
  flex-shrink: 0;
}}

.term-legend-name {{
  color: var(--text-main);
  font-weight: 500;
  flex-grow: 1;
}}

.term-legend-dept {{
  color: #64748B;
  font-size: 0.8rem;
  font-weight: 600;
  margin-left: 0.35rem;
}}

.term-legend-courses {{
  color: #0369A1;
  font-size: 0.78rem;
  font-weight: 600;
  margin-left: 0.5rem;
}}

/* ------------------------------------------------------------- Print Optimizations */
@page {{
  size: landscape;
  margin: 8mm 6mm;
}}

@media print {{
  html, body {{
    background: #FFFFFF !important;
    color: #000000 !important;
    padding: 0 !important;
    margin: 0 !important;
    font-size: 10px;
  }}
  .wrap {{
    box-shadow: none !important;
    border: none !important;
    padding: 0 !important;
    max-width: 100% !important;
    width: 100% !important;
  }}
  nav, footer, .master-subnav-toolbar, .teacher-filter-toolbar,
  .routine-download-bar, .master-controls, .dept-pill-group,
  .teacher-filter-status button {{
    display: none !important;
  }}
  section[hidden] {{
    display: none !important;
  }}
  section:not([hidden]) {{
    display: block !important;
  }}
  .master-view-panel[style*="display: none"] {{
    display: none !important;
  }}
  header.app-masthead {{
    border-color: #000000;
    padding-bottom: 0.35rem;
    margin-bottom: 0.75rem;
  }}
  .scroll, .master-table-scroll {{
    border: none !important;
    box-shadow: none !important;
    overflow: visible !important;
    width: 100% !important;
    max-height: none !important;
  }}
  table.routine, table.master-table {{
    width: 100% !important;
    border-collapse: collapse !important;
    font-size: 9.5px !important;
  }}
  table.master-table {{
    font-size: 8px !important;
  }}
  table.routine th, table.routine td, table.master-table th, table.master-table td {{
    border-color: #334155 !important;
    -webkit-print-color-adjust: exact !important;
    print-color-adjust: exact !important;
  }}
  table.routine thead th, th.corner, th.day, table.master-table thead th {{
    background: #E2E8F0 !important;
    color: #000000 !important;
    -webkit-print-color-adjust: exact !important;
    print-color-adjust: exact !important;
  }}
  td.lab, td.m-cell-lab {{
    background: #FEF9C3 !important;
    border-color: #000000 !important;
    -webkit-print-color-adjust: exact !important;
    print-color-adjust: exact !important;
  }}
  td.theory, td.m-cell-theory {{
    background: #FFFFFF !important;
    -webkit-print-color-adjust: exact !important;
    print-color-adjust: exact !important;
  }}
  h2 {{
    page-break-after: avoid;
    font-size: 13px;
    margin: 6px 0 3px;
  }}
  tr {{
    page-break-inside: avoid;
  }}
  .term-legend-card {{
    page-break-inside: avoid !important;
    border: 1px solid #94A3B8 !important;
    box-shadow: none !important;
    margin-top: 8px !important;
    margin-bottom: 8px !important;
  }}
  .term-legend-card-header {{
    background: #E2E8F0 !important;
    padding: 3px 6px !important;
  }}
  .term-legend-grid {{
    gap: 8px !important;
    padding: 6px !important;
  }}
  .term-legend-col {{
    background: #FFFFFF !important;
    border: 1px solid #CBD5E1 !important;
    padding: 4px 6px !important;
  }}
  .term-legend-row {{
    padding: 1px 0 !important;
    font-size: 9px !important;
    line-height: 1.25 !important;
  }}
  .term-legend-code {{
    min-width: 75px !important;
  }}
  .term-legend-code.teacher-code {{
    min-width: 45px !important;
  }}
}}

@media (prefers-reduced-motion: reduce) {{ * {{ transition: none !important; }} }}
"""


JS = """
// Tab Switching
const tabs = Array.from(document.querySelectorAll('nav.primary-nav button'));
const panels = Array.from(document.querySelectorAll('section[id]'));

function show(id) {
  tabs.forEach(t => t.setAttribute('aria-selected', String(t.dataset.target === id)));
  panels.forEach(p => { p.hidden = (p.id !== id); });
  // If showing teachers, ensure filter state is applied
  if (id === 'teachers') {
    applyTeacherFilters();
  }
}
tabs.forEach(t => t.addEventListener('click', () => show(t.dataset.target)));

// Master Routine Sub-view Toggle
function showMasterSubView(view) {
  document.querySelectorAll('.master-subtab').forEach(b => {
    b.classList.toggle('active', b.dataset.view === view);
  });
  const views = ['teachers', 'labs', 'batches'];
  views.forEach(v => {
    const el = document.getElementById('view-master-' + v);
    if (el) el.style.display = (v === view ? 'block' : 'none');
  });
}

// Master Routine Table Filter
function onMasterSearchInput(val) {
  val = (val || '').toLowerCase().trim();
  const activeTable = document.querySelector('.master-view-panel:not([style*="display: none"]) table');
  if (!activeTable) return;
  const rows = activeTable.querySelectorAll('tbody tr');
  rows.forEach(r => {
    if (!val) {
      r.style.display = '';
      return;
    }
    const txt = r.textContent.toLowerCase();
    r.style.display = txt.includes(val) ? '' : 'none';
  });
}

// ----------------------------------------------------------------- Teacher Filter & Search
let activeTeacherDept = '';

function onTeacherDropdownChange(val) {
  const searchInput = document.getElementById('teacher-search-input');
  if (searchInput && val !== 'all') {
    searchInput.value = '';
  }
  applyTeacherFilters();
}

function onTeacherSearch(val) {
  applyTeacherFilters();
}

function filterTeacherDept(dept) {
  activeTeacherDept = dept;
  document.querySelectorAll('.dept-pill').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.dept === dept);
  });

  // Filter dropdown options by dept
  const dropdown = document.getElementById('teacher-dropdown-select');
  if (dropdown) {
    Array.from(dropdown.options).forEach(opt => {
      if (opt.value === 'all') return;
      const optDept = opt.dataset.dept || '';
      opt.hidden = (dept && optDept !== dept);
    });
    if (dropdown.selectedOptions[0]?.hidden) {
      dropdown.value = 'all';
    }
  }
  applyTeacherFilters();
}

function applyTeacherFilters() {
  const dropdown = document.getElementById('teacher-dropdown-select');
  const searchInput = document.getElementById('teacher-search-input');
  const countBadge = document.getElementById('teacher-filter-count');
  const cards = document.querySelectorAll('.teacher-card');

  const selectedTid = dropdown ? dropdown.value : 'all';
  const searchTerm = (searchInput ? searchInput.value : '').toLowerCase().trim();

  let visibleCount = 0;

  cards.forEach(c => {
    const tid = c.dataset.tid;
    const tdept = c.dataset.dept;
    const tname = c.dataset.name;
    const tshort = c.dataset.short;

    let matchDropdown = (selectedTid === 'all' || selectedTid === tid);
    let matchDept = (!activeTeacherDept || tdept === activeTeacherDept);
    let matchSearch = true;

    if (searchTerm) {
      matchSearch = tname.includes(searchTerm) || tshort.includes(searchTerm) || tid.includes(searchTerm);
    }

    const showCard = matchDropdown && matchDept && matchSearch;
    c.style.display = showCard ? '' : 'none';
    if (showCard) visibleCount++;
  });

  if (countBadge) {
    if (selectedTid !== 'all') {
      countBadge.textContent = 'Showing 1 selected teacher';
    } else if (searchTerm || activeTeacherDept) {
      countBadge.textContent = `Found ${visibleCount} teacher${visibleCount === 1 ? '' : 's'}`;
    } else {
      countBadge.textContent = `Showing all ${visibleCount} teachers`;
    }
  }
}

function navigateTeacherStep(delta) {
  const dropdown = document.getElementById('teacher-dropdown-select');
  if (!dropdown) return;
  const visibleOpts = Array.from(dropdown.options).filter(o => !o.hidden && o.value !== 'all');
  if (visibleOpts.length === 0) return;

  let currIdx = visibleOpts.findIndex(o => o.value === dropdown.value);
  if (currIdx === -1) {
    currIdx = (delta > 0 ? 0 : visibleOpts.length - 1);
  } else {
    currIdx = (currIdx + delta + visibleOpts.length) % visibleOpts.length;
  }
  dropdown.value = visibleOpts[currIdx].value;
  onTeacherDropdownChange(dropdown.value);
}

function printTeacherView() {
  window.print();
}

// ----------------------------------------------------------------- PDF Export Engine
function downloadElementAsPDF(element, filename, format, btn) {
  format = format || 'a4';
  if (!element) return;
  if (!window.html2pdf) {
    alert("PDF generator library is still loading. Please try again or use the Print button.");
    return;
  }

  let originalBtnHtml = '';
  if (btn) {
    originalBtnHtml = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = '<span>⏳</span> Generating PDF...';
  }

  // Show floating loading indicator
  const loadingIndicator = document.createElement('div');
  loadingIndicator.style.position = 'fixed';
  loadingIndicator.style.bottom = '24px';
  loadingIndicator.style.right = '24px';
  loadingIndicator.style.background = '#0F172A';
  loadingIndicator.style.color = '#FFFFFF';
  loadingIndicator.style.padding = '12px 20px';
  loadingIndicator.style.borderRadius = '8px';
  loadingIndicator.style.boxShadow = '0 10px 25px rgba(0,0,0,0.3)';
  loadingIndicator.style.zIndex = '1000000';
  loadingIndicator.style.fontFamily = '"Source Sans 3", system-ui, sans-serif';
  loadingIndicator.style.fontSize = '14px';
  loadingIndicator.style.fontWeight = '600';
  loadingIndicator.innerHTML = '📄 Generating PDF routine... Please wait.';
  document.body.appendChild(loadingIndicator);

  const prevScrollX = window.scrollX || window.pageXOffset || 0;
  const prevScrollY = window.scrollY || window.pageYOffset || 0;
  window.scrollTo(0, 0);

  const isWide = format === 'a3' || (element.scrollWidth && element.scrollWidth > 1400);

  const clone = element.cloneNode(true);

  // CRITICAL FIX: Ensure clone and all sub-elements are visible (not hidden by tab system)
  clone.removeAttribute('hidden');
  clone.style.display = 'block';
  clone.style.visibility = 'visible';
  clone.style.opacity = '1';
  clone.querySelectorAll('[hidden]').forEach(el => el.removeAttribute('hidden'));
  clone.querySelectorAll('.master-view-panel').forEach(el => { el.style.display = 'block'; });
  clone.querySelectorAll('*').forEach(el => {
    if (el.style.display === 'none' && !el.classList.contains('hidden-by-filter')) {
      el.style.display = '';
    }
  });

  // Strip UI toolbars, download bars, search inputs, and buttons from PDF export
  clone.querySelectorAll('.routine-download-bar, .master-subnav-toolbar, .teacher-filter-toolbar, button, input, .master-controls, .dept-pill-group, .teacher-filter-status').forEach(el => el.remove());

  clone.querySelectorAll('.scroll, .master-table-scroll').forEach(el => {
    el.style.overflow = 'visible';
    el.style.maxHeight = 'none';
    el.style.border = 'none';
    el.style.boxShadow = 'none';
    el.style.width = '100%';
  });

  if (isWide) {
    clone.querySelectorAll('table.master-table').forEach(t => {
      t.style.width = '100%';
      t.style.fontSize = '8px';
    });
    clone.querySelectorAll('table.master-table th, table.master-table td').forEach(td => {
      td.style.padding = '3px 4px';
    });
  } else {
    clone.querySelectorAll('table.routine').forEach(t => {
      t.style.width = '100%';
      t.style.fontSize = '8.5px';
      t.style.pageBreakInside = 'avoid';
      t.style.breakInside = 'avoid';
    });
    clone.querySelectorAll('table.routine th, table.routine td').forEach(td => {
      td.style.padding = '3px 5px';
    });

    // Clean page break before each subsequent section (e.g. Section B on page 2)
    let sectionCount = 0;
    clone.querySelectorAll('h2').forEach(h2 => {
      h2.style.margin = '8px 0 4px';
      h2.style.fontSize = '13px';
      h2.style.pageBreakAfter = 'avoid';
      h2.style.breakAfter = 'avoid';
      if (h2.textContent.toLowerCase().includes('section')) {
        sectionCount++;
        if (sectionCount > 1) {
          h2.style.pageBreakBefore = 'always';
          h2.style.breakBefore = 'page';
          h2.style.marginTop = '14px';
        }
      }
    });
  }

  const container = document.createElement('div');
  container.id = 'pdf-export-container';
  container.style.position = 'static';
  container.style.display = 'block';
  container.style.background = '#FFFFFF';
  container.style.padding = '0';
  container.style.margin = '0 auto';
  container.style.color = '#000000';
  container.style.fontFamily = '"Source Sans 3", system-ui, -apple-system, sans-serif';
  container.style.width = isWide ? '1700px' : '1020px';

  const headerHtml = `
    <div style="text-align: center; margin-bottom: 10px; padding: 6px 0 6px; border-bottom: 2px solid #0F172A;">
      <div style="font-size: 13px; font-weight: 600; color: #475569;">Khulna University of Engineering & Technology (KUET)</div>
      <div style="font-size: 17px; font-weight: 800; color: #0F172A; letter-spacing: -0.01em;">Department of Computer Science and Engineering</div>
      <div style="font-size: 12px; font-weight: 700; color: #D97706; text-transform: uppercase; margin-top: 2px;">Official Class Routine Timetable</div>
    </div>
  `;
  container.innerHTML = headerHtml;
  container.appendChild(clone);
  document.body.appendChild(container);

  const pdfFormat = isWide ? 'a3' : 'a4';

  const opt = {
    margin: [6, 6, 6, 6],
    filename: filename,
    image: { type: 'jpeg', quality: 0.98 },
    html2canvas: {
      scale: 1.5,
      useCORS: true,
      logging: false,
      scrollY: 0,
      scrollX: 0
    },
    jsPDF: {
      unit: 'mm',
      format: pdfFormat,
      orientation: 'landscape'
    },
    pagebreak: { mode: ['css', 'legacy'] }
  };

  function cleanup() {
    if (document.body.contains(loadingIndicator)) document.body.removeChild(loadingIndicator);
    if (document.body.contains(container)) document.body.removeChild(container);
    window.scrollTo(prevScrollX, prevScrollY);
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = originalBtnHtml;
    }
  }

  html2pdf()
    .set(opt)
    .from(container)
    .save()
    .then(() => {
      cleanup();
    })
    .catch(err => {
      console.error('PDF generation error:', err);
      cleanup();
      alert('Direct PDF generation encountered an issue. Opening printer dialog...');
      window.print();
    });
}

function downloadCurrentMasterPDF(btn) {
  const activeSubtab = document.querySelector('.master-subtab.active');
  const view = activeSubtab ? activeSubtab.dataset.view : 'teachers';
  const panel = document.getElementById('view-master-' + view);
  const nameMap = {
    teachers: 'Teachers',
    labs: 'Labs_and_Rooms',
    batches: 'Batches_and_Sections'
  };
  const label = nameMap[view] || 'Master';
  downloadElementAsPDF(panel, `KUET_CSE_Master_Routine_${label}.pdf`, 'a3', btn);
}

function printCurrentMasterRoutine() {
  window.print();
}

function downloadTermRoutinePDF(sectionId, batchId, btn) {
  const section = document.getElementById(sectionId);
  downloadElementAsPDF(section, `KUET_CSE_Routine_Term_${batchId}.pdf`, 'a4', btn);
}

function printTermRoutine(sectionId) {
  window.print();
}

function downloadTeacherRoutinePDF(btn) {
  const dropdown = document.getElementById('teacher-dropdown-select');
  const tid = dropdown ? dropdown.value : 'all';
  if (tid && tid !== 'all') {
    const card = document.getElementById('tc-' + tid);
    downloadElementAsPDF(card, `KUET_CSE_Teacher_Routine_${tid}.pdf`, 'a4', btn);
  } else {
    const container = document.getElementById('teacher-cards-container');
    downloadElementAsPDF(container, 'KUET_CSE_Teachers_All_Routines.pdf', 'a4', btn);
  }
}

// Show first tab by default (Master Routine)
if (tabs.length > 0) {
  show(tabs[0].dataset.target);
}
"""


# ----------------------------------------------------------------- Term Reference Section


def _render_term_reference_section(problem: Problem, solution: Solution, batch_id: str) -> str:
    """Render a clean two-column reference card below the timetable of a specific term.

    Column 1: All Theory and Sessional courses with their code and title.
    Column 2: All teachers assigned to the term courses with their shortcut code and full name.
    """
    # 1. Collect all courses for this batch
    batch_courses: list = []
    seen_codes = set()
    for c in problem.courses:
        if c.batch == batch_id and c.code not in seen_codes:
            seen_codes.add(c.code)
            batch_courses.append(c)

    for a in solution.assignments:
        if a.event.batch_id == batch_id and a.event.course.code not in seen_codes:
            seen_codes.add(a.event.course.code)
            batch_courses.append(a.event.course)

    theory_courses = [c for c in batch_courses if c.is_theory]
    sessional_courses = [c for c in batch_courses if not c.is_theory]

    theory_courses.sort(key=lambda c: c.code)
    sessional_courses.sort(key=lambda c: c.code)

    # 2. Collect all teachers assigned to courses of this term
    teacher_courses_map: dict[str, set[str]] = defaultdict(set)
    for a in solution.assignments:
        if a.event.batch_id == batch_id:
            for tid in a.event.teacher_ids:
                teacher_courses_map[tid].add(a.event.course.code)

    for c in batch_courses:
        if c.teacher1_id:
            teacher_courses_map[c.teacher1_id].add(c.code)
        if c.teacher2_id:
            teacher_courses_map[c.teacher2_id].add(c.code)
        if isinstance(c.teachers, dict):
            for s, val in c.teachers.items():
                if isinstance(val, str) and val:
                    teacher_courses_map[val].add(c.code)
                elif isinstance(val, dict):
                    for g, gval in val.items():
                        if isinstance(gval, list):
                            for tid in gval:
                                if tid:
                                    teacher_courses_map[tid].add(c.code)
                        elif isinstance(gval, str) and gval:
                            teacher_courses_map[gval].add(c.code)

    teachers = [problem.teachers[tid] for tid in teacher_courses_map.keys() if tid in problem.teachers]
    dept_order = ["CSE", "ECE", "EEE", "ME", "MATH", "PHY", "CHEM", "HUM"]
    teachers.sort(
        key=lambda t: (
            dept_order.index(t.department) if t.department in dept_order else 99,
            t.short.upper(),
            t.name,
        )
    )

    # Format Column 1: Courses (Theory & Sessional)
    col1_parts = []
    if theory_courses:
        col1_parts.append("<div class='term-legend-subheading'>Theory Courses</div>")
        col1_parts.append("<div class='term-legend-list'>")
        for c in theory_courses:
            credit_info = f" ({c.credit:.2f} Cr.)" if getattr(c, "credit", None) else ""
            col1_parts.append(
                f"<div class='term-legend-row'>"
                f"<span class='term-legend-code'>{html.escape(c.code)}</span>"
                f"<span class='term-legend-sep'>:</span>"
                f"<span class='term-legend-name'>{html.escape(c.title)}{html.escape(credit_info)}</span>"
                f"</div>"
            )
        col1_parts.append("</div>")

    if sessional_courses:
        margin_top = " style='margin-top: 0.85rem;'" if theory_courses else ""
        col1_parts.append(f"<div class='term-legend-subheading'{margin_top}>Sessional / Laboratory Courses</div>")
        col1_parts.append("<div class='term-legend-list'>")
        for c in sessional_courses:
            credit_info = f" ({c.credit:.2f} Cr.)" if getattr(c, "credit", None) else ""
            clean_code = c.code.replace(" ", "").upper()
            display_code = "CSE 3200" if "3200" in clean_code else ("CSE 4000" if "4000" in clean_code else c.code)
            col1_parts.append(
                f"<div class='term-legend-row'>"
                f"<span class='term-legend-code sessional-code'>{html.escape(display_code)}</span>"
                f"<span class='term-legend-sep'>:</span>"
                f"<span class='term-legend-name'>{html.escape(c.title)}{html.escape(credit_info)}</span>"
                f"</div>"
            )
        col1_parts.append("</div>")

    if not col1_parts:
        col1_parts.append("<div style='color: var(--text-dim); font-size: 0.85rem;'>No courses listed for this term.</div>")

    # Format Column 2: Teachers (Shortcut code & full name)
    col2_parts = []
    if teachers:
        col2_parts.append("<div class='term-legend-subheading'>Assigned Faculty Members</div>")
        col2_parts.append("<div class='term-legend-list'>")
        for t in teachers:
            dept_info = f" ({t.department})" if t.department else ""
            assigned_c_list = sorted(teacher_courses_map.get(t.id, []))
            courses_tag = (
                f"<span class='term-legend-courses' title='Courses taught in Term {html.escape(batch_id)}'>"
                f"[{', '.join(assigned_c_list)}]</span>"
                if assigned_c_list
                else ""
            )
            col2_parts.append(
                f"<div class='term-legend-row'>"
                f"<span class='term-legend-code teacher-code'>{html.escape(t.short)}</span>"
                f"<span class='term-legend-sep'>:</span>"
                f"<span class='term-legend-name'>{html.escape(t.name)}<span class='term-legend-dept'>{html.escape(dept_info)}</span>{courses_tag}</span>"
                f"</div>"
            )
        col2_parts.append("</div>")
    else:
        col2_parts.append("<div style='color: var(--text-dim); font-size: 0.85rem;'>No teachers assigned for this term.</div>")

    return f"""
    <div class="term-legend-card">
      <div class="term-legend-card-header">
        <span class="term-legend-card-title">📋 Term {html.escape(batch_id)} Academic Curriculum & Faculty Reference</span>
        <span class="term-legend-card-subtitle">{len(theory_courses)} Theory · {len(sessional_courses)} Sessional · {len(teachers)} Teachers Assigned</span>
      </div>
      <div class="term-legend-grid">
        <div class="term-legend-col">
          <div class="term-legend-col-header">
            <span class="term-legend-icon">📖</span>
            <h4>Courses (Theory & Sessional)</h4>
          </div>
          {''.join(col1_parts)}
        </div>
        <div class="term-legend-col">
          <div class="term-legend-col-header">
            <span class="term-legend-icon">👨‍🏫</span>
            <h4>Teachers (Shortcut Code & Name)</h4>
          </div>
          {''.join(col2_parts)}
        </div>
      </div>
    </div>
    """


# ----------------------------------------------------------------- Main HTML Generation


def write_html(
    problem: Problem,
    solution: Solution,
    path: str | Path,
    title: str = "Department of Computer Science and Engineering",
    subtitle: str = "Khulna University of Engineering & Technology (KUET) · Class Routine",
) -> Path:
    grid = problem.grid
    path = Path(path)

    busy_teachers_set = {t for a in solution.assignments for t in a.event.teacher_ids}
    sorted_busy_teachers = _get_sorted_teachers(problem, busy_teachers_set)

    panels: list[str] = []
    tabs: list[str] = []

    # 1. Master Routine Tab (Premier Tab, active by default!)
    tabs.append("<button data-target='master' aria-selected='true'>📋 Master Routine</button>")

    master_teachers_html = _render_master_teachers_table(problem, solution, sorted_busy_teachers)
    master_labs_html = _render_master_labs_table(problem, solution)
    master_batches_html = _render_master_batches_table(problem, solution)

    master_panel = f"""
    <section id='master'>
      <div class="master-header">
        <div class="univ">Khulna University of Engineering & Technology (KUET)</div>
        <div class="dept">Department of Computer Science and Engineering</div>
        <div class="doc-title">Master Routine</div>
      </div>

      <div class="master-subnav-toolbar">
        <div class="master-subtabs">
          <button type="button" class="master-subtab active" data-view="teachers" onclick="showMasterSubView('teachers')">
            👨‍🏫 Teachers Master Routine
          </button>
          <button type="button" class="master-subtab" data-view="labs" onclick="showMasterSubView('labs')">
            🔬 Labs & Rooms Master Routine
          </button>
          <button type="button" class="master-subtab" data-view="batches" onclick="showMasterSubView('batches')">
            🎓 Batches & Sections Master Routine
          </button>
        </div>

        <div class="master-controls">
          <div class="search-box">
            <input type="text" id="master-search-input" placeholder="🔍 Quick filter rows (teacher, code, room)..." oninput="onMasterSearchInput(this.value)" autocomplete="off" />
          </div>
          <button type="button" class="btn-download-pdf" onclick="downloadCurrentMasterPDF(this)">
            <span>📥</span> Download PDF
          </button>
          <button type="button" class="btn-action-icon" onclick="printCurrentMasterRoutine()">
            🖨️ Print
          </button>
        </div>
      </div>

      <div id="view-master-teachers" class="master-view-panel">
        {master_teachers_html}
        <div class="routine-download-bar">
          <div class="download-bar-info">
            <span class="download-bar-title">👨‍🏫 Teachers Master Routine</span>
            <span class="download-bar-subtitle">Full faculty schedule across all 5 weekdays</span>
          </div>
          <div class="download-bar-actions">
            <button type="button" class="btn-download-pdf" onclick="downloadCurrentMasterPDF(this)">
              <span>📥</span> Download Master Routine (PDF)
            </button>
            <button type="button" class="btn-print-routine" onclick="printCurrentMasterRoutine()">
              <span>🖨️</span> Print Master Routine
            </button>
          </div>
        </div>
      </div>

      <div id="view-master-labs" class="master-view-panel" style="display: none;">
        {master_labs_html}
        <div class="routine-download-bar">
          <div class="download-bar-info">
            <span class="download-bar-title">🔬 Labs & Rooms Master Routine</span>
            <span class="download-bar-subtitle">Computer laboratories & specialized room occupancy schedule</span>
          </div>
          <div class="download-bar-actions">
            <button type="button" class="btn-download-pdf" onclick="downloadCurrentMasterPDF(this)">
              <span>📥</span> Download Master Routine (PDF)
            </button>
            <button type="button" class="btn-print-routine" onclick="printCurrentMasterRoutine()">
              <span>🖨️</span> Print Master Routine
            </button>
          </div>
        </div>
      </div>

      <div id="view-master-batches" class="master-view-panel" style="display: none;">
        {master_batches_html}
        <div class="routine-download-bar">
          <div class="download-bar-info">
            <span class="download-bar-title">🎓 Batches & Sections Master Routine</span>
            <span class="download-bar-subtitle">All student cohort and section timetables unified</span>
          </div>
          <div class="download-bar-actions">
            <button type="button" class="btn-download-pdf" onclick="downloadCurrentMasterPDF(this)">
              <span>📥</span> Download Master Routine (PDF)
            </button>
            <button type="button" class="btn-print-routine" onclick="printCurrentMasterRoutine()">
              <span>🖨️</span> Print Master Routine
            </button>
          </div>
        </div>
      </div>
    </section>
    """
    panels.append(master_panel)

    # 2. Individual Teachers Tab (With Dropdown Menu, Real-time Search, and Quick Navigation)
    tabs.append("<button data-target='teachers' aria-selected='false'>👨‍🏫 Teachers</button>")

    # Build teacher dropdown options
    t_options = [f"<option value='all'>👥 Show All Teachers ({len(sorted_busy_teachers)})</option>"]
    for sl, t in enumerate(sorted_busy_teachers, start=1):
        load = sum(a.event.length for a in solution.assignments if t.id in a.event.teacher_ids)
        t_options.append(
            f"<option value='{html.escape(t.id)}' data-dept='{html.escape(t.department)}'>"
            f"{sl}. {html.escape(t.name)} ({html.escape(t.short)}) [{html.escape(t.department)}] — {load} p/wk"
            f"</option>"
        )

    tcards = []
    for t in sorted_busy_teachers:
        load = sum(a.event.length for a in solution.assignments if t.id in a.event.teacher_ids)
        events_count = sum(1 for a in solution.assignments if t.id in a.event.teacher_ids)
        cells = _teacher_grid(problem, solution, t.id)
        dept_cls = f"badge-{t.department.lower()}"

        card = f"""
        <div class='teacher-card' id='tc-{html.escape(t.id)}' data-tid='{html.escape(t.id)}' data-dept='{html.escape(t.department)}' data-name='{html.escape(t.name.lower())}' data-short='{html.escape(t.short.lower())}'>
          <div class='teacher-card-header'>
            <div class='teacher-card-title'>
              <h3>{html.escape(t.name)}</h3>
              <span class='badge' style='background: #E2E8F0; color: #1E293B; font-weight: 700;'>{html.escape(t.short)}</span>
              <span class='badge {dept_cls}'>{html.escape(t.department)}</span>
            </div>
            <div class='teacher-card-load'>
              Weekly Load: <b>{load}</b> periods/week · {events_count} meetings
            </div>
          </div>
          <div class='scroll'>{_render_table(problem, cells)}</div>
        </div>
        """
        tcards.append(card)

    teachers_section = f"""
    <section id='teachers' hidden>
      <div class="teacher-filter-toolbar">
        <div class="teacher-filter-row">
          <div class="filter-controls-left">
            <div class="filter-item">
              <label for="teacher-dropdown-select">Select Teacher:</label>
              <select id="teacher-dropdown-select" class="teacher-dropdown" onchange="onTeacherDropdownChange(this.value)">
                {''.join(t_options)}
              </select>
            </div>

            <div class="filter-item">
              <input type="text" id="teacher-search-input" class="teacher-search-input" placeholder="🔍 Search teacher by name or short code..." oninput="onTeacherSearch(this.value)" autocomplete="off" />
            </div>
          </div>

          <div class="dept-pill-group">
            <span style="font-size: 0.8rem; font-weight: 700; color: #64748B; margin-right: 0.25rem;">Dept:</span>
            <button type="button" class="dept-pill active" data-dept="" onclick="filterTeacherDept('')">All</button>
            <button type="button" class="dept-pill" data-dept="CSE" onclick="filterTeacherDept('CSE')">CSE</button>
            <button type="button" class="dept-pill" data-dept="ECE" onclick="filterTeacherDept('ECE')">ECE</button>
            <button type="button" class="dept-pill" data-dept="EEE" onclick="filterTeacherDept('EEE')">EEE</button>
            <button type="button" class="dept-pill" data-dept="ME" onclick="filterTeacherDept('ME')">ME</button>
            <button type="button" class="dept-pill" data-dept="MATH" onclick="filterTeacherDept('MATH')">MATH</button>
            <button type="button" class="dept-pill" data-dept="PHY" onclick="filterTeacherDept('PHY')">PHY</button>
            <button type="button" class="dept-pill" data-dept="HUM" onclick="filterTeacherDept('HUM')">HUM</button>
          </div>
        </div>

        <div class="teacher-filter-status">
          <span id="teacher-filter-count" style="font-weight: 700; color: #475569; font-size: 0.85rem;">Showing all {len(sorted_busy_teachers)} teachers</span>
          <div style="display: flex; gap: 0.5rem; flex-wrap: wrap;">
            <button type="button" class="btn-action-icon" onclick="navigateTeacherStep(-1)">◀ Prev Teacher</button>
            <button type="button" class="btn-action-icon" onclick="navigateTeacherStep(1)">Next Teacher ▶</button>
            <button type="button" class="btn-download-pdf" style="padding: 0.45rem 0.9rem; font-size: 0.8rem;" onclick="downloadTeacherRoutinePDF(this)">
              <span>📥</span> Download PDF
            </button>
            <button type="button" class="btn-action-icon" onclick="printTeacherView()">🖨️ Print Teacher Routine</button>
          </div>
        </div>
      </div>

      <div id="teacher-cards-container">
        {''.join(tcards)}
      </div>
    </section>
    """
    panels.append(teachers_section)

    # 3. Individual Batch Tabs strictly in CURRICULUM_ORDER
    sorted_batches = sorted(problem.batches.values(), key=lambda b: _curriculum_key(b.id))
    for batch in sorted_batches:
        pid = f"b-{batch.id}"
        tabs.append(
            f"<button data-target='{pid}' aria-selected='false'>"
            f"{html.escape(batch.id)}</button>"
        )
        blocks = [f"<h2>{html.escape(batch.name)} ({html.escape(batch.id)})</h2>"]
        for section in batch.sections:
            cells = _section_grid(problem, solution, batch.id, section)
            blocks.append(f"<h2>Section {html.escape(section)}</h2>")
            blocks.append(f"<div class='scroll'>{_render_table(problem, cells)}</div>")
        
        # Add two-column course & teacher reference below the term routine table(s)
        blocks.append(_render_term_reference_section(problem, solution, batch.id))

        # Download bar below the term routine
        download_bar = f"""
        <div class="routine-download-bar">
          <div class="download-bar-info">
            <span class="download-bar-title">🎓 Term {html.escape(batch.id)} Routine</span>
            <span class="download-bar-subtitle">{html.escape(batch.name)} — All Sections Schedule</span>
          </div>
          <div class="download-bar-actions">
            <button type="button" class="btn-download-pdf" onclick="downloadTermRoutinePDF('{pid}', '{html.escape(batch.id)}', this)">
              <span>📥</span> Download Term {html.escape(batch.id)} PDF
            </button>
            <button type="button" class="btn-print-routine" onclick="printTermRoutine('{pid}')">
              <span>🖨️</span> Print Term Routine
            </button>
          </div>
        </div>
        """
        blocks.append(download_bar)
        panels.append(f"<section id='{pid}' hidden>{''.join(blocks)}</section>")

    used_slots = sum(a.event.length for a in solution.assignments)
    room_slots = len(problem.rooms) * grid.n_slots

    stats = [
        ("Batches", len(problem.batches)),
        ("Sections", sum(len(b.sections) for b in problem.batches.values())),
        ("Faculty & Teachers", len(sorted_busy_teachers)),
        ("Classes placed", len(solution.assignments)),
        ("Room use", f"{used_slots / room_slots:.0%}"),
        ("Penalty", solution.objective),
    ]
    stat_html = "".join(
        f"<div class='stat'><b>{v}</b><span>{k}</span></div>" for k, v in stats
    )

    doc = f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Source+Sans+3:wght@400;500;600;700;800&family=Source+Serif+4:opsz,wght@8..60,600;700&display=swap" rel="stylesheet">
<script src="/static/html2pdf.bundle.min.js"></script>
<script>
if (!window.html2pdf) {{
  document.write('<script src="https://cdnjs.cloudflare.com/ajax/libs/html2pdf.js/0.10.1/html2pdf.bundle.min.js"><\\/script>');
}}
</script>
<style>{CSS}</style>
</head><body><div class="wrap">
<header class="app-masthead">
  <div class="masthead-titles">
    <h1>{html.escape(title)}</h1>
    <p class="sub">{html.escape(subtitle)}</p>
  </div>
  <div class="stats">{stat_html}</div>
</header>
<nav class="primary-nav">{''.join(tabs)}</nav>
{''.join(panels)}
<footer>Department of Computer Science and Engineering, Khulna University of Engineering & Technology (KUET). Generated by CP-SAT solver. Light yellow cells represent sessional / laboratory blocks. Hatching denotes breaks.</footer>
</div><script>{JS}</script></body></html>"""

    path.write_text(doc, encoding="utf-8")
    return path
