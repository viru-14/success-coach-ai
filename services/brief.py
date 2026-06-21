from __future__ import annotations

from typing import Callable

BRIEF_SYSTEM_PROMPT = """
You are a coaching assistant preparing a coach for a 1:1 session with a
student. Using ONLY the three context blocks provided (live academic data,
factual memory from past sessions, and prior session summaries), write a
focused, skimmable brief.

Do not invent facts that are not supported by the context. If a section has
no supporting information, say so plainly rather than guessing.

Return the brief in EXACTLY this markdown structure and nothing else:

** Student Brief — [Student ID]**

** Current academic situation**
- 2–4 bullets on grade level, recent performance, attendance, strengths and
  weaknesses drawn from the live academic data.

** What changed since the last session**
- 1–3 bullets contrasting the most recent session summary with earlier ones
  and the current data. If there is only one (or no) prior session, say that
  explicitly.

** Open concerns**
- 1–3 bullets on unresolved issues, recurring misunderstandings, stress
  triggers, or risk flags. If none are evident, state
  "No open concerns on record."

** Conversation starters for today**
- 2–3 concrete, specific opening questions or prompts the coach can use,
  grounded in this student's actual history and data.

Keep the whole brief under ~250 words. Be factual and specific — no filler.
"""

# to generate brief of any student
def generate_student_brief(
    student_id: str,
    *,
    student_data_fn: Callable[[str], str] | None = None,
    factual_memory_fn: Callable[[str], str] | None = None,
    session_summaries_fn: Callable[[str], str] | None = None,
    llm_fn: Callable[[list], str] | None = None,
) -> str:
    

    if student_data_fn is None:
        from services.googlesheets import (
            get_student_specific_data as student_data_fn,
        )

    if factual_memory_fn is None:
        from services.memory import (
            get_all_factual_memories as factual_memory_fn,
        )

    if session_summaries_fn is None:
        from services.memory import (
            get_session_summaries as session_summaries_fn,
        )

    if llm_fn is None:
        from services.chatgpt import llm_call as llm_fn

    academic = student_data_fn(student_id) or "No academic data available."
    factual = factual_memory_fn(student_id) or "No factual memory on record."
    summaries = (
        session_summaries_fn(student_id)
        or "No session history found."
    )

    context = (
        f"Student ID: {student_id}\n\n"
        f"=== LIVE ACADEMIC DATA ===\n{academic}\n\n"
        f"=== FACTUAL MEMORY (past sessions) ===\n{factual}\n\n"
        f"=== PRIOR SESSION SUMMARIES ===\n{summaries}\n"
    )

    messages = [
        {
            "role": "system",
            "content": BRIEF_SYSTEM_PROMPT,
        },
        {
            "role": "user",
            "content": (
                f"Prepare today's brief for {student_id} "
                f"using the context below.\n\n{context}"
            ),
        },
    ]

    return llm_fn(messages)

#print(generate_student_brief())