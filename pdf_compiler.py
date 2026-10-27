
import os
from pathlib import Path
from jinja2 import Template
from playwright.sync_api import sync_playwright
from schemas import JobApplicationState
from gdrive_gsheet_client import upload_pdf_to_gdrive


def html_to_pdf(rendered_html: str, output_path: str):
    """Compiles HTML string to PDF using Playwright."""
    with sync_playwright() as p:
        # Launch headless browser
        browser = p.chromium.launch(headless=True)
        # 🟢 CORRECT: Remove format from new_page()
        page = browser.new_page()
        
        # Load HTML content
        page.set_content(rendered_html, wait_until="networkidle")
        
        # 🟢 CORRECT: Pass format="A4" into page.pdf() instead
        page.pdf(
            path=output_path,
            format="A4",
            print_background=True,
            margin={"top": "10mm", "bottom": "10mm", "left": "10mm", "right": "10mm"}
        )
        browser.close()


def compile_pdf_node(state: JobApplicationState) -> dict:
    """Renders resume using the custom HTML/CSS template via WeasyPrint and saves locally."""
    output_dir = Path("output_resumes")
    output_dir.mkdir(exist_ok=True)
    
    safe_company = "".join(c for c in state["company"] if c.isalnum() or c in ("_", "-"))[:20]
    local_pdf_path = Path("G:/My Drive/LinkedInAgent_resume") / f"Resume_{safe_company}_{state['job_id']}.pdf"

    master = state["master_profile"]
    basics = master.get("basics", {})
    education = master.get("education", [])
    awards = master.get("awards", [])
    tailored = state["tailored_resume"]

    template_path = Path("templates/resume_template.html")
    if not template_path.exists():
        raise FileNotFoundError(f"Template file '{template_path}' not found in project directory.")

    with open(template_path, "r", encoding="utf-8") as f:
        html_content = f.read()

    jinja_template = Template(html_content)
    rendered_html = jinja_template.render(
        basics=basics,
        tailored=tailored,
        awards=awards,
        education=education
    )

    # Compile HTML to PDF using WeasyPrint
    HTML(string=rendered_html).write_pdf(str(local_pdf_path))
    absolute_pdf_path = str(local_pdf_path.resolve())
    print(f"[PDF Compiler] Successfully compiled local PDF: {absolute_pdf_path}")

    # Return local path to state so gsheet tracker saves it cleanly without calling Google Drive API
    return {
        "pdf_path": absolute_pdf_path,
        "gdrive_link": absolute_pdf_path,  # Logs local path into the sheet column cleanly
        "application_status": "TAILORED"
    }