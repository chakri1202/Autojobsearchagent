import os
import asyncio
import random
from playwright.async_api import async_playwright, Page
from agents import answer_screening_question
from schemas import JobApplicationState
from dotenv import load_dotenv

load_dotenv()

USER_DATA_DIR = os.getenv("CHROME_USER_DATA_DIR", "./playwright_user_data")
DRY_RUN = os.getenv("DRY_RUN", "True").lower() == "true"

async def human_delay(min_sec: float = 1.8, max_sec: float = 4.2):
    await asyncio.sleep(random.uniform(min_sec, max_sec))

async def fill_dynamic_modal_fields(page: Page, master_profile: dict):
    """Inspects empty text inputs, selects, and radio buttons inside the LinkedIn Easy Apply modal."""
    modal = page.locator("div.jobs-easy-apply-modal")

    # 1. Handle Text / Numeric Inputs
    text_inputs = modal.locator("input[type='text'], input[type='number']")
    count = await text_inputs.count()
    for i in range(count):
        inp = text_inputs.nth(i)
        if not await inp.is_visible():
            continue
        current_val = await inp.input_value()
        if current_val.strip():
            continue  # Already pre-filled by LinkedIn

        # Find associated label
        input_id = await inp.get_attribute("id")
        label_loc = modal.locator(f"label[for='{input_id}']")
        if await label_loc.count() > 0:
            question = (await label_loc.inner_text()).strip()
            answer = answer_screening_question(question, [], master_profile)
            await inp.fill(str(answer))
            await human_delay(0.8, 1.5)

    # 2. Handle Select Dropdowns
    selects = modal.locator("select")
    s_count = await selects.count()
    for i in range(s_count):
        sel = selects.nth(i)
        if not await sel.is_visible():
            continue
        sel_id = await sel.get_attribute("id")
        label_loc = modal.locator(f"label[for='{sel_id}']")
        question = (await label_loc.inner_text()).strip() if await label_loc.count() > 0 else "Select option"
        options = [o.strip() for o in await sel.locator("option").all_inner_texts() if "Select" not in o]
        if options:
            chosen = answer_screening_question(question, options, master_profile)
            if chosen in options:
                await sel.select_option(label=chosen)
                await human_delay(0.8, 1.5)

async def execute_linkedin_easy_apply(state: JobApplicationState) -> dict:
    """Launches persistent Playwright browser, uploads tailored PDF, steps through modal, and submits."""
    job_url = state["job_url"]
    pdf_path = state["pdf_path"]
    master_profile = state["master_profile"]

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=USER_DATA_DIR,
            headless=False,
            viewport={"width": 1280, "height": 800},
            args=["--disable-blink-features=AutomationControlled"]
        )
        page = context.pages[0] if context.pages else await context.new_page()

        try:
            print(f"[Playwright] Navigating to {job_url}")
            await page.goto(job_url, wait_until="domcontentloaded")
            await human_delay(3.0, 5.0)

            # Check if login is required on first run
            if "login" in page.url or "authwall" in page.url:
                print("[Playwright] Please log in to LinkedIn manually in the opened browser window (60s timeout)...")
                await page.wait_for_url("**/jobs/**", timeout=60000)

            # Locate Easy Apply button
            easy_apply_btn = page.locator("button.jobs-apply-button").first
            if await easy_apply_btn.count() == 0 or "Easy Apply" not in (await easy_apply_btn.inner_text()):
                await context.close()
                return {"application_status": "SKIPPED_EXTERNAL_APPLY", "error_message": "Not an Easy Apply job."}

            await easy_apply_btn.click()
            await human_delay(2.0, 3.5)

            # Step through up to 6 modal pages
            for step in range(6):
                modal = page.locator("div.jobs-easy-apply-modal")

                # Upload tailored resume PDF if file input is present on this step
                file_input = modal.locator("input[type='file']")
                if await file_input.count() > 0:
                    print(f"[Playwright] Uploading tailored resume: {pdf_path}")
                    await file_input.first.set_input_files(pdf_path)
                    await human_delay(2.0, 4.0)

                # Fill any custom screening questions
                await fill_dynamic_modal_fields(page, master_profile)

                # Check for final 'Submit application' button
                submit_btn = modal.locator("button[aria-label='Submit application']")
                if await submit_btn.count() > 0 and await submit_btn.is_visible():
                    if DRY_RUN:
                        print("[Playwright] DRY_RUN=True: Stopping right before clicking Submit application.")
                        await context.close()
                        return {"application_status": "DRY_RUN_READY"}
                    else:
                        await submit_btn.click()
                        await human_delay(3.0, 5.0)
                        print("[Playwright] Successfully submitted Easy Apply application!")
                        await context.close()
                        return {"application_status": "APPLIED"}

                # Check for 'Review' or 'Next' button
                review_btn = modal.locator("button[aria-label='Review your application']")
                next_btn = modal.locator("button[aria-label='Continue to next step']")

                if await review_btn.count() > 0 and await review_btn.is_visible():
                    await review_btn.click()
                elif await next_btn.count() > 0 and await next_btn.is_visible():
                    await next_btn.click()
                else:
                    break

                await human_delay(2.0, 3.5)

            await context.close()
            return {"application_status": "FAILED", "error_message": "Could not reach Submit button within 6 steps."}

        except Exception as e:
            await context.close()
            return {"application_status": "FAILED", "error_message": str(e)}

def playwright_apply_node(state: JobApplicationState) -> dict:
    """Sync wrapper for LangGraph to invoke the async Playwright routine."""
    return asyncio.run(execute_linkedin_easy_apply(state))