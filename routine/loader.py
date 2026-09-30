"""Load a problem instance from JSON and check it before wasting solver time.

Most 'the solver says INFEASIBLE and I don't know why' situations are really
data problems. The validator below catches the common ones and reports them in
plain language instead of leaving you to guess.
"""

from __future__ import annotations

import json
from pathlib import Path

from .models import SESSIONAL, THEORY, Batch, Course, Event, Problem, Room, Teacher
from .timegrid import TimeGrid

DEFAULT_HOME_ROOMS = {
    "1-1|A": "CSE-101",
    "1-1|B": "CSE-102",
    "2-1|A": "B-102",
    "2-1|B": "B-105",
    "2-2|A": "D-402",
    "2-2|B": "B-102",
    "3-2|A": "B-306",
    "3-2|B": "D-401",
    "4-1|A": "CSE-501",
    "4-1|B": "CSE-502",
}

DEFAULT_OPTIONS = {
    "sync_group_labs": True,  # both groups of a section do their lab at the same time
    "max_consecutive_periods": 3,
    "home_rooms": DEFAULT_HOME_ROOMS,
    "weights": {
        "cohort_gap": 8,
        "teacher_gap": 4,
        "last_period": 2,
        "teacher_daily_overload": 6,
        "consecutive_overrun": 5,
        "room_churn": 4,
        "theory_slot_priority": 2,
        "block_gap": 10,
    },
    "solver": {"max_seconds": 180, "workers": 8, "log": False},
}


def _merge(base: dict, override: dict) -> dict:
    out = dict(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def load_problem(path: str | Path) -> Problem:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))

    grid = TimeGrid.from_dict(raw["config"])
    options = _merge(DEFAULT_OPTIONS, raw["config"].get("options", {}))

    rooms = {r["id"]: Room(**r) for r in raw["rooms"]}
    batches = {b["id"]: Batch(**b) for b in raw["batches"]}
    teachers = {t["id"]: _make_teacher(t, grid) for t in raw["teachers"]}
    courses = [_make_course(c) for c in raw["courses"]]

    events = _build_events(courses, batches, grid)

    return Problem(
        grid=grid,
        teachers=teachers,
        rooms=rooms,
        batches=batches,
        courses=courses,
        events=events,
        options=options,
    )


def _make_teacher(t: dict, grid: TimeGrid) -> Teacher:
    blocked: set[int] = set()
    for entry in t.get("unavailable", []):
        d = grid.day_index(entry["day"])
        names = entry.get("periods", "all")
        idxs = (
            range(grid.n_periods)
            if names == "all"
            else [grid.period_index(n) for n in names]
        )
        for p in idxs:
            blocked.add(grid.slot(d, p))
    return Teacher(
        id=t["id"],
        name=t["name"],
        short=t.get("short", t["id"]),
        unavailable=blocked,
        max_periods_per_day=t.get("max_periods_per_day", 4),
    )


def _make_course(c: dict) -> Course:
    return Course(
        code=c["code"],
        title=c["title"],
        batch=c["batch"],
        kind=c["kind"],
        room_kind=c.get("room_kind", "theory"),
        periods_per_week=c.get("periods_per_week", 0),
        blocks_per_week=c.get("blocks_per_week", 0),
        credit=c.get("credit", 3.0 if c["kind"] == "theory" else (1.5 if c.get("blocks_per_week", 1) == 1 else 3.0)),
        paired_course_id=c.get("paired_course_id"),
        teacher1_id=c.get("teacher1_id"),
        teacher2_id=c.get("teacher2_id"),
        teachers=c.get("teachers", {}),
    )


def _build_events(
    courses: list[Course], batches: dict[str, Batch], grid: TimeGrid
) -> list[Event]:
    events: list[Event] = []
    eid = 0
    lab_section_events: dict[tuple[str, str, str], Event] = {}

    for course in courses:
        batch = batches.get(course.batch)
        if not batch:
            continue

        t1 = course.teacher1_id
        t2 = course.teacher2_id

        for section in batch.sections:
            if course.is_theory:
                for k in range(course.periods_per_week):
                    if t1 and t2:
                        if k == 0:
                            tids = [t1]
                            is_shared = False
                        elif k == 1:
                            tids = [t2]
                            is_shared = False
                        else:
                            tids = [t1, t2]
                            is_shared = True
                    elif t1:
                        tids = [t1]
                        is_shared = False
                    elif t2:
                        tids = [t2]
                        is_shared = False
                    else:
                        fallback = course.theory_teacher(section)
                        tids = [fallback] if fallback else []
                        is_shared = False

                    events.append(
                        Event(
                            eid=eid,
                            course=course,
                            batch_id=batch.id,
                            section=section,
                            group=None,
                            length=1,
                            teacher_ids=tids,
                            room_kind=course.room_kind,
                            size=batch.section_size,
                            meeting_index=k,
                            is_shared=is_shared,
                        )
                    )
                    eid += 1
            else:
                # Sessional (Lab)
                lab_tids = [t for t in [t1, t2] if t]
                is_075 = (course.credit == 0.75)

                if is_075 and course.paired_course_id:
                    partner_key = (course.paired_course_id, batch.id, section)
                    if partner_key in lab_section_events:
                        partner_ev = lab_section_events[partner_key]
                        ev = Event(
                            eid=eid,
                            course=course,
                            batch_id=batch.id,
                            section=section,
                            group="G2",
                            length=grid.lab_periods,
                            teacher_ids=lab_tids or course.lab_teachers(section, "G2"),
                            room_kind=course.room_kind,
                            size=batch.group_size,
                            meeting_index=0,
                            paired_event_id=partner_ev.eid,
                        )
                        partner_ev.paired_event_id = ev.eid
                        events.append(ev)
                        lab_section_events[(course.code, batch.id, section)] = ev
                        eid += 1
                    else:
                        ev = Event(
                            eid=eid,
                            course=course,
                            batch_id=batch.id,
                            section=section,
                            group="G1",
                            length=grid.lab_periods,
                            teacher_ids=lab_tids or course.lab_teachers(section, "G1"),
                            room_kind=course.room_kind,
                            size=batch.group_size,
                            meeting_index=0,
                        )
                        events.append(ev)
                        lab_section_events[(course.code, batch.id, section)] = ev
                        eid += 1
                elif is_075:
                    events.append(
                        Event(
                            eid=eid,
                            course=course,
                            batch_id=batch.id,
                            section=section,
                            group="G1",
                            length=grid.lab_periods,
                            teacher_ids=lab_tids or course.lab_teachers(section, "G1"),
                            room_kind=course.room_kind,
                            size=batch.group_size,
                            meeting_index=0,
                        )
                    )
                    eid += 1
                else:
                    for gi, group in enumerate(batch.groups):
                        if t1 and t2:
                            g_tids = [t1] if gi % 2 == 0 else [t2]
                        elif lab_tids:
                            g_tids = lab_tids
                        else:
                            fallback_tids = course.lab_teachers(section, group)
                            g_tids = fallback_tids if fallback_tids else ([t1] if t1 else ([t2] if t2 else []))

                        for k in range(course.blocks_per_week or 1):
                            events.append(
                                Event(
                                    eid=eid,
                                    course=course,
                                    batch_id=batch.id,
                                    section=section,
                                    group=group,
                                    length=grid.lab_periods,
                                    teacher_ids=g_tids,
                                    room_kind=course.room_kind,
                                    size=batch.group_size,
                                    meeting_index=k,
                                )
                            )
                            eid += 1
    return events


# --------------------------------------------------------------- validation


def validate(problem: Problem) -> tuple[list[str], list[str]]:
    """Return (errors, warnings). Errors make the instance unsolvable as given."""
    errors: list[str] = []
    warnings: list[str] = []
    grid = problem.grid

    # Every teacher referenced must exist.
    for ev in problem.events:
        for tid in ev.teacher_ids:
            if tid not in problem.teachers:
                errors.append(f"{ev.label}: unknown teacher id {tid!r}.")

    # Rule: within a single batch, a teacher may not hold two different THEORY
    # courses. Scoped per batch rather than department-wide: your department's
    # own real routines show the same person owning a theory course for one
    # batch (e.g. 2nd Year) and a different theory course for another batch
    # (e.g. 4th Year) in the same term -- that's normal course-load spreading,
    # not the overload case the original rule is protecting against. What the
    # rule actually guards against is one section's own weekly bundle handing
    # the same teacher two different theory courses, which is checked here.
    theory_load: dict[tuple[str, str], set[str]] = {}
    for c in problem.courses:
        if not c.is_theory:
            continue
        for section in problem.batches[c.batch].sections:
            key = (c.theory_teacher(section), c.batch)
            theory_load.setdefault(key, set()).add(c.code)
    for (tid, batch), codes in theory_load.items():
        if len(codes) > 1:
            name = problem.teachers[tid].name if tid in problem.teachers else tid
            errors.append(
                f"{name} is assigned {len(codes)} different theory courses within "
                f"batch {batch} ({', '.join(sorted(codes))}). Department rule "
                f"allows only one per batch."
            )

    # Every event needs at least one room and at least one start slot.
    for ev in problem.events:
        if not problem.feasible_rooms(ev):
            errors.append(
                f"{ev.label}: no room of kind {ev.room_kind!r} with capacity "
                f">= {ev.size}."
            )
        if not problem.feasible_starts(ev):
            errors.append(
                f"{ev.label}: teacher availability leaves no legal start slot."
            )

    # Theory meetings must be spreadable across distinct days.
    for c in problem.courses:
        if c.is_theory and c.periods_per_week > grid.n_days:
            errors.append(
                f"{c.code} needs {c.periods_per_week} theory periods per week but "
                f"only {grid.n_days} teaching days exist, so they cannot be on "
                f"distinct days."
            )

    # Room supply: peak simultaneous demand per room kind.
    for kind in {r.kind for r in problem.rooms.values()}:
        supply = sum(1 for r in problem.rooms.values() if r.kind == kind)
        demand = sum(ev.length for ev in problem.events if ev.room_kind == kind)
        capacity = supply * grid.n_slots
        if demand > capacity:
            errors.append(
                f"Room kind {kind!r}: {demand} period-slots of demand against "
                f"{capacity} available ({supply} rooms x {grid.n_slots} slots)."
            )
        elif demand > 0.85 * capacity:
            warnings.append(
                f"Room kind {kind!r} is {demand / capacity:.0%} utilised. "
                f"Expect long solve times or poor soft-constraint scores."
            )

    # Cohort load: a cohort cannot need more periods than the week has.
    per_cohort: dict[tuple, int] = {}
    for ev in problem.events:
        for ck in problem.cohorts_of(ev):
            per_cohort[ck] = per_cohort.get(ck, 0) + ev.length
    for ck, load in per_cohort.items():
        if load > grid.n_slots:
            errors.append(
                f"Cohort {ck}: {load} periods of class against {grid.n_slots} "
                f"slots in the week."
            )
        elif load > 0.8 * grid.n_slots:
            warnings.append(f"Cohort {ck} is booked {load}/{grid.n_slots} periods.")

    # Teacher load sanity.
    tload: dict[str, int] = {}
    for ev in problem.events:
        for tid in ev.teacher_ids:
            tload[tid] = tload.get(tid, 0) + ev.length
    for tid, load in tload.items():
        if tid not in problem.teachers:
            continue
        t = problem.teachers[tid]
        ceiling = t.max_periods_per_day * grid.n_days
        if load > ceiling:
            errors.append(
                f"{t.name}: {load} periods per week exceeds the hard ceiling of "
                f"{ceiling} ({t.max_periods_per_day}/day x {grid.n_days} days)."
            )

    return errors, warnings
