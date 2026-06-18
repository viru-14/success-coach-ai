import gspread
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent  
gc = gspread.oauth(
    credentials_filename=f"{BASE_DIR}/client_secrets.json", 
    authorized_user_filename=f"{BASE_DIR}/authorized_user.json"
)

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

#get_student_specific_data("STU001")
