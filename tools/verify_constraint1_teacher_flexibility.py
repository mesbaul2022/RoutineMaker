"""Automated verification and screenshot capture for Constraint 1:
Teacher Flexibility (Daily & Weekly Manual Slot Unavailability).

Tests:
1. Sets availability rules via API:
   - Dr. M. M. A. Hashem: Unavailable Daily 8:00 AM - 10:30 AM (P1, P2, P3)
   - Dr. K. M. Azharul Hasan: Unavailable Monday 8:00 AM - 10:30 AM (P1-P3) and Tuesday 2:30 PM - 5:00 PM (P7-P9)
2. Verifies API returns correctly calculated rules, summary, and flat slot sets.
3. Solves the routine using CP-SAT solver and independent verify.py.
4. Confirms 0 hard faults (H7 verified).
5. Renders live web UI via Playwright and captures high-res screenshots:
   - Teachers directory table with new Slot Availability status
   - Interactive availability modal for Dr. M. M. A. Hashem
   - Interactive availability modal for Dr. K. M. Azharul Hasan
   - Master Teachers routine table showing marked unavailable slots
   - Individual teacher routine cards rendering unavailable slots
"""

import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from playwright.sync_api import sync_playwright

SCREENSHOTS_DIR = ROOT / "screenshots"
SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)

BASE_URL = "http://127.0.0.1:8000"


def http_get(url: str):
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode())


def http_put(url: str, payload: dict):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="PUT")
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode())


def http_post(url: str, payload: dict):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode())


def main():
    print("=" * 70)
    print("Starting Constraint 1: Teacher Manual Slot Flexibility Verification")
    print("=" * 70)

    # 1. Start uvicorn server in a subprocess if not running
    server_process = None
    try:
        urllib.request.urlopen(f"{BASE_URL}/api/teachers", timeout=2)
        print("Server is already running at", BASE_URL)
    except Exception:
        print("Starting local uvicorn server...")
        python_exe = sys.executable
        server_process = subprocess.Popen(
            [python_exe, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000"],
            cwd=str(ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        time.sleep(3)
        print("Server started successfully.")

    try:
        # 2. Configure Teacher Flexibility Constraints via REST API
        print("\n--- Step 1: Configuring Teacher Availability Rules via API ---")

        # Senior Teacher 1: Dr. M. M. A. Hashem -> Daily 8:00 AM - 10:30 AM (P1, P2, P3)
        payload_hashem = {
            "rules": [
                {"day": "daily", "periods": "P1,P2,P3"}
            ]
        }
        res_hashem = http_put(f"{BASE_URL}/api/teachers/mma_hashem/availability", payload_hashem)
        print(f"Dr. M. M. A. Hashem rules saved: {len(res_hashem['rules'])} rule(s)")
        print(f"  Blocked periods: {res_hashem['total_blocked_periods']} slots")
        print(f"  Slots: {res_hashem['blocked_slots']}")
        assert res_hashem["total_blocked_periods"] == 15, "Expected 15 daily blocked slots for Hashem"

        # Senior Teacher 2: Dr. K. M. Azharul Hasan -> Monday P1-P3 (8:00-10:30) & Tuesday P7-P9 (2:30-5:00)
        payload_hasan = {
            "rules": [
                {"day": "Monday", "periods": "P1,P2,P3"},
                {"day": "Tuesday", "periods": "P7,P8,P9"}
            ]
        }
        res_hasan = http_put(f"{BASE_URL}/api/teachers/km_azharul_hasan/availability", payload_hasan)
        print(f"\nDr. K. M. Azharul Hasan rules saved: {len(res_hasan['rules'])} rule(s)")
        print(f"  Blocked periods: {res_hasan['total_blocked_periods']} slots")
        print(f"  Slots: {res_hasan['blocked_slots']}")
        assert res_hasan["total_blocked_periods"] == 6, "Expected 6 weekly blocked slots for Hasan"

        # Check /api/teachers summary
        teachers_list = http_get(f"{BASE_URL}/api/teachers")
        hashem_t = next(t for t in teachers_list if t["id"] == "mma_hashem")
        hasan_t = next(t for t in teachers_list if t["id"] == "km_azharul_hasan")
        print("\nAPI Teacher Directory Summaries:")
        print(f"  Dr. Hashem summary: {hashem_t['unavailable_summary']}")
        print(f"  Dr. Hasan summary: {hasan_t['unavailable_summary']}")

        # 3. Solve Routine with CP-SAT
        print("\n--- Step 2: Triggering Routine Solver ---")
        gen_resp = http_post(f"{BASE_URL}/api/generate-routine", {"mode": "full", "seconds": 30.0})
        print(f"Generation status: ok={gen_resp.get('ok')}, status={gen_resp.get('status')}")
        print(f"Hard faults count: {len(gen_resp.get('faults', []))}")
        print(f"Faults: {gen_resp.get('faults', [])}")
        assert gen_resp.get("ok") is True, f"Routine generation failed: {gen_resp}"
        assert len(gen_resp.get("faults", [])) == 0, f"Found hard constraint faults: {gen_resp.get('faults')}"

        # 4. Independent Python Verification of Constraint Compliance
        print("\n--- Step 3: Verifying Individual Teacher Class Placements ---")
        from app.db import SessionLocal, ScheduledAssignment
        db = SessionLocal()
        scheds = db.query(ScheduledAssignment).all()
        from app.db_loader import load_problem_from_db
        prob = load_problem_from_db(db)

        # Check Hashem's placements
        hashem_events = [ev for ev in prob.events if "mma_hashem" in ev.teacher_ids]
        hashem_eids = {ev.eid for ev in hashem_events}
        hashem_slots = []
        for s in scheds:
            for ev in hashem_events:
                if (ev.batch_id == s.batch_id and ev.course.code == s.course_code and 
                    ev.section == s.section and ev.meeting_index == s.meeting_index):
                    for k in range(ev.length):
                        hashem_slots.append(s.start_slot + k)
        
        hashem_clashes = set(hashem_slots).intersection(prob.teachers["mma_hashem"].unavailable)
        print(f"Dr. Hashem scheduled slots ({len(hashem_slots)} periods): {sorted(list(set(hashem_slots)))}")
        print(f"Dr. Hashem clashes with daily 8:00-10:30 AM: {hashem_clashes}")
        assert len(hashem_clashes) == 0, f"Dr. Hashem scheduled in forbidden slots: {hashem_clashes}"

        # Check Hasan's placements
        hasan_events = [ev for ev in prob.events if "km_azharul_hasan" in ev.teacher_ids]
        hasan_slots = []
        for s in scheds:
            for ev in hasan_events:
                if (ev.batch_id == s.batch_id and ev.course.code == s.course_code and 
                    ev.section == s.section and ev.meeting_index == s.meeting_index):
                    for k in range(ev.length):
                        hasan_slots.append(s.start_slot + k)

        hasan_clashes = set(hasan_slots).intersection(prob.teachers["km_azharul_hasan"].unavailable)
        print(f"Dr. Hasan scheduled slots ({len(hasan_slots)} periods): {sorted(list(set(hasan_slots)))}")
        print(f"Dr. Hasan clashes with Mon morning / Tue afternoon: {hasan_clashes}")
        assert len(hasan_clashes) == 0, f"Dr. Hasan scheduled in forbidden slots: {hasan_clashes}"

        print("\n>>> ALL CONSTRAINT CHECKS PASSED: 0 FAULTS, 0 CLASHES! <<<")

        # 5. Playwright Screenshot Capture
        print("\n--- Step 4: Live UI Rendering and Playwright Screenshot Capture ---")
        with sync_playwright() as p:
            browser = p.chromium.launch(channel="msedge", headless=True)
            context = browser.new_context(viewport={"width": 1600, "height": 1050})
            page = context.new_page()

            # Screenshot 1: Teachers Table with Slot Availability Column
            page.goto(BASE_URL)
            page.wait_for_selector("#nav-teachers")
            page.click("#nav-teachers")
            time.sleep(1)
            # Filter to CSE teachers to see senior faculty easily
            page.select_option("#teacher-dept-select", "CSE")
            time.sleep(0.5)
            img1 = SCREENSHOTS_DIR / "constraint1_teachers_table.png"
            page.screenshot(path=str(img1), full_page=False)
            print(f"  [1/5] Captured {img1.name}")

            # Screenshot 2: Modal for Dr. M. M. A. Hashem (Daily P1-P3)
            page.evaluate("openTeacherAvailabilityModal('mma_hashem')")
            time.sleep(1)
            img2 = SCREENSHOTS_DIR / "constraint1_modal_mma_hashem.png"
            page.screenshot(path=str(img2), full_page=False)
            print(f"  [2/5] Captured {img2.name}")
            page.evaluate("closeTeacherAvailabilityModal()")
            time.sleep(0.5)

            # Screenshot 3: Modal for Dr. K. M. Azharul Hasan (Monday morning & Tuesday afternoon)
            page.evaluate("openTeacherAvailabilityModal('km_azharul_hasan')")
            time.sleep(1)
            img3 = SCREENSHOTS_DIR / "constraint1_modal_km_azharul_hasan.png"
            page.screenshot(path=str(img3), full_page=False)
            print(f"  [3/5] Captured {img3.name}")
            page.evaluate("closeTeacherAvailabilityModal()")
            time.sleep(0.5)

            # Screenshot 4: Master Teachers Routine Table in out/routine.html
            page.goto(f"{BASE_URL}/out/routine.html")
            page.wait_for_selector("#table-master-teachers")
            time.sleep(1)
            # Scroll to table-master-teachers
            page.locator("#table-master-teachers").scroll_into_view_if_needed()
            time.sleep(0.5)
            img4 = SCREENSHOTS_DIR / "constraint1_master_teachers_routine.png"
            page.screenshot(path=str(img4), full_page=False)
            print(f"  [4/5] Captured {img4.name}")

            # Screenshot 5: Individual Teacher Routine Card for Dr. M. M. A. Hashem
            # First switch to Teachers tab in routine.html
            page.click("button[data-target='teachers']")
            time.sleep(1)
            page.select_option("#teacher-dropdown-select", "mma_hashem")
            page.evaluate("onTeacherDropdownChange('mma_hashem')")
            time.sleep(0.5)
            hashem_card = page.locator("#tcard-mma_hashem")
            if hashem_card.is_visible():
                hashem_card.scroll_into_view_if_needed()
                time.sleep(0.5)
            img5 = SCREENSHOTS_DIR / "constraint1_teacher_card_mma_hashem.png"
            page.screenshot(path=str(img5), full_page=False)
            print(f"  [5/6] Captured {img5.name}")

            # Screenshot 6: Individual Teacher Routine Card for Dr. K. M. Azharul Hasan
            page.select_option("#teacher-dropdown-select", "km_azharul_hasan")
            page.evaluate("onTeacherDropdownChange('km_azharul_hasan')")
            time.sleep(0.5)
            hasan_card = page.locator("#tcard-km_azharul_hasan")
            if hasan_card.is_visible():
                hasan_card.scroll_into_view_if_needed()
                time.sleep(0.5)
            img6 = SCREENSHOTS_DIR / "constraint1_teacher_card_km_azharul_hasan.png"
            page.screenshot(path=str(img6), full_page=False)
            print(f"  [6/6] Captured {img6.name}")

            browser.close()

        print("\n=======================================================")
        print("Constraint 1 Verification and Screenshot Capture SUCCESS!")
        print("=======================================================")

    finally:
        if server_process:
            print("Stopping local uvicorn server...")
            server_process.terminate()
            server_process.wait()


if __name__ == "__main__":
    main()
