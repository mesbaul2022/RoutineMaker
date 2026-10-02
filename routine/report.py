"""Turn a solved timetable into things people actually use: a console summary,
flat CSV, and a printable, interactive HTML routine with Master Routine and Teacher Search."""

from __future__ import annotations

import csv
import html
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
            if ev.is_shared:
                t_str = "/".join(problem.teachers[t].name for t in ev.teacher_ids if t in problem.teachers)
            elif ev.is_lab:
                t_str = " + ".join(problem.teachers[t].name for t in ev.teacher_ids if t in problem.teachers)
            else:
                t_str = ", ".join(problem.teachers[t].name for t in ev.teacher_ids if t in problem.teachers)

            grp = ev.group or ""
            if ev.paired_event_id is not None:
                grp = f"{ev.group} (0.75cr alt)" if ev.group else "(0.75cr alt)"

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
                    ev.course.code,
                    ev.course.title,
                    ev.course.kind,
                    problem.rooms[a.room_id].name,
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
        if ev.paired_event_id is not None:
            key = (d, p, "paired_075_lab")
        elif ev.is_lab:
            key = (d, p, ev.course.code)
        else:
            key = (d, p, ev.course.code, ev.eid)

        bucket = merged.setdefault(
            key,
            {"day": d, "period": p, "span": ev.length, "lab": ev.is_lab, "entries": []},
        )
        if ev.is_shared:
            t_str = "/".join(problem.teachers[t].short for t in ev.teacher_ids if t in problem.teachers)
        elif ev.is_lab:
            t_str = "+".join(problem.teachers[t].short for t in ev.teacher_ids if t in problem.teachers)
        else:
            t_str = ", ".join(problem.teachers[t].short for t in ev.teacher_ids if t in problem.teachers)

        grp_label = ev.group
        if ev.paired_event_id is not None:
            grp_label = f"{ev.group} (0.75cr alt)" if ev.group else "(0.75cr alt)"

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
        cells[d][p] = {
            "day": d,
            "period": p,
            "span": ev.length,
            "lab": ev.is_lab,
            "entries": [
                {
                    "code": ev.course.code,
                    "group": f"{ev.batch_id} {ev.section}{ev.group or ''}",
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
                        if e["group"]:
                            tag += f" <span class='grp'>{html.escape(e['group'])}</span>"
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
        for tid in ev.teacher_ids:
            if tid in t_grids:
                t_grids[tid][d][p] = {
                    "span": ev.length,
                    "code": ev.course.code,
                    "batch": ev.batch_id,
                    "section": ev.section,
                    "group": ev.group or "",
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
                    grp_txt = f" ({cell['group']})" if cell["group"] else ""
                    tag_meta = f"{cell['batch']} {cell['section']}{grp_txt}"

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
            r_grids[a.room_id][d][p] = {
                "span": ev.length,
                "code": ev.course.code,
                "batch": ev.batch_id,
                "section": ev.section,
                "group": ev.group or "",
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
                        grp_txt = f" ({e['group']})" if e["group"] else ""
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

/* ------------------------------------------------------------- Print Optimizations */
@media print {{
  body {{
    background: #FFFFFF;
    color: #000000;
    padding: 0;
    font-size: 11px;
  }}
  .wrap {{
    box-shadow: none;
    border: none;
    padding: 0;
    max-width: 100%;
  }}
  nav, footer, .master-subnav-toolbar, .teacher-filter-toolbar {{
    display: none !important;
  }}
  section[hidden] {{
    display: block !important;
  }}
  header.app-masthead {{
    border-color: #000000;
    padding-bottom: 0.5rem;
    margin-bottom: 1rem;
  }}
  .scroll, .master-table-scroll {{
    border-color: #000000;
    box-shadow: none;
  }}
  table.routine th, table.routine td, table.master-table th, table.master-table td {{
    border-color: #475569 !important;
  }}
  table.routine thead th, th.corner, th.day, table.master-table thead th {{
    background: #E2E8F0 !important;
    color: #000000 !important;
  }}
  td.lab, td.m-cell-lab {{
    background: #FEF9C3 !important;
    border-color: #000000 !important;
  }}
  td.theory, td.m-cell-theory {{
    background: #FFFFFF !important;
  }}
  h2 {{ page-break-after: avoid; }}
  .scroll, .master-table-scroll {{ page-break-inside: avoid; }}
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

// Show first tab by default (Master Routine)
if (tabs.length > 0) {
  show(tabs[0].dataset.target);
}
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
          <button type="button" class="btn-action-icon" onclick="window.print()">
            🖨️ Print Master Routine
          </button>
        </div>
      </div>

      <div id="view-master-teachers" class="master-view-panel">
        {master_teachers_html}
      </div>

      <div id="view-master-labs" class="master-view-panel" style="display: none;">
        {master_labs_html}
      </div>

      <div id="view-master-batches" class="master-view-panel" style="display: none;">
        {master_batches_html}
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
          <div style="display: flex; gap: 0.5rem;">
            <button type="button" class="btn-action-icon" onclick="navigateTeacherStep(-1)">◀ Prev Teacher</button>
            <button type="button" class="btn-action-icon" onclick="navigateTeacherStep(1)">Next Teacher ▶</button>
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
