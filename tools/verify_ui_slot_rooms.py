import sys
from pathlib import Path
from playwright.sync_api import sync_playwright

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

        # Open slot availability modal for CSE1203
        print("Opening slot availability modal for CSE1203...")
        page.evaluate("openCourseAvailabilityModal('CSE1203')")
        page.wait_for_selector("#modal-course-availability.open", state="visible", timeout=10000)
        page.wait_for_timeout(1000)

        # 1. Capture initial modal state showing assigned rooms bar and room dropdown
        shot1 = screenshots_dir / "slot_room_01_modal_view.png"
        page.screenshot(path=str(shot1))
        print(f"Captured: {shot1}")

        # 2. Select Section A, Sunday P1, Allowed, Room CSE-101, and click + Add Rule
        print("Adding rule: Sec A, Sunday P1, Allowed, CSE Room 101...")
        page.select_option("#course-rule-select-day", "Sunday")
        page.select_option("#course-rule-select-period", "P1")
        page.select_option("#course-rule-select-type", "allowed")
        page.select_option("#course-rule-select-section", "A")
        page.select_option("#course-rule-select-room", "CSE-101")
        page.click("#modal-course-availability button[onclick='handleAddCourseAvailabilityRule()']")
        page.wait_for_timeout(500)

        # 3. Select Section B, Sunday P2, Allowed, Room CSE-102, and click + Add Rule
        print("Adding rule: Sec B, Sunday P2, Allowed, CSE Room 102...")
        page.select_option("#course-rule-select-day", "Sunday")
        page.select_option("#course-rule-select-period", "P2")
        page.select_option("#course-rule-select-type", "allowed")
        page.select_option("#course-rule-select-section", "B")
        page.select_option("#course-rule-select-room", "CSE-102")
        page.click("#modal-course-availability button[onclick='handleAddCourseAvailabilityRule()']")
        page.wait_for_timeout(500)

        # Scroll modal to show rule builder and configured rules
        page.evaluate("document.querySelector('#modal-course-availability .modal-body').scrollTop = 400")
        page.wait_for_timeout(500)

        # 4. Capture screenshot showing configured rules with room badges
        shot2 = screenshots_dir / "slot_room_02_rules_with_rooms.png"
        page.screenshot(path=str(shot2))
        print(f"Captured: {shot2}")

        shot_dialog = screenshots_dir / "slot_room_modal_dialog.png"
        page.locator("#modal-course-availability .modal-dialog").screenshot(path=str(shot_dialog))
        print(f"Captured: {shot_dialog}")

        # 5. Click Save Course Slots
        print("Clicking Save Course Slots (OK)...")
        page.click("#modal-course-availability button[onclick='saveCourseAvailability()']")
        page.wait_for_timeout(1500)

        # 6. Capture courses list showing the updated fixed slot summary with rooms
        shot3 = screenshots_dir / "slot_room_03_courses_list_summary.png"
        page.screenshot(path=str(shot3))
        print(f"Captured: {shot3}")

        # 7. Re-open modal to verify persisted rules with rooms
        print("Re-opening modal to confirm persistence...")
        page.evaluate("openCourseAvailabilityModal('CSE1203')")
        page.wait_for_selector("#modal-course-availability.open", state="visible", timeout=10000)
        page.wait_for_timeout(1000)
        page.evaluate("document.querySelector('#modal-course-availability .modal-body').scrollTop = 400")
        page.wait_for_timeout(500)

        shot4 = screenshots_dir / "slot_room_04_persisted_rules.png"
        page.screenshot(path=str(shot4))
        print(f"Captured: {shot4}")

        # 8. Filter to Term 1-2 to capture CSE1203 slot availability chip
        print("Filtering to Term 1-2 in Courses list...")
        page.click("#modal-course-availability .modal-close")
        page.wait_for_timeout(500)
        page.select_option("#course-batch-select", "1-2")
        page.wait_for_timeout(800)
        shot5 = screenshots_dir / "slot_room_05_courses_term1_2.png"
        page.screenshot(path=str(shot5))
        print(f"Captured: {shot5}")

        browser.close()
        print("Visual verification complete!")

        # Copy to artifact screenshots directory
        import shutil
        artifact_dir = Path(r"C:\Users\Mesbaul Islam\.gemini\antigravity\brain\7fa64768-97c3-4235-84ce-7c2bb25d7a9f\screenshots")
        artifact_dir.mkdir(parents=True, exist_ok=True)
        for img in screenshots_dir.glob("slot_room_*.png"):
            shutil.copy2(img, artifact_dir / img.name)
        print("Copied screenshots to artifact directory.")

if __name__ == "__main__":
    run()
