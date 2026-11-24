import os
import sys
import time
from playwright.sync_api import sync_playwright

SCREENSHOTS_DIR = r"C:\Users\Mesbaul Islam\.gemini\antigravity\brain\7fa64768-97c3-4235-84ce-7c2bb25d7a9f\screenshots"

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        # Use an isolated context to ensure no cache
        context = browser.new_context(viewport={"width": 1400, "height": 950})
        page = context.new_page()

        page.on("console", lambda msg: print(f"Console [{msg.type}]: {msg.text}"))
        page.on("pageerror", lambda err: print(f"Page Error: {err}"))

        print("Navigating to http://127.0.0.1:8000...")
        page.goto("http://127.0.0.1:8000", wait_until="networkidle")
        time.sleep(1)

        print("Opening Courses tab...")
        page.click("button[data-tab='courses']")
        time.sleep(1)

        print("Clicking '+ Add Course' button...")
        page.click("button:text('+ Add Course')")
        time.sleep(1)

        # Check initial state: default description is visible, custom container is hidden
        default_desc = page.locator("#room-mode-default-desc")
        custom_container = page.locator("#room-mode-custom-container")
        btn_default = page.locator("#btn-room-mode-default")
        btn_custom = page.locator("#btn-room-mode-custom")

        assert default_desc.is_visible(), "Initial state: default_desc should be visible!"
        assert not custom_container.is_visible(), "Initial state: custom_container should be hidden!"
        print("Initial state verified: 'All Category Rooms' is active.")

        # Real user click on "🎯 Specific Room(s)" button!
        print("Clicking '#btn-room-mode-custom' button...")
        btn_custom.click()
        time.sleep(0.5)

        assert not default_desc.is_visible(), "After click: default_desc should now be hidden!"
        assert custom_container.is_visible(), "After click: custom_container should now be visible!"
        print("SUCCESS: Clicked 'Specific Room(s)' -> custom container is visible!")

        # Verify rooms checkboxes are present
        pills = page.locator("#course-specific-rooms-grid .room-checkbox-pill")
        count = pills.count()
        print(f"Rendered {count} room checkbox pills in the grid.")
        assert count > 0, "No room pills rendered in grid!"

        # Click the first room pill (e.g. CSE Room 101)
        first_pill = pills.first
        first_pill.click()
        time.sleep(0.3)
        assert "selected" in first_pill.get_attribute("class"), "First pill should be selected after click!"
        print("SUCCESS: Clicked room pill -> pill is selected!")

        # Take screenshot of specific rooms mode active
        shot1 = os.path.join(SCREENSHOTS_DIR, "verified_click_custom_rooms.png")
        page.screenshot(path=shot1)
        print(f"Saved screenshot: {shot1}")

        # Real user click back to "🏢 All Category Rooms" button!
        print("Clicking '#btn-room-mode-default' button...")
        btn_default.click()
        time.sleep(0.5)

        assert default_desc.is_visible(), "After click back: default_desc should be visible!"
        assert not custom_container.is_visible(), "After click back: custom_container should be hidden!"
        print("SUCCESS: Clicked 'All Category Rooms' -> default description is visible!")

        # Take screenshot of default mode active
        shot2 = os.path.join(SCREENSHOTS_DIR, "verified_click_default_rooms.png")
        page.screenshot(path=shot2)
        print(f"Saved screenshot: {shot2}")

        browser.close()
        print("ALL INTERACTIVE BUTTON CLICK TESTS PASSED WITH 100% SUCCESS!")

if __name__ == "__main__":
    main()
