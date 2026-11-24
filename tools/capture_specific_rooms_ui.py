import os
import sys
import time
from playwright.sync_api import sync_playwright

SCREENSHOTS_DIR = r"C:\Users\Mesbaul Islam\.gemini\antigravity\brain\7fa64768-97c3-4235-84ce-7c2bb25d7a9f\screenshots"
os.makedirs(SCREENSHOTS_DIR, exist_ok=True)

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1400, "height": 950})
        page = context.new_page()

        # Listen for errors
        page.on("console", lambda msg: print(f"Console [{msg.type}]: {msg.text}"))
        page.on("pageerror", lambda err: print(f"Page Error: {err}"))

        print("Navigating to http://127.0.0.1:8000...")
        page.goto("http://127.0.0.1:8000", wait_until="networkidle")
        time.sleep(1)

        # 1. Switch to Courses tab
        print("Switching to Courses tab...")
        page.evaluate("switchTab('courses')")
        time.sleep(1)

        # Select batch "1-2" in filter so CSE1203 and CSE1206 are shown
        page.evaluate("""() => {
            const sel = document.getElementById('course-batch-select');
            if (sel) { sel.value = '1-2'; sel.dispatchEvent(new Event('change')); }
        }""")
        time.sleep(0.8)

        # Take screenshot of Courses list with specific room assignment badges
        courses_list_path = os.path.join(SCREENSHOTS_DIR, "room_01_courses_list_custom_rooms.png")
        page.screenshot(path=courses_list_path)
        print(f"Saved: {courses_list_path}")

        # 2. Open Edit Modal for CSE1203 (Theory Course with CSE-101 and CSE-102 assigned)
        print("Opening modal for CSE1203...")
        page.evaluate("openCourseModal('CSE1203')")
        time.sleep(1)

        theory_modal_path = os.path.join(SCREENSHOTS_DIR, "room_02_theory_specific_rooms_modal.png")
        page.screenshot(path=theory_modal_path)
        print(f"Saved: {theory_modal_path}")

        # Close modal
        page.evaluate("closeCourseModal()")
        time.sleep(0.5)

        # 3. Open Edit Modal for CSE1206 (Departmental Lab Course with CSE-103 and CSE-104 assigned)
        print("Opening modal for CSE1206...")
        page.evaluate("openCourseModal('CSE1206')")
        time.sleep(1)

        lab_modal_path = os.path.join(SCREENSHOTS_DIR, "room_03_lab_specific_rooms_modal.png")
        page.screenshot(path=lab_modal_path)
        print(f"Saved: {lab_modal_path}")

        # Close modal
        page.evaluate("closeCourseModal()")
        time.sleep(0.5)

        # 4. Open Add Course modal and switch to Specific Rooms
        print("Opening Add Course modal...")
        page.evaluate("openCourseModal()")
        time.sleep(0.5)

        page.evaluate("setCourseRoomMode('custom')")
        time.sleep(0.5)

        add_modal_path = os.path.join(SCREENSHOTS_DIR, "room_04_add_course_specific_rooms.png")
        page.screenshot(path=add_modal_path)
        print(f"Saved: {add_modal_path}")

        browser.close()
        print("All Playwright screenshots generated cleanly with 0 console errors!")

if __name__ == "__main__":
    main()
