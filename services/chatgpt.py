from openai import OpenAI
from dotenv import load_dotenv
import os

load_dotenv()
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

def llm_call(messages: list) -> str:
    try:
        response = client.chat.completions.create(
            model="gpt-5.4-mini-2026-03-17",
            messages=messages,
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"Error: {str(e)}"