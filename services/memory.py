from mem0 import MemoryClient
import streamlit as st
from dotenv import load_dotenv
import os

load_dotenv()

try:
    api_key = st.secrets["MEM0_API_KEY"]
except Exception:
    api_key = os.getenv("MEM0_API_KEY")

client = MemoryClient(api_key=api_key)


def get_memories(student_id: str, query: str) -> str:
    """
    Retrieve memories relevant to the query for a specific student.
    Called as a tool — the LLM decides when to invoke this.
    """
    response = client.search(
        query, 
        filters={
            "user_id": student_id
        }
    ) # {'results:[]}
    #print(response)
    results = response['results']

    if not results:
        return "No relevant memories found for this student."

    memories = [f"- {r['memory']}" for r in results]
    return "\n".join(memories)


def save_memory(student_id: str, messages: list):
    """
    Save the full conversation to mem0 when the student ends the chat.

    Filters out tool and system messages — only user/assistant turns are saved
    since those are what mem0 needs to extract meaningful memories.
    """
    filtered = [
        {"role": m["role"], "content": m["content"]}
        for m in messages
        if isinstance(m, dict)
        and m.get("role") in ("user", "assistant")
        and m.get("content")
    ]

    if filtered:
        client.add(filtered, user_id=student_id)

# get_memories("STU002", "what is my fav subject")
