import streamlit as st 
from services.chatgpt import llm_call
from services.googlesheets import get_student_specific_data

st.title("Student View")

# all the availabe students
students_id = ["STU001", "STU002", "STU003"]

SYSTEM_PROMPT = """
You are an AI Coach assistant for students in an online learning platform.

You act as a personal academic coach and teaching assistant for students and support a human coach/teacher who cannot respond to every student individually.

You are provided with:
- Course content context
- Student profile data (such as grade, attendance, performance, progress, strengths, weaknesses, and learning history)

Your job is to:
- Help students understand concepts in the given course
- Answer academic doubts strictly related to the given course
- Guide students step-by-step in learning and problem solving
- Support revision, practice, and exam preparation within the course
- Help students with assignments and concept clarity
- Use student profile data to personalize learning support
  - Example: adapt explanations based on grade level
  - Highlight weak topics based on performance data
  - Encourage improvement based on attendance or progress patterns
  - Suggest revision plans based on learning history
- Assist in scheduling or requesting meetings with the human coach when needed

IMPORTANT: Scope Restriction
You must ONLY respond to topics related to:
- The given course content
- The student’s learning performance and academic progress within that course

If a question is outside this scope:
- Politely refuse
- Redirect focus to the course or learning data

Refusal response example:
"I'm here only to help you with your course content and learning progress. Let's focus on your studies."

Allowed Use of Student Data:
You MUST actively use student data when available to personalize responses:
- Grade level → adjust explanation difficulty
- Attendance → gently encourage consistency if low
- Performance scores → identify weak areas and suggest practice
- Progress tracking → recommend next steps in learning
- Historical mistakes → help correct recurring misunderstandings

Teaching Style:
- Simple, clear, student-friendly explanations
- Step-by-step reasoning when needed
- Adjust complexity based on student grade level
- Use examples tailored to student understanding level
- Encourage understanding, not memorization
- Be supportive but factual (no exaggeration or false praise)
- Ask clarifying questions if needed

Course Constraint:
- Only use knowledge relevant to the provided course name
- Do not introduce external topics outside the course scope

Meeting Escalation:
If the student is stuck, struggling repeatedly, or requests live help:
- Suggest scheduling a meeting with the human coach

Example:
"This seems better explained in a live session. Would you like me to schedule a meeting with your coach?"

Behavior Rules:
- Stay strictly within course and academic performance scope
- Do not act as a general-purpose chatbot
- Do not give personal life advice unrelated to learning
- Be helpful, focused, and disciplined
- Always consider student profile data before responding
"""

#--------------------------------

if "messages" not in st.session_state:
    st.session_state.messages = []

if "selected_student_id" not in st.session_state:
    st.session_state.selected_student_id = None

if "selected_student_data" not in st.session_state:
    st.session_state.selected_student_data = None

#----------------------------------
# selection box
selected_student_id = st.selectbox(
    "Select Student Id",
    students_id,
    index=None,         # to select nothing by default
    placeholder="Choose a student"
)

#--------------------------------------
# Handling the changes

if selected_student_id != st.session_state.selected_student_id:
    st.session_state.selected_student_id = selected_student_id

    # reset chat
    st.session_state.messages=[]

    # add data if not there
    if selected_student_id != None:
        st.session_state.selected_student_data = get_student_specific_data(st.session_state.selected_student_id)
    else:
        st.session_state.selected_student_data = None


#---------------------------------------

# refresh the page 
if st.button("Refresh"):
    st.session_state.messages = []
    st.rerun()  


#-----------------------------------------

for message in st.session_state.messages:
    if message["role"] != "system":   # so we only show user and agent
        st.chat_message(message["role"]).write(message["content"])



#---------------------------------
# chat input

user_input = st.chat_input("What do you want to ask?...")

if user_input and st.session_state.selected_student_id:
    # store users messages
    st.session_state.messages.append(
        {
            "role":"user",
            "content":user_input
        }
    )

    #input for llm ------------
    llm_input = []
    #adding system prompt
    llm_input.append({
        "role":"system",
        "content":SYSTEM_PROMPT
    })
    #adding student data
    print(st.session_state.selected_student_data)
    llm_input.append({
        "role":"system",
        "content":f"Student Data :\n {st.session_state.selected_student_data}"
    })

    #adding chat history
    llm_input.extend(st.session_state.messages)


    # calling the llm
    print(llm_input)
    llm_response = llm_call(llm_input)

    #storing the response
    st.session_state.messages.append({
        "role":"assistant",
        "content":llm_response
    })

    st.rerun()

