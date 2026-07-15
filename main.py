import asyncio

import streamlit as st

from src.agent import set_retrieval_top_k, stream_response
from src.webapp.helpers import clear_chat_history

st.set_page_config(page_title="kAIusbot", layout="wide")
st.title("kAIusbot")

# -- sidebar --
with st.sidebar:
    st.header("Configuration")

    model_name = st.text_input(
        "Model",
        value=st.session_state.get("model_name", "gpt-oss:20b"),
        key="model_name_input",
    )
    st.session_state["model_name"] = model_name

    base_url = st.text_input(
        "API Base URL",
        value=st.session_state.get("base_url", "http://localhost:11434/v1"),
        key="base_url_input",
    )
    st.session_state["base_url"] = base_url

    st.divider()
    st.subheader("Generation")

    temperature = st.slider(
        "Temperature",
        min_value=0.0,
        max_value=2.0,
        value=st.session_state.get("temperature", 0.7),
        step=0.1,
        key="temperature_slider",
    )
    st.session_state["temperature"] = temperature

    st.subheader("Retrieval")

    top_n = st.selectbox(
        "Top-N results",
        options=[1, 2, 3, 5, 7, 10],
        index=[1, 2, 3, 5, 7, 10].index(st.session_state.get("top_n", 3)),
        key="top_n_selector",
    )
    st.session_state["top_n"] = top_n
    set_retrieval_top_k(top_n)

    st.divider()
    st.button("Clear Chat History", on_click=clear_chat_history)
    st.caption("This is a study project. I use Streamlit as UI and run LLama using Ollama on the background.")
    "[![LinkedIn](https://img.shields.io/badge/LinkedIn-0077B5?style=for-the-badge&logo=linkedin&logoColor=white)](https://www.linkedin.com/in/kaiusdepaula/)"
    "[![GitHub](https://img.shields.io/badge/GitHub-kaiusdepaula%2FkAIusbot-24292e?style=for-the-badge&logo=github&logoColor=white)](https://github.com/kaiusdepaula/kAIusbot)"

# -- chat --
if "messages" not in st.session_state:
    st.session_state.messages = [{"role": "assistant", "content": "How may I assist you today?"}]

for message in st.session_state.messages:
    if message["role"] != "system":
        with st.chat_message(message["role"]):
            st.write(message["content"])

if prompt := st.chat_input():
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.write(prompt)

if st.session_state.messages[-1]["role"] != "assistant":
    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            placeholder = st.empty()
            full_response = [""]

            user_input = st.session_state.messages[-1]["content"]
            history = st.session_state.messages[:-1]

            async def _stream():
                tool_name = None
                async for event in stream_response(
                    user_input,
                    history,
                    model_name=st.session_state.get("model_name"),
                    base_url=st.session_state.get("base_url"),
                    temperature=st.session_state.get("temperature"),
                ):
                    match event:
                        case {"type": "text", "delta": delta}:
                            full_response[0] += delta
                            label = (
                                f"*Calling `{tool_name}`...*\n\n{full_response[0]}"
                                if tool_name
                                else full_response[0]
                            )
                            placeholder.markdown(label)
                        case {"type": "tool_call", "name": name}:
                            tool_name = name
                            placeholder.markdown(f"*Calling `{tool_name}`...*\n\n{full_response[0]}")
                        case {"type": "tool_result", "name": _}:
                            tool_name = None
                            placeholder.markdown(full_response[0])
                placeholder.markdown(full_response[0])

            try:
                asyncio.run(_stream())
            except Exception as e:
                full_response[0] = f"Error: {e}"

    st.session_state.messages.append({"role": "assistant", "content": full_response[0]})
