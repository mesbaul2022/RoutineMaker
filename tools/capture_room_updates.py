import asyncio
from pathlib import Path
from playwright.async_api import async_playwright

async def main():
    out_dir = Path("screenshots")
    out_dir.mkdir(exist_ok=True)
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1280, "height": 900})
        await page.goto("http://127.0.0.1:8000")
        await page.wait_for_timeout(1000)

        # 1. Switch to Courses tab
        await page.click('button[data-tab="courses"]')
        await page.wait_for_timeout(1000)
        await page.screenshot(path=str(out_dir / "updated_courses_table.png"))
        print("Captured updated_courses_table.png")

        # 2. Click '+ Add Course' to open modal
        await page.click("#btn-add-course")
        await page.wait_for_selector("#modal-course.open")
        await page.wait_for_timeout(600)
        await page.screenshot(path=str(out_dir / "updated_add_course_modal.png"))
        print("Captured updated_add_course_modal.png")

        # 3. Switch Course Type to Sessional to verify hint and default
        await page.select_option("#course-kind", "sessional")
        await page.wait_for_timeout(600)
        await page.screenshot(path=str(out_dir / "updated_add_course_sessional.png"))
        print("Captured updated_add_course_sessional.png")

        # 4. Close modal and check Assignments tab
        await page.click("#modal-course .modal-close")
        await page.wait_for_timeout(400)
        await page.click('button[data-tab="assignments"]')
        await page.wait_for_timeout(1000)
        await page.screenshot(path=str(out_dir / "updated_assignments_tab.png"))
        print("Captured updated_assignments_tab.png")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
