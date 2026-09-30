#!/usr/bin/env python3
"""Build a departmental class routine.

    python run.py                                   # solve data/kuet_cse.json
    python run.py --data data/my_dept.json          # your own instance
    python run.py --seconds 300                     # longer optimisation
    python run.py --check                           # validate data, do not solve
    python run.py --reschedule 3-1                  # redo one batch, freeze the rest
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from routine.loader import load_problem, validate
from routine.report import console_summary, write_csv, write_html
from routine.scheduler import reschedule_batch, solve_routine

ROOT = Path(__file__).resolve().parent


def main() -> int:
    ap = argparse.ArgumentParser(description="Departmental class routine builder")
    ap.add_argument("--data", default=str(ROOT / "data" / "kuet_cse.json"))
    ap.add_argument("--out", default=str(ROOT / "out"))
    ap.add_argument("--seconds", type=float, default=None)
    ap.add_argument("--check", action="store_true", help="validate only")
    ap.add_argument(
        "--reschedule",
        metavar="BATCH_ID",
        help="solve once, then rebuild only this batch with everything else frozen",
    )
    args = ap.parse_args()

    problem = load_problem(args.data)
    if args.seconds:
        problem.options["solver"]["max_seconds"] = args.seconds

    print("Teaching day")
    print(problem.grid.pretty())
    print(
        f"\n{len(problem.batches)} batches, {len(problem.events)} meetings to place, "
        f"{len(problem.cohorts())} student cohorts, {len(problem.teachers)} teachers, "
        f"{len(problem.rooms)} rooms\n"
    )

    errors, warnings = validate(problem)
    for w in warnings:
        print(f"  warning: {w}")
    if errors:
        print("\nThe instance cannot be solved as given:")
        for e in errors:
            print(f"  error: {e}")
        return 1
    print("  data checks passed\n")
    if args.check:
        return 0

    def on_phase(n: int, sol) -> None:
        label = "feasibility" if n == 1 else "optimisation"
        print(
            f"  phase {n} ({label}): {sol.status} "
            f"penalty={sol.objective} in {sol.wall_seconds:.1f}s"
        )

    print("Solving")
    solution = solve_routine(problem, on_phase=on_phase)
    if not solution.ok:
        print(f"\nNo routine found (status {solution.status}).")
        print("Try --seconds 600, or relax room supply / teacher availability.")
        return 2

    if args.reschedule:
        if args.reschedule not in problem.batches:
            print(f"\nUnknown batch {args.reschedule!r}.")
            return 1
        print(f"\nRebuilding batch {args.reschedule}, everything else frozen")
        redone = reschedule_batch(problem, solution, args.reschedule)
        if redone.ok:
            moved = sum(
                1
                for eid, place in redone.freeze_map().items()
                if solution.freeze_map().get(eid) != place
            )
            print(f"  {redone.status}: {moved} meetings moved, penalty {redone.objective}")
            solution = redone
        else:
            print(f"  could not rebuild ({redone.status}); keeping original")

    print("\n" + console_summary(problem, solution))

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    csv_path = write_csv(problem, solution, out / "routine.csv")
    html_path = write_html(
        problem,
        solution,
        out / "routine.html",
        title="Department of Computer Science and Engineering",
        subtitle="Weekly class routine · generated with CP-SAT",
    )
    print(f"\nwrote {csv_path}\nwrote {html_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
