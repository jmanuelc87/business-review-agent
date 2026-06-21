import streamlit as st
import uuid

from langgraph.types import Command

from router import app as router

if "messages" not in st.session_state:
    st.session_state.messages = []  # chat transcript: [{role, content}]
if "thread_id" not in st.session_state:
    st.session_state.thread_id = str(uuid.uuid4())
if "pending_review" not in st.session_state:
    st.session_state.pending_review = None  # interrupt payload while paused


def run_graph(graph_input):
    stream = router.stream_events(
        graph_input,
        config={"configurable": {"thread_id": st.session_state.thread_id}},
        version="v3",
    )

    _ = stream.output  # type: ignore

    if stream.interrupted:  # type: ignore
        # First interrupt's payload -> the dict passed to interrupt(...)
        st.session_state.pending_review = stream.interrupts[0].value  # type: ignore
    else:
        st.session_state.pending_review = None
        st.session_state.messages.append(
            {"role": "assistant", "content": stream.output["final_answer"][-1]["text"]}
        )


st.title("Business Review Agent")


for m in st.session_state.messages:
    with st.chat_message(m["role"]):
        st.markdown(m["content"])


# If the graph is paused, render the review/edit panel.
if st.session_state.pending_review:
    payload = st.session_state.pending_review
    with st.chat_message("assistant"):
        st.markdown(f"**{payload['question']}**")
        edited = st.text_area(
            "Edit the draft, then submit",
            value=payload["args"][payload["args"]["type"]],
            height=220,
            key="review_box",
        )
        col_submit, col_approve = st.columns(2)
        if col_submit.button("✅ Submit edit", use_container_width=True):
            st.session_state.messages.append(
                {"role": "user", "content": "*(reviewed and edited the draft)*"}
            )
            run_graph(Command(resume={"approve": "y", "query": edited}))
            st.rerun()
        if col_approve.button("↩️ Approve as-is", use_container_width=True):
            st.session_state.messages.append(
                {"role": "user", "content": "*(approved the draft as-is)*"}
            )
            run_graph(
                Command(
                    resume={
                        "approve": "y",
                        "query": payload["args"][payload["args"]["type"]],
                    }
                )
            )
            st.rerun()


# Chat input — disabled while a review is pending so the user finishes one
# review cycle before starting another.
prompt = st.chat_input(
    "Ask the agent to draft something...",
    disabled=bool(st.session_state.pending_review),
)

if prompt:
    # Fresh thread per top-level request keeps each draft cycle isolated.
    st.session_state.thread_id = str(uuid.uuid4())
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.spinner("Thinking...", show_time=True):
        run_graph(
            {
                "query": st.session_state.messages[-1]["content"],
                "classifications": [],
                "final_answer": "",
                "results": [],
            }
        )
    st.rerun()
