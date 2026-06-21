import json

from services.googlesheets import (
    get_student_specific_data,
    get_pending_signals,
)
from services.memory import (
    get_memories,
    get_session_summaries,
)
from services.calendar import create_calendar_event
from RAG.ask import get_setup_data
from services.chatgpt import llm_call_with_tools


# ---------------------------------------------------------------------------
# Student tool schemas (unchanged)
# ---------------------------------------------------------------------------

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_student_specific_data",
            "description": (
                "Fetches the academic profile for a specific student, including "
                "their grade level, attendance record, performance scores, progress "
                "tracking, strengths, weaknesses, and learning history. "
                "Call this whenever the student asks about their own progress, "
                "performance, or when you need to personalise your response."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "student_id": {
                        "type": "string",
                        "description": (
                            "The unique student identifier (e.g. STU001)."
                        ),
                    }
                },
                "required": ["student_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_setup_data",
            "description": (
                "Searches the platform's course and feature documentation using "
                "a query, and returns the most relevant content chunks. "
                "Call this when the student asks about how the platform works, "
                "what features are available, course structure, login, scheduling, "
                "or any topic that requires knowledge of the platform setup."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": (
                            "A short, specific search query describing what to "
                            "look up in the platform docs."
                        ),
                    }
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_memories",
            "description": (
                "Retrieves factual memories from this student's past sessions: "
                "known stress triggers, what explanations have helped them, "
                "recurring misunderstandings, and personal learning patterns. "
                "Call this at the start of a conversation to personalise your "
                "approach, or when the student references something from a past "
                "session. Do NOT call this for session summaries — those are "
                "handled separately for coach briefings."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "student_id": {
                        "type": "string",
                        "description": (
                            "The unique student identifier (e.g. STU001)."
                        ),
                    },
                    "query": {
                        "type": "string",
                        "description": (
                            "What to search for in the student's factual memory. "
                            "Use the student's current message or topic as the query."
                        ),
                    },
                },
                "required": ["student_id", "query"],
            },
        },
    },
]


# ---------------------------------------------------------------------------
# Coach tool schemas
# ---------------------------------------------------------------------------

COACH_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_pending_signals",
            "description": (
                "Fetches all unactioned student signals from the platform, "
                "pre-sorted by severity (Critical first) then urgency (Today first). "
                "Always call this FIRST when generating a day plan — it tells you "
                "exactly which students need attention and why."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_student_specific_data",
            "description": (
                "Fetches the full academic profile for a specific student: "
                "grade level, attendance, performance scores, strengths, and weaknesses. "
                "Call this for every flagged student to inform the session type "
                "and talking points."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "student_id": {
                        "type": "string",
                        "description": (
                            "The unique student identifier (e.g. STU001)."
                        ),
                    }
                },
                "required": ["student_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_session_summaries",
            "description": (
                "Retrieves all past coaching session summaries for a student. "
                "Use this to understand their history, recurring issues, and what "
                "has or hasn't worked in previous sessions."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "student_id": {
                        "type": "string",
                        "description": (
                            "The unique student identifier (e.g. STU001)."
                        ),
                    }
                },
                "required": ["student_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_calendar_event",
            "description": (
                "Creates a session event on the coach's Google Calendar. "
                "Call this for EVERY student scheduled for TODAY — one call per student. "
                "Do NOT call this for students deferred to tomorrow."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": (
                            "Event title in the format: '[Student ID] – [Session Type]', "
                            "e.g. 'STU001 – Concept Review Session'."
                        ),
                    },
                    "start_time": {
                        "type": "string",
                        "description": (
                            "Session start in 24-hour 'HH:MM', e.g. '09:00'."
                        ),
                    },
                    "end_time": {
                        "type": "string",
                        "description": (
                            "Session end in 24-hour 'HH:MM', e.g. '09:45'."
                        ),
                    },
                    "description": {
                        "type": "string",
                        "description": (
                            "Plain-text session agenda: why this student is being "
                            "seen today and key talking points."
                        ),
                    },
                    "date": {
                        "type": "string",
                        "description": (
                            "Date in 'YYYY-MM-DD' format. "
                            "Omit or pass null to default to today."
                        ),
                    },
                },
                "required": [
                    "title",
                    "start_time",
                    "end_time",
                    "description",
                ],
            },
        },
    },
]


# ---------------------------------------------------------------------------
# Tool dispatcher — student (unchanged)
# ---------------------------------------------------------------------------

def _dispatch_tool(tool_name: str, tool_args: dict) -> str:
    if tool_name == "get_student_specific_data":
        result = get_student_specific_data(tool_args["student_id"])

    elif tool_name == "get_setup_data":
        result = get_setup_data(tool_args["query"])

    elif tool_name == "get_memories":
        result = get_memories(
            tool_args["student_id"],
            tool_args["query"],
        )

    else:
        result = f"[Error] Unknown tool: {tool_name}"

    return (
        json.dumps(result)
        if not isinstance(result, str)
        else result
    )


# ---------------------------------------------------------------------------
# Tool dispatcher — coach
# ---------------------------------------------------------------------------

def _dispatch_coach_tool(tool_name: str, tool_args: dict) -> str:
    if tool_name == "get_pending_signals":
        result = get_pending_signals()

    elif tool_name == "get_student_specific_data":
        result = get_student_specific_data(tool_args["student_id"])

    elif tool_name == "get_session_summaries":
        result = get_session_summaries(tool_args["student_id"])

    elif tool_name == "create_calendar_event":
        result = create_calendar_event(
            title=tool_args["title"],
            start_time=tool_args["start_time"],
            end_time=tool_args["end_time"],
            description=tool_args["description"],
            date=tool_args.get("date"),
        )

    else:
        result = f"[Error] Unknown coach tool: {tool_name}"

    return (
        json.dumps(result)
        if not isinstance(result, str)
        else result
    )


# ---------------------------------------------------------------------------
# Agentic loop — student (unchanged)
# ---------------------------------------------------------------------------

DEBUG = True


def run_agent(messages: list) -> tuple[str, list]:
    msgs = list(messages)

    while True:
        response = llm_call_with_tools(
            msgs,
            tools=TOOLS,
        )

        assistant_message = response.choices[0].message

        if not assistant_message.tool_calls:
            msgs.append(
                {
                    "role": "assistant",
                    "content": assistant_message.content,
                }
            )

            return assistant_message.content, msgs

        msgs.append(assistant_message)

        for tool_call in assistant_message.tool_calls:
            func_name = tool_call.function.name
            func_args = json.loads(
                tool_call.function.arguments
            )

            if DEBUG:
                print(
                    f"[Agent] Calling tool: "
                    f"{func_name}({func_args})"
                )

            tool_result = _dispatch_tool(
                func_name,
                func_args,
            )

            msgs.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": tool_result,
                }
            )


# ---------------------------------------------------------------------------
# Agentic loop — coach
# ---------------------------------------------------------------------------

def run_coach_agent(messages: list) -> tuple[str, list]:
    msgs = list(messages)

    while True:
        response = llm_call_with_tools(
            msgs,
            tools=COACH_TOOLS,
        )

        assistant_message = response.choices[0].message

        if not assistant_message.tool_calls:
            msgs.append(
                {
                    "role": "assistant",
                    "content": assistant_message.content,
                }
            )

            return assistant_message.content, msgs

        msgs.append(assistant_message)

        for tool_call in assistant_message.tool_calls:
            func_name = tool_call.function.name
            func_args = json.loads(
                tool_call.function.arguments
            )

            if DEBUG:
                print(
                    f"[Coach Agent] Calling tool: "
                    f"{func_name}({func_args})"
                )

            tool_result = _dispatch_coach_tool(
                func_name,
                func_args,
            )

            msgs.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": tool_result,
                }
            )