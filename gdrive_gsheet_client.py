import os
import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from dotenv import load_dotenv

load_dotenv()

CREDENTIALS_FILE = "credentials.json"
SHEET_NAME = os.getenv("GOOGLE_SHEET_NAME", "Linkedinresume_Tracker")
DRIVE_FOLDER_ID = os.getenv("GOOGLE_DRIVE_FOLDER_ID")

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

def get_gspread_client():
    return gspread.service_account(filename=CREDENTIALS_FILE, scopes=SCOPES)

def get_gdrive_service():
    # Directly use the imported Credentials class from service_account
    creds = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=SCOPES)
    return build("drive", "v3", credentials=creds)

def init_sheet():
    client = get_gspread_client()
    try:
        sheet = client.open(SHEET_NAME).sheet1
    except gspread.SpreadsheetNotFound:
        spreadsheet = client.create(SHEET_NAME)
        spreadsheet.share(client.auth.service_account_email, perm_type='user', role='owner')
        sheet = spreadsheet.sheet1

    headers = [
        "job_id", "timestamp", "company", "title", "archetype",
        "status", "fit_score", "ats_coverage_pct", "required_skills",
        "tailored_skills", "gdrive_pdf_link", "job_url", "notes"
    ]
    current_headers = sheet.row_values(1)
    if not current_headers or current_headers[0] != "job_id":
        sheet.insert_row(headers, 1)
    return sheet

def is_job_processed(job_id: str) -> bool:
    sheet = init_sheet()
    job_ids = sheet.col_values(1)
    return str(job_id) in job_ids

def save_job_to_gsheet(
    job_id: str,
    timestamp: str,
    company: str,
    title: str,
    archetype: str,
    status: str,
    fit_score: int,
    ats_coverage_pct: int,
    required_skills: str,
    tailored_skills: str,
    gdrive_pdf_link: str,
    job_url: str,
    notes: str
):
    sheet = init_sheet()
    cell = sheet.find(str(job_id))

    row_data = [
        str(job_id), timestamp, company, title, archetype,
        status, fit_score, ats_coverage_pct, required_skills,
        tailored_skills, gdrive_pdf_link, job_url, notes
    ]

    if cell:
        sheet.update(f"A{cell.row}:M{cell.row}", [row_data])
    else:
        sheet.append_row(row_data)

def upload_pdf_to_gdrive(local_pdf_path: str, company: str, job_id: str) -> str:
    """Uploads local PDF to Google Drive and returns the web view link."""
    if not os.path.exists(local_pdf_path):
        return ""
    
    drive_service = get_gdrive_service()
    file_name = f"Resume_{company}_{job_id}.pdf".replace(" ", "_")

    file_metadata = {
        'name': file_name,
        'parents': [DRIVE_FOLDER_ID] if DRIVE_FOLDER_ID else []
    }
    media = MediaFileUpload(local_pdf_path, mimetype='application/pdf', resumable=True)

    file = drive_service.files().create(
        body=file_metadata,
        media_body=media,
        fields='id, webViewLink'
    ).execute()

    file_id = file.get('id')
    drive_service.permissions().create(
        fileId=file_id,
        body={'role': 'reader', 'type': 'anyone'}
    ).execute()

    return file.get('webViewLink', '')