import os
import json
from datetime import datetime
from langgraph.graph import StateGraph, END
from dotenv import load_dotenv

from schemas import JobApplicationState
from agents import evaluate_jd_node, tailor_resume_node
from pdf_compiler import compile_pdf_node
from browser_bot import playwright_apply_node
from scraper import fetch_latest_linkedin_jobs
from gdrive_gsheet_client import init_sheet, save_job_to_gsheet

load_dotenv()
FIT_SCORE_THRESHOLD = int(os.getenv("FIT_SCORE_THRESHOLD", 75))

def route_after_evaluation(state: JobApplicationState) -> str:
    """Conditional edge: Skip jobs that fall below the fit score threshold."""
    if state["evaluation"].fit_score >= FIT_SCORE_THRESHOLD:
        return "tailor_resume"
    return "log_and_exit"

def route_after_tailoring(state: JobApplicationState) -> str:
    """Conditional edge: Self-correction loop if ATS keyword coverage is below 70% (max 2 tries)."""
    coverage = state["tailored_resume"].ats_keyword_coverage_pct
    attempts = state.get("rewrite_attempts", 1)
    if coverage < 70 and attempts < 2:
        print(f"[Router] Keyword coverage ({coverage}%) below 70%. Triggering rewrite loop...")
        return "tailor_resume"
    return "compile_pdf"

def log_and_exit_node(state: JobApplicationState) -> dict:
    """Final node: Persists full validation metrics and Google Drive PDF link to Google Sheets."""
    eval_obj = state.get("evaluation")
    tailored_obj = state.get("tailored_resume")
    status = state.get("application_status") or "SKIPPED_LOW_FIT"

    save_job_to_gsheet(
        job_id=state["job_id"],
        timestamp=datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        company=state["company"],
        title=state["title"],
        archetype=eval_obj.role_archetype if eval_obj else "Unclassified",
        status=status,
        fit_score=eval_obj.fit_score if eval_obj else 0,
        ats_coverage_pct=tailored_obj.ats_keyword_coverage_pct if tailored_obj else 0,
        required_skills=", ".join(eval_obj.required_skills) if eval_obj else "",
        tailored_skills=", ".join(tailored_obj.highlighted_skills) if tailored_obj else "",
        gdrive_pdf_link=state.get("gdrive_link", ""),
        job_url=state["job_url"],
        notes=state.get("error_message") or (eval_obj.reasoning if eval_obj else "")
    )
    print(f"[Google Sheet] Synced job {state['job_id']} | Status: {status}\n" + "-"*60)
    return {"application_status": status}


# --- Threshold & Routing Adjustments ---
FIT_SCORE_THRESHOLD = 45  # Lowered from 75 to 45
TARGET_ATS_COVERAGE = 96  # Target forced keyword coverage %

def route_after_evaluation(state: JobApplicationState) -> str:
    """Conditional edge: Process jobs if fit score is >= 45%."""
    if state["evaluation"].fit_score >= FIT_SCORE_THRESHOLD:
        print(f"[Router] Fit score {state['evaluation'].fit_score}% >= {FIT_SCORE_THRESHOLD}%. Proceeding to tailor resume.")
        return "tailor_resume"
    print(f"[Router] Fit score {state['evaluation'].fit_score}% < {FIT_SCORE_THRESHOLD}%. Skipping job.")
    return "log_and_exit"

def route_after_tailoring(state: JobApplicationState) -> str:
    """Conditional edge: Self-correction loop until ATS keyword coverage hits 96% (max 4 tries)."""
    tailored = state["tailored_resume"]
    coverage = tailored.ats_keyword_coverage_pct if tailored else 0
    attempts = state.get("rewrite_attempts", 1)

    if coverage < TARGET_ATS_COVERAGE and attempts < 4:
        print(f"[Router] ATS coverage ({coverage}%) is below target ({TARGET_ATS_COVERAGE}%). Triggering rewrite attempt #{attempts + 1}...")
        return "tailor_resume"
    
    print(f"[Router] Target reached! ATS coverage: {coverage}% after {attempts} attempts. Compiling PDF.")
    return "compile_pdf"

def build_application_graph():
    workflow = StateGraph(JobApplicationState)

    # Register nodes
    workflow.add_node("evaluate_jd", evaluate_jd_node)
    workflow.add_node("tailor_resume", tailor_resume_node)
    workflow.add_node("compile_pdf", compile_pdf_node)
    workflow.add_node("playwright_apply", playwright_apply_node)
    workflow.add_node("log_and_exit", log_and_exit_node)

    # Define edges
    workflow.set_entry_point("evaluate_jd")
    workflow.add_conditional_edges("evaluate_jd", route_after_evaluation)
    workflow.add_conditional_edges("tailor_resume", route_after_tailoring)
    workflow.add_edge("compile_pdf", "playwright_apply")
    workflow.add_edge("playwright_apply", "log_and_exit")
    workflow.add_edge("log_and_exit", END)

    return workflow.compile()

if __name__ == "__main__":
    init_sheet()
    
    with open("master_profile.json", "r", encoding="utf-8") as f:
        master_profile = json.load(f)

    app_graph = build_application_graph()

    # 1. Discover recent jobs across your target tracks in Hyderabad
    jobs = fetch_latest_linkedin_jobs(
        roles=["Data Analyst", 
            "Data Scientist", 
            "AI/ML Engineer", 
            "Machine Learning Engineer", 
            "AI Engineer", 
            "Analytics Engineer"],
        location="Hyderabad, Telangana, India",
        hours_old=4,
        results_per_role=3
    )

    print(f"[Main] Processing {len(jobs)} discovered jobs through LangGraph pipeline...")

    # 2. Run each discovered job through the stateful pipeline
    for job in jobs:
        initial_state: JobApplicationState = {
            "job_id": job["job_id"],
            "title": job["title"],
            "company": job["company"],
            "job_url": job["job_url"],
            "jd_text": job["jd_text"],
            "master_profile": master_profile,
            "evaluation": None,
            "tailored_resume": None,
            "pdf_path": None,
            "gdrive_link": None,
            "rewrite_attempts": 0,
            "application_status": "DISCOVERED",
            "error_message": None
        }
        app_graph.invoke(initial_state)