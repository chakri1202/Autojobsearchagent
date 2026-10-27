import time
import random
from jobspy import scrape_jobs
import pandas as pd
from gdrive_gsheet_client import init_sheet

def get_all_processed_job_ids() -> set:
    """Fetches all processed job IDs from Google Sheet in a single API call to prevent 429 quota limits."""
    try:
        sheet = init_sheet()
        # col_values(1) gets all entries in Column A (job_id) in 1 API request
        job_ids = sheet.col_values(1)
        return set(str(jid).strip() for jid in job_ids if jid)
    except Exception as e:
        print(f"[Scraper Warning] Could not fetch existing sheet rows: {e}")
        return set()

def fetch_latest_linkedin_jobs(
    roles: list[str] = ["Data Analyst", "Data Scientist", "AI/ML Engineer"],
    location: str = "Hyderabad, Telangana, India",
    hours_old: int = 4,
    results_per_role: int = 10
) -> list[dict]:
    discovered_jobs = []
    
    # Fetch processed IDs ONCE before loop (saves hundreds of individual API calls)
    print("[Scraper] Fetching already processed job IDs from Google Sheet...")
    processed_ids = get_all_processed_job_ids()
    print(f"[Scraper] Found {len(processed_ids)} previously processed jobs in tracker.")

    for role in roles:
        print(f"[Scraper] Searching LinkedIn for '{role}' in '{location}'...")
        try:
            df = scrape_jobs(
                site_name=["linkedin"],
                search_term=role,
                location=location,
                results_wanted=results_per_role,
                hours_old=hours_old,
                linkedin_fetch_description=True
            )
        except Exception as e:
            print(f"[Scraper] Rate limited or error for {role}: {e}")
            time.sleep(15)  # Wait if blocked before trying the next role
            continue

        if df.empty:
            print(f"[Scraper] No jobs found for {role} within the last {hours_old} hours.")
            continue

        for _, row in df.iterrows():
            job_id = str(row.get("id", ""))
            jd_text = str(row.get("description", ""))
            
            if not job_id or not jd_text or jd_text == "nan":
                continue
            
            # Check against local memory set (Zero API quota cost)
            if job_id in processed_ids:
                continue

            discovered_jobs.append({
                "job_id": job_id,
                "title": str(row.get("title", role)),
                "company": str(row.get("company", "Unknown")),
                "job_url": str(row.get("job_url", "")),
                "jd_text": jd_text
            })
        
        # Add a human-like random delay between role queries to prevent LinkedIn 429 blocks
        sleep_time = random.uniform(6.0, 12.0)
        print(f"[Scraper] Waiting {sleep_time:.1f}s before next search...")
        time.sleep(sleep_time)

    unique_jobs = list({j["job_id"]: j for j in discovered_jobs}.values())
    print(f"[Scraper] Total new unique jobs queued for processing: {len(unique_jobs)}")
    return unique_jobs