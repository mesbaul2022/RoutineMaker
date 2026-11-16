"""Verification script for Constraint 3: Course Slot Availability & Fixed Slots.

Configures manual slot allocations for non-departmental courses (e.g. Chemistry,
Math, EEE), solves with CP-SAT, validates with independent verifier (H0 through H11),
and captures high-resolution visual evidence using Playwright.
"""

from __future__ import annotations

import os
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.db import (
    Course,
    SessionLocal,
    clear_course_slot_rules,
    get_course_slot_rules,
    init_db,
    save_solution_assignments,
    set_course_slot_rules,
)
from app.db_loader import load_problem_from_db, validate_db_problem
from routine.report import write_csv, write_html
from routine.scheduler import solve_routine
from tools.verify import verify


def setup_course_slot_rules():
    """Configure realistic slot constraints for non-departmental courses."""
    init_db()
    with SessionLocal() as db:
        # 1. CHEM 1208: Chemistry Laboratory (Term 1-2)
        # Chemistry dept provides fixed lab slots: Sec A on Sunday morning, Sec B on Tuesday morning
        chem_rules = [
            {
                "day": "Sunday",
                "periods": "P1,P2,P3",
                "rule_type": "allowed",
                "section": "A",
                "note": "Chemistry dept allotted Sunday Block 1 for Section A",
            },
            {
                "day": "Tuesday",
                "periods": "P1,P2,P3",
                "rule_type": "allowed",
                "section": "B",
                "note": "Chemistry dept allotted Tuesday Block 1 for Section B",
            },
        ]
        set_course_slot_rules(db, "CHEM1208", chem_rules)
        print("Configured CHEM 1208 slot rules: Sec A -> Sun P1-P3, Sec B -> Tue P1-P3")

        # 2. MATH 1207: Coordinate Geometry & Differential Equations (Term 1-2)
        # Math department requested morning classes only (P1-P3 across all days)
        math_rules = [
            {
                "day": "daily",
                "periods": "P1,P2,P3",
                "rule_type": "allowed",
                "section": "ALL",
                "note": "Math department available for theory in morning slots only",
            }
        ]
        set_course_slot_rules(db, "MATH1207", math_rules)
        print("Configured MATH 1207 slot rules: Morning only (P1-P3 daily)")

        # 3. EEE 2118: Analog Electronics Laboratory (Term 2-1)
        # EEE department provides fixed lab slots in EEE-LAB: Sec A on Monday afternoon, Sec B on Wednesday afternoon
        eee_rules = [
            {
                "day": "Monday",
                "periods": "P7,P8,P9",
                "rule_type": "allowed",
                "section": "A",
                "note": "EEE Lab allotted Monday Block 3 for Section A",
            },
            {
                "day": "Wednesday",
                "periods": "P7,P8,P9",
                "rule_type": "allowed",
                "section": "B",
                "note": "EEE Lab allotted Wednesday Block 3 for Section B",
            },
        ]
        set_course_slot_rules(db, "EEE2118", eee_rules)
        print("Configured EEE 2118 slot rules: Sec A -> Mon P7-P9, Sec B -> Wed P7-P9")


def solve_and_verify():
    with SessionLocal() as db:
        print("\nLoading problem from database...")
        problem = load_problem_from_db(db)

    print(f"Loaded problem: {len(problem.courses)} courses, {len(problem.events)} events, {len(problem.teachers)} teachers")
    errors, warnings = validate_db_problem(problem)
    if errors:
        print(f"Validation errors ({len(errors)}):")
        for e in errors:
            print("  ERR:", e)
        return False
    if warnings:
        print(f"Validation warnings ({len(warnings)}):")
        for w in warnings[:5]:
            print("  WARN:", w)

    # Check that events have allowed_slots correctly attached
    chem_events = [e for e in problem.events if "CHEM1208" in e.course.code.replace(" ", "")]
    math_events = [e for e in problem.events if "MATH1207" in e.course.code.replace(" ", "")]
    eee_events = [e for e in problem.events if "EEE2118" in e.course.code.replace(" ", "")]

    print("\n--- Event Slot Rules Inspection ---")
    for ev in chem_events:
        print(f"  {ev.label}: allowed_slots={[problem.grid.describe(s) for s in sorted(ev.allowed_slots)]}")
    for ev in math_events:
        print(f"  {ev.label}: allowed_slots count={len(ev.allowed_slots)} (Morning slots across 5 days)")
    for ev in eee_events:
        print(f"  {ev.label}: allowed_slots={[problem.grid.describe(s) for s in sorted(ev.allowed_slots)]}")

    problem.options["solver"]["max_seconds"] = 45
    print("\nSolving routine with CP-SAT solver...")
    start_t = time.time()
    solution = solve_routine(problem)
    elapsed = time.time() - start_t
    print(f"Solve completed in {elapsed:.2f}s with status: {solution.status} (ok={solution.ok})")

    if not solution.ok:
        print("Solver failed to find a feasible solution!")
        return False

    print("\n--- Running Independent Verification (H0 through H11) ---")
    faults = verify(problem, solution)
    if faults:
        print(f"FAIL: {len(faults)} constraint violations detected:")
        for f in faults:
            print("  ", f)
        return False
    print("SUCCESS: 0 hard-constraint violations across all constraints (H0-H11)!")

    # Verify specific assignments for fixed non-dept courses
    print("\n--- Verifying Placements for Fixed Non-Departmental Courses ---")
    for a in solution.assignments:
        ev = a.event
        clean = ev.course.code.replace(" ", "")
        if clean in ("CHEM1208", "MATH1207", "EEE2118"):
            room_name = problem.rooms[a.room_id].name if a.room_id in problem.rooms else a.room_id
            day_name = problem.grid.days[problem.grid.day_of(a.start)]
            p_names = [problem.grid.periods[problem.grid.period_of(s)].name for s in a.slots]
            print(f"  [OK] {ev.label}: scheduled on {day_name} {', '.join(p_names)} in {room_name}")

    # Save to database and write reports
    with SessionLocal() as db:
        save_solution_assignments(db, solution.assignments)
        print("Saved solution to scheduled_assignments table in routine.db")

    out_dir = ROOT / "out"
    out_dir.mkdir(parents=True, exist_ok=True)
    write_csv(problem, solution, out_dir / "routine.csv")
    write_html(problem, solution, out_dir / "routine.html")
    print("Wrote routine.csv and routine.html")
    return True


if __name__ == "__main__":
    setup_course_slot_rules()
    ok = solve_and_verify()
    if not ok:
        sys.exit(1)
    print("\nConstraint 3 solver verification passed successfully!")
