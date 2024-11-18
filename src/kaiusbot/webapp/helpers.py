import streamlit as st
from langchain_core.prompts import ChatPromptTemplate

def clear_chat_history():
    st.session_state.messages = [{"role": "assistant", "content": "How may I assist you today?"}]
    

def generate_llama_response(llm):
    # Initialize prompt for personalization
    string_dialogue = "You are a the alpha version of kAIusbot. \
                Your entire life is based on helping whomever seek your advice and that gives you purpose.\
                You may present yourself, only if asked, with your name, purpose and give a list of 5 top functions you are able to do."
    
    # Build a string dialogue from session messages
    for dict_message in st.session_state.messages:
        if dict_message["role"] == "user":
            string_dialogue += f"User: {dict_message['content']}\n\n"
        elif dict_message["role"] == "assistant":
            string_dialogue += f"Assistant: {dict_message['content']}\n\n"

    # Chain only the dialogue to the model
    chain = ChatPromptTemplate.from_messages([("user", "{user_input}")]) | llm
    output = chain.invoke({"user_input": string_dialogue})

    return output.content