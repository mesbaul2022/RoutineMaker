"""Turn a solved timetable into things people actually use: a console summary,
flat CSV, and a printable HTML routine."""

from __future__ import annotations

import csv
import html
from collections import defaultdict
from pathlib import Path

from .models import Problem
from .scheduler import Solution

# Navy ground, gold accent. The gold is spent on one thing only: the break
# bands and the lab blocks, both of which carry real structural information.
NAVY_DEEP = "#0A1A30"
NAVY = "#122A4A"
NAVY_LINE = "#1E3A5F"
GOLD = "#C9A227"
GOLD_SOFT = "#E3B23C"
PAPER = "#F2EFE6"
INK_DIM = "#9FB3C8"


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
        rows = sorted(solution.assignments, key=lambda a: (a.start, a.event.batch_id))
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


# -------------------------------------------------------------------- HTML


def _section_grid(problem: Problem, solution: Solution, batch_id: str, section: str):
    """cells[day][period] -> None | {'span': n, 'entries': [...]}, plus 'skip'."""
    grid = problem.grid
    cells: list[list] = [[None] * grid.n_periods for _ in range(grid.n_days)]

    relevant = [
        a
        for a in solution.assignments
        if a.event.batch_id == batch_id and a.event.section == section
    ]
    # Group synced lab events so both groups share one cell.
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


CSS = f"""
:root {{
  --navy-deep: {NAVY_DEEP};
  --navy: {NAVY};
  --line: {NAVY_LINE};
  --gold: {GOLD};
  --gold-soft: {GOLD_SOFT};
  --paper: {PAPER};
  --dim: {INK_DIM};
}}
* {{ box-sizing: border-box; }}
body {{
  margin: 0;
  padding: 2.5rem 1.5rem 4rem;
  background: var(--navy-deep);
  color: var(--paper);
  font-family: "Source Sans 3", "Segoe UI", system-ui, sans-serif;
  font-size: 15px;
  line-height: 1.5;
}}
.wrap {{ max-width: 1400px; margin: 0 auto; }}
header {{ border-bottom: 2px solid var(--gold); padding-bottom: 1.25rem; margin-bottom: 2rem; }}
h1 {{
  font-family: "Source Serif 4", Georgia, serif;
  font-weight: 600; font-size: 2.1rem; margin: 0 0 .35rem;
  letter-spacing: -0.015em;
}}
.sub {{ color: var(--dim); margin: 0; }}
.stats {{ display: flex; flex-wrap: wrap; gap: 2rem; margin-top: 1.1rem; }}
.stat b {{ display: block; font-size: 1.5rem; color: var(--gold-soft); font-weight: 600; }}
.stat span {{ color: var(--dim); font-size: .85rem; }}
nav {{ display: flex; flex-wrap: wrap; gap: .4rem; margin-bottom: 1.5rem; }}
nav button {{
  background: transparent; color: var(--dim); border: 1px solid var(--line);
  padding: .4rem .85rem; border-radius: 3px; cursor: pointer; font: inherit;
  font-size: .9rem;
}}
nav button:hover {{ color: var(--paper); border-color: var(--gold); }}
nav button[aria-selected="true"] {{
  background: var(--gold); color: var(--navy-deep); border-color: var(--gold);
  font-weight: 600;
}}
nav button:focus-visible {{ outline: 2px solid var(--gold-soft); outline-offset: 2px; }}
section[hidden] {{ display: none; }}
h2 {{ font-family: "Source Serif 4", Georgia, serif; font-weight: 600; font-size: 1.25rem;
     margin: 2rem 0 .75rem; }}
h2:first-of-type {{ margin-top: 0; }}
.scroll {{ overflow-x: auto; border: 1px solid var(--line); border-radius: 4px; }}
table.routine {{ border-collapse: collapse; width: 100%; min-width: 900px; }}
table.routine th, table.routine td {{
  border: 1px solid var(--line); padding: .4rem .5rem; vertical-align: top;
  text-align: left;
}}
table.routine thead th {{
  background: var(--navy); font-weight: 600; font-size: .78rem; white-space: nowrap;
}}
.pname {{ display: block; }}
.ptime {{ display: block; color: var(--dim); font-weight: 400; font-size: .72rem; }}
th.corner, th.day {{ background: var(--navy); width: 108px; font-size: .85rem; }}
td.free {{ background: rgba(255,255,255,.015); }}
td.theory {{ background: rgba(255,255,255,.05); }}
td.lab {{ background: rgba(201,162,39,.16); border-left: 3px solid var(--gold); }}
.ent {{ font-size: .82rem; }}
.ent + .ent {{ margin-top: .3rem; padding-top: .3rem; border-top: 1px dashed var(--line); }}
.grp {{ color: var(--gold-soft); font-size: .76rem; }}
.meta {{ display: block; color: var(--dim); font-size: .74rem; }}
.brk {{
  background: repeating-linear-gradient(135deg, rgba(201,162,39,.20) 0 5px,
              transparent 5px 10px);
  width: 46px; font-size: .68rem; color: var(--gold-soft); text-align: center;
}}
.brk span {{ writing-mode: vertical-rl; }}
footer {{ margin-top: 3rem; color: var(--dim); font-size: .85rem;
          border-top: 1px solid var(--line); padding-top: 1rem; }}
@media print {{
  body {{ background: #fff; color: #10203a; padding: 0; }}
  nav, footer {{ display: none; }}
  section[hidden] {{ display: block !important; }}
  header {{ border-color: #10203a; }}
  .scroll {{ border-color: #93a5b8; }}
  table.routine th, table.routine td {{ border-color: #93a5b8; }}
  table.routine thead th, th.corner, th.day {{ background: #e8eaee; }}
  td.lab {{ background: #f3e6c0; border-left-color: #8a6f14; }}
  td.theory {{ background: #fff; }}
  .stat b, .grp {{ color: #7a5e0d; }}
  .meta, .ptime, .sub, .stat span {{ color: #4a5b70; }}
  h2 {{ page-break-after: avoid; }}
  .scroll {{ page-break-inside: avoid; }}
}}
@media (prefers-reduced-motion: reduce) {{ * {{ transition: none !important; }} }}
"""

JS = """
const tabs = Array.from(document.querySelectorAll('nav button'));
const panels = Array.from(document.querySelectorAll('section'));
function show(id) {
  tabs.forEach(t => t.setAttribute('aria-selected', String(t.dataset.target === id)));
  panels.forEach(p => { p.hidden = (p.id !== id); });
}
tabs.forEach(t => t.addEventListener('click', () => show(t.dataset.target)));
show(tabs[0].dataset.target);
"""


def write_html(
    problem: Problem,
    solution: Solution,
    path: str | Path,
    title: str = "Department Class Routine",
    subtitle: str = "",
) -> Path:
    grid = problem.grid
    path = Path(path)

    panels: list[str] = []
    tabs: list[str] = []

    for batch in problem.batches.values():
        pid = f"b-{batch.id}"
        tabs.append(
            f"<button data-target='{pid}' aria-selected='false'>"
            f"{html.escape(batch.id)}</button>"
        )
        blocks = [f"<h2>{html.escape(batch.name)}</h2>"]
        for section in batch.sections:
            cells = _section_grid(problem, solution, batch.id, section)
            blocks.append(f"<h2>Section {html.escape(section)}</h2>")
            blocks.append(f"<div class='scroll'>{_render_table(problem, cells)}</div>")
        panels.append(f"<section id='{pid}' hidden>{''.join(blocks)}</section>")

    # Teacher view
    tabs.append("<button data-target='teachers' aria-selected='false'>Teachers</button>")
    tblocks = []
    busy_teachers = sorted(
        {t for a in solution.assignments for t in a.event.teacher_ids},
        key=lambda t: problem.teachers[t].name,
    )
    for tid in busy_teachers:
        t = problem.teachers[tid]
        load = sum(
            a.event.length for a in solution.assignments if tid in a.event.teacher_ids
        )
        tblocks.append(
            f"<h2>{html.escape(t.name)} <span class='grp'>{html.escape(tid)} · "
            f"{load} periods/week</span></h2>"
        )
        cells = _teacher_grid(problem, solution, tid)
        tblocks.append(f"<div class='scroll'>{_render_table(problem, cells)}</div>")
    panels.append(f"<section id='teachers' hidden>{''.join(tblocks)}</section>")

    used_slots = sum(a.event.length for a in solution.assignments)
    room_slots = len(problem.rooms) * grid.n_slots

    stats = [
        ("Batches", len(problem.batches)),
        ("Sections", sum(len(b.sections) for b in problem.batches.values())),
        ("Teachers", len(busy_teachers)),
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
<link href="https://fonts.googleapis.com/css2?family=Source+Sans+3:wght@400;600&family=Source+Serif+4:opsz,wght@8..60,600&display=swap" rel="stylesheet">
<style>{CSS}</style>
</head><body><div class="wrap">
<header>
  <h1>{html.escape(title)}</h1>
  <p class="sub">{html.escape(subtitle)}</p>
  <div class="stats">{stat_html}</div>
</header>
<nav>{''.join(tabs)}</nav>
{''.join(panels)}
<footer>Generated by the CP-SAT routine scheduler. Gold cells are sessional
(lab) blocks; hatched columns are breaks. Print this page for the notice
board — the print layout switches to ink on white and expands every tab.</footer>
</div><script>{JS}</script></body></html>"""

    path.write_text(doc, encoding="utf-8")
    return path
