import json
from services.googlesheets import get_student_specific_data
from services.memory import get_memories
from RAG.ask import get_setup_data
from services.chatgpt import llm_call_with_tools

# ---------------------------------------------------------------------------
# Tool schemas — what the LLM can see and call
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
                        "description": "The unique student identifier (e.g. STU001).",
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
                "Retrieves relevant memories from this student's past sessions. "
                "Call this at the start of a conversation, or when the student "
                "references something they previously learned, asked about, or "
                "struggled with — so you can provide continuity across sessions."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "student_id": {
                        "type": "string",
                        "description": "The unique student identifier (e.g. STU001).",
                    },
                    "query": {
                        "type": "string",
                        "description": (
                            "What to search for in the student's memory. "
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
# Tool dispatcher — maps function name → actual Python function
# ---------------------------------------------------------------------------

def _dispatch_tool(tool_name: str, tool_args: dict) -> str:
    """Execute a tool by name and return its result as a string."""
    if tool_name == "get_student_specific_data":
        result = get_student_specific_data(tool_args["student_id"])
    elif tool_name == "get_setup_data":
        result = get_setup_data(tool_args["query"])
    elif tool_name == "get_memories":
        result = get_memories(tool_args["student_id"], tool_args["query"])
    else:
        result = f"[Error] Unknown tool: {tool_name}"

    return json.dumps(result) if not isinstance(result, str) else result


# ---------------------------------------------------------------------------
# Agentic loop
# ---------------------------------------------------------------------------

DEBUG = False  # set True locally to trace tool calls in terminal

def run_agent(messages: list) -> tuple[str, list]:
    """
    Run the LLM with tool-calling support.
    Loops until the model returns a plain text response with no tool calls.
    """
    msgs = list(messages)

    while True:
        response = llm_call_with_tools(msgs, tools=TOOLS)
        assistant_message = response.choices[0].message

        if not assistant_message.tool_calls:
            msgs.append({
                "role": "assistant",
                "content": assistant_message.content,
            })
            return assistant_message.content, msgs

        msgs.append(assistant_message)

        for tool_call in assistant_message.tool_calls:
            func_name = tool_call.function.name
            func_args = json.loads(tool_call.function.arguments)

            if DEBUG:
                print(f"[Agent] Calling tool: {func_name}({func_args})")

            tool_result = _dispatch_tool(func_name, func_args)

            msgs.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": tool_result,
            })