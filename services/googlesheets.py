import os
import json
import gspread
import streamlit as st
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()

try:
    # 1. Try Streamlit Cloud setup first
    secret_credentials = dict(st.secrets["gcp_service_account"])
except Exception:
    # 2. If st.secrets fails or doesn't exist locally, fallback to your .env file
    env_creds = os.getenv("GCP_SERVICE_ACCOUNT")
    secret_credentials = json.loads(env_creds)

gc = gspread.service_account_from_dict(secret_credentials)

SPREADSHEET_ID = "1Q6pzpOvreiVxQ5PCtGQE67d3YeLM17wnuEXTUiMtx_I"
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

def log_student_signal(student_id: str, signal_type: str, severity: str, urgency: str, reason: str) -> bool:
    """
    Appends a new signal record to the 'signal_sheet' tab.
    
    Parameters:
    - student_id: ID of the student (e.g., 'STU001')
    - signal_type: The category of the signal (e.g., 'Attendance', 'Performance')
    - severity: How serious the issue is (e.g., 'High', 'Medium', 'Low')
    - urgency: Timeframe for action (e.g., 'Today', 'This Week')
    - reason: Brief description of why the signal fired
    """
    try:
        # Access the specific signal sheet
        signal_sheet = spreadsheet.worksheet("signal_sheet")
        
        # Generate the current timestamp
        current_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Default 'actioned' status for a brand new signal is False/No
        actioned_status = "No"
        
        # Prepare the row exactly matching your column order:
        # student_id | signal_type | severity | urgency | reason | timestamp | actioned
        new_row = [
            student_id,
            signal_type,
            severity,
            urgency,
            reason,
            current_timestamp,
            actioned_status
        ]
        
        # Append the row to the bottom of the sheet
        signal_sheet.append_row(new_row)
        print(f"Successfully logged {severity} severity signal for {student_id}.")
        return True
        
    except gspread.exceptions.WorksheetNotFound:
        print("Error: The worksheet 'signal_sheet' was not found.")
        return False
    except Exception as e:
        print(f"An error occurred while logging the signal: {e}")
        return False

# print(get_student_specific_data("STU001"))