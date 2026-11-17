import os
import sys
import time
from playwright.sync_api import sync_playwright

def run_verification():
    os.makedirs("screenshots", exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1400, "height": 900})
        page = context.new_page()

        print("1. Navigating to http://127.0.0.1:8000...")
        page.goto("http://127.0.0.1:8000", wait_until="networkidle")
        time.sleep(1)

        # 2. Check Teachers tab & export dropdown
        print("2. Testing Teachers tab & export dropdown...")
        page.locator("button.dropdown-toggle").first.click()
        time.sleep(0.5)
        page.screenshot(path="screenshots/bulk_01_teachers_export_dropdown.png")
        print("Saved bulk_01_teachers_export_dropdown.png")

        # 3. Check Rooms & Labs tab
        print("3. Navigating to Rooms & Labs tab...")
        page.click("#nav-rooms")
        time.sleep(1)
        page.screenshot(path="screenshots/bulk_02_rooms_tab.png")
        print("Saved bulk_02_rooms_tab.png")

        # 4. Check Add Room modal
        print("4. Testing Add Room modal...")
        page.click("#btn-add-room")
        time.sleep(0.5)
        page.screenshot(path="screenshots/bulk_03_add_room_modal.png")
        print("Saved bulk_03_add_room_modal.png")
        page.click("#modal-room .modal-close")
        time.sleep(0.3)

        # 5. Open Bulk Import & Export Hub from header
        print("5. Opening Universal Bulk Import / Export Hub...")
        page.click("button.btn-header-hub")
        time.sleep(0.8)
        page.screenshot(path="screenshots/bulk_04_hub_master_workbook.png")
        print("Saved bulk_04_hub_master_workbook.png")

        # 6. Switch to Teachers tab in Hub
        print("6. Switching to Teachers tab in Bulk Hub...")
        page.click("#btn-bulk-tab-teachers")
        time.sleep(0.5)
        page.screenshot(path="screenshots/bulk_05_hub_teachers_tab.png")
        print("Saved bulk_05_hub_teachers_tab.png")

        # 7. Switch to Courses tab in Hub
        print("7. Switching to Courses tab in Bulk Hub...")
        page.click("#btn-bulk-tab-courses")
        time.sleep(0.5)
        page.screenshot(path="screenshots/bulk_06_hub_courses_tab.png")
        print("Saved bulk_06_hub_courses_tab.png")

        # 8. Switch to Rooms tab in Hub
        print("8. Switching to Rooms tab in Bulk Hub...")
        page.click("#btn-bulk-tab-rooms")
        time.sleep(0.5)
        page.screenshot(path="screenshots/bulk_07_hub_rooms_tab.png")
        print("Saved bulk_07_hub_rooms_tab.png")

        # 9. Test uploading a file via UI into Master Workbook tab
        print("9. Testing Master Workbook upload via UI...")
        page.click("#btn-bulk-tab-all")
        time.sleep(0.5)

        # Let's export live all-in-one workbook to a temp file
        import urllib.request
        temp_wb_path = os.path.abspath("tools/test_master_export.xlsx")
        urllib.request.urlretrieve("http://127.0.0.1:8000/api/export/all?format=xlsx", temp_wb_path)

        page.set_input_files("#bulk-file-all", temp_wb_path)
        time.sleep(0.5)
        page.click("#btn-upload-all")
        time.sleep(2)
        page.screenshot(path="screenshots/bulk_08_upload_success_result.png")
        print("Saved bulk_08_upload_success_result.png")

        browser.close()
        print("Verification completed successfully!")

if __name__ == "__main__":
    run_verification()
