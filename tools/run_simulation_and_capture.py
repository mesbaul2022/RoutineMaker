"""Automated simulation execution and high-resolution screenshot capture."""
import os
import sys
import time
import json
import urllib.request
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
SCREENSHOTS_DIR = ROOT / "screenshots"
SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)

BASE_URL = "http://127.0.0.1:8000"

def set_batches(active_batch_ids):
    req = urllib.request.Request(f"{BASE_URL}/api/batches")
    with urllib.request.urlopen(req) as resp:
        batches = json.loads(resp.read().decode())
    
    for b in batches:
        desired = "on" if b["id"] in active_batch_ids else "off"
        if b.get("status") != desired:
            patch_req = urllib.request.Request(
                f"{BASE_URL}/api/batches/{b['id']}/status",
                data=json.dumps({"status": desired}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="PATCH"
            )
            with urllib.request.urlopen(patch_req) as p_resp:
                p_resp.read()

def generate(mode="full"):
    req = urllib.request.Request(
        f"{BASE_URL}/api/generate-routine",
        data=json.dumps({"mode": mode, "seconds": 30.0}).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode())

def run():
    print("=== Starting Automated Simulation and Screenshot Pipeline ===")
    
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        context = browser.new_context(viewport={"width": 1600, "height": 1050})
        page = context.new_page()

        # -------------------------------------------------------------
        # SCENARIO 1: ['1-1', '1-2', '2-1', '3-2', '4-1']
        # -------------------------------------------------------------
        print("\n--- Running Scenario 1: ['1-1', '1-2', '2-1', '3-2', '4-1'] ---")
        set1 = ["1-1", "1-2", "2-1", "3-2", "4-1"]
        set_batches(set1)
        
        # 1. Capture Batches & Courses View
        page.goto(f"{BASE_URL}")
        page.wait_for_selector("#nav-courses")
        page.click("#nav-courses")
        time.sleep(1)
        page.screenshot(path=str(SCREENSHOTS_DIR / "01_scenario1_batches_config.png"), full_page=False)
        print("  Captured 01_scenario1_batches_config.png")

        # 2. Trigger Generation
        res1 = generate("full")
        print(f"  Scenario 1 Generation result: ok={res1.get('ok')}, status={res1.get('status')}")

        # Navigate to Generate Tab to view solved stats
        page.click("#nav-generate")
        time.sleep(1)
        page.screenshot(path=str(SCREENSHOTS_DIR / "02_scenario1_solve_result.png"), full_page=False)
        print("  Captured 02_scenario1_solve_result.png")

        # 3. View Master Routine Tab
        page.click("#nav-master")
        time.sleep(2)
        page.screenshot(path=str(SCREENSHOTS_DIR / "03_scenario1_master_routine.png"), full_page=False)
        print("  Captured 03_scenario1_master_routine.png")

        # 4. Open routine.html directly to capture high-res routine tables
        page.goto(f"{BASE_URL}/out/routine.html")
        time.sleep(1)
        
        # Scroll to 1st year table (1-1 and 1-2)
        y1_table = page.locator("text=1st Year 2nd Term").first
        if y1_table.is_visible():
            y1_table.scroll_into_view_if_needed()
            time.sleep(0.5)
        page.screenshot(path=str(SCREENSHOTS_DIR / "04_scenario1_year1_routine.png"), full_page=False)
        print("  Captured 04_scenario1_year1_routine.png")

        # Scroll to 3rd year 2nd term table
        y3_table = page.locator("text=3rd Year 2nd Term").first
        if y3_table.is_visible():
            y3_table.scroll_into_view_if_needed()
            time.sleep(0.5)
        page.screenshot(path=str(SCREENSHOTS_DIR / "05_scenario1_year3_routine.png"), full_page=False)
        print("  Captured 05_scenario1_year3_routine.png")

        # Scroll to Teacher Routine section
        t_table = page.locator("text=Individual Teacher Schedules").first
        if t_table.is_visible():
            t_table.scroll_into_view_if_needed()
            time.sleep(0.5)
        page.screenshot(path=str(SCREENSHOTS_DIR / "06_scenario1_teacher_routine.png"), full_page=False)
        print("  Captured 06_scenario1_teacher_routine.png")

        # -------------------------------------------------------------
        # SCENARIO 2: ['1-2', '2-1', '3-1', '3-2', '4-2']
        # -------------------------------------------------------------
        print("\n--- Running Scenario 2: ['1-2', '2-1', '3-1', '3-2', '4-2'] ---")
        set2 = ["1-2", "2-1", "3-1", "3-2", "4-2"]
        set_batches(set2)

        page.goto(f"{BASE_URL}")
        page.wait_for_selector("#nav-courses")
        page.click("#nav-courses")
        time.sleep(1)
        page.screenshot(path=str(SCREENSHOTS_DIR / "07_scenario2_batches_config.png"), full_page=False)
        print("  Captured 07_scenario2_batches_config.png")

        res2 = generate("full")
        print(f"  Scenario 2 Generation result: ok={res2.get('ok')}, status={res2.get('status')}")

        page.click("#nav-generate")
        time.sleep(1)
        page.screenshot(path=str(SCREENSHOTS_DIR / "08_scenario2_solve_result.png"), full_page=False)
        print("  Captured 08_scenario2_solve_result.png")

        page.goto(f"{BASE_URL}/out/routine.html")
        time.sleep(1)
        page.screenshot(path=str(SCREENSHOTS_DIR / "09_scenario2_master_routine.png"), full_page=False)
        print("  Captured 09_scenario2_master_routine.png")

        y3_1_table = page.locator("text=3rd Year 1st Term").first
        if y3_1_table.is_visible():
            y3_1_table.scroll_into_view_if_needed()
            time.sleep(0.5)
        page.screenshot(path=str(SCREENSHOTS_DIR / "10_scenario2_year3_routine.png"), full_page=False)
        print("  Captured 10_scenario2_year3_routine.png")

        y4_2_table = page.locator("text=4th Year 2nd Term").first
        if y4_2_table.is_visible():
            y4_2_table.scroll_into_view_if_needed()
            time.sleep(0.5)
        page.screenshot(path=str(SCREENSHOTS_DIR / "11_scenario2_year4_routine.png"), full_page=False)
        print("  Captured 11_scenario2_year4_routine.png")

        t_table2 = page.locator("text=Individual Teacher Schedules").first
        if t_table2.is_visible():
            t_table2.scroll_into_view_if_needed()
            time.sleep(0.5)
        page.screenshot(path=str(SCREENSHOTS_DIR / "12_scenario2_teacher_routine.png"), full_page=False)
        print("  Captured 12_scenario2_teacher_routine.png")

        # -------------------------------------------------------------
        # SYSTEM MANAGEMENT VIEWS
        # -------------------------------------------------------------
        print("\n--- Capturing System Management Views ---")
        page.goto(f"{BASE_URL}")
        page.wait_for_selector("#nav-teachers")
        page.click("#nav-teachers")
        time.sleep(1)
        page.screenshot(path=str(SCREENSHOTS_DIR / "13_teachers_directory.png"), full_page=False)
        print("  Captured 13_teachers_directory.png")

        page.click("#nav-assignments")
        time.sleep(1)
        page.screenshot(path=str(SCREENSHOTS_DIR / "14_assignments_matrix.png"), full_page=False)
        print("  Captured 14_assignments_matrix.png")

        browser.close()
    
    print("\n>>> All 14 screenshots successfully captured and saved to /screenshots! <<<")

if __name__ == "__main__":
    run()
