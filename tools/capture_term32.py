import asyncio
from pathlib import Path
from playwright.async_api import async_playwright

async def main():
    out_dir = Path("screenshots")
    out_dir.mkdir(exist_ok=True)
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1280, "height": 950})
        await page.goto("http://127.0.0.1:8000")
        await page.wait_for_timeout(800)

        # Assignments tab for Term 3-2
        await page.click('button[data-tab="assignments"]')
        await page.wait_for_timeout(600)
        await page.select_option("#assign-batch-select", "3-2")
        await page.wait_for_timeout(800)
        await page.screenshot(path=str(out_dir / "updated_assignments_term32.png"))
        print("Captured updated_assignments_term32.png")

        # Edit course modal for CSE3230 to show seminar_501 selection
        await page.click('button[data-tab="courses"]')
        await page.wait_for_timeout(600)
        await page.select_option("#course-batch-select", "3-2")
        await page.wait_for_timeout(600)
        # Click Edit on CSE3230
        edit_btn = page.locator("tr:has-text('CSE3230') button:text('Edit')")
        if await edit_btn.count() > 0:
            await edit_btn.first.click()
            await page.wait_for_selector("#modal-course.open")
            await page.wait_for_timeout(600)
            await page.screenshot(path=str(out_dir / "updated_edit_cse3230_modal.png"))
            print("Captured updated_edit_cse3230_modal.png")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())

