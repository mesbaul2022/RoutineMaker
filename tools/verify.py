"""Independent checker for a produced routine.

Deliberately written without touching the CP-SAT model: it re-reads the
instance and the exported CSV-equivalent solution and checks every hard
constraint from scratch. If the model and the checker ever disagree, one of
them has a bug -- and you want to find that out before a routine goes on the
notice board, not after.

This is also the artifact a reviewer will ask for if you publish: a claim that
your timetables are feasible is only as good as the verifier behind it.
"""

from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from routine.loader import load_problem  # noqa: E402
from routine.models import Problem  # noqa: E402
from routine.scheduler import Solution, solve_routine  # noqa: E402


def verify(problem: Problem, solution: Solution) -> list[str]:
    grid = problem.grid
    faults: list[str] = []

    placed = {a.event.eid for a in solution.assignments}
    for ev in problem.events:
        if ev.eid not in placed:
            faults.append(f"H0 unplaced meeting: {ev.label}")

    cohort_use: dict[tuple, list] = defaultdict(list)
    teacher_use: dict[tuple, list] = defaultdict(list)
    room_use: dict[tuple, list] = defaultdict(list)

    for a in solution.assignments:
        ev = a.event
        room = problem.rooms[a.room_id]

        theory_kinds = {"theory", "year1_theory"}
        if not ev.is_lab and room.kind in theory_kinds and ev.room_kind in theory_kinds:
            pass
        elif room.kind != ev.room_kind:
            faults.append(f"H5 {ev.label} placed in {room.name} of kind {room.kind}")
        if room.capacity < ev.size:
            faults.append(
                f"H5 {ev.label} ({ev.size} students) placed in {room.name} "
                f"(capacity {room.capacity})"
            )

        if a.start + ev.length > grid.n_slots:
            faults.append(f"H6 {ev.label} runs past the end of the week")
            continue

        days = {grid.day_of(s) for s in a.slots}
        if len(days) > 1:
            faults.append(f"H6 {ev.label} spans more than one day")
        if ev.is_lab:
            block = set(grid.block_of_period(grid.period_of(a.start)))
            if not {grid.period_of(s) for s in a.slots} <= block:
                faults.append(f"H6 {ev.label} crosses a break")

        for s in a.slots:
            for ck in problem.cohorts_of(ev):
                cohort_use[(ck, s)].append(ev.label)
            for tid in ev.teacher_ids:
                teacher_use[(tid, s)].append(ev.label)
                if s in problem.teachers[tid].unavailable:
                    faults.append(
                        f"H7 {problem.teachers[tid].name} booked for {ev.label} at "
                        f"{grid.describe(s)} but is unavailable then"
                    )
            room_use[(a.room_id, s)].append(ev.label)

    for (ck, s), items in cohort_use.items():
        if len(items) > 1:
            faults.append(f"H1 cohort {ck} double-booked at {grid.describe(s)}: {items}")
    for (tid, s), items in teacher_use.items():
        if len(items) > 1:
            faults.append(
                f"H2 {problem.teachers[tid].name} double-booked at "
                f"{grid.describe(s)}: {items}"
            )
    for (rid, s), items in room_use.items():
        if len(items) > 1:
            faults.append(
                f"H3 {problem.rooms[rid].name} double-booked at "
                f"{grid.describe(s)}: {items}"
            )

    # H4 theory meetings of one course-section sit on distinct days
    spread: dict[tuple, list[int]] = defaultdict(list)
    for a in solution.assignments:
        ev = a.event
        if not ev.is_lab:
            spread[(ev.course.code, ev.batch_id, ev.section)].append(grid.day_of(a.start))
    for key, days in spread.items():
        if len(days) != len(set(days)):
            faults.append(f"H4 {key} has two meetings on the same day")

    # H8 one teacher, at most one theory course PER BATCH (see loader.py for
    # why this is scoped per batch rather than department-wide)
    owned: dict[tuple[str, str], set] = defaultdict(set)
    for a in solution.assignments:
        ev = a.event
        if not ev.is_lab:
            for tid in ev.teacher_ids:
                owned[(tid, ev.batch_id)].add(ev.course.code)
    for (tid, batch), codes in owned.items():
        if len(codes) > 1:
            faults.append(
                f"H8 {problem.teachers[tid].name} holds {len(codes)} theory "
                f"courses within batch {batch}: {sorted(codes)}"
            )

    # H9 synced group labs share a start slot -- but ONLY where enough rooms
    # of that room_kind actually exist for every group to run at once. A
    # course with fewer rooms than groups is *supposed* to be staggered (the
    # scheduler skips syncing it for exactly that reason), so it's excluded
    # here rather than reported as a violation.
    if problem.options.get("sync_group_labs", True):
        room_supply: dict[str, int] = defaultdict(int)
        for r in problem.rooms.values():
            room_supply[r.kind] += 1
        group_counts: dict[tuple, int] = defaultdict(int)
        for ev in problem.events:
            if ev.is_lab:
                group_counts[(ev.course.code, ev.batch_id, ev.section)] += 0
                group_counts[(ev.course.code, ev.batch_id, ev.section)] = max(
                    group_counts[(ev.course.code, ev.batch_id, ev.section)],
                    room_supply.get(ev.room_kind, 0),
                )

        starts: dict[tuple, set] = defaultdict(set)
        kinds: dict[tuple, str] = {}
        for a in solution.assignments:
            ev = a.event
            if ev.is_lab:
                key = (ev.course.code, ev.batch_id, ev.section)
                starts[key].add(a.start)
                kinds[key] = ev.room_kind
        for key, s in starts.items():
            expected_syncable = room_supply.get(kinds[key], 0) >= 2
            if expected_syncable and len(s) > 1:
                faults.append(f"H9 {key} groups are not synchronised: starts {sorted(s)}")

    return faults


def main() -> int:
    data = sys.argv[1] if len(sys.argv) > 1 else "data/kuet_cse.json"
    problem = load_problem(data)
    problem.options["solver"]["max_seconds"] = float(
        sys.argv[2] if len(sys.argv) > 2 else 90
    )
    solution = solve_routine(problem)
    if not solution.ok:
        print(f"no solution ({solution.status})")
        return 2
    faults = verify(problem, solution)
    if faults:
        print(f"{len(faults)} hard-constraint violations")
        for f in faults[:40]:
            print(" ", f)
        return 1
    print(
        f"all hard constraints satisfied across {len(solution.assignments)} meetings "
        f"(penalty {solution.objective})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
