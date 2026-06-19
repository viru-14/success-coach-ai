import os
import json
import gspread
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

try:
    # 1. Try Streamlit Cloud setup first
    secret_credentials = dict(st.secrets["gcp_service_account"])
except Exception:
    # 2. If st.secrets fails or doesn't exist locally, fallback to your .env file
    env_creds = os.getenv("GCP_SERVICE_ACCOUNT")
    secret_credentials = json.loads(env_creds)

gc = gspread.service_account_from_dict(secret_credentials)

SPREADSHEET_ID = "1vKn-9LCCcBPjfcFUgEzAWBGpsjzCJtPvrln05rR1Ht0"
spreadsheet = gc.open_by_key(SPREADSHEET_ID)


def get_student_specific_data(student_id: str) -> str:
    """
    Fetch all records that belong to a specific student across every
    data sheet (excluding signal_sheet).

    Returns a formatted string the LLM can read as context.
    """
    all_sheets = spreadsheet.worksheets()
    student_data = []

    for sheet in all_sheets:
        if sheet.title != "signal_sheet":
            data = sheet.get_all_records()
            for entry in data:
                if student_id in entry.values():
                    student_data.append(entry)

    if not student_data:
        return f"No data found for student_id={student_id}"

    formatted = [f"Record {i}: {record}" for i, record in enumerate(student_data, 1)]
    return "\n".join(formatted)