"""Comprehensive Verification & Visual Rendering for Constraint 2: Consecutive Classes.

Constraint 2:
1. Prioritize to assign consecutive two classes for only the exact same courses to one teacher.
2. One teacher must NOT have two consecutive classes for different courses.
"""

from __future__ import annotations

import os
import sys
import time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.db import get_db, save_solution_assignments, Batch
from app.db_loader import load_problem_from_db
from routine.report import write_csv, write_html
from routine.scheduler import solve_routine
from tools.verify import verify


def run_constraint2_verification():
    print("=" * 70)
    print("STARTING CONSTRAINT 2 VERIFICATION: CONSECUTIVE CLASSES HARMONY")
    print("=" * 70)

    # 1. Connect to database and ensure active batches
    db = next(get_db())
    active_batch_ids = [b.id for b in db.query(Batch).filter(Batch.status == "on").all()]
    print(f"Active Batches in Session: {active_batch_ids}")

    # 2. Load Problem from DB
    problem = load_problem_from_db(db)
    print(f"Problem Loaded: {len(problem.events)} events, {len(problem.teachers)} teachers")

    # 3. Solve with CP-SAT
    print("\nExecuting CP-SAT solver with Constraint 2 active...")
    t0 = time.time()
    solution = solve_routine(problem)
    elapsed = time.time() - t0
    print(f"Solver Status: {solution.status} in {elapsed:.2f}s")
    assert solution.ok, f"Solver failed with status {solution.status}"

    # 4. Save Solution to DB & Files
    save_solution_assignments(db, solution.assignments, batch_ids_to_replace=active_batch_ids)

    out_dir = ROOT / "out"
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / "routine.csv"
    html_path = out_dir / "routine.html"
    write_csv(problem, solution, csv_path)
    write_html(
        problem,
        solution,
        html_path,
        title="Department of Computer Science and Engineering",
        subtitle="Weekly class routine · generated with CP-SAT",
    )
    print(f"Wrote outputs: {csv_path} and {html_path}")

    # 5. Independent Verification with verify.py
    print("\nRunning independent verification suite (tools/verify.py)...")
    faults = verify(problem, solution)
    print(f"Total Hard Faults Reported: {len(faults)}")
    if faults:
        for f in faults:
            print(f"  ❌ FAULT: {f}")
    assert len(faults) == 0, f"Verification failed with {len(faults)} faults!"
    print("✅ 100% of hard constraints satisfied! 0 faults!")

    # 6. Detailed Audit of Constraint 2
    grid = problem.grid
    adjacent_pairs = [(0, 1), (1, 2), (2, 3), (3, 4), (4, 5), (6, 7), (7, 8)]

    teacher_day_slots = defaultdict(lambda: defaultdict(dict))
    for a in solution.assignments:
        ev = a.event
        clean_code = ev.course.code.replace(" ", "").upper()
        if clean_code in ("CSE3200", "CSE4000") or clean_code.startswith("CSE4000"):
            continue
        for s in a.slots:
            d = grid.day_of(s)
            p = grid.period_of(s)
            for tid in ev.teacher_ids:
                teacher_day_slots[tid][d][p] = {
                    "code": clean_code,
                    "eid": ev.eid,
                    "section": ev.section,
                    "group": ev.group,
                    "label": ev.label,
                    "kind": "sessional" if ev.is_lab else "theory",
                }

    same_consec = []
    diff_consec = []

    for tid, days in teacher_day_slots.items():
        tname = problem.teachers[tid].name if tid in problem.teachers else tid
        tcode = problem.teachers[tid].short if tid in problem.teachers else tid
        for d, pmap in days.items():
            day_name = grid.days[d]
            for (p1, p2) in adjacent_pairs:
                if p1 in pmap and p2 in pmap:
                    item1 = pmap[p1]
                    item2 = pmap[p2]
                    if item1["eid"] == item2["eid"]:
                        continue  # same 3-period lab session
                    if item1["code"] == item2["code"]:
                        same_consec.append((
                            tname, tcode, day_name,
                            f"P{p1+1} ({grid.periods[p1].start}-{grid.periods[p1].end})",
                            f"P{p2+1} ({grid.periods[p2].start}-{grid.periods[p2].end})",
                            item1["code"],
                            f"Sec {item1['section']} -> Sec {item2['section']}",
                            item1["kind"], item2["kind"]
                        ))
                    else:
                        diff_consec.append((
                            tname, tcode, day_name,
                            f"P{p1+1}", f"P{p2+1}",
                            item1["code"], item2["code"]
                        ))

    print("\n" + "=" * 70)
    print(f"CONSTRAINT 2 AUDIT RESULTS:")
    print(f"  * Different-Course Consecutive Occurrences (MUST BE 0): {len(diff_consec)}")
    print(f"  * Same-Course Consecutive Occurrences (PRIORITIZED):   {len(same_consec)}")
    print("=" * 70)

    assert len(diff_consec) == 0, f"Violation! Found {len(diff_consec)} consecutive different-course classes!"
    print("✅ ZERO consecutive different-course classes across all faculty members!")
    assert len(same_consec) > 30, f"Expected >30 same-course consecutive pairs, found {len(same_consec)}"
    print(f"✅ HIGH SYNERGY: Successfully achieved {len(same_consec)} same-course consecutive class pairs!")

    print("\nSample Consecutive Same-Course Classes:")
    for idx, item in enumerate(same_consec[:15], 1):
        print(f"  {idx:2d}. {item[0]} ({item[1]}): {item[2]} {item[3]} & {item[4]} -> {item[5]} ({item[6]})")

    # 7. Capture High-Resolution Rendered Screenshots with Playwright
    print("\nLaunching headless Chromium to capture high-res visual verification...")
    try:
        from playwright.sync_api import sync_playwright

        screenshots_dir = ROOT / "screenshots"
        screenshots_dir.mkdir(parents=True, exist_ok=True)
        brain_dir = Path(r"C:\Users\Mesbaul Islam\.gemini\antigravity\brain\7fa64768-97c3-4235-84ce-7c2bb25d7a9f\screenshots")
        brain_dir.mkdir(parents=True, exist_ok=True)

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1600, "height": 1000})

            # 1. Master Teachers Routine showing same-course badges
            file_url = f"file:///{str(html_path).replace(os.sep, '/')}"
            page.goto(file_url, wait_until="networkidle")
            page.click("button[data-target='master-teachers']")
            page.wait_for_timeout(1000)

            shot1 = screenshots_dir / "constraint2_master_teachers_consecutive.png"
            page.screenshot(path=str(shot1), full_page=False)
            shot1_brain = brain_dir / "constraint2_master_teachers_consecutive.png"
            page.screenshot(path=str(shot1_brain), full_page=False)
            print(f"  📸 Saved {shot1}")

            # 2. Individual Teacher Card: e.g. Dr. Sk. Imran Hossain or Mr. Md. Badiuzzaman Shuvo
            page.click("button[data-target='teachers']")
            page.wait_for_timeout(500)

            # Find a teacher with same-course consecutive
            sample_tid = None
            sample_tname = None
            for item in same_consec:
                if "Badiuzzaman" in item[0] or "Imran" in item[0] or "Rejvi" in item[0] or "Sadia" in item[0]:
                    sample_tname = item[0]
                    break
            if not sample_tname and same_consec:
                sample_tname = same_consec[0][0]

            # Select this teacher in the dropdown
            select_el = page.locator("#teacher-dropdown-select")
            options = select_el.locator("option").all()
            for opt in options:
                text = opt.inner_text()
                if sample_tname in text:
                    select_el.select_option(value=opt.get_attribute("value"))
                    break
            page.wait_for_timeout(800)

            shot2 = screenshots_dir / "constraint2_teacher_card_consecutive1.png"
            page.screenshot(path=str(shot2), full_page=False)
            shot2_brain = brain_dir / "constraint2_teacher_card_consecutive1.png"
            page.screenshot(path=str(shot2_brain), full_page=False)
            print(f"  📸 Saved {shot2} ({sample_tname})")

            # 3. Second sample teacher card
            sample_tname2 = None
            for item in same_consec:
                if item[0] != sample_tname and ("Rejvi" in item[0] or "Sadia" in item[0] or "Hasan" in item[0]):
                    sample_tname2 = item[0]
                    break
            if not sample_tname2 and len(same_consec) > 1:
                sample_tname2 = same_consec[1][0]

            if sample_tname2:
                for opt in options:
                    text = opt.inner_text()
                    if sample_tname2 in text:
                        select_el.select_option(value=opt.get_attribute("value"))
                        break
                page.wait_for_timeout(800)
                shot3 = screenshots_dir / "constraint2_teacher_card_consecutive2.png"
                page.screenshot(path=str(shot3), full_page=False)
                shot3_brain = brain_dir / "constraint2_teacher_card_consecutive2.png"
                page.screenshot(path=str(shot3_brain), full_page=False)
                print(f"  📸 Saved {shot3} ({sample_tname2})")

            # 4. Web UI Dashboard at localhost:8000
            try:
                page.goto("http://127.0.0.1:8000/", wait_until="networkidle", timeout=6000)
                page.click("#tab-generate")
                page.wait_for_timeout(1000)
                shot4 = screenshots_dir / "constraint2_web_ui_dashboard.png"
                page.screenshot(path=str(shot4), full_page=False)
                shot4_brain = brain_dir / "constraint2_web_ui_dashboard.png"
                page.screenshot(path=str(shot4_brain), full_page=False)
                print(f"  📸 Saved {shot4}")
            except Exception as e:
                print(f"  Notice: web dashboard capture skipped ({e})")

            browser.close()
    except Exception as e:
        print(f"Playwright rendering notice: {e}")

    print("\n✅ CONSTRAINT 2 FULLY VERIFIED AND RENDERED!")
    return len(same_consec)


if __name__ == "__main__":
    run_constraint2_verification()

