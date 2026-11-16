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
    CourseSlotRule as CourseSlotRuleModel,
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
    "1-2|A": "CSE-101",
    "1-2|B": "CSE-102",
    "2-1|A": "CSE-105",
    "2-1|B": "CSE-306",
    "2-2|A": "CSE-105",
    "2-2|B": "CSE-306",
    "3-1|A": "CSE-401",
    "3-1|B": "CSE-402",
    "3-2|A": "CSE-401",
    "3-2|B": "CSE-402",
    "4-1|A": "CSE-501",
    "4-1|B": "CSE-502",
    "4-2|A": "CSE-501",
    "4-2|B": "CSE-502",
}

DEFAULT_OPTIONS = {
    "sync_group_labs": True,
    "max_consecutive_periods": 3,
    "max_teacher_labs_per_day": 2,
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
        "lab_room_priority": 2,
        "same_course_consecutive": 30,
        "teacher_extra_lab_day": 120,
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
    """Load grid and solver options from DB if available, else defaults."""
    import sqlite3
    from routine.timegrid import build_time_grid_from_config
    from .db import DB_PATH, get_db_time_grid_config

    try:
        with sqlite3.connect(DB_PATH) as con:
            cfg = get_db_time_grid_config(con)
            grid = build_time_grid_from_config(cfg)
            return grid, dict(DEFAULT_OPTIONS)
    except Exception:
        pass

    periods = [Period(**p) for p in DEFAULT_PERIODS]
    breaks = [Break(**b) for b in DEFAULT_BREAKS]
    grid = TimeGrid(days=DEFAULT_DAYS, periods=periods, breaks=breaks, lab_periods=3)
    return grid, dict(DEFAULT_OPTIONS)


CURRICULUM_ORDER = ["1-1", "1-2", "2-1", "2-2", "3-1", "3-2", "4-1", "4-2"]


def _parse_slots_from_rule(day_str: str, periods_str: str, grid: TimeGrid) -> set[int]:
    """Parse human day and period strings (e.g. 'Monday', 'P1,P2,P3') into set of slot indices."""
    day_name_map = {d.lower(): i for i, d in enumerate(grid.days)}
    period_name_map = {p.name.lower(): i for i, p in enumerate(grid.periods)}

    day_str = (day_str or "").strip().lower()
    if day_str in ("all", "daily", "*"):
        day_indices = list(range(grid.n_days))
    elif day_str in day_name_map:
        day_indices = [day_name_map[day_str]]
    else:
        match = None
        for d_idx, d_name in enumerate(grid.days):
            if d_name.lower() == day_str:
                match = d_idx
                break
        try:
            day_indices = [match] if match is not None else [grid.day_index(day_str.capitalize())]
        except Exception:
            day_indices = []

    periods_str = (periods_str or "").strip().lower()
    if periods_str in ("all", "*"):
        period_indices = list(range(grid.n_periods))
    else:
        period_indices = []
        for token in periods_str.split(","):
            token = token.strip().lower()
            if not token:
                continue
            if token in period_name_map:
                period_indices.append(period_name_map[token])
            else:
                try:
                    period_indices.append(grid.period_index(token.upper()))
                except Exception:
                    pass

    slots: set[int] = set()
    for day_i in day_indices:
        for p in period_indices:
            slots.add(grid.slot(day_i, p))
    return slots


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

    # 2. Batches (Only active running batches with status='on', strictly in CURRICULUM_ORDER)
    batches: dict[str, RoutineBatch] = {}
    active_batch_ids: set[str] = set()
    active_batch_models = db.query(BatchModel).filter(BatchModel.status == "on").all()
    active_batch_models.sort(
        key=lambda b: CURRICULUM_ORDER.index(b.id) if b.id in CURRICULUM_ORDER else 99
    )
    for b in active_batch_models:
        active_batch_ids.add(b.id)
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

    day_name_map = {d.lower(): i for i, d in enumerate(grid.days)}
    period_name_map = {p.name.lower(): i for i, p in enumerate(grid.periods)}

    for t in db_teachers:
        blocked: set[int] = set()

        # If teacher is on leave, block all slots across the week
        if getattr(t, "status", "active") == "on_leave":
            blocked.update(range(grid.n_slots))

        for u in unavail_by_teacher.get(t.id, []):
            try:
                day_str = (u.day or "").strip().lower()
                if day_str in ("all", "daily", "*"):
                    day_indices = list(range(grid.n_days))
                elif day_str in day_name_map:
                    day_indices = [day_name_map[day_str]]
                else:
                    match = None
                    for d_idx, d_name in enumerate(grid.days):
                        if d_name.lower() == day_str:
                            match = d_idx
                            break
                    day_indices = [match] if match is not None else [grid.day_index(u.day.strip())]

                periods_str = (u.periods or "").strip().lower()
                if periods_str in ("all", "*"):
                    period_indices = list(range(grid.n_periods))
                else:
                    period_indices = []
                    for token in periods_str.split(","):
                        token = token.strip().lower()
                        if not token:
                            continue
                        if token in period_name_map:
                            period_indices.append(period_name_map[token])
                        else:
                            try:
                                period_indices.append(grid.period_index(token.upper()))
                            except Exception:
                                pass

                for day_i in day_indices:
                    for p in period_indices:
                        blocked.add(grid.slot(day_i, p))
            except Exception:
                pass

        teachers[t.id] = RoutineTeacher(
            id=t.id,
            name=t.full_name,
            short=t.short_code,
            unavailable=blocked,
            max_periods_per_day=t.max_periods_per_day,
            department=t.department or "CSE",
        )

    # 4. Courses & Assignments (Only active batches, strictly in CURRICULUM_ORDER)
    db_courses = [c for c in db.query(CourseModel).all() if c.batch_id in active_batch_ids]
    db_courses.sort(
        key=lambda c: (
            CURRICULUM_ORDER.index(c.batch_id) if c.batch_id in CURRICULUM_ORDER else 99,
            c.id,
        )
    )
    db_assignments = db.query(AssignmentModel).all()

    # Index assignments by course_id
    assign_by_course: dict[str, list[AssignmentModel]] = {}
    for a in db_assignments:
        assign_by_course.setdefault(a.course_id, []).append(a)

    # Query course slot rules (Constraint 3)
    db_slot_rules = db.query(CourseSlotRuleModel).all()
    slot_rules_by_course: dict[str, list[CourseSlotRuleModel]] = {}
    for sr in db_slot_rules:
        slot_rules_by_course.setdefault(sr.course_id, []).append(sr)

    courses: list[RoutineCourse] = []
    for c in db_courses:
        batch = batches.get(c.batch_id)
        c_assigns = assign_by_course.get(c.id, [])

        t1 = c.teacher1_id
        t2 = c.teacher2_id
        if c_assigns:
            seen_tids = list(dict.fromkeys(a.teacher_id for a in c_assigns if a.teacher_id))
            if not t1 and seen_tids:
                t1 = seen_tids[0]
            if not t2:
                for tid in seen_tids:
                    if tid != t1:
                        t2 = tid
                        break

        # For optional / elective courses: only schedule if teachers have been assigned (offered this term)
        if c.category in ("optional_ii", "optional_iii") and not t1 and not t2 and not c_assigns:
            continue

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

        clean_id = c.id.replace(" ", "").upper()
        if clean_id.startswith("CSE3200"):
            course_code = "CSE 3200"
            course_rkind = "no_room"
        elif clean_id.startswith("CSE4000"):
            course_code = "CSE 4000"
            course_rkind = "no_room"
        elif clean_id == "CSE3230":
            course_code = "CSE 3230"
            course_rkind = "seminar_501"
        else:
            course_code = c.id
            course_rkind = c.room_kind

        # Constraint 3: Parse allowed and blocked slots for this course
        c_allowed: set[int] = set()
        c_blocked: set[int] = set()
        c_sec_allowed: dict[str, set[int]] = {}
        c_sec_blocked: dict[str, set[int]] = {}

        for rule in slot_rules_by_course.get(c.id, []):
            rule_slots = _parse_slots_from_rule(rule.day, rule.periods, grid)
            rtype = (rule.rule_type or "allowed").strip().lower()
            sec = (rule.section or "").strip()
            if not sec or sec.upper() == "ALL":
                if rtype == "allowed":
                    c_allowed.update(rule_slots)
                else:
                    c_blocked.update(rule_slots)
            else:
                if rtype == "allowed":
                    c_sec_allowed.setdefault(sec, set()).update(rule_slots)
                else:
                    c_sec_blocked.setdefault(sec, set()).update(rule_slots)

        courses.append(
            RoutineCourse(
                code=course_code,
                title=c.title,
                batch=c.batch_id,
                kind=c.kind,
                room_kind=course_rkind,
                periods_per_week=c.periods_per_week or (3 if c.kind == THEORY else 0),
                blocks_per_week=c.blocks_per_week or (1 if c.kind != THEORY else 0),
                credit=course_credit,
                paired_course_id=c.paired_course_id,
                teacher1_id=t1,
                teacher2_id=t2,
                teachers=teachers_map,
                allowed_slots=c_allowed,
                blocked_slots=c_blocked,
                section_allowed_slots=c_sec_allowed,
                section_blocked_slots=c_sec_blocked,
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

        clean_code = course.code.replace(" ", "").upper()
        if clean_code in ("CSE3200", "CSE4000") or clean_code.startswith("CSE4000"):
            # Project / Thesis courses: section-wide weekly slot (not group-wise)
            # Supervised individually, no classroom teachers or physical rooms assigned
            n_blocks = course.blocks_per_week or (2 if course.credit == 3.0 else 1)
            for section in batch.sections:
                for k in range(n_blocks):
                    events.append(
                        Event(
                            eid=eid,
                            course=course,
                            batch_id=batch.id,
                            section=section,
                            group=None,
                            length=grid.lab_periods,
                            teacher_ids=[],
                            room_kind="no_room",
                            size=batch.section_size,
                            meeting_index=k,
                        )
                    )
                    eid += 1
            continue

        if clean_code == "CSE3230":
            # CSE 3230: Technical Writing and Seminar:
            # Taken jointly for both Section A and Section B at the same time in CSE Room 501
            lab_tids = [t for t in [course.teacher1_id, course.teacher2_id] if t]
            if not lab_tids:
                all_g_tids = []
                for s in batch.sections:
                    for g in batch.groups:
                        for tid in course.lab_teachers(s, g):
                            if tid and tid not in all_g_tids:
                                all_g_tids.append(tid)
                lab_tids = all_g_tids
            if not lab_tids:
                lab_tids = ["km_azharul_hasan", "kazi_saeed_alam"]

            events.append(
                Event(
                    eid=eid,
                    course=course,
                    batch_id=batch.id,
                    section="A/B",
                    group=None,
                    length=grid.lab_periods,
                    teacher_ids=lab_tids,
                    room_kind="seminar_501",
                    size=min(batch.section_size, 70),
                    meeting_index=0,
                )
            )
            eid += 1
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
                    if t1 and t2 and t1 != t2:
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

                    tids = list(dict.fromkeys([t for t in tids if t]))

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
                    all_g_tids = []
                    for g in batch.groups:
                        for tid in course.lab_teachers(section, g):
                            if tid and tid not in all_g_tids:
                                all_g_tids.append(tid)
                    lab_tids = all_g_tids

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
                    # Standalone 0.75 credit lab: one session per section alternating G1/G2 bi-weekly
                    events.append(
                        Event(
                            eid=eid,
                            course=course,
                            batch_id=batch.id,
                            section=section,
                            group="G1/G2",
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
                    # All labs must be conducted by both assigned teachers
                    for gi, group in enumerate(batch.groups):
                        grp_tids = course.lab_teachers(section, group)
                        grp_tids = [tid for tid in grp_tids if tid]
                        combined_tids = list(dict.fromkeys(grp_tids or lab_tids))
                        if not combined_tids:
                            combined_tids = [t for t in [t1, t2] if t]
                        for k in range(course.blocks_per_week or 1):
                            events.append(
                                Event(
                                    eid=eid,
                                    course=course,
                                    batch_id=batch.id,
                                    section=section,
                                    group=group,
                                    length=grid.lab_periods,
                                    teacher_ids=combined_tids,
                                    room_kind=course.room_kind,
                                    size=batch.group_size,
                                    meeting_index=k,
                                )
                            )
                            eid += 1

    def _apply_course_slot_rules(ev: Event) -> None:
        blocked = set(ev.course.blocked_slots)
        if ev.section and ev.section in ev.course.section_blocked_slots:
            blocked.update(ev.course.section_blocked_slots[ev.section])
        ev.blocked_slots = blocked

        sec_allowed = ev.course.section_allowed_slots.get(ev.section)
        if sec_allowed:
            if ev.course.allowed_slots:
                ev.allowed_slots = set(sec_allowed).intersection(ev.course.allowed_slots)
            else:
                ev.allowed_slots = set(sec_allowed)
        elif ev.course.allowed_slots:
            ev.allowed_slots = set(ev.course.allowed_slots)
        else:
            ev.allowed_slots = set()

    for ev in events:
        _apply_course_slot_rules(ev)

    # Synchronize allowed/blocked slots between paired 0.75-credit sessional events
    for ev in events:
        if ev.paired_event_id is not None:
            partner = next((other for other in events if other.eid == ev.paired_event_id), None)
            if partner:
                common_blocked = ev.blocked_slots | partner.blocked_slots
                if ev.allowed_slots and partner.allowed_slots:
                    common_allowed = ev.allowed_slots & partner.allowed_slots
                else:
                    common_allowed = ev.allowed_slots or partner.allowed_slots
                ev.allowed_slots = set(common_allowed)
                partner.allowed_slots = set(common_allowed)
                ev.blocked_slots = set(common_blocked)
                partner.blocked_slots = set(common_blocked)

    return events


def _has_bipartite_matching(adj: list[list[int]]) -> bool:
    """Check if every left vertex can be matched to a distinct right vertex (Kuhn's algo)."""
    match_r: dict[int, int] = {}

    def dfs(u: int, seen: set[int]) -> bool:
        for v in adj[u]:
            if v in seen:
                continue
            seen.add(v)
            if v not in match_r or dfs(match_r[v], seen):
                match_r[v] = u
                return True
        return False

    for u in range(len(adj)):
        if not dfs(u, set()):
            return False
    return True


def _max_teacher_capacity_under_h4_h10(
    tid: str,
    evs: list[Event],
    problem: Problem,
    feasible_starts_map: dict[int, set[int]],
) -> tuple[int, bool]:
    """Compute provably sound maximum weekly periods teacher `tid` can teach
    under H2 (single place), H4 (same course-section distinct days), H10
    (no consecutive different-course classes), Constraint 1 (unavailability),
    and Constraint 3 (course slot rules).

    Returns (exact_max_periods, lab_blocks_feasible).
    """
    from collections import defaultdict

    grid = problem.grid
    blocks = [list(b) for b in grid.blocks]
    lab_evs = [ev for ev in evs if ev.is_lab]
    th_evs = [ev for ev in evs if not ev.is_lab]
    n_labs = len(lab_evs)

    # Guard for non-standard multi-period structures
    if any(ev.length != grid.lab_periods for ev in lab_evs) or any(ev.length != 1 for ev in th_evs):
        return problem.teachers[tid].max_periods_per_day * grid.n_days, True

    # 1. Check bipartite matching of lab events to distinct feasible blocks
    lab_adj: list[list[int]] = []
    block_start_slots = [d * grid.n_periods + blk[0] for d in range(grid.n_days) for blk in blocks]
    block_slot_set = set(block_start_slots)
    for ev in lab_evs:
        feas_blks = [s for s in feasible_starts_map[ev.eid] if s in block_slot_set]
        lab_adj.append(feas_blks)
    lab_blocks_feasible = _has_bipartite_matching(lab_adj)
    if not lab_blocks_feasible:
        return 0, False

    adjacent_pairs = [(0, 1), (1, 2), (2, 3), (3, 4), (4, 5), (6, 7), (7, 8)]
    if problem.options.get("teacher_consecutive_include_lunch", False):
        adjacent_pairs.append((5, 6))

    adj_map: dict[int, set[int]] = defaultdict(set)
    for a, b in adjacent_pairs:
        adj_map[a].add(b)
        adj_map[b].add(a)

    th_by_course: dict[str, list[Event]] = defaultdict(list)
    for ev in th_evs:
        th_by_course[ev.course.code.replace(" ", "").upper()].append(ev)

    max_labs_day = problem.options.get("max_teacher_labs_per_day", 2)

    day_caps: list[list[int]] = []
    for d in range(grid.n_days):
        base = d * grid.n_periods
        lab_ok: list[bool] = []
        lab_courses: list[set[str]] = []
        for blk in blocks:
            start_s = base + blk[0]
            cs = {
                ev.course.code.replace(" ", "").upper()
                for ev in lab_evs
                if start_s in feasible_starts_map[ev.eid]
            }
            lab_ok.append(bool(cs))
            lab_courses.append(cs)

        th_courses_at: list[set[str]] = []
        th_cohorts_at: list[dict[str, set[tuple]]] = []
        for per in range(grid.n_periods):
            s = base + per
            cs: set[str] = set()
            coh: dict[str, set[tuple]] = defaultdict(set)
            for c_code, cevs in th_by_course.items():
                for ev in cevs:
                    if s in feasible_starts_map[ev.eid]:
                        cs.add(c_code)
                        coh[c_code].add((ev.batch_id, ev.section, ev.group))
            th_courses_at.append(cs)
            th_cohorts_at.append(coh)

        best_k = [-1] * (len(blocks) + 1)
        for lmask in range(1 << len(blocks)):
            if any(((lmask >> bi) & 1) and not lab_ok[bi] for bi in range(len(blocks))):
                continue
            k_labs = bin(lmask).count("1")
            if max_labs_day is not None and max_labs_day >= 0 and k_labs > max_labs_day:
                continue
            used_by_lab: set[int] = set()
            for bi in range(len(blocks)):
                if (lmask >> bi) & 1:
                    used_by_lab.update(blocks[bi])

            free_periods = [
                per for per in range(grid.n_periods) if per not in used_by_lab and th_courses_at[per]
            ]

            best_th = 0
            nf = len(free_periods)
            for tmask in range(1, 1 << nf):
                cnt = bin(tmask).count("1")
                if cnt <= best_th:
                    continue
                chosen = {free_periods[i] for i in range(nf) if (tmask >> i) & 1}
                active = chosen | used_by_lab
                visited: set[int] = set()
                valid = True
                for start_p in chosen:
                    if start_p in visited:
                        continue
                    comp: list[int] = []
                    q = [start_p]
                    visited.add(start_p)
                    while q:
                        u = q.pop()
                        comp.append(u)
                        for v in adj_map[u]:
                            if v in active and v not in visited:
                                visited.add(v)
                                q.append(v)

                    th_in_comp = [x for x in comp if x in chosen]
                    touched_bis = {
                        bi
                        for bi in range(len(blocks))
                        if ((lmask >> bi) & 1) and any(x in blocks[bi] for x in comp)
                    }
                    cand_courses = set(th_courses_at[th_in_comp[0]])
                    for x in th_in_comp[1:]:
                        cand_courses &= th_courses_at[x]
                    for bi in touched_bis:
                        cand_courses &= lab_courses[bi]
                    if not cand_courses:
                        valid = False
                        break

                    ok_h4 = False
                    for c_code in cand_courses:
                        avail_cohorts: set[tuple] = set()
                        for x in th_in_comp:
                            avail_cohorts |= th_cohorts_at[x][c_code]
                        if len(avail_cohorts) >= len(th_in_comp):
                            ok_h4 = True
                            break
                    if not ok_h4:
                        valid = False
                        break

                if valid:
                    best_th = cnt

            tot_day = k_labs * grid.lab_periods + best_th
            if tot_day > best_k[k_labs]:
                best_k[k_labs] = tot_day
        day_caps.append(best_k)

    dp: dict[int, int] = {0: 0}
    for best_k in day_caps:
        ndp: dict[int, int] = {}
        for used_l, val in dp.items():
            for kl, dval in enumerate(best_k):
                if dval < 0:
                    continue
                nl = used_l + kl
                if nl > n_labs:
                    continue
                nv = val + dval
                if nl not in ndp or nv > ndp[nl]:
                    ndp[nl] = nv
        dp = ndp

    return dp.get(n_labs, -1), True


def validate_db_problem(problem: Problem, db: Session | None = None) -> tuple[list[str], list[str]]:
    """Return (errors, warnings).

    Errors make the instance unsolvable. Warnings flag risky situations
    (e.g., high room utilization, on-leave teachers assigned).
    """
    from collections import defaultdict

    errors: list[str] = []
    warnings: list[str] = []
    grid = problem.grid

    feasible_starts_map: dict[int, set[int]] = {
        ev.eid: set(problem.feasible_starts(ev)) for ev in problem.events
    }
    on_leave_teachers: dict[str, str] = {}
    if db is not None:
        on_leave_teachers = {
            t.id: t.full_name for t in db.query(TeacherModel).filter_by(status="on_leave").all()
        }

    # 1. Teacher existence, completeness, rooms, and feasible starts
    seen_warned: set[tuple[str, str]] = set()
    for ev in problem.events:
        clean_code = ev.course.code.replace(" ", "").upper()
        is_project = clean_code in ("CSE3200", "CSE4000") or clean_code.startswith("CSE4000")

        if not problem.feasible_rooms(ev):
            errors.append(
                f"{ev.label}: no room of kind {ev.room_kind!r} with capacity >= {ev.size}."
            )

        if is_project:
            if not feasible_starts_map[ev.eid]:
                errors.append(
                    f"{ev.label}: no feasible time slot available on the weekly grid."
                )
            continue

        if not ev.teacher_ids:
            errors.append(f"{ev.label}: no teacher assigned to this meeting.")
            continue

        bad_tid = False
        leave_names: list[str] = []
        for tid in ev.teacher_ids:
            if not tid or tid not in problem.teachers:
                errors.append(f"{ev.label}: unknown teacher id {tid!r}.")
                bad_tid = True
            elif tid in on_leave_teachers:
                leave_names.append(on_leave_teachers[tid])
                if (tid, ev.label) not in seen_warned:
                    warnings.append(
                        f"Teacher {on_leave_teachers[tid]} is marked 'on_leave' but assigned to {ev.label}."
                    )
                    seen_warned.add((tid, ev.label))

        if not bad_tid and not feasible_starts_map[ev.eid]:
            if leave_names:
                errors.append(
                    f"{ev.label}: no feasible time slot because assigned teacher(s) "
                    f"({', '.join(leave_names)}) marked ON LEAVE."
                )
            else:
                errors.append(
                    f"{ev.label}: no feasible time slot available on the weekly grid "
                    f"(restricted by teacher availability or course slot rules)."
                )

    # 2. Theory load (H8): at most one theory course per batch per teacher (checks BOTH Teacher 1 & Teacher 2)
    theory_load: dict[tuple[str, str], set[str]] = {}
    for ev in problem.events:
        if ev.is_lab:
            continue
        for tid in ev.teacher_ids:
            if tid:
                theory_load.setdefault((tid, ev.batch_id), set()).add(ev.course.code)

    for (tid, batch), codes in theory_load.items():
        if len(codes) > 1:
            name = problem.teachers[tid].name if tid in problem.teachers else tid
            errors.append(
                f"H8 Violation — {name} is assigned {len(codes)} different theory courses within "
                f"batch {batch} ({', '.join(sorted(codes))}). Department rule allows only one theory course per batch."
            )

    # 3. Paired 0.75-credit lab simultaneous teacher check (H2 vs paired sync)
    ev_by_id = {ev.eid: ev for ev in problem.events}
    checked_pairs: set[tuple[int, int]] = set()
    for ev in problem.events:
        if ev.paired_event_id is not None and ev.paired_event_id in ev_by_id:
            pair_key = (min(ev.eid, ev.paired_event_id), max(ev.eid, ev.paired_event_id))
            if pair_key in checked_pairs:
                continue
            checked_pairs.add(pair_key)
            partner = ev_by_id[ev.paired_event_id]
            shared = sorted(set(ev.teacher_ids) & set(partner.teacher_ids))
            if shared:
                names = ", ".join(problem.teachers[t].name if t in problem.teachers else t for t in shared)
                errors.append(
                    f"Paired 0.75-cr labs {ev.label} and {partner.label} run in the same time block "
                    f"and cannot share teacher(s): {names}."
                )

    # 4. Theory & multi-block meetings distinct days (H4) + day feasibility bipartite check
    for c in problem.courses:
        if c.is_theory and c.periods_per_week > grid.n_days:
            errors.append(
                f"{c.code} needs {c.periods_per_week} theory periods per week but "
                f"only {grid.n_days} teaching days exist, so they cannot be on distinct days."
            )

    h4_groups: dict[tuple, list[Event]] = defaultdict(list)
    for ev in problem.events:
        h4_groups[(ev.course.code, ev.batch_id, ev.section, ev.group)].append(ev)

    for key, grp_evs in h4_groups.items():
        if len(grp_evs) < 2:
            continue
        if any(not feasible_starts_map[e.eid] for e in grp_evs):
            continue
        day_adj = [sorted({grid.day_of(s) for s in feasible_starts_map[e.eid]}) for e in grp_evs]
        if not _has_bipartite_matching(day_adj):
            errors.append(
                f"H4 Conflict — {grp_evs[0].label}: {len(grp_evs)} weekly meetings must fall on distinct "
                f"days, but teacher/course slot rules leave insufficient distinct days."
            )

    # 5. Fixed single-slot + single-room direct collision check (H3)
    fixed_room_slot: dict[tuple[str, int], list[Event]] = defaultdict(list)
    for ev in problem.events:
        rooms = problem.feasible_rooms(ev)
        starts = feasible_starts_map[ev.eid]
        if len(rooms) == 1 and rooms[0].id not in ("NO_ROOM", "", None) and len(starts) == 1:
            s0 = next(iter(starts))
            rid = rooms[0].id
            for t in range(s0, s0 + ev.length):
                fixed_room_slot[(rid, t)].append(ev)

    reported_fixed_room: set[tuple[str, str]] = set()
    for (rid, t), cevs in fixed_room_slot.items():
        if len(cevs) > 1:
            labels = sorted({e.label for e in cevs})
            # Ignore if same paired lab sharing a slot intentionally? (Only if different rooms; here same rid!)
            sig = (rid, ", ".join(labels))
            if sig not in reported_fixed_room:
                reported_fixed_room.add(sig)
                rname = problem.rooms[rid].name if rid in problem.rooms else rid
                errors.append(
                    f"Fixed Slot Room Collision in {rname} at {grid.describe(t)}: {', '.join(labels)}."
                )

    # 6. Room supply
    for kind in {r.kind for r in problem.rooms.values() if r.kind != "no_room"}:
        supply = sum(1 for r in problem.rooms.values() if r.kind == kind)
        demand = sum(
            ev.length
            for ev in problem.events
            if ev.room_kind == kind
            and ev.course.code.replace(" ", "").upper() not in ("CSE3200", "CSE4000")
            and not ev.course.code.replace(" ", "").upper().startswith("CSE4000")
        )
        if kind == "theory":
            # Technical Writing & Seminar (CSE 3230) runs in CSE Room 501
            demand += sum(ev.length for ev in problem.events if ev.room_kind == "seminar_501")
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

    # 7. Cohort load
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

    # 8. Teacher load + Exact H4 & H10 & Availability block-packing ceiling
    t_evs_map: dict[str, list[Event]] = defaultdict(list)
    for ev in problem.events:
        clean_c = ev.course.code.replace(" ", "").upper()
        if clean_c in ("CSE3200", "CSE4000") or clean_c.startswith("CSE4000"):
            continue
        for tid in ev.teacher_ids:
            t_evs_map[tid].append(ev)

    max_lab_starts = len(grid.lab_start_slots())
    max_th_starts = len(grid.theory_start_slots())
    max_labs_day = problem.options.get("max_teacher_labs_per_day", 2)
    block_start_slots = {
        d * grid.n_periods + blk[0] for d in range(grid.n_days) for blk in grid.blocks
    }

    for tid, evs in t_evs_map.items():
        if tid not in problem.teachers:
            continue
        t = problem.teachers[tid]
        load = sum(ev.length for ev in evs)
        ceiling = t.max_periods_per_day * grid.n_days
        if load > ceiling:
            errors.append(
                f"{t.name} ({t.short}): {load} periods/week exceeds the hard ceiling of "
                f"{ceiling} ({t.max_periods_per_day}/day x {grid.n_days} days)."
            )

        lab_evs = [ev for ev in evs if ev.is_lab]
        n_labs = len(lab_evs)

        # H12: Daily lab session ceiling per teacher (at most max_teacher_labs_per_day labs/day)
        if (
            max_labs_day is not None
            and max_labs_day >= 0
            and n_labs > max_labs_day
            and not any(not feasible_starts_map[ev.eid] for ev in lab_evs)
        ):
            assigned_codes = sorted({f"{ev.course.code} ({ev.batch_id})" for ev in evs})
            if n_labs > max_labs_day * grid.n_days:
                errors.append(
                    f"H12 Teacher Daily Lab Limit — {t.name} ({t.short}) is assigned {n_labs} weekly lab "
                    f"sessions, exceeding the maximum of {max_labs_day * grid.n_days} ({max_labs_day} labs/day × "
                    f"{grid.n_days} days) (Assigned: {', '.join(assigned_codes)})."
                )
                continue
            lab_day_adj = [
                [
                    d * max_labs_day + copy_i
                    for d in sorted({grid.day_of(s) for s in feasible_starts_map[ev.eid] if s in block_start_slots})
                    for copy_i in range(max_labs_day)
                ]
                for ev in lab_evs
            ]
            if not _has_bipartite_matching(lab_day_adj):
                errors.append(
                    f"H12 Teacher Daily Lab Limit — {t.name} ({t.short}) cannot be scheduled within the limit of "
                    f"at most {max_labs_day} lab session(s)/day given current availability/course slot rules "
                    f"(Assigned {n_labs} labs: {', '.join(assigned_codes)})."
                )
                continue

        # Skip deeper H4+H10+Availability DP if a teacher has no missing slots and load is safely below 30
        has_restrictions = bool(t.unavailable) or any(
            len(feasible_starts_map[ev.eid]) < (max_lab_starts if ev.is_lab else max_th_starts)
            for ev in evs
        )
        if not has_restrictions and load <= 30 + n_labs and load < 26:
            continue

        # Skip if some event already has 0 feasible starts (already reported above)
        if any(not feasible_starts_map[ev.eid] for ev in evs):
            continue

        exact_cap, lab_ok = _max_teacher_capacity_under_h4_h10(tid, evs, problem, feasible_starts_map)
        assigned_codes = sorted({f"{ev.course.code} ({ev.batch_id})" for ev in evs})
        if not lab_ok:
            errors.append(
                f"Teacher Lab Slot Conflict — {t.name} ({t.short}) needs {n_labs} distinct 3-period "
                f"lab block(s), but availability/course rules leave too few non-overlapping blocks "
                f"(Assigned: {', '.join(assigned_codes)})."
            )
        elif exact_cap < 0:
            errors.append(
                f"H12 / Teacher Daily Lab Limit — {t.name} ({t.short}) cannot fit {n_labs} lab block(s) "
                f"with at most {max_labs_day} lab(s)/day across distinct blocks under current slot rules "
                f"(Assigned: {', '.join(assigned_codes)})."
            )
        elif load > exact_cap:
            th_periods = sum(ev.length for ev in evs if not ev.is_lab)
            lab_periods = sum(ev.length for ev in evs if ev.is_lab)
            excess = load - exact_cap
            errors.append(
                f"Teacher Overload (H4 + H10 + H12 + Availability) — {t.name} ({t.short}) is assigned "
                f"{load} periods/week ({th_periods} theory + {lab_periods} lab across {n_labs} lab block(s)), "
                f"which exceeds the maximum mathematically feasible capacity of {exact_cap} periods/week. "
                f"Under Hard Constraints H10 (no consecutive different-course classes), H12 (max {max_labs_day} labs/day), and H4, "
                f"each non-lab block can hold at most 2 periods. Assigned: {', '.join(assigned_codes)}. "
                f"Reassign/remove at least {excess} period(s) (e.g., update a 2nd teacher in Assignments) "
                f"or relax slot restrictions."
            )
        elif exact_cap > 0 and load == exact_cap and load >= 34:
            warnings.append(
                f"{t.name} ({t.short}) is at {load}/{exact_cap} maximum feasible weekly periods under H10/H12 (0 block slack)."
            )

    return errors, warnings
