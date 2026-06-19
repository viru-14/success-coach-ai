import streamlit as st
from services.tools import run_agent
from services.memory import save_memory, get_all_factual_memories

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
5. You can answer casual question like :
    - Hii, how are you, etc
4. If you are unsure whether something is in scope, refuse.

## When a request is out of scope
Respond with exactly this and nothing more:
"I can only help you with the course content and your learning progress on
this platform. Let's get back to your studies!"
Do NOT apologise at length, do NOT engage with the off-topic request at all,
do NOT offer alternatives outside the platform.

## Tools — call these before answering, not after
1. get_student_specific_data(student_id)
   Call when the student asks about their own progress, performance, or
   attendance, or when you need to personalise a response to their level.

2. get_setup_data(query)
   Call to verify a topic exists in this platform's course and to retrieve
   relevant content. If the topic is not found in the results, refuse.

3. get_memories(student_id, query)
   Retrieves FACTUAL memory from past sessions: known stress triggers,
   what explanations have worked, recurring misunderstandings, and personal
   learning patterns. Call this at the start of each conversation, or when
   the student references something from a previous session.
   Use it to adapt your tone and approach — not to summarise past sessions
   aloud (session summaries are a separate system for coaches).

You may call multiple tools in the same turn. Always prefer fetching over assuming.


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
    st.session_state.messages = []

if "selected_student_id" not in st.session_state:
    st.session_state.selected_student_id = None

# if "session_count" not in st.session_state:
#     st.session_state.session_count = 0

if "student_memories" not in st.session_state:
    st.session_state.student_memories = ""


# ---------------------------------------------------------------------------
# Student selector
# ---------------------------------------------------------------------------

selected_student_id = st.selectbox(
    "Select Student ID",
    STUDENTS_ID,
    index=None,
    placeholder="Choose a student",
)

# Reset everything when a different student is chosen
if selected_student_id != st.session_state.selected_student_id:
    st.session_state.selected_student_id = selected_student_id
    st.session_state.messages = []
    if selected_student_id:
        # st.session_state.session_count = get_session_count(selected_student_id)
        st.session_state.student_memories = get_all_factual_memories(selected_student_id)
    else:
        # st.session_state.session_count = 0
        st.session_state.student_memories = ""


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
            with st.spinner("Saving memory..."):
                save_memory(
                    st.session_state.selected_student_id,
                    st.session_state.messages
                )
            st.success("Session saved!")
        st.session_state.messages = []
        st.rerun()


# ---------------------------------------------------------------------------
# Render existing conversation
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

    st.chat_message("user").write(user_input)

    #current_session = st.session_state.session_count + 1  # sessions completed + this one

    memory_block = (
        f"\n\n## What you already know about this student (from past sessions)\n"
        f"{st.session_state.student_memories}"
        if st.session_state.student_memories else ""
    )

    agent_messages = [
        {
            "role": "system",
            "content": (
                f"{SYSTEM_PROMPT}"
                f"{memory_block}\n\n"
                f"Student ID: {st.session_state.selected_student_id}\n"
                # f"Current session number: {current_session}"
            ),
        },
        *st.session_state.messages,
        {"role": "user", "content": user_input},
    ]

    with st.spinner("Thinking..."):
        final_response, updated_messages = run_agent(agent_messages)

    new_turns = updated_messages[1 + len(st.session_state.messages):]
    st.session_state.messages.extend(new_turns)

    st.chat_message("assistant").write(final_response)