from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()
client = OpenAI()

def llm_call(messages: list) -> str:
    try:
        response = client.chat.completions.create(
            model="gpt-5.4-mini-2026-03-17",
            messages=messages,
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"Error: {str(e)}"