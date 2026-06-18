from openai import OpenAI 
from pprint import pprint 
from dotenv import load_dotenv


load_dotenv()

client = OpenAI()

# messages = []

# while True:
#     query = input("You: ")
#     if(query == "exit"):
#         break

#     messages.append(
#         {"role":"user", "content":query}
#     )
#     stream = client.chat.completions.create(
#         model="gpt-5.4-mini-2026-03-17",
#         messages=messages,
#         stream=True
#     )
#     #answer = response.choices[0].message.content 
#     answer = ""
#     print("ChatGPT : ", end="")
#     for chunk in stream:
#         delta = chunk.choices[0].delta.content

#         if delta:
#             print(delta, end="", flush=True)
#             answer += delta
        

#     messages.append(
#         {"role":"assistant", "content":answer}
#     )
#     print()


def llm_call(query:list):
    response = client.chat.completions.create(
        model="gpt-5.4-mini-2026-03-17",
        messages=query,
    
    )
    answer = response.choices[0].message.content

    return answer
