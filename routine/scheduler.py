"""The CP-SAT model.

ENCODING
--------
For every event e we create one boolean per legal (room, start-slot) pair:

    x[e][(room, start)] = 1  <=>  event e runs in `room` beginning at `start`

Exactly one of them is true. Everything else -- conflicts, gaps, spread,
balance -- is a linear expression over those booleans, which is exactly the
shape CP-SAT is fastest on.

A "slot" is a flat index over the whole week: day * n_periods + period.
A theory event covers 1 slot. A lab event covers `lab_periods` consecutive
slots, and its start domain is restricted so it always lands inside a single
break-free block.
"""

from __future__ import annotations

from collections import defaultdict
import time
from dataclasses import dataclass, field

from ortools.sat.python import cp_model

from .models import Event, Problem


@dataclass
class Assignment:
    event: Event
    room_id: str
    start: int

    @property
    def slots(self) -> list[int]:
        return [self.start + k for k in range(self.event.length)]


@dataclass
class Solution:
    status: str
    assignments: list[Assignment] = field(default_factory=list)
    objective: int = 0
    best_bound: int = 0
    wall_seconds: float = 0.0
    penalties: dict[str, int] = field(default_factory=dict)
    unsynced_courses: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.status in ("OPTIMAL", "FEASIBLE")

    @property
    def by_event(self) -> dict[int, Assignment]:
        return {a.event.eid: a for a in self.assignments}

    def freeze_map(self) -> dict[int, tuple[str, int]]:
        return {a.event.eid: (a.room_id, a.start) for a in self.assignments}


class RoutineScheduler:
    def __init__(self, problem: Problem) -> None:
        self.p = problem
        self.grid = problem.grid
        self.opt = problem.options
        self.w = {"lab_room_priority": 2, **self.opt.get("weights", {})}

        self.model = cp_model.CpModel()
        self.x: dict[int, dict[tuple[str, int], cp_model.IntVar]] = {}
        self.cover: dict[int, dict[int, list]] = {}
        self.cover_room: dict[int, dict[tuple[str, int], list]] = {}
        self.unsynced_courses: list[str] = []
        self.slot_var: dict[int, cp_model.IntVar] = {}
        self.penalty_terms: dict[str, list] = {}
        self.bonus_terms: dict[str, list] = {}

    # ------------------------------------------------------------------ build

    def build(
        self,
        freeze: dict[int, tuple[str, int]] | None = None,
        hint: dict[int, tuple[str, int]] | None = None,
    ) -> None:
        self._create_variables()
        self._c_cohort_conflicts()
        self._c_teacher_conflicts()
        self._c_room_conflicts()
        self._c_theory_spread_and_symmetry()
        self._c_sync_group_labs()
        self._c_sync_paired_labs()
        self._c_teacher_diff_course_consecutive()
        self._c_teacher_max_labs_per_day()
        if freeze:
            self._c_freeze(freeze)
        self._objective()
        if hint:
            self._add_hint(hint)

    def _add_hint(self, hint: dict[int, tuple[str, int]]) -> None:
        """Warm-start from a known-feasible timetable.

        Finding *a* legal timetable is easy; finding a good one is not. Handing
        the optimiser a feasible starting point lets it spend its whole budget
        improving rather than searching for the first solution.
        """
        for eid, key in hint.items():
            cells = self.x.get(eid)
            if cells and key in cells:
                self.model.AddHint(cells[key], 1)

    # -- variables -----------------------------------------------------------

    def _create_variables(self) -> None:
        default_homerooms = {
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
        home_rooms = {**default_homerooms, **self.opt.get("home_rooms", {})}
        for ev in self.p.events:
            rooms = self.p.feasible_rooms(ev)
            clean_c = ev.course.code.replace(" ", "").upper()
            is_proj = clean_c in ("CSE3200", "CSE4000") or clean_c.startswith("CSE4000") or ev.room_kind in ("no_room", "none", "")
            if not ev.is_lab and not is_proj and not ev.allowed_rooms:
                home = home_rooms.get(f"{ev.batch_id}|{ev.section}")
                if home:
                    match = [r for r in rooms if r.id == home]
                    if match:
                        rooms = match
                    elif home in self.p.rooms:
                        rooms = [self.p.rooms[home]]

            # Ensure any specific room in ev.slot_room_rules is included in candidate rooms
            if hasattr(ev, "slot_room_rules") and ev.slot_room_rules:
                for rid in ev.slot_room_rules.values():
                    if rid in self.p.rooms and self.p.rooms[rid] not in rooms:
                        rooms.append(self.p.rooms[rid])
                    else:
                        for r in self.p.rooms.values():
                            if (r.id.lower() == rid.lower() or r.name.lower() == rid.lower()) and r not in rooms:
                                rooms.append(r)

            starts = self.p.feasible_starts(ev)

            cells: dict[tuple[str, int], cp_model.IntVar] = {}
            for r in rooms:
                for s in starts:
                    if hasattr(ev, "slot_room_rules") and ev.slot_room_rules:
                        # Check if this start slot covers a slot constrained to a specific room
                        covered = self.grid.covered_slots(s, ev.length)
                        req_room = None
                        for c_slot in covered:
                            if c_slot in ev.slot_room_rules:
                                req_room = ev.slot_room_rules[c_slot]
                                break
                        if req_room and r.id != req_room and r.name.lower() != req_room.lower():
                            continue

                    cells[(r.id, s)] = self.model.NewBoolVar(f"x_{ev.eid}_{r.id}_{s}")
            if not cells:
                raise ValueError(
                    f"{ev.label} has no legal (room, slot) pair. Run validate() first."
                )
            self.model.AddExactlyOne(cells.values())
            self.x[ev.eid] = cells

            sv = self.model.NewIntVar(0, self.grid.n_slots - 1, f"slot_{ev.eid}")
            self.model.Add(sv == sum(s * var for (_, s), var in cells.items()))
            self.slot_var[ev.eid] = sv

            # Coverage indexes. Built once per event so that every conflict
            # constraint below is an O(1) dictionary lookup instead of a rescan
            # of the whole variable table. Without this the model build itself
            # becomes the bottleneck long before the solver does.
            cover: dict[int, list] = {}
            cover_room: dict[tuple[str, int], list] = {}
            for (room_id, s), var in cells.items():
                for t in range(s, s + ev.length):
                    cover.setdefault(t, []).append(var)
                    cover_room.setdefault((room_id, t), []).append(var)
            self.cover[ev.eid] = cover
            self.cover_room[ev.eid] = cover_room

    def _occupies(self, ev: Event, t: int) -> list:
        """Booleans that put event `ev` on the grid during slot `t`."""
        return self.cover[ev.eid].get(t, [])

    # -- hard constraints ----------------------------------------------------

    def _c_cohort_conflicts(self) -> None:
        """H1. A student cohort attends at most one thing at a time.

        A cohort is (batch, section, group). A theory class occupies every
        group of its section, so theory automatically blocks both groups.
        """
        buckets: dict[tuple, list[Event]] = {c: [] for c in self.p.cohorts()}
        for ev in self.p.events:
            for ck in self.p.cohorts_of(ev):
                buckets[ck].append(ev)

        self.cohort_busy: dict[tuple, list[cp_model.IntVar]] = {}
        for ck, evs in buckets.items():
            busy = []
            for t in range(self.grid.n_slots):
                lits: list = []
                for ev in evs:
                    lits.extend(self._occupies(ev, t))
                b = self.model.NewBoolVar(f"cbusy_{ck}_{t}")
                # Equality also enforces the conflict: the sum cannot exceed 1.
                self.model.Add(b == sum(lits) if lits else b == 0)
                busy.append(b)
            self.cohort_busy[ck] = busy

    def _c_teacher_conflicts(self) -> None:
        """H2. A teacher is in one place at a time (your requirement 6)."""
        buckets: dict[str, list[Event]] = {tid: [] for tid in self.p.teachers}
        for ev in self.p.events:
            for tid in ev.teacher_ids:
                buckets[tid].append(ev)

        self.teacher_busy: dict[str, list[cp_model.IntVar]] = {}
        for tid, evs in buckets.items():
            busy = []
            unavail = self.p.teachers[tid].unavailable if tid in self.p.teachers else set()
            for t in range(self.grid.n_slots):
                lits: list = []
                for ev in evs:
                    lits.extend(self._occupies(ev, t))
                b = self.model.NewBoolVar(f"tbusy_{tid}_{t}")
                if t in unavail:
                    for lit in lits:
                        self.model.Add(lit == 0)
                    self.model.Add(b == 0)
                else:
                    self.model.Add(b == sum(lits) if lits else b == 0)
                busy.append(b)
            self.teacher_busy[tid] = busy

    def _c_room_conflicts(self) -> None:
        """H3. A room hosts one class at a time."""
        buckets: dict[tuple[str, int], list] = {}
        for ev in self.p.events:
            for (room_id, t), lits in self.cover_room[ev.eid].items():
                if room_id in ("NO_ROOM", "", None):
                    continue
                buckets.setdefault((room_id, t), []).extend(lits)
        for lits in buckets.values():
            if len(lits) > 1:
                self.model.AddAtMostOne(lits)

    def _c_theory_spread_and_symmetry(self) -> None:
        """H4. Meetings of one theory or multi-block course for the same cohort fall on distinct days.

        Also breaks the symmetry between interchangeable sibling meetings by
        forcing them into increasing slot order. Without this the solver wastes
        time exploring k! identical permutations of the same timetable.
        """
        groups: dict[tuple, list[Event]] = {}
        for ev in self.p.events:
            groups.setdefault((ev.course.code, ev.batch_id, ev.section, ev.group), []).append(ev)

        for key, evs in groups.items():
            evs.sort(key=lambda e: e.meeting_index)
            if len(evs) < 2:
                continue
            for d in range(self.grid.n_days):
                lo = d * self.grid.n_periods
                hi = lo + self.grid.n_periods
                per_day = []
                for ev in evs:
                    terms = [
                        var for (_, s), var in self.x[ev.eid].items() if lo <= s < hi
                    ]
                    if terms:
                        per_day.append(sum(terms))
                if per_day:
                    self.model.Add(sum(per_day) <= 1)
            for a, b in zip(evs, evs[1:]):
                self.model.Add(self.slot_var[a.eid] < self.slot_var[b.eid])

    def _c_sync_group_labs(self) -> None:
        """H5 (optional). Both groups of a section do their lab simultaneously,
        in different rooms of the same kind -- but ONLY where enough rooms of
        that kind actually exist for that to be physically possible.

        A section's two groups syncing needs two simultaneous rooms of the
        course's room_kind. A specialised lab that only has one physical room
        (an AI lab, say) can never host two groups at once no matter what this
        option says, so forcing sync there would make the instance
        unsolvable for a reason that has nothing to do with time, teachers, or
        any other real constraint -- purely a room-count mismatch. Instead,
        each course's groups are synced only when room supply allows it;
        otherwise they're left free and the solver staggers them by itself,
        the same way a department does by hand when a lab room is scarce.
        """
        if not self.opt.get("sync_group_labs", True):
            return
        groups: dict[tuple, list[Event]] = {}
        for ev in self.p.events:
            if not ev.is_lab:
                continue
            key = (ev.course.code, ev.batch_id, ev.section, ev.meeting_index)
            groups.setdefault(key, []).append(ev)

        room_supply = {
            kind: sum(1 for r in self.p.rooms.values() if r.kind == kind)
            for kind in {ev.room_kind for ev in self.p.events}
        }

        skipped: set[str] = set()
        for evs in groups.values():
            kind = evs[0].room_kind
            feasible = self.p.feasible_rooms(evs[0])
            if len(feasible) < len(evs) or room_supply.get(kind, 0) < len(evs):
                skipped.add(f"{evs[0].course.code} ({kind}: only "
                            f"{len(feasible)} feasible room(s) for {len(evs)} groups)")
                continue
            # Groups sharing any teacher cannot physically run simultaneously in two rooms.
            all_teachers: set[str] = set()
            has_shared_teacher = False
            for ev in evs:
                if any(tid in all_teachers for tid in ev.teacher_ids):
                    has_shared_teacher = True
                    break
                all_teachers.update(ev.teacher_ids)
            if has_shared_teacher:
                skipped.add(f"{evs[0].course.code} (groups share teacher, staggered)")
                continue

            # Check if groups have independent or conflicting slot constraints
            has_slot_conflict = False
            for a, b in zip(evs, evs[1:]):
                if a.allowed_slots and b.allowed_slots and not (a.allowed_slots & b.allowed_slots):
                    has_slot_conflict = True
                    break
                if a.allowed_slots and any(s in b.blocked_slots for s in a.allowed_slots):
                    has_slot_conflict = True
                    break
                if b.allowed_slots and any(s in a.blocked_slots for s in b.allowed_slots):
                    has_slot_conflict = True
                    break
            if has_slot_conflict:
                skipped.add(f"{evs[0].course.code} (groups have independent fixed slots, staggered)")
                continue

            for a, b in zip(evs, evs[1:]):
                self.model.Add(self.slot_var[a.eid] == self.slot_var[b.eid])
        self.unsynced_courses = sorted(skipped)

    def _c_sync_paired_labs(self) -> None:
        """Synchronize paired 0.75 credit labs so both courses run in the same 3-period block."""
        seen = set()
        for ev in self.p.events:
            if ev.paired_event_id is not None and ev.eid not in seen:
                pid = ev.paired_event_id
                if pid in self.slot_var:
                    self.model.Add(self.slot_var[ev.eid] == self.slot_var[pid])
                    seen.add(ev.eid)
                    seen.add(pid)

    def _c_freeze(self, freeze: dict[int, tuple[str, int]]) -> None:
        """Pin events to a known placement.

        This is what makes 'regenerate the routine for 3rd year only' work:
        freeze every other batch's events and let the solver move just the one
        batch. It is also the hook for minimal-perturbation rescheduling.
        """
        for eid, (room_id, start) in freeze.items():
            cells = self.x.get(eid)
            if not cells:
                continue
            key = (room_id, start)
            if key not in cells:
                if ("NO_ROOM", start) in cells:
                    key = ("NO_ROOM", start)
                else:
                    raise ValueError(
                        f"Cannot freeze event {eid} at {key}: that placement is no "
                        f"longer legal under the current data."
                    )
            self.model.Add(cells[key] == 1)

    def _c_teacher_diff_course_consecutive(self) -> None:
        """H10 (Constraint 2): For any teacher, forbid two consecutive classes for different courses.

        A teacher must not have two consecutive classes for different courses on the same day.
        Adjacent period pairs considered within continuous school hours:
        - Within Block 1: (P1, P2), (P2, P3)
        - Across Break 1: (P3, P4) (10-minute break between morning blocks)
        - Within Block 2: (P4, P5), (P5, P6)
        - Within Block 3: (P7, P8), (P8, P9)
        Optionally across lunch (P6, P7) if teacher_consecutive_include_lunch option is set.
        """
        teacher_events: dict[str, list[Event]] = defaultdict(list)
        for ev in self.p.events:
            clean_c = ev.course.code.replace(" ", "").upper()
            if clean_c in ("CSE3200", "CSE4000") or clean_c.startswith("CSE4000"):
                continue
            for tid in ev.teacher_ids:
                teacher_events[tid].append(ev)

        self.teacher_course_lits: dict[tuple[str, str], dict[int, list]] = defaultdict(lambda: defaultdict(list))
        self.teacher_course_sec_lits: dict[tuple[str, str, str], dict[int, list]] = defaultdict(lambda: defaultdict(list))
        th_lits_by_t_slot: dict[str, dict[int, list]] = defaultdict(lambda: defaultdict(list))
        lab_lits_by_t_start: dict[str, dict[int, list]] = defaultdict(lambda: defaultdict(list))

        for tid, evs in teacher_events.items():
            for ev in evs:
                clean_c = ev.course.code.replace(" ", "").upper()
                sec = ev.section
                for (rid, s), var in self.x[ev.eid].items():
                    if not ev.is_lab and ev.length == 1:
                        th_lits_by_t_slot[tid][s].append(var)
                    elif ev.is_lab and ev.length == self.grid.lab_periods:
                        lab_lits_by_t_start[tid][s].append(var)
                    for t in range(s, s + ev.length):
                        self.teacher_course_lits[(tid, clean_c)][t].append(var)
                        self.teacher_course_sec_lits[(tid, clean_c, sec)][t].append(var)

        adjacent_pairs = [(0, 1), (1, 2), (2, 3), (3, 4), (4, 5), (6, 7), (7, 8)]
        if self.opt.get("teacher_consecutive_include_lunch", False):
            adjacent_pairs.append((5, 6))

        for tid, evs in teacher_events.items():
            courses = sorted({ev.course.code.replace(" ", "").upper() for ev in evs})
            if len(courses) > 1:
                for d in range(self.grid.n_days):
                    for (p1, p2) in adjacent_pairs:
                        t1 = d * self.grid.n_periods + p1
                        t2 = d * self.grid.n_periods + p2

                        # Positive-literal cliques eliminate +b2/-u2 cancellation so CP-SAT
                        # propagates H10 conflicts and clique structure directly.
                        for c in courses:
                            l1 = self.teacher_course_lits[(tid, c)][t1]
                            if not l1:
                                continue
                            other_l2 = [
                                lit
                                for c2 in courses
                                if c2 != c
                                for lit in self.teacher_course_lits[(tid, c2)][t2]
                            ]
                            if other_l2:
                                self.model.AddAtMostOne(l1 + other_l2)

            # Sound implied block-capacity cut (H2 + H4 + H10):
            # Inside a 3-period academic block, if no single course has >= 3 distinct
            # non-lab (batch, section, group) meetings capable of landing in that block,
            # at most 2 theory periods can sit in the block (and 0 if a 3-period lab runs there).
            th_evs = [ev for ev in evs if not ev.is_lab]
            lab_evs = [ev for ev in evs if ev.is_lab]
            if (
                th_evs
                and all(ev.length == 1 for ev in th_evs)
                and all(ev.length == self.grid.lab_periods for ev in lab_evs)
            ):
                th_by_c: dict[str, list[Event]] = defaultdict(list)
                for ev in th_evs:
                    th_by_c[ev.course.code.replace(" ", "").upper()].append(ev)

                for blk in self.grid.blocks:
                    if len(blk) < 3:
                        continue
                    for d in range(self.grid.n_days):
                        base = d * self.grid.n_periods
                        blk_slots = [base + per for per in blk]
                        max_cohorts = 0
                        for cevs in th_by_c.values():
                            cohs = set()
                            for ev in cevs:
                                if any(s in self.cover[ev.eid] for s in blk_slots):
                                    cohs.add((ev.batch_id, ev.section, ev.group))
                            max_cohorts = max(max_cohorts, len(cohs))
                        if max_cohorts < len(blk):
                            tb = [var for s in blk_slots for var in th_lits_by_t_slot[tid][s]]
                            lb = list(lab_lits_by_t_start[tid][blk_slots[0]])
                            if tb or lb:
                                self.model.Add(sum(tb) + (len(blk) - 1) * sum(lb) <= len(blk) - 1)

    def _c_teacher_max_labs_per_day(self) -> None:
        """H12: Assign at most `max_teacher_labs_per_day` (default 2) lab sessions per day per teacher.

        Applies strictly to teachers to limit daily teaching lab workload, NOT student cohorts.
        """
        max_labs = self.opt.get("max_teacher_labs_per_day", 2)
        if max_labs is None or max_labs < 0:
            return

        teacher_lab_evs: dict[str, list[Event]] = defaultdict(list)
        for ev in self.p.events:
            if not ev.is_lab:
                continue
            clean_c = ev.course.code.replace(" ", "").upper()
            if clean_c in ("CSE3200", "CSE4000") or clean_c.startswith("CSE4000"):
                continue
            for tid in dict.fromkeys(ev.teacher_ids):
                if tid:
                    teacher_lab_evs[tid].append(ev)

        for tid, evs in teacher_lab_evs.items():
            if len(evs) <= max_labs:
                continue
            for d in range(self.grid.n_days):
                lo = d * self.grid.n_periods
                hi = lo + self.grid.n_periods
                day_lits: list = []
                ev_count = 0
                for ev in evs:
                    ev_day_lits = [
                        var for (_, s), var in self.x[ev.eid].items() if lo <= s < hi
                    ]
                    if ev_day_lits:
                        ev_count += 1
                        day_lits.extend(ev_day_lits)
                if ev_count > max_labs:
                    self.model.Add(sum(day_lits) <= max_labs)

    # -- soft constraints ----------------------------------------------------

    def _day_slice(self, busy: list[cp_model.IntVar], d: int) -> list[cp_model.IntVar]:
        lo = d * self.grid.n_periods
        return busy[lo : lo + self.grid.n_periods]

    def _gap_vars(self, busy_day: list[cp_model.IntVar], tag: str) -> list:
        """Count free periods that sit between two busy periods on the same day."""
        gaps = []
        n = len(busy_day)
        for p in range(1, n - 1):
            before = self.model.NewBoolVar(f"bef_{tag}_{p}")
            self.model.AddMaxEquality(before, busy_day[:p])
            after = self.model.NewBoolVar(f"aft_{tag}_{p}")
            self.model.AddMaxEquality(after, busy_day[p + 1 :])
            g = self.model.NewBoolVar(f"gap_{tag}_{p}")
            self.model.Add(g >= before + after - busy_day[p] - 1)
            self.model.Add(g <= before)
            self.model.Add(g <= after)
            self.model.Add(g <= 1 - busy_day[p])
            gaps.append(g)
        return gaps

    def _wants(self, name: str) -> bool:
        """Skip building a penalty's variables entirely when its weight is 0.

        Soft-constraint machinery dominates the variable count, so switching a
        weight off should cost nothing rather than merely contributing nothing.
        """
        return bool(self.w.get(name, 0))

    def _objective(self) -> None:
        terms: list = []
        P = self.grid.n_periods

        # S1. Idle gaps in a student cohort's day.
        cohort_gaps = []
        if self._wants("cohort_gap"):
            for ck, busy in self.cohort_busy.items():
                for d in range(self.grid.n_days):
                    cohort_gaps += self._gap_vars(self._day_slice(busy, d), f"c{ck}_{d}")
        self.penalty_terms["cohort_gap"] = cohort_gaps

        # S2. Idle gaps in a teacher's day.
        teacher_gaps = []
        if self._wants("teacher_gap"):
            for tid, busy in self.teacher_busy.items():
                for d in range(self.grid.n_days):
                    teacher_gaps += self._gap_vars(self._day_slice(busy, d), f"t{tid}_{d}")
        self.penalty_terms["teacher_gap"] = teacher_gaps

        # S3. Classes in the final period of the day.
        last = []
        if self._wants("last_period"):
            for busy in self.cohort_busy.values():
                for d in range(self.grid.n_days):
                    last.append(busy[d * P + (P - 1)])
        self.penalty_terms["last_period"] = last

        # S4. Teacher taught more periods in a day than they should.
        overload = []
        if self._wants("teacher_daily_overload"):
            for tid, busy in self.teacher_busy.items():
                cap = self.p.teachers[tid].max_periods_per_day
                for d in range(self.grid.n_days):
                    ex = self.model.NewIntVar(0, P, f"over_{tid}_{d}")
                    self.model.Add(ex >= sum(self._day_slice(busy, d)) - cap)
                    overload.append(ex)
        self.penalty_terms["teacher_daily_overload"] = overload

        # S5. Too many classes back to back (never counted across a break).
        max_run = self.opt.get("max_consecutive_periods", 3)
        runs = []
        if self._wants("consecutive_overrun"):
            windows = list(self.grid.block_windows(max_run + 1))
            for ck, busy in self.cohort_busy.items():
                for d in range(self.grid.n_days):
                    day = self._day_slice(busy, d)
                    for wi, window in enumerate(windows):
                        ex = self.model.NewIntVar(0, len(window), f"run_{ck}_{d}_{wi}")
                        self.model.Add(ex >= sum(day[p] for p in window) - max_run)
                        runs.append(ex)
        self.penalty_terms["consecutive_overrun"] = runs

        # S6. A section bouncing between theory rooms all week.
        churn = []
        theory_by_cohort: dict[tuple, list[Event]] = {}
        for ev in self.p.events:
            if ev.is_lab:
                continue
            theory_by_cohort.setdefault((ev.batch_id, ev.section), []).append(ev)
        for key, evs in theory_by_cohort.items() if self._wants("room_churn") else []:
            room_ids = sorted({r for ev in evs for (r, _) in self.x[ev.eid]})
            if len(room_ids) <= 1:
                continue
            used = []
            for rid in room_ids:
                u = self.model.NewBoolVar(f"use_{key}_{rid}")
                lits = [
                    var for ev in evs for (r, _), var in self.x[ev.eid].items() if r == rid
                ]
                for lit in lits:
                    self.model.AddImplication(lit, u)
                used.append(u)
            extra = self.model.NewIntVar(0, len(room_ids), f"churn_{key}")
            self.model.Add(extra == sum(used) - 1)
            churn.append(extra)
        self.penalty_terms["room_churn"] = churn

        # S7. Theory slot priorities:
        # 10:40-11:30 > 11:30-12:20 > 12:20-13:10 > 9:40-10:30 > 8:50-9:40 > 8:00-8:50 > 14:30-15:20 > P815:20-16:10 > P916:10-17:00
        theory_slot_terms = []
        if self._wants("theory_slot_priority"):
            period_cost = {3: 0, 4: 1, 5: 2, 2: 4, 1: 6, 0: 8, 6: 14, 7: 18, 8: 24}
            for ev in self.p.events:
                if not ev.is_lab:
                    for (r, s), var in self.x[ev.eid].items():
                        p = self.grid.period_of(s)
                        cost = period_cost.get(p, 0)
                        if cost > 0:
                            theory_slot_terms.append(cost * var)
        self.penalty_terms["theory_slot_priority"] = theory_slot_terms

        # S8. Consecutive classes within Block 1 (8:00 to 10:30) and Block 2 (10:40 to 13:10)
        block_gaps = []
        if self._wants("block_gap"):
            for ck, busy in self.cohort_busy.items():
                for d in range(self.grid.n_days):
                    # Block 1 gap: P1 (0) and P3 (2) busy while P2 (1) is free
                    bg1 = self.model.NewBoolVar(f"bg1_{ck}_{d}")
                    self.model.Add(bg1 >= busy[d * P + 0] + busy[d * P + 2] - busy[d * P + 1] - 1)
                    block_gaps.append(bg1)
                    # Block 2 gap: P4 (3) and P6 (5) busy while P5 (4) is free
                    bg2 = self.model.NewBoolVar(f"bg2_{ck}_{d}")
                    self.model.Add(bg2 >= busy[d * P + 3] + busy[d * P + 5] - busy[d * P + 4] - 1)
                    block_gaps.append(bg2)
        self.penalty_terms["block_gap"] = block_gaps

        # S9. Departmental Software Lab room priority & overflow handling:
        # - CSE Lab 103 priority: CSE 3218 > CSE 42** > CSE 41**
        # - CSE Lab 104 priority (if 103 filled): CSE 42** > CSE 41**
        # - CSE Room 306: dual-use theory/lab, overflow only (high penalty)
        # - Other departmental labs: CSE Lab 201, 202, 305 used normally
        lab_room_terms = []
        if self._wants("lab_room_priority"):
            for ev in self.p.events:
                if ev.is_lab and ev.room_kind in ("cse_lab", "year1_cse_lab", "ai_lab", "network_lab"):
                    clean_c = ev.course.code.replace(" ", "").upper()
                    is_3218 = (clean_c == "CSE3218")
                    is_42xx = clean_c.startswith("CSE42")
                    is_41xx = clean_c.startswith("CSE41")

                    for (rid, _), var in self.x[ev.eid].items():
                        if rid == "CSE-306":
                            # Dual-use overflow backup only
                            lab_room_terms.append(1000 * var)
                        elif is_3218:
                            if rid == "CSE-103":
                                pass
                            elif rid == "CSE-104":
                                lab_room_terms.append(50 * var)
                            else:
                                lab_room_terms.append(200 * var)
                        elif is_42xx:
                            if rid == "CSE-103":
                                pass
                            elif rid == "CSE-104":
                                lab_room_terms.append(15 * var)
                            else:
                                lab_room_terms.append(100 * var)
                        elif is_41xx:
                            if rid == "CSE-103":
                                lab_room_terms.append(25 * var)
                            elif rid == "CSE-104":
                                lab_room_terms.append(30 * var)
                            else:
                                lab_room_terms.append(80 * var)
                        else:
                            # Other software labs (1st, 2nd, 3rd year labs other than 3218)
                            if rid in ("CSE-103", "CSE-104"):
                                lab_room_terms.append(35 * var)
                            else:
                                pass
        self.penalty_terms["lab_room_priority"] = lab_room_terms

        # S10 (Constraint 2): Prioritize consecutive two classes for the exact same course
        same_consec_vars = []
        if self._wants("same_course_consecutive"):
            adjacent_pairs = [(0, 1), (1, 2), (2, 3), (3, 4), (4, 5), (6, 7), (7, 8)]
            if self.opt.get("teacher_consecutive_include_lunch", False):
                adjacent_pairs.append((5, 6))

            teacher_events = defaultdict(list)
            for ev in self.p.events:
                for tid in ev.teacher_ids:
                    teacher_events[tid].append(ev)

            for tid, evs in teacher_events.items():
                courses_map = defaultdict(lambda: defaultdict(list))
                for ev in evs:
                    clean_c = ev.course.code.replace(" ", "").upper()
                    if clean_c in ("CSE3200", "CSE4000") or clean_c.startswith("CSE4000"):
                        continue
                    courses_map[clean_c][ev.section].append(ev)

                for c, sec_dict in courses_map.items():
                    sections = list(sec_dict.keys())
                    if len(sections) < 2:
                        continue

                    for i in range(len(sections)):
                        for j in range(i + 1, len(sections)):
                            sA, sB = sections[i], sections[j]
                            for d in range(self.grid.n_days):
                                for (p1, p2) in adjacent_pairs:
                                    t1 = d * self.grid.n_periods + p1
                                    t2 = d * self.grid.n_periods + p2

                                    lits_A1 = self.teacher_course_sec_lits[(tid, c, sA)][t1]
                                    lits_B2 = self.teacher_course_sec_lits[(tid, c, sB)][t2]
                                    lits_B1 = self.teacher_course_sec_lits[(tid, c, sB)][t1]
                                    lits_A2 = self.teacher_course_sec_lits[(tid, c, sA)][t2]

                                    if lits_A1 and lits_B2:
                                        sc_ab = self.model.NewBoolVar(f"sc_{tid}_{c}_{sA}_{sB}_{d}_{p1}_{p2}_ab")
                                        u_A1 = sum(lits_A1)
                                        u_B2 = sum(lits_B2)
                                        self.model.Add(sc_ab <= u_A1)
                                        self.model.Add(sc_ab <= u_B2)
                                        self.model.Add(sc_ab >= u_A1 + u_B2 - 1)
                                        same_consec_vars.append(sc_ab)

                                    if lits_B1 and lits_A2:
                                        sc_ba = self.model.NewBoolVar(f"sc_{tid}_{c}_{sB}_{sA}_{d}_{p1}_{p2}_ba")
                                        u_B1 = sum(lits_B1)
                                        u_A2 = sum(lits_A2)
                                        self.model.Add(sc_ba <= u_B1)
                                        self.model.Add(sc_ba <= u_A2)
                                        self.model.Add(sc_ba >= u_B1 + u_A2 - 1)
                                        same_consec_vars.append(sc_ba)

        self.bonus_terms["same_course_consecutive"] = same_consec_vars

        # S11: Prefer assigning at most 1 lab session per day per teacher (penalize >= 2 labs/day)
        extra_lab_days = []
        if self._wants("teacher_extra_lab_day"):
            teacher_lab_evs: dict[str, list[Event]] = defaultdict(list)
            for ev in self.p.events:
                if not ev.is_lab:
                    continue
                clean_c = ev.course.code.replace(" ", "").upper()
                if clean_c in ("CSE3200", "CSE4000") or clean_c.startswith("CSE4000"):
                    continue
                for tid in dict.fromkeys(ev.teacher_ids):
                    if tid:
                        teacher_lab_evs[tid].append(ev)

            for tid, evs in teacher_lab_evs.items():
                if len(evs) <= 1:
                    continue
                for d in range(self.grid.n_days):
                    lo = d * self.grid.n_periods
                    hi = lo + self.grid.n_periods
                    day_lits: list = []
                    ev_count = 0
                    for ev in evs:
                        ev_day_lits = [
                            var for (_, s), var in self.x[ev.eid].items() if lo <= s < hi
                        ]
                        if ev_day_lits:
                            ev_count += 1
                            day_lits.extend(ev_day_lits)
                    if ev_count > 1:
                        ex = self.model.NewIntVar(0, ev_count, f"exlab_{tid}_{d}")
                        self.model.Add(ex >= sum(day_lits) - 1)
                        extra_lab_days.append(ex)
        self.penalty_terms["teacher_extra_lab_day"] = extra_lab_days

        for name, vars_ in self.penalty_terms.items():
            weight = self.w.get(name, 0)
            if weight and vars_:
                terms.append(weight * sum(vars_))

        for name, vars_ in self.bonus_terms.items():
            weight = self.w.get(name, 0)
            if weight and vars_:
                terms.append(-weight * sum(vars_))

        if terms:
            self.model.Minimize(sum(terms))

    # ------------------------------------------------------------------ solve

    def solve(self) -> Solution:
        cfg = self.opt["solver"]
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = float(cfg.get("max_seconds", 120))
        solver.parameters.num_search_workers = int(cfg.get("workers", 8))
        solver.parameters.log_search_progress = bool(cfg.get("log", False))

        t0 = time.time()
        status = solver.Solve(self.model)
        elapsed = time.time() - t0

        name = solver.StatusName(status)
        sol = Solution(status=name, wall_seconds=elapsed)
        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            return sol

        for ev in self.p.events:
            for (room_id, start), var in self.x[ev.eid].items():
                if solver.Value(var):
                    sol.assignments.append(Assignment(ev, room_id, start))
                    break

        sol.objective = int(solver.ObjectiveValue())
        sol.best_bound = int(solver.BestObjectiveBound())
        sol.penalties = {
            name_: int(sum(solver.Value(v) for v in vars_))
            for name_, vars_ in self.penalty_terms.items()
            if vars_
        }
        for name_, vars_ in self.bonus_terms.items():
            if vars_:
                sol.penalties[name_] = int(sum(solver.Value(v) for v in vars_))
        sol.unsynced_courses = self.unsynced_courses
        return sol


# --------------------------------------------------------------- public API


def solve_routine(
    problem: Problem,
    freeze: dict[int, tuple[str, int]] | None = None,
    two_phase: bool = True,
    on_phase=None,
) -> Solution:
    """Solve in staged phases: feasibility -> lab-spread/room pre-polish -> full optimisation.

    Phase 1 drops every soft constraint and asks only for feasibility, which is
    fast. Phase 1b (when lab-spread/room weights are active and time remains)
    pre-optimises `teacher_extra_lab_day` and `lab_room_priority` in a quick
    linear pass so Phase 2 starts from a single-lab-per-day layout rather than
    a dense arbitrary hint. Phase 2 restores the full objective and warm-starts
    from the best prior hint.
    """
    if not two_phase:
        sched = RoutineScheduler(problem)
        sched.build(freeze=freeze)
        return sched.solve()

    budget = float(problem.options["solver"].get("max_seconds", 120))
    weights = problem.options["weights"]
    saved = dict(weights)

    try:
        for k in weights:
            weights[k] = 0
        problem.options["solver"]["max_seconds"] = max(10.0, budget * 0.25)
        phase1 = RoutineScheduler(problem)
        phase1.build(freeze=freeze)
        first = phase1.solve()
    finally:
        weights.clear()
        weights.update(saved)
        problem.options["solver"]["max_seconds"] = budget

    if on_phase:
        on_phase(1, first)
    if not first.ok:
        first.unsynced_courses = phase1.unsynced_courses
        return first

    warm_sol = first
    warm_sched = phase1
    used_time = first.wall_seconds

    has_lab_spread = bool(saved.get("teacher_extra_lab_day", 0))
    has_room_prio = bool(saved.get("lab_room_priority", 0))
    remaining_after_p1 = budget - used_time

    if (has_lab_spread or has_room_prio) and remaining_after_p1 > 15.0:
        try:
            for k in weights:
                weights[k] = 0
            if has_lab_spread:
                weights["teacher_extra_lab_day"] = 100
            if has_room_prio:
                weights["lab_room_priority"] = max(1, int(saved.get("lab_room_priority", 2)))
            problem.options["solver"]["max_seconds"] = min(12.0, remaining_after_p1 * 0.25)
            phase1b = RoutineScheduler(problem)
            phase1b.build(freeze=freeze, hint=first.freeze_map())
            polish = phase1b.solve()
            used_time += polish.wall_seconds
            if polish.ok:
                warm_sol = polish
                warm_sched = phase1b
        finally:
            weights.clear()
            weights.update(saved)
            problem.options["solver"]["max_seconds"] = budget

    try:
        problem.options["solver"]["max_seconds"] = max(10.0, budget - used_time)
        sched = RoutineScheduler(problem)
        sched.build(freeze=freeze, hint=warm_sol.freeze_map())
        best = sched.solve()
    finally:
        weights.clear()
        weights.update(saved)
        problem.options["solver"]["max_seconds"] = budget

    if on_phase:
        on_phase(2, best)
    winner = best if best.ok else warm_sol
    winner.unsynced_courses = sched.unsynced_courses if best.ok else warm_sched.unsynced_courses
    return winner


def reschedule_batch(problem: Problem, existing: Solution, batch_id: str) -> Solution:
    """Rebuild one batch's routine, leaving every other batch untouched.

    This is your 'make a new routine for a specific batch' requirement. It is
    also the experimental setup for a minimal-perturbation study: vary what you
    freeze, measure how much the rest of the timetable has to move.
    """
    index = {ev.eid: ev for ev in problem.events}
    freeze = {
        eid: place
        for eid, place in existing.freeze_map().items()
        if index[eid].batch_id != batch_id
    }
    return solve_routine(problem, freeze=freeze)


def _quick_phase1_ok(
    problem: Problem,
    freeze: dict[int, tuple[str, int]] | None = None,
    *,
    skip_h10: bool = False,
    skip_h12: bool = False,
    seconds: float = 3.5,
) -> bool:
    """Fast feasibility-only probe used only after a solve failure to locate conflicts."""
    saved_w = dict(problem.options["weights"])
    saved_sec = problem.options["solver"].get("max_seconds", 120)
    try:
        for k in problem.options["weights"]:
            problem.options["weights"][k] = 0
        problem.options["solver"]["max_seconds"] = seconds
        sched = RoutineScheduler(problem)
        sched._create_variables()
        sched._c_cohort_conflicts()
        sched._c_teacher_conflicts()
        sched._c_room_conflicts()
        sched._c_theory_spread_and_symmetry()
        sched._c_sync_group_labs()
        sched._c_sync_paired_labs()
        if not skip_h10:
            sched._c_teacher_diff_course_consecutive()
        if not skip_h12:
            sched._c_teacher_max_labs_per_day()
        if freeze:
            sched._c_freeze(freeze)
        sol = sched.solve()
        return sol.ok
    except Exception:
        return False
    finally:
        problem.options["weights"].update(saved_w)
        problem.options["solver"]["max_seconds"] = saved_sec


def diagnose_infeasibility(
    problem: Problem,
    freeze: dict[int, tuple[str, int]] | None = None,
) -> list[str]:
    """Run a fast ablation probe after solver failure to identify conflicting constraints/teachers."""
    findings: list[str] = []

    # 1. Check frozen batch pin conflict
    if freeze:
        if _quick_phase1_ok(problem, freeze=None, seconds=8.0):
            findings.append(
                "Frozen running terms conflict with newly modified courses or constraints. "
                "Try switching to 'Full Generation Mode' or unfreezing conflicting terms."
            )
            return findings

    # 2. Isolate individual overloaded/restricted teachers directly (super fast, ~0.2s per teacher)
    t_evs: dict[str, list[Event]] = defaultdict(list)
    for ev in problem.events:
        for tid in ev.teacher_ids:
            t_evs[tid].append(ev)

    h10_culprits: list[str] = []
    h12_culprits: list[str] = []
    combined_culprits: list[str] = []
    max_labs_day = problem.options.get("max_teacher_labs_per_day", 2)

    for tid, evs in sorted(t_evs.items(), key=lambda x: -sum(e.length for e in x[1])):
        load = sum(e.length for e in evs)
        n_labs = sum(1 for e in evs if e.is_lab)
        has_unavail = tid in problem.teachers and bool(problem.teachers[tid].unavailable)
        if load < 20 and n_labs <= (max_labs_day or 2) and not has_unavail:
            continue
        sub_p = Problem(
            grid=problem.grid,
            teachers={k: v for k, v in problem.teachers.items()},
            rooms=problem.rooms,
            batches=problem.batches,
            courses=problem.courses,
            events=evs,
            options={
                **problem.options,
                "sync_group_labs": False,
                "weights": {k: 0 for k in problem.options["weights"]},
                "solver": {"max_seconds": 2.0, "workers": 4, "log": False},
            },
        )
        if not _quick_phase1_ok(sub_p, freeze=None, skip_h10=False, skip_h12=False, seconds=2.0):
            t = problem.teachers.get(tid)
            tlabel = f"{t.name} ({t.short}) [{load} periods, {n_labs} labs]" if t else tid
            ok_no_h12 = _quick_phase1_ok(sub_p, freeze=None, skip_h10=False, skip_h12=True, seconds=2.0)
            ok_no_h10 = _quick_phase1_ok(sub_p, freeze=None, skip_h10=True, skip_h12=False, seconds=2.0)
            if ok_no_h12 and not ok_no_h10:
                h12_culprits.append(tlabel)
            elif ok_no_h10 and not ok_no_h12:
                h10_culprits.append(tlabel)
            else:
                combined_culprits.append(tlabel)

    if h12_culprits:
        findings.append(
            f"Hard Constraint H12 (at most {max_labs_day} lab sessions per day per teacher) cannot be satisfied "
            f"with the current lab assignments/availability for: {', '.join(h12_culprits)}."
        )
    if h10_culprits:
        findings.append(
            "Constraint 2 (H10: No consecutive different-course classes) cannot be satisfied "
            f"with the current weekly workload/availability for: {', '.join(h10_culprits)}. "
            "Reduce theory/lab overlap or adjust unavailable/course slots for these faculty members."
        )
    if combined_culprits:
        findings.append(
            f"Combined H10/H12 & slot rules leave no feasible weekly layout for: {', '.join(combined_culprits)}. "
            "Reduce theory/lab overlap or relax slot restrictions for these faculty members."
        )
    if findings:
        return findings

    # 3. Check Constraint 2 (H10: no different-course consecutive classes) system-wide
    if _quick_phase1_ok(problem, freeze=freeze, skip_h10=True, seconds=8.0):
        findings.append(
            "Hard Constraint H10 (no consecutive different-course classes for teachers) is "
            "over-constrained in combination with room/slot/teacher interactions across active batches."
        )

    # 3b. Check H12 (max daily labs per teacher) system-wide
    if max_labs_day is not None and _quick_phase1_ok(problem, freeze=freeze, skip_h12=True, seconds=8.0):
        findings.append(
            f"Hard Constraint H12 (at most {max_labs_day} lab sessions per day per teacher) is "
            "over-constrained in combination with room/slot/teacher interactions across active batches."
        )

    # 4. Check Constraint 3 (Course fixed / allowed / blocked slots)
    saved_slot_rules = {
        ev.eid: (set(ev.allowed_slots), set(ev.blocked_slots)) for ev in problem.events
    }
    try:
        if any(a or b for a, b in saved_slot_rules.values()):
            for ev in problem.events:
                ev.allowed_slots = set()
                ev.blocked_slots = set()
            if _quick_phase1_ok(problem, freeze=freeze, seconds=8.0):
                constrained = sorted(
                    {
                        f"{ev.course.code} ({ev.batch_id})"
                        for ev in problem.events
                        if saved_slot_rules[ev.eid][0] or saved_slot_rules[ev.eid][1]
                    }
                )
                findings.append(
                    f"Constraint 3 course fixed/blocked slot rules ({', '.join(constrained)}) conflict "
                    "with teacher availability, rooms, or H10 consecutive rules."
                )
    finally:
        for ev in problem.events:
            ev.allowed_slots, ev.blocked_slots = saved_slot_rules[ev.eid]

    # 5. Check Constraint 1 (Teacher manual slot unavailability)
    saved_unavail = {tid: set(t.unavailable) for tid, t in problem.teachers.items()}
    try:
        if any(saved_unavail.values()):
            for t in problem.teachers.values():
                t.unavailable = set()
            if _quick_phase1_ok(problem, freeze=freeze, seconds=8.0):
                restricted = sorted(
                    f"{problem.teachers[tid].name} ({problem.teachers[tid].short})"
                    for tid, slots in saved_unavail.items()
                    if slots
                )
                findings.append(
                    f"Constraint 1 teacher slot unavailability rules ({', '.join(restricted)}) leave "
                    "no conflict-free placement under the current workload."
                )
    finally:
        for tid, t in problem.teachers.items():
            t.unavailable = saved_unavail[tid]

    # 6. Check H9 synced group labs
    if problem.options.get("sync_group_labs", True):
        saved_sync = problem.options["sync_group_labs"]
        try:
            problem.options["sync_group_labs"] = False
            if _quick_phase1_ok(problem, freeze=freeze, seconds=8.0):
                findings.append(
                    "Hard Constraint H9 (simultaneous lab group synchronization) conflicts with "
                    "lab room availability or course/teacher slot restrictions."
                )
        finally:
            problem.options["sync_group_labs"] = saved_sync

    if not findings:
        findings.append(
            "No feasible solution could be found within the time budget with all active constraints combined. "
            "Check heavy teacher loads, restricted course/teacher slots, or increase the solver time budget."
        )
    return findings
