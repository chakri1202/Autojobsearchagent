import os
import json
import pandas as pd
import plotly.express as px
import streamlit as st
from gdrive_gsheet_client import init_sheet, save_job_to_gsheet
from browser_bot import execute_linkedin_easy_apply
import asyncio

st.set_page_config(page_title="LinkedIn GDrive & GSheet Dashboard", layout="wide")

def load_gsheet_df() -> pd.DataFrame:
    sheet = init_sheet()
    data = sheet.get_all_records()
    if not data:
        return pd.DataFrame()
    return pd.DataFrame(data)

df = load_gsheet_df()

st.title("🎯 LinkedIn Agent — Google Sheets & GDrive Command Matrix")

if df.empty:
    st.info("Google Sheet is currently empty. Run `python main.py` to populate data.")
    st.stop()

# Sidebar Filters
st.sidebar.header("Filter Applications")
selected_statuses = st.sidebar.multiselect("Status", options=df["status"].unique(), default=list(df["status"].unique()))
filtered_df = df[df["status"].isin(selected_statuses)]

# Metrics
c1, c2, c3, c4 = st.columns(4)
c1.metric("Total Tracked", len(filtered_df))
c2.metric("Applied", len(filtered_df[filtered_df["status"] == "APPLIED"]))
c3.metric("Avg Fit Score", f"{filtered_df['fit_score'].mean():.1f}%")
c4.metric("Avg ATS Coverage", f"{filtered_df['ats_coverage_pct'].mean():.1f}%")

st.divider()

st.subheader("Application Spreadsheet View")
st.dataframe(filtered_df, use_container_width=True)

st.subheader("Google Drive Resume Links & Actions")
selected_job_id = st.selectbox("Select Job ID to Review", filtered_df["job_id"].tolist())
if selected_job_id:
    row = filtered_df[filtered_df["job_id"] == str(selected_job_id)].iloc[0]
    st.markdown(f"**Company:** {row['company']} | **Title:** {row['title']}")
    st.markdown(f"**Google Drive Resume:** [Open PDF in Google Drive]({row['gdrive_pdf_link']})")
    st.markdown(f"**LinkedIn Posting:** [Open Job]({row['job_url']})")

    if row["status"] in ["DRY_RUN_READY", "TAILORED", "FAILED"]:
        if st.button("🚀 Trigger Playwright Application Now"):
            with open("master_profile.json", "r", encoding="utf-8") as f:
                mp = json.load(f)
            os.environ["DRY_RUN"] = "False"
            # Assumes local PDF is stored at output_resumes/
            local_pdf = f"output_resumes/Resume_{row['company']}_{row['job_id']}.pdf"
            with st.spinner("Running Playwright submission..."):
                res = asyncio.run(execute_linkedin_easy_apply({
                    "job_url": row["job_url"],
                    "pdf_path": local_pdf,
                    "master_profile": mp
                }))
                st.success(f"Result: {res.get('application_status')}")