"""Build Problem objects from the database and validate before solving.

Mirrors routine/loader.py's structure and validate() logic, but reads from
the SQLAlchemy database session instead of static JSON.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

from routine.models import (
    SESSIONAL,
    THEORY,
    Batch as RoutineBatch,
    Course as RoutineCourse,
    Event,
    Problem,
    Room as RoutineRoom,
    Teacher as RoutineTeacher,
)
from routine.timegrid import Break, Period, TimeGrid

from .db import (
    Assignment as AssignmentModel,
    Batch as BatchModel,
    Course as CourseModel,
    Room as RoomModel,
    Teacher as TeacherModel,
    TeacherUnavailable as TeacherUnavailableModel,
)

ROOT = Path(__file__).resolve().parents[1]

# Default time grid matching KUET CSE
DEFAULT_DAYS = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday"]
DEFAULT_PERIODS = [
    {"name": "P1", "start": "08:00", "end": "08:50"},
    {"name": "P2", "start": "08:50", "end": "09:40"},
    {"name": "P3", "start": "09:40", "end": "10:30"},
    {"name": "P4", "start": "10:40", "end": "11:30"},
    {"name": "P5", "start": "11:30", "end": "12:20"},
    {"name": "P6", "start": "12:20", "end": "13:10"},
    {"name": "P7", "start": "14:30", "end": "15:20"},
    {"name": "P8", "start": "15:20", "end": "16:10"},
    {"name": "P9", "start": "16:10", "end": "17:00"},
]
DEFAULT_BREAKS = [
    {"name": "Snack break", "after_period": "P3", "start": "10:30", "end": "10:40"},
    {"name": "Lunch & prayer", "after_period": "P6", "start": "13:10", "end": "14:30"},
]

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
    "sync_group_labs": True,
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


def _load_config() -> tuple[TimeGrid, dict]:
    """Load grid and solver options from real json if available, else defaults."""
    json_path = ROOT / "data" / "kuet_cse_real.json"
    if json_path.exists():
        try:
            raw = json.loads(json_path.read_text(encoding="utf-8"))
            cfg = raw.get("config", {})
            grid = TimeGrid.from_dict(cfg)
            opts = _merge(DEFAULT_OPTIONS, cfg.get("options", {}))
            return grid, opts
        except Exception:
            pass

    periods = [Period(**p) for p in DEFAULT_PERIODS]
    breaks = [Break(**b) for b in DEFAULT_BREAKS]
    grid = TimeGrid(days=DEFAULT_DAYS, periods=periods, breaks=breaks, lab_periods=3)
    return grid, dict(DEFAULT_OPTIONS)


def load_problem_from_db(db: Session, options_override: Optional[dict] = None) -> Problem:
    """Build a Problem instance entirely from current database contents."""
    grid, options = _load_config()
    if options_override:
        options = _merge(options, options_override)

    # Ensure default homerooms are set
    if "home_rooms" not in options:
        options["home_rooms"] = dict(DEFAULT_HOME_ROOMS)
    else:
        options["home_rooms"] = {**DEFAULT_HOME_ROOMS, **options["home_rooms"]}

    # 1. Rooms
    rooms: dict[str, RoutineRoom] = {}
    for r in db.query(RoomModel).all():
        rooms[r.id] = RoutineRoom(
            id=r.id,
            name=r.name,
            kind=r.kind,
            capacity=r.capacity,
        )

    # 2. Batches
    batches: dict[str, RoutineBatch] = {}
    for b in db.query(BatchModel).all():
        sections = [s.strip() for s in b.sections.split(",") if s.strip()]
        groups = [g.strip() for g in b.groups.split(",") if g.strip()]
        batches[b.id] = RoutineBatch(
            id=b.id,
            name=b.name,
            sections=sections,
            groups=groups,
            section_size=b.section_size,
            group_size=b.group_size,
        )

    # 3. Teachers & Unavailability
    teachers: dict[str, RoutineTeacher] = {}
    db_teachers = db.query(TeacherModel).all()
    unavail_records = db.query(TeacherUnavailableModel).all()
    unavail_by_teacher: dict[str, list[TeacherUnavailableModel]] = {}
    for u in unavail_records:
        unavail_by_teacher.setdefault(u.teacher_id, []).append(u)

    for t in db_teachers:
        blocked: set[int] = set()
        for u in unavail_by_teacher.get(t.id, []):
            try:
                day_i = grid.day_index(u.day)
                names = u.periods
                idxs = (
                    range(grid.n_periods)
                    if names == "all"
                    else [grid.period_index(p.strip()) for p in names.split(",") if p.strip()]
                )
                for p in idxs:
                    blocked.add(grid.slot(day_i, p))
            except Exception:
                pass

        teachers[t.id] = RoutineTeacher(
            id=t.id,
            name=t.full_name,
            short=t.short_code,
            unavailable=blocked,
            max_periods_per_day=t.max_periods_per_day,
        )

    # 4. Courses & Assignments
    db_courses = db.query(CourseModel).all()
    db_assignments = db.query(AssignmentModel).all()

    # Index assignments by course_id
    assign_by_course: dict[str, list[AssignmentModel]] = {}
    for a in db_assignments:
        assign_by_course.setdefault(a.course_id, []).append(a)

    courses: list[RoutineCourse] = []
    for c in db_courses:
        batch = batches.get(c.batch_id)
        c_assigns = assign_by_course.get(c.id, [])

        t1 = c.teacher1_id
        t2 = c.teacher2_id
        if not t1 and c_assigns:
            tids = [a.teacher_id for a in c_assigns if a.teacher_id]
            t1 = tids[0] if tids else None
            t2 = tids[1] if len(tids) > 1 else None

        teachers_map: dict = {}
        if c.kind == THEORY:
            for s in (batch.sections if batch else ["A", "B"]):
                teachers_map[s] = t1 or ""
        else:
            for s in (batch.sections if batch else ["A", "B"]):
                teachers_map[s] = {}
                for g in (batch.groups if batch else ["G1", "G2"]):
                    teachers_map[s][g] = [t for t in [t1, t2] if t]

        course_credit = c.credit or (3.0 if c.kind == THEORY else (1.5 if (c.blocks_per_week or 1) == 1 else 3.0))

        courses.append(
            RoutineCourse(
                code=c.id,
                title=c.title,
                batch=c.batch_id,
                kind=c.kind,
                room_kind=c.room_kind,
                periods_per_week=c.periods_per_week or (3 if c.kind == THEORY else 0),
                blocks_per_week=c.blocks_per_week or (1 if c.kind != THEORY else 0),
                credit=course_credit,
                paired_course_id=c.paired_course_id,
                teacher1_id=t1,
                teacher2_id=t2,
                teachers=teachers_map,
            )
        )

    # 5. Events
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


def _build_events(
    courses: list[RoutineCourse], batches: dict[str, RoutineBatch], grid: TimeGrid
) -> list[Event]:
    events: list[Event] = []
    eid = 0
    # Map for pairing 0.75 credit labs: (course_id, batch_id, section) -> Event
    lab_section_events: dict[tuple[str, str, str], Event] = {}

    for course in courses:
        batch = batches.get(course.batch)
        if not batch:
            continue

        t1 = course.teacher1_id
        t2 = course.teacher2_id

        for section in batch.sections:
            if course.is_theory:
                # Two teachers co-teach theory:
                # Class 1: personal by Teacher 1
                # Class 2: personal by Teacher 2
                # Class 3: shared by Teacher 1 and Teacher 2 (SR/TJ)
                # If only 1 teacher is set: all classes by Teacher 1
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
                if not lab_tids:
                    for g in batch.groups:
                        lab_tids = course.lab_teachers(section, g)
                        if lab_tids:
                            break

                is_075 = (course.credit == 0.75)
                if is_075 and course.paired_course_id:
                    # Paired 0.75 credit lab:
                    # Check if partner course was already processed for this section
                    partner_key = (course.paired_course_id, batch.id, section)
                    if partner_key in lab_section_events:
                        partner_ev = lab_section_events[partner_key]
                        # Course A had group "G1", so Course B takes group "G2"
                        ev = Event(
                            eid=eid,
                            course=course,
                            batch_id=batch.id,
                            section=section,
                            group="G2",
                            length=grid.lab_periods,
                            teacher_ids=lab_tids,
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
                            teacher_ids=lab_tids,
                            room_kind=course.room_kind,
                            size=batch.group_size,
                            meeting_index=0,
                        )
                        events.append(ev)
                        lab_section_events[(course.code, batch.id, section)] = ev
                        eid += 1
                elif is_075:
                    # Standalone 0.75 credit lab (alternating)
                    events.append(
                        Event(
                            eid=eid,
                            course=course,
                            batch_id=batch.id,
                            section=section,
                            group="G1",
                            length=grid.lab_periods,
                            teacher_ids=lab_tids,
                            room_kind=course.room_kind,
                            size=batch.group_size,
                            meeting_index=0,
                        )
                    )
                    eid += 1
                else:
                    # Standard 1.5 or 3.0 cr weekly lab (meets every week for each group)
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


def validate_db_problem(problem: Problem, db: Session | None = None) -> tuple[list[str], list[str]]:
    """Return (errors, warnings).

    Errors make the instance unsolvable. Warnings flag risky situations
    (e.g., high room utilization, on-leave teachers assigned).
    """
    errors: list[str] = []
    warnings: list[str] = []
    grid = problem.grid

    # 1. Teacher existence and completeness
    for ev in problem.events:
        if not ev.teacher_ids:
            errors.append(f"{ev.label}: no teacher assigned to this meeting.")
            continue
        for tid in ev.teacher_ids:
            if not tid or tid not in problem.teachers:
                errors.append(f"{ev.label}: unknown teacher id {tid!r}.")

    # Check for on-leave teachers assigned if db session provided
    if db is not None:
        on_leave_teachers = {
            t.id: t.full_name for t in db.query(TeacherModel).filter_by(status="on_leave").all()
        }
        seen_warned = set()
        for ev in problem.events:
            for tid in ev.teacher_ids:
                if tid in on_leave_teachers and (tid, ev.label) not in seen_warned:
                    warnings.append(
                        f"Teacher {on_leave_teachers[tid]} is marked 'on_leave' but assigned to {ev.label}."
                    )
                    seen_warned.add((tid, ev.label))

    # 2. Theory load: at most one theory course per batch per teacher
    theory_load: dict[tuple[str, str], set[str]] = {}
    for c in problem.courses:
        if not c.is_theory or c.batch not in problem.batches:
            continue
        for section in problem.batches[c.batch].sections:
            tid = c.theory_teacher(section)
            if tid:
                key = (tid, c.batch)
                theory_load.setdefault(key, set()).add(c.code)

    for (tid, batch), codes in theory_load.items():
        if len(codes) > 1:
            name = problem.teachers[tid].name if tid in problem.teachers else tid
            errors.append(
                f"{name} is assigned {len(codes)} different theory courses within "
                f"batch {batch} ({', '.join(sorted(codes))}). Department rule "
                f"allows only one per batch."
            )

    # 3. Room and slot feasibility for each event
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

    # 4. Theory meetings distinct days
    for c in problem.courses:
        if c.is_theory and c.periods_per_week > grid.n_days:
            errors.append(
                f"{c.code} needs {c.periods_per_week} theory periods per week but "
                f"only {grid.n_days} teaching days exist, so they cannot be on "
                f"distinct days."
            )

    # 5. Room supply
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

    # 6. Cohort load
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

    # 7. Teacher load
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
