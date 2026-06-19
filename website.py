import streamlit as st
from services.tools import run_agent
from services.memory import save_memory

st.title("Student View")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

STUDENTS_ID = ["STU001", "STU002", "STU003"]

SYSTEM_PROMPT = """
You are an AI Coach assistant strictly limited to this online learning platform.

## HARD RULES — never break these
1. You ONLY answer questions that are directly about:
   - The course content available in THIS platform (verified via get_setup_data)
   - The student's own academic data in THIS platform (verified via get_student_specific_data)
2. You NEVER answer anything else — no exceptions.
   This includes but is not limited to:
   - Stories, jokes, poems, creative writing of any kind
   - General knowledge, trivia, or fun facts
   - Academic topics from subjects NOT found in this platform's course data
   - Advice, opinions, or personal guidance unrelated to the course
   - Anything a general-purpose chatbot would answer
3. Before answering any academic question, call get_setup_data to confirm
   the topic actually exists in this platform's course. If it does not appear
   in the retrieved data, refuse — even if the topic sounds academic.
4. If you are unsure whether something is in scope, refuse.

## When a request is out of scope
Respond with exactly this and nothing more:
"I can only help you with the course content and your learning progress on
this platform. Let's get back to your studies!"
Do NOT apologise at length, do NOT engage with the off-topic request at all,
do NOT offer alternatives outside the platform.

## Tools — call these before answering, not after
1. get_student_specific_data(student_id) — call when the student asks about
   their own progress, performance, attendance, or when you need to personalise
   a response to their level.
2. get_setup_data(query) — call to verify a topic exists in this platform's
   course and to retrieve the relevant content. If the topic is not found in
   the results, treat the question as out of scope and refuse.
3. get_memories(student_id, query) — call at the start of every new conversation
   and whenever the student references something previously learned, discussed,
   attempted, struggled with, or planned. Use the student's current message or
   topic as the query to retrieve relevant context from prior sessions.

You may call all tools in the same turn. Always prefer fetching over assuming.

## When a question IS in scope
- Give simple, clear, student-friendly explanations.
- Use step-by-step reasoning when needed.
- Adjust complexity based on the student's grade level (fetch their data first).
- Encourage understanding, not memorisation.
- Be supportive but factual — no false praise.
- If the student is repeatedly stuck, suggest a live session:
  "This might be easier to cover with your coach directly. Should I help
  schedule a session?"
"""


# ---------------------------------------------------------------------------
# Session state initialisation
# ---------------------------------------------------------------------------

if "messages" not in st.session_state:
    st.session_state.messages = []          # full conversation history

if "selected_student_id" not in st.session_state:
    st.session_state.selected_student_id = None


# ---------------------------------------------------------------------------
# Student selector
# ---------------------------------------------------------------------------

selected_student_id = st.selectbox(
    "Select Student ID",
    STUDENTS_ID,
    index=None,
    placeholder="Choose a student",
)

# Reset conversation when a different student is chosen
if selected_student_id != st.session_state.selected_student_id:
    st.session_state.selected_student_id = selected_student_id
    st.session_state.messages = []


# ---------------------------------------------------------------------------
# Refresh and End Chat buttons
# ---------------------------------------------------------------------------

col1, col2 = st.columns(2)

with col1:
    if st.button("🔄 Refresh", use_container_width=True):
        st.session_state.messages = []
        st.rerun()

with col2:
    if st.button("✅ End Chat & Save Memory", use_container_width=True):
        if st.session_state.messages and st.session_state.selected_student_id:
            save_memory(st.session_state.selected_student_id, st.session_state.messages)
            st.success("Memory saved!")
        st.session_state.messages = []
        st.rerun()


# ---------------------------------------------------------------------------
# Render existing conversation (skip system and tool messages)
# ---------------------------------------------------------------------------

for message in st.session_state.messages:
    role = message.get("role") if isinstance(message, dict) else message.role
    content = message.get("content") if isinstance(message, dict) else message.content

    if role in ("user", "assistant") and content:
        st.chat_message(role).write(content)


# ---------------------------------------------------------------------------
# Chat input + agentic loop
# ---------------------------------------------------------------------------

user_input = st.chat_input("What do you want to ask?...")

if user_input and st.session_state.selected_student_id:

    # Show the user's message immediately
    st.chat_message("user").write(user_input)

    # Build the messages list the agent will work with:
    #   [system prompt]  +  [conversation history so far]  +  [new user message]
    agent_messages = [
        {
            "role": "system",
            "content": (
                f"{SYSTEM_PROMPT}\n\n"
                f"The currently selected student ID is: "
                f"{st.session_state.selected_student_id}"
            ),
        },
        *st.session_state.messages,
        {"role": "user", "content": user_input},
    ]

    # Run the agentic loop — the LLM decides which tools to call and when
    with st.spinner("Thinking..."):
        final_response, updated_messages = run_agent(agent_messages)

    # Persist only the new turns from this round (strip the system prompt and
    # already-stored history at the front of updated_messages)
    new_turns = updated_messages[1 + len(st.session_state.messages):]
    st.session_state.messages.extend(new_turns)

    # Render the assistant's reply
    st.chat_message("assistant").write(final_response)