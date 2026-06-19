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

def llm_call(messages: list) -> str:
    try:
        response = client.chat.completions.create(
            model="gpt-5.4-mini-2026-03-17",
            messages=messages,
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"Error: {str(e)}"