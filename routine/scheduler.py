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
        self.w = self.opt["weights"]

        self.model = cp_model.CpModel()
        self.x: dict[int, dict[tuple[str, int], cp_model.IntVar]] = {}
        self.cover: dict[int, dict[int, list]] = {}
        self.cover_room: dict[int, dict[tuple[str, int], list]] = {}
        self.unsynced_courses: list[str] = []
        self.slot_var: dict[int, cp_model.IntVar] = {}
        self.penalty_terms: dict[str, list] = {}

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
            "2-1|A": "B-102",
            "2-1|B": "B-105",
            "2-2|A": "D-402",
            "2-2|B": "B-102",
            "3-2|A": "B-306",
            "3-2|B": "D-401",
            "4-1|A": "CSE-501",
            "4-1|B": "CSE-502",
        }
        home_rooms = {**default_homerooms, **self.opt.get("home_rooms", {})}
        for ev in self.p.events:
            rooms = self.p.feasible_rooms(ev)
            if not ev.is_lab:
                home = home_rooms.get(f"{ev.batch_id}|{ev.section}")
                if home:
                    match = [r for r in rooms if r.id == home]
                    if match:
                        rooms = match
                    elif home in self.p.rooms:
                        rooms = [self.p.rooms[home]]
            starts = self.p.feasible_starts(ev)

            cells: dict[tuple[str, int], cp_model.IntVar] = {}
            for r in rooms:
                for s in starts:
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
            for t in range(self.grid.n_slots):
                lits: list = []
                for ev in evs:
                    lits.extend(self._occupies(ev, t))
                b = self.model.NewBoolVar(f"tbusy_{tid}_{t}")
                self.model.Add(b == sum(lits) if lits else b == 0)
                busy.append(b)
            self.teacher_busy[tid] = busy

    def _c_room_conflicts(self) -> None:
        """H3. A room hosts one class at a time."""
        buckets: dict[tuple[str, int], list] = {}
        for ev in self.p.events:
            for key, lits in self.cover_room[ev.eid].items():
                buckets.setdefault(key, []).extend(lits)
        for lits in buckets.values():
            if len(lits) > 1:
                self.model.AddAtMostOne(lits)

    def _c_theory_spread_and_symmetry(self) -> None:
        """H4. Meetings of one theory course fall on distinct days.

        Also breaks the symmetry between interchangeable sibling meetings by
        forcing them into increasing slot order. Without this the solver wastes
        time exploring k! identical permutations of the same timetable.
        """
        groups: dict[tuple, list[Event]] = {}
        for ev in self.p.events:
            if ev.is_lab:
                continue
            groups.setdefault((ev.course.code, ev.batch_id, ev.section), []).append(ev)

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
            if room_supply.get(kind, 0) < len(evs):
                skipped.add(f"{evs[0].course.code} ({kind}: only "
                            f"{room_supply.get(kind, 0)} room(s) for {len(evs)} groups)")
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
                raise ValueError(
                    f"Cannot freeze event {eid} at {key}: that placement is no "
                    f"longer legal under the current data."
                )
            self.model.Add(cells[key] == 1)

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

        for name, vars_ in self.penalty_terms.items():
            weight = self.w.get(name, 0)
            if weight and vars_:
                terms.append(weight * sum(vars_))

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
        sol.unsynced_courses = self.unsynced_courses
        return sol


# --------------------------------------------------------------- public API


def solve_routine(
    problem: Problem,
    freeze: dict[int, tuple[str, int]] | None = None,
    two_phase: bool = True,
    on_phase=None,
) -> Solution:
    """Solve in two phases: find a legal routine, then improve it.

    Phase 1 drops every soft constraint and asks only for feasibility, which is
    fast. Phase 2 restores the full objective and warm-starts from phase 1, so
    you always end up with a usable routine even if the time budget runs out
    mid-optimisation.
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
        problem.options["weights"].update(saved)
        problem.options["solver"]["max_seconds"] = budget

    if on_phase:
        on_phase(1, first)
    if not first.ok:
        first.unsynced_courses = phase1.unsynced_courses
        return first

    problem.options["solver"]["max_seconds"] = max(10.0, budget - first.wall_seconds)
    sched = RoutineScheduler(problem)
    sched.build(freeze=freeze, hint=first.freeze_map())
    best = sched.solve()
    problem.options["solver"]["max_seconds"] = budget

    if on_phase:
        on_phase(2, best)
    winner = best if best.ok else first
    winner.unsynced_courses = sched.unsynced_courses if best.ok else phase1.unsynced_courses
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
