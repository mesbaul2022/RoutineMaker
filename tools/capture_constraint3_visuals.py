"""Capture high-resolution visual evidence for Constraint 3: Course Slot Availability.

Demonstrates:
1. Courses Table with Slot Availability column & badges (CHEM 1208, MATH 1207, EEE 2118).
2. Course Slot Availability Modal for CHEM 1208 showing Section A fixed slot (Sunday P1-P3).
3. Course Slot Availability Modal for CHEM 1208 showing Section B fixed slot (Tuesday P1-P3).
4. Master Routine timetable rendering with '📌 Fixed' badges on fixed courses.
"""

from __future__ import annotations

import os
import shutil
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
SCREENSHOTS_DIR = ROOT / "screenshots"
ARTIFACT_DIR = Path(r"C:\Users\Mesbaul Islam\.gemini\antigravity\brain\7fa64768-97c3-4235-84ce-7c2bb25d7a9f\screenshots")

SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)


def copy_to_artifacts(src_file: Path):
    dest = ARTIFACT_DIR / src_file.name
    shutil.copy2(src_file, dest)
    print(f"  [Copied to Artifacts] {dest}")


def capture():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 960})
        page = context.new_page()

        print("Navigating to http://localhost:8000 ...")
        page.goto("http://localhost:8000", wait_until="networkidle")
        time.sleep(1.5)

        # 1. Courses Table: Term 1-2 (CHEM 1208, MATH 1207, EEE 1208)
        print("Capturing Courses Table for Term 1-2 ...")
        page.evaluate("switchTab('courses')")
        page.wait_for_selector("#course-batch-select", state="visible")
        time.sleep(1.0)
        page.select_option("#course-batch-select", "1-2")
        time.sleep(1.0)

        shot1 = SCREENSHOTS_DIR / "constraint3_courses_table_term12.png"
        page.screenshot(path=str(shot1))
        copy_to_artifacts(shot1)

        # 2. Open Course Slot Availability Modal for CHEM 1208 (Section A)
        print("Opening Course Availability Modal for CHEM 1208 ...")
        page.evaluate("openCourseAvailabilityModal('CHEM1208')")
        page.wait_for_selector("#modal-course-availability.open", state="visible")
        time.sleep(1.0)

        # Ensure Section A is selected
        page.select_option("#course-avail-section-select", "A")
        time.sleep(0.8)
        shot2 = SCREENSHOTS_DIR / "constraint3_modal_chem1208_secA.png"
        page.screenshot(path=str(shot2))
        copy_to_artifacts(shot2)

        # Switch to Section B
        print("Capturing Modal for CHEM 1208 (Section B) ...")
        page.select_option("#course-avail-section-select", "B")
        time.sleep(0.8)
        shot3 = SCREENSHOTS_DIR / "constraint3_modal_chem1208_secB.png"
        page.screenshot(path=str(shot3))
        copy_to_artifacts(shot3)

        # Close modal
        page.click("#modal-course-availability .modal-close")
        time.sleep(0.6)

        # 3. Courses Table: Term 2-1 (EEE 2118, ME 2170, MATH 2107)
        print("Capturing Courses Table for Term 2-1 ...")
        page.select_option("#course-batch-select", "2-1")
        time.sleep(1.0)
        shot4 = SCREENSHOTS_DIR / "constraint3_courses_table_term21.png"
        page.screenshot(path=str(shot4))
        copy_to_artifacts(shot4)

        # 4. Master Routine HTML rendering (showing 📌 Fixed badge)
        print("Capturing Master Timetable with 📌 Fixed slot badges ...")
        page.goto("http://localhost:8000/out/routine.html", wait_until="networkidle")
        time.sleep(1.5)

        # Scroll to Term 1-2 section using JS scrollIntoView
        page.evaluate("""() => {
            const targets = Array.from(document.querySelectorAll('h2, .download-bar-title, table'));
            const el = targets.find(e => e.textContent.includes('Term 1-2') || e.textContent.includes('1st Year 2nd Term'));
            if (el) el.scrollIntoView({ behavior: 'instant', block: 'start' });
        }""")
        time.sleep(1.0)
        shot5 = SCREENSHOTS_DIR / "constraint3_routine_term12_fixed_chem.png"
        page.screenshot(path=str(shot5))
        copy_to_artifacts(shot5)

        # Scroll to Term 2-1 section using JS scrollIntoView
        page.evaluate("""() => {
            const targets = Array.from(document.querySelectorAll('h2, .download-bar-title, table'));
            const el = targets.find(e => e.textContent.includes('Term 2-1') || e.textContent.includes('2nd Year 1st Term'));
            if (el) el.scrollIntoView({ behavior: 'instant', block: 'start' });
        }""")
        time.sleep(1.0)
        shot6 = SCREENSHOTS_DIR / "constraint3_routine_term21_fixed_eee.png"
        page.screenshot(path=str(shot6))
        copy_to_artifacts(shot6)

        browser.close()
        print("\nAll Constraint 3 visual screenshots captured successfully!")


if __name__ == "__main__":
    capture()
