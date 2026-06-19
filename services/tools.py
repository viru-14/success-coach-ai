import json
from services.googlesheets import get_student_specific_data
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
                        "description": (
                            "The unique student identifier (e.g. STU001). "
                            "Use the currently selected student's ID."
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
                            "look up in the platform docs. "
                            "Example: 'how does login work', "
                            "'what topics are covered', 'how to submit assignment'."
                        ),
                    }
                },
                "required": ["query"],
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
    else:
        result = f"[Error] Unknown tool: {tool_name}"

    return json.dumps(result) if not isinstance(result, str) else result


# ---------------------------------------------------------------------------
# Agentic loop — keeps calling the LLM until it produces a plain text reply
# ---------------------------------------------------------------------------

DEBUG = False  # Bro is only for debuging purposes

def run_agent(messages: list) -> tuple[str, list]:
    """
    Run the LLM with tool-calling support.

    Keeps looping until the model returns a plain text response (no tool calls).

    Args:
        messages: The full conversation history including system prompt(s).

    Returns:
        (final_text_response, updated_messages_list)
        The caller should persist updated_messages_list so tool results
        become part of the conversation history for future turns.
    """
    msgs = list(messages)

    while True:
        response = llm_call_with_tools(msgs, tools=TOOLS)
        choice = response.choices[0]    
        assistant_message = choice.message

        # ── No tool calls → we have our final answer ──────────────────────
        if not assistant_message.tool_calls:
            msgs.append({
                "role": "assistant",
                "content": assistant_message.content,
            })
            return assistant_message.content, msgs

        # ── One or more tool calls → execute them, then loop ──────────────
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