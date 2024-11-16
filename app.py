import streamlit as st

# Set page config
st.set_page_config(
    page_title="kAIusbot UI",
    page_icon="🤖",
    layout="centered",
)

# App title
st.title("kAIusbot Assistant")
st.caption("A friendly chatbot to help with your queries.")

# Session state to store the chat history
if "messages" not in st.session_state:
    st.session_state.messages = []

# Function to handle chatbot responses
def generate_response(input_text):
    # Placeholder response
    return "No model connected. But you said: " + input_text

# Chat Interface
with st.container():

    # Display chat history
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    # User input form
    with st.chat_message("user"):
        with st.form(key="chat_form", clear_on_submit=True):
            user_input = st.text_area(
                "Your message:",
                placeholder="Type your message here...",
                height=100,
                label_visibility="collapsed",
            )
            submitted = st.form_submit_button("Send")
            if submitted and user_input:
                # Add user message to session state
                st.session_state.messages.append({"role": "user", "content": user_input})
                
                # Generate response
                response = generate_response(user_input)
                st.session_state.messages.append({"role": "assistant", "content": response})

                # Re-render page to show new messages
                st.query_params.user_input = ""

# Footer
st.markdown("---")
st.markdown(
    "Designed with ❤️ using [Streamlit](https://streamlit.io)."
)
