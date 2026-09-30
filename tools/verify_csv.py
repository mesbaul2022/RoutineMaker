"""Verify an already-exported routine.csv against every hard constraint.

Unlike tools/verify.py (which re-solves from scratch), this checks the exact
artifact that was handed to the user -- reconstructing assignments from the
CSV and matching them back to the problem's events by (course, batch,
section, group, meeting slot).
"""

import csv
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from routine.loader import load_problem
from routine.models import Event
from routine.scheduler import Assignment, Solution


def reconstruct(problem, csv_path):
    grid = problem.grid
    by_key: dict[tuple, list[Event]] = defaultdict(list)
    for ev in problem.events:
        key = (ev.course.code, ev.batch_id, ev.section, ev.group)
        by_key[key].append(ev)
    for key in by_key:
        by_key[key].sort(key=lambda e: e.meeting_index)

    used = defaultdict(int)
    assignments = []
    with open(csv_path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            key = (row["course_code"], row["batch"], row["section"], row["group"] or None)
            idx = used[key]
            used[key] += 1
            ev = by_key[key][idx]
            d = grid.day_index(row["day"])
            p = grid.period_index(row["start_period"])
            start = grid.slot(d, p)
            room_id = next(
                r.id for r in problem.rooms.values() if r.name == row["room"]
            )
            assignments.append(Assignment(ev, room_id, start))
    return Solution(status="FROM_CSV", assignments=assignments)


def main():
    problem = load_problem("data/kuet_cse.json")
    sol = reconstruct(problem, "out/routine.csv")
    print(f"reconstructed {len(sol.assignments)} / {len(problem.events)} meetings")

    from tools.verify import verify

    faults = verify(problem, sol)
    if faults:
        print(f"{len(faults)} violations")
        for f in faults[:30]:
            print(" ", f)
        return 1
    print("all hard constraints satisfied on the delivered routine.csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
