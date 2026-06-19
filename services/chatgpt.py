from openai import OpenAI
from dotenv import load_dotenv
import streamlit as st
import os

load_dotenv()

try:
    # 1. Try Streamlit Cloud setup first
    api_key = st.secrets["OPENAI_API_KEY"]
except Exception:
    # 2. Fallback to your laptop's .env file if running locally
    api_key = os.getenv("OPENAI_API_KEY")

client = OpenAI(api_key=api_key)

MODEL = "gpt-5.4-mini-2026-03-17"


def llm_call(messages: list) -> str:
    """Simple chat completion. Returns the assistant's text content."""
    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"Error: {str(e)}"


def llm_call_with_tools(messages: list, tools: list):
    """
    Chat completion with optional tool/function calling.

    Returns the raw response object (not just text) so the caller can
    inspect response.choices[0].message.tool_calls and act accordingly.

    Args:
        messages: Conversation history including any prior tool results.
        tools:    OpenAI-format tool schemas, or None to disable tool calling.
    """
    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=tools,
            tool_choice="auto"
        )
        return response
    except Exception as e:
        raise RuntimeError(f"LLM call failed: {str(e)}")