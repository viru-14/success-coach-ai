import os
import json
import gspread
import streamlit as st
from dotenv import load_dotenv
import streamlit as st

load_dotenv()

try:
    # 1. Try Streamlit Cloud setup first
    secret_credentials = dict(st.secrets["gcp_service_account"])
except Exception:
    # 2. If st.secrets fails or doesn't exist locally, fallback to your .env file
    env_creds = os.getenv("GCP_SERVICE_ACCOUNT")
    secret_credentials = json.loads(env_creds)

gc = gspread.service_account_from_dict(secret_credentials)

# 2. Open the spreadsheet using your ID
SPREADSHEET_ID = "1vKn-9LCCcBPjfcFUgEzAWBGpsjzCJtPvrln05rR1Ht0"
spreadsheet = gc.open_by_key(SPREADSHEET_ID)

def get_student_specific_data(student_id:str):
    # select all the tabs   
    all_sheets = spreadsheet.worksheets()

    student_data = []

    #print(all_sheets)

    for sheet in all_sheets:
        if(sheet.title != "signal_sheet"):
            data = sheet.get_all_records()
            for entry in data:
                if student_id in entry.values():
                    student_data.append(entry)  
    
    formatted = []
    for i, record in enumerate(student_data, 1):
        formatted.append(f"Record {i}: {record}")

    return "\n".join(formatted)

#print(get_student_specific_data("STU001"))
