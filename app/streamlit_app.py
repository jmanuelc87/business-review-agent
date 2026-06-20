import streamlit as st
import time


from router import app as router


def stream_data(text, delay: float = 0.02):
    for word in text.split():
        yield word + " "
        time.sleep(delay)


# Input for the prompt
prompt = st.chat_input("Ask Question")

# Initialize chat history in session state if it doesn't exist
if "messages" not in st.session_state:
    st.session_state.messages = []

# Display chat history
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

if prompt:
    # Add user message to chat history
    st.session_state.messages.append({"role": "user", "content": prompt})

    # Display input prompt from user
    with st.chat_message("user"):
        st.markdown(prompt)

    # Processing
    with st.chat_message("assistant"):
        message_placeholder = st.empty()
        full_response = ""

        # Stream the response with a spinner while waiting for the initial response
        with st.spinner("Thinking...", show_time=True):
            response = router.invoke(
                {
                    "query": st.session_state.messages[-1]["content"],
                    "classifications": [],
                    "final_answer": "",
                    "results": [],
                }
            )

            # Fallback for non-streaming response
            full_response = (
                response["final_answer"]
                if len(response["final_answer"]) > 0
                else "I dont have anything to show you"
            )

            message_placeholder.markdown(full_response)

        # Add assistant response to chat history
        st.session_state.messages.append(
            {"role": "assistant", "content": full_response}
        )
