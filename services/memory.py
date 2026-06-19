from mem0 import MemoryClient
from services.chatgpt import llm_call
import streamlit as st
from dotenv import load_dotenv
import os

load_dotenv()

try:
    api_key = st.secrets["MEM0_API_KEY"]
except Exception:
    api_key = os.getenv("MEM0_API_KEY")

client = MemoryClient(api_key=api_key)

# Two namespaces — factual memories and session summaries are kept separate
# so they can be retrieved and used independently
def _factual_uid(student_id: str) -> str:
    return student_id

def _session_uid(student_id: str) -> str:
    return f"{student_id}_sessions"


# ---------------------------------------------------------------------------
# Factual memory — retrieved by the LLM as a tool
# ---------------------------------------------------------------------------

def get_memories(student_id: str, query: str) -> str:
    """
    Semantic search over factual memory for a student.
    Called as a tool by the LLM for specific mid-conversation lookups.
    """
    response = client.search(
        query,
        filters={"user_id": _factual_uid(student_id)}
    )
    results = response["results"]

    if not results:
        return "No relevant memories found for this student."

    memories = [f"- {r['memory']}" for r in results]
    return "\n".join(memories)


def get_all_factual_memories(student_id: str) -> str:
    """
    Fetch ALL factual memories for a student — injected into the system
    prompt at the start of every session so the LLM always has full context
    without needing to call a tool first.
    """
    response = client.get_all(
        filters={"user_id": _factual_uid(student_id)}
    )
    results = response.get("results", [])

    if not results:
        return ""

    memories = [f"- {r['memory']}" for r in results]
    return "\n".join(memories)


# ---------------------------------------------------------------------------
# Session summaries — used for session count and coach briefings
# ---------------------------------------------------------------------------

# def get_session_count(student_id: str) -> int:
#     """
#     Returns the number of completed sessions for this student,
#     derived from how many session summaries exist in mem0.
#     """
#     response = client.get_all(
#         filters={"user_id": _session_uid(student_id)}
#     )
#     results = response.get("results", [])
#     return len(results)


def get_session_summaries(student_id: str) -> str:
    """
    Retrieve all session summaries for a student.
    Intended for coach briefings, not for the student-facing agent.
    """
    response = client.get_all(
        filters={"user_id": _session_uid(student_id)}
    )
    results = response.get("results", [])

    if not results:
        return "No session history found for this student."

    summaries = [f"Session {i+1}:\n{r['memory']}" for i, r in enumerate(results)]
    return "\n\n".join(summaries)


# ---------------------------------------------------------------------------
# Internal — generate a session summary via LLM
# ---------------------------------------------------------------------------

def _generate_session_summary(messages: list) -> str:
    """
    Ask the LLM to produce a structured summary of the session.
    Stored in mem0 for future coach briefings and session continuity.
    """
    conversation = "\n".join(
        f"{m['role'].capitalize()}: {m['content']}" for m in messages
    )

    prompt = [
        {
            "role": "system",
            "content": (
                "You are a summarisation assistant. Given a tutoring session "
                "transcript, write a concise structured summary covering:\n"
                "- Topics discussed\n"
                "- Concepts the student understood well\n"
                "- Concepts the student struggled with\n"
                "- Any decisions or action items\n"
                "- Overall engagement and progress\n"
                "Keep it under 200 words. Write in third person about the student."
            ),
        },
        {
            "role": "user",
            "content": f"Summarise this tutoring session:\n\n{conversation}",
        },
    ]

    return llm_call(prompt)


# ---------------------------------------------------------------------------
# Save — called once when student clicks End Chat
# ---------------------------------------------------------------------------

def save_memory(student_id: str, messages: list):
    """
    Called when the student ends a session. Does two things:
    1. Saves the conversation to factual memory — mem0 auto-extracts
       facts, patterns, and recurring themes.
    2. Generates a structured session summary and stores it separately
       so coaches can request a briefing across all past sessions.
    """
    filtered = [
        {"role": m["role"], "content": m["content"]}
        for m in messages
        if isinstance(m, dict)
        and m.get("role") in ("user", "assistant")
        and m.get("content")
    ]

    if not filtered:
        return

    # 1. Factual memory — mem0 extracts stress triggers, patterns, preferences
    client.add(filtered, user_id=_factual_uid(student_id))

    # 2. Session summary — structured, stored in the sessions namespace
    summary = _generate_session_summary(filtered)
    client.add(
        [{"role": "assistant", "content": summary}],
        user_id=_session_uid(student_id)
    )