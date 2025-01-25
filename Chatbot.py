import streamlit as st
import os

from langchain_ollama import ChatOllama

from src import *

# Set page config
st.set_page_config(
    page_title="kAIusbot",
    layout="wide"
)

# Display page settings
st.title("kAIusbot")
st.caption("This is a study project. I use Streamlit as UI and run LLama using LangChain on the background.")

# Sidebar settings
with st.sidebar:
    st.button('Clear Chat History', on_click=clear_chat_history)
    "[![Check my Linkedin](https://img.shields.io/badge/LinkedIn-0077B5?style=for-the-badge&logo=linkedin&logoColor=white)](https://www.linkedin.com/in/kaiusdepaula/)"
    "[View the source code](https://github.com/kaiusdepaula/kAIusbot)"

# Initiate LLM model
llm = ChatOllama(
    model="llama3.1",
    temperature=0.1,
    # other params...
)

# Store LLM generated responses
if "messages" not in st.session_state.keys():
    st.session_state.messages = [{"role": "assistant", "content": "How may I assist you today?"}]

# Display or clear chat messages
for message in st.session_state.messages:
    if message["role"] != "system":  # Skip system messages
        with st.chat_message(message["role"]):
            st.write(message["content"])

# User-provided prompt
if prompt := st.chat_input():
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.write(prompt)


# Generate a new response if last message is not from assistant
if st.session_state.messages[-1]["role"] != "assistant":
    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            response = generate_llama_response(llm)
            placeholder = st.empty()
            full_response = ''
            for item in response:
                full_response += item
                placeholder.markdown(full_response)
            placeholder.markdown(full_response)
    message = {"role": "assistant", "content": full_response}
    st.session_state.messages.append(message)