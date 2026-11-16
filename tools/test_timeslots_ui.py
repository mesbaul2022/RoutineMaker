import asyncio
from pathlib import Path
from playwright.async_api import async_playwright

async def main():
    out_dir = Path("screenshots")
    out_dir.mkdir(exist_ok=True)
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1366, "height": 950})
        await page.goto("http://127.0.0.1:8000")
        await page.wait_for_timeout(1000)

        # 1. Switch to Time Slots tab
        await page.click('button[data-tab="timeslots"]')
        await page.wait_for_timeout(1000)
        await page.screenshot(path=str(out_dir / "timeslots_default_view.png"))
        print("Captured timeslots_default_view.png")

        # 2. Test live modification: change period duration to 45 min, periods per day to 8
        duration_input = page.locator("#cfg-period-duration")
        await duration_input.fill("45")
        await duration_input.dispatch_event("input")
        await page.wait_for_timeout(400)

        periods_input = page.locator("#cfg-periods-per-day")
        await periods_input.fill("8")
        await periods_input.dispatch_event("input")
        await page.wait_for_timeout(800)

        await page.screenshot(path=str(out_dir / "timeslots_customized_preview.png"))
        print("Captured timeslots_customized_preview.png")

        # 3. Open Teachers tab and open availability modal to verify dynamic period options
        await page.click('button[data-tab="teachers"]')
        await page.wait_for_timeout(800)
        avail_btn = page.locator("button:has-text('🕒 Slots')").first
        await avail_btn.click()
        await page.wait_for_selector("#modal-teacher-availability.open", timeout=5000)
        await page.wait_for_timeout(600)
        await page.screenshot(path=str(out_dir / "timeslots_teacher_availability_modal.png"))
        print("Captured timeslots_teacher_availability_modal.png")

        # 4. Close teacher modal and open Courses tab to check course slot modal
        await page.click("#modal-teacher-availability .modal-close")
        await page.wait_for_timeout(400)
        await page.click('button[data-tab="courses"]')
        await page.wait_for_timeout(800)
        course_avail_btn = page.locator("button:has-text('⚡ Any Slot')").first
        if await course_avail_btn.count() > 0:
            await course_avail_btn.click()
            await page.wait_for_selector("#modal-course-availability.open", timeout=5000)
            await page.wait_for_timeout(600)
            await page.screenshot(path=str(out_dir / "timeslots_course_availability_modal.png"))
            print("Captured timeslots_course_availability_modal.png")
            await page.click("#modal-course-availability .modal-close")
            await page.wait_for_timeout(400)

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
