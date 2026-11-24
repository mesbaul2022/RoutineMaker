import os
import time
from playwright.sync_api import sync_playwright

def run():
    os.makedirs("screenshots", exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 900})
        page = context.new_page()

        console_errors = []
        page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
        page.on("pageerror", lambda err: console_errors.append(str(err)))

        print("1. Opening http://127.0.0.1:8000 ...")
        page.goto("http://127.0.0.1:8000", wait_until="networkidle")
        time.sleep(1.0)

        # Verify Home tab is active by default
        assert "active" in page.locator("#nav-home").get_attribute("class"), "#nav-home should be active"
        assert "active" in page.locator("#tab-home").get_attribute("class"), "#tab-home should be active"
        assert "active" not in page.locator("#tab-teachers").get_attribute("class"), "#tab-teachers should not be active initially"

        # Verify live metrics populated
        t_val = page.locator("#home-stat-teachers").inner_text().strip()
        c_val = page.locator("#home-stat-courses").inner_text().strip()
        r_val = page.locator("#home-stat-rooms").inner_text().strip()
        s_val = page.locator("#home-stat-slots").inner_text().strip()
        terms = page.locator("#home-active-terms").inner_text().strip()
        print(f"Live Stats -> Teachers: {t_val} | Courses: {c_val} | Rooms: {r_val} | Slots: {s_val} | Active Terms: {terms}")
        assert t_val != "—" and int(t_val) > 0, f"Teachers stat not populated: {t_val}"
        assert c_val != "—" and int(c_val) > 0, f"Courses stat not populated: {c_val}"
        assert r_val != "—" and int(r_val) > 0, f"Rooms stat not populated: {r_val}"

        # Capture above-the-fold and full-page screenshots
        page.screenshot(path="screenshots/home_01_above_fold.png")
        page.screenshot(path="screenshots/home_02_full_page.png", full_page=True)
        print("Saved home_01_above_fold.png and home_02_full_page.png")

        # Test interactive navigation from Home cards/buttons
        page.locator(".home-stat-card").nth(1).click()  # Courses card
        time.sleep(0.4)
        assert "active" in page.locator("#tab-courses").get_attribute("class"), "Clicking Courses card should open Courses tab"

        # Test clicking Brand logo returns to Home
        page.locator(".brand").click()
        time.sleep(0.4)
        assert "active" in page.locator("#tab-home").get_attribute("class"), "Clicking brand logo should return to Home"

        # Test Bulk Hub button from Hero
        page.locator(".home-hero-actions button", has_text="Bulk Import / Export").click()
        time.sleep(0.4)
        assert "open" in page.locator("#modal-bulk-import").get_attribute("class"), "Bulk Hub modal should open"
        page.locator("#modal-bulk-import .modal-close").click()
        time.sleep(0.3)

        # Test Step 1 link -> Time Slots
        page.locator(".home-step-card button", has_text="Configure Time Slots").click()
        time.sleep(0.4)
        assert "active" in page.locator("#tab-timeslots").get_attribute("class"), "Step 1 link should open Time Slots"

        if console_errors:
            print("Console errors found:", console_errors)
            raise RuntimeError(f"Console errors: {console_errors}")

        browser.close()
        print("All homepage UI & navigation checks PASSED with 0 console errors!")

if __name__ == "__main__":
    run()

