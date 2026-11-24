import sys
from pathlib import Path
from playwright.sync_api import sync_playwright
import shutil

def run():
    screenshots_dir = Path("screenshots")
    screenshots_dir.mkdir(exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1400, "height": 950})
        page = context.new_page()

        print("Navigating to http://127.0.0.1:8000...")
        page.goto("http://127.0.0.1:8000", wait_until="networkidle")

        # Navigate to Courses tab
        print("Clicking Courses tab...")
        page.click("button[data-tab='courses']")
        page.wait_for_timeout(1000)

        # Open slot availability modal for CSE1206 (1.5 cr Sessional Lab)
        print("Opening slot availability modal for CSE1206 (Object Oriented Programming Laboratory)...")
        page.evaluate("openCourseAvailabilityModal('CSE1206')")
        page.wait_for_selector("#modal-course-availability.open", state="visible", timeout=10000)
        page.wait_for_timeout(1000)

        # 1. Capture modal dialog showing the group options in dropdown
        shot1 = screenshots_dir / "group_slot_01_modal_view.png"
        page.locator("#modal-course-availability .modal-dialog").screenshot(path=str(shot1))
        print(f"Captured: {shot1}")

        # 2. Add rule for Group A1: Sunday P1-P3, Allowed, CSE Lab 103
        print("Adding rule: Group A1, Sunday P1-P3, Allowed, CSE Lab 103...")
        page.select_option("#course-rule-select-day", "Sunday")
        page.select_option("#course-rule-select-period", "P1,P2,P3")
        page.select_option("#course-rule-select-type", "allowed")
        page.select_option("#course-rule-select-section", "A1")
        page.select_option("#course-rule-select-room", "CSE-103")
        page.click("#modal-course-availability button[onclick='handleAddCourseAvailabilityRule()']")
        page.wait_for_timeout(500)

        # 3. Add rule for Group A2: Tuesday P1-P3, Allowed, CSE Lab 104
        print("Adding rule: Group A2, Tuesday P1-P3, Allowed, CSE Lab 104...")
        page.select_option("#course-rule-select-day", "Tuesday")
        page.select_option("#course-rule-select-period", "P1,P2,P3")
        page.select_option("#course-rule-select-type", "allowed")
        page.select_option("#course-rule-select-section", "A2")
        page.select_option("#course-rule-select-room", "CSE-104")
        page.click("#modal-course-availability button[onclick='handleAddCourseAvailabilityRule()']")
        page.wait_for_timeout(500)

        # 4. Add rule for Group B1: Monday P1-P3, Allowed, CSE Lab 103
        print("Adding rule: Group B1, Monday P1-P3, Allowed, CSE Lab 103...")
        page.select_option("#course-rule-select-day", "Monday")
        page.select_option("#course-rule-select-period", "P1,P2,P3")
        page.select_option("#course-rule-select-type", "allowed")
        page.select_option("#course-rule-select-section", "B1")
        page.select_option("#course-rule-select-room", "CSE-103")
        page.click("#modal-course-availability button[onclick='handleAddCourseAvailabilityRule()']")
        page.wait_for_timeout(500)

        # Scroll down to show configured rules
        page.evaluate("document.querySelector('#modal-course-availability .modal-body').scrollTop = 450")
        page.wait_for_timeout(500)

        # 5. Capture screenshot showing configured rules with Group A1, Group A2, Group B1 badges and rooms
        shot2 = screenshots_dir / "group_slot_02_rules_with_groups.png"
        page.locator("#modal-course-availability .modal-dialog").screenshot(path=str(shot2))
        print(f"Captured: {shot2}")

        # 6. Click Save Course Slots
        print("Clicking Save Course Slots (OK)...")
        page.click("#modal-course-availability button[onclick='saveCourseAvailability()']")
        page.wait_for_timeout(1500)

        # 7. Re-open modal to verify persistence
        print("Re-opening modal to confirm persistence of group rules...")
        page.evaluate("openCourseAvailabilityModal('CSE1206')")
        page.wait_for_selector("#modal-course-availability.open", state="visible", timeout=10000)
        page.wait_for_timeout(1000)
        page.evaluate("document.querySelector('#modal-course-availability .modal-body').scrollTop = 450")
        page.wait_for_timeout(500)

        shot3 = screenshots_dir / "group_slot_03_persisted_group_rules.png"
        page.locator("#modal-course-availability .modal-dialog").screenshot(path=str(shot3))
        print(f"Captured: {shot3}")

        # 8. Filter to Term 1-2 to capture Courses list summary
        print("Filtering to Term 1-2 in Courses list...")
        page.click("#modal-course-availability .modal-close")
        page.wait_for_timeout(500)
        page.select_option("#course-batch-select", "1-2")
        page.wait_for_timeout(800)
        shot4 = screenshots_dir / "group_slot_04_courses_term1_2.png"
        page.screenshot(path=str(shot4))
        print(f"Captured: {shot4}")

        browser.close()
        print("Visual verification complete!")

        # Copy to artifact screenshots directory
        artifact_dir = Path(r"C:\Users\Mesbaul Islam\.gemini\antigravity\brain\7fa64768-97c3-4235-84ce-7c2bb25d7a9f\screenshots")
        artifact_dir.mkdir(parents=True, exist_ok=True)
        for img in screenshots_dir.glob("group_slot_*.png"):
            shutil.copy2(img, artifact_dir / img.name)
        print("Copied group slot screenshots to artifact directory.")

if __name__ == "__main__":
    run()
