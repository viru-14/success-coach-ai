import os
import json  # Added this for the JSON parsing

import streamlit as st
from dotenv import load_dotenv
from mem0 import MemoryClient

from services.googlesheets import log_student_signal
from services.chatgpt import llm_call


load_dotenv()

try:
    api_key = st.secrets["MEM0_API_KEY"]
except Exception:
    api_key = os.getenv("MEM0_API_KEY")

client = MemoryClient(api_key=api_key)

# Two namespaces — factual memories and session summaries are kept separate
# so they can be retrieved and used independently.


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
        filters={"user_id": _factual_uid(student_id)},
    )

    results = response["results"]

    if not results:
        return "No relevant memories found for this student."

    memories = [f"- {r['memory']}" for r in results]

    return "\n".join(memories)


def get_all_factual_memories(student_id: str) -> str:
    """
    Fetch ALL factual memories for a student — injected into the system prompt
    at the start of every session so the LLM always has full context without
    needing to call a tool first.
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

    summaries = [
        f"Session {i + 1}:\n{r['memory']}"
        for i, r in enumerate(results)
    ]

    return "\n\n".join(summaries)


# ---------------------------------------------------------------------------
# Internal — generate a session summary via LLM and log signals
# ---------------------------------------------------------------------------

def _generate_session_summary_and_check_signals(
    messages: list,
    student_id: str,
) -> str:
    """
    Asks the LLM to produce a structured summary of the session AND evaluate
    if a coach signal is required.

    Returns the summary for mem0 and automatically logs the signal to Google
    Sheets if needed.
    """
    conversation = "\n".join(
        f"{m['role'].capitalize()}: {m['content']}"
        for m in messages
    )

    prompt = [
        {
            "role": "system",
            "content": (
                "You are an AI assistant for a tutoring program. Read the "
                "following session transcript and return a STRICT JSON object "
                "containing two things: a session summary, and a signal "
                "evaluation to alert human coaches of any issues.\n\n"
                "Your JSON output must follow this exact structure:\n"
                "{\n"
                '  "summary": "A concise (under 200 words) structured summary '
                "in the third person covering: topics discussed, understood "
                'concepts, struggled concepts, action items, and overall '
                'progress.",\n'
                '  "requires_signal": true or false. Set to true ONLY IF the '
                "student exhibits issues requiring coach intervention (e.g., "
                "severe academic struggle, attendance risks, high frustration, "
                'behavioral issues).\n'
                '  "signal_data": If requires_signal is true, provide an object '
                'with the keys: "signal_type" (e.g., "Academic Struggle", '
                '"Mental Health"), "severity" ("Low", "Medium", "High", '
                '"Critical"), "urgency" ("Today", "Tomorrow", "This Week"), '
                'and "reason" (1-2 sentence explanation). If '
                'requires_signal is false, set this to null.\n'
                "}\n\n"
                "Do not include any markdown formatting like ```json in your "
                "response. Return ONLY the raw JSON object."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Analyze this tutoring session:\n\n{conversation}"
            ),
        },
    ]

    # 1. Get the response from your LLM
    llm_response = llm_call(prompt)

    try:
        # 2. Parse the JSON response
        extracted_data = json.loads(llm_response.strip())

        # 3. Check if a signal was triggered and log it
        if (
            extracted_data.get("requires_signal")
            and extracted_data.get("signal_data")
        ):
            sig_data = extracted_data["signal_data"]

            # Call the Google Sheets function
            log_student_signal(
                student_id=student_id,
                signal_type=sig_data.get(
                    "signal_type",
                    "Unknown",
                ),
                severity=sig_data.get(
                    "severity",
                    "Medium",
                ),
                urgency=sig_data.get(
                    "urgency",
                    "This Week",
                ),
                reason=sig_data.get(
                    "reason",
                    "Flagged by AI summarizer.",
                ),
            )

        # 4. Return the summary string so your existing mem0 flow works perfectly
        return extracted_data.get(
            "summary",
            "Summary could not be generated.",
        )

    except json.JSONDecodeError:
        print(
            "Error: The LLM did not return valid JSON. "
            "Fallback to raw text."
        )

        # If the LLM fails to output JSON, you can just return the raw text
        # so you don't lose the summary entirely.
        return llm_response

    except Exception as e:
        print(
            f"An error occurred during summarization/signaling: {e}"
        )
        return "Error generating summary."


# ---------------------------------------------------------------------------
# Save — called once when student clicks End Chat
# ---------------------------------------------------------------------------

def save_memory(
    student_id: str,
    messages: list,
):
    """
    Called when the student ends a session.

    Does two things:
    1. Saves the conversation to factual memory — mem0 auto-extracts facts,
       patterns, and recurring themes.
    2. Generates a structured session summary and stores it separately so
       coaches can request a briefing across all past sessions.
    """
    filtered = [
        {
            "role": m["role"],
            "content": m["content"],
        }
        for m in messages
        if (
            isinstance(m, dict)
            and m.get("role") in ("user", "assistant")
            and m.get("content")
        )
    ]

    if not filtered:
        return

    # 1. Factual memory — mem0 extracts stress triggers, patterns, preferences
    client.add(
        filtered,
        user_id=_factual_uid(student_id),
    )

    # 2. Session summary — structured, stored in the sessions namespace
    # UPDATED: Now calls the combined function and passes the student_id
    summary = _generate_session_summary_and_check_signals(
        filtered,
        student_id,
    )

    client.add(
        [{"role": "assistant", "content": summary}],
        user_id=_session_uid(student_id),
    )