import streamlit as st 
from chatgpt import llm_call

st.title("Student View")

if st.button("Refresh"):
    st.session_state.clear()
    st.rerun()  


if "messages" not in st.session_state:
    st.session_state.messages = []


for message in st.session_state.messages:
    st.chat_message(message["role"]).write(message["content"])

user_message = st.chat_input("What you want to ask?...")

if user_message:
    st.session_state.messages.append(
        {
            "role":"user",
            "content":user_message
        }
    )

    bot_response = llm_call(st.session_state.messages)

    st.session_state.messages.append(
        {
            "role":"assistant",
            "content":bot_response
        }
    )

    st.rerun()

print(st.session_state) 