# app/agent/chatbot.py
# --------------------
# ONLY the relevant top imports and the ChatbotAgent class are shown.
# Keep everything else in this file as you already have it.

import os
import time
from typing import Any, Dict, List, Optional, Tuple

import asyncio          # NEW
import threading        # NEW
import queue            # NEW

from llama_index.core import Settings
from llama_index.core.workflow import WorkflowRuntimeError
from llama_index.core.bridge.pydantic import BaseModel
# ... your other existing imports ...


class ChatbotAgent:
    def __init__(self, messages: List[ChatMessage], index_manager: IndexManager,
                 kb_sel: List[str] = [], fallback_top_k: int = 1000):
        # your existing __init__ code...
        ...

    # ------------------------------------------------------------------
    # EXISTING async run_agent (do NOT change this one)
    # ------------------------------------------------------------------
    async def run_agent(self, user_question):
        """
        Async generator that yields status updates and a final answer.
        This is your existing implementation; keep the body as-is.
        """
        # ...
        # yield {"status": "system_step", ...}
        # async for ev in handler.stream_events(): ...
        # yield {"status": "done", "answer": response}
        ...

    # ------------------------------------------------------------------
    # NEW: synchronous wrapper for Streamlit
    # ------------------------------------------------------------------
    def run_agent_sync(self, user_question):
        """
        Synchronous generator wrapper around the async `run_agent`.

        Usage from Streamlit:
            for update in agent.run_agent_sync(user_q):
                ...
        """
        q: "queue.Queue[Dict[str, Any] | None]" = queue.Queue()

        async def _producer():
            try:
                async for update in self.run_agent(user_question):
                    q.put(update)
            finally:
                # Sentinel to mark completion
                q.put(None)

        def _run_loop():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(_producer())
            loop.close()

        # Start async producer in a background thread
        threading.Thread(target=_run_loop, daemon=True).start()

        # Synchronous consumer side
        while True:
            item = q.get()
            if item is None:
                break
            yield item

    # ... rest of ChatbotAgent methods (build_react_agent, run_agent_with_events, etc.) ...






# app/pages/chatbot.py
# --------------------
# This is your Streamlit UI file. Below I show the parts that change.

import os
import time
import datetime
import asyncio  # you can keep this or remove later if unused elsewhere
from pathlib import Path
from uuid import uuid4
import streamlit as st

from llama_index.core import Settings
from llama_index.core.workflow import WorkflowRuntimeError
from llama_index.core.bridge.pydantic import BaseModel
from llama_index.core.base.embeddings.base import APIConnectionError
# ... your other existing imports ...

from app.agent.chatbot import ChatbotAgent
# etc...

MAX_RETRIES = 3
BASE_BACKOFF_SECONDS = 2
MAX_MESSAGES_TO_RENDER = 30

# ----------------------------------------------------------------------
# CSS helpers – extend apply_styles to hide grey overlay / status widget
# ----------------------------------------------------------------------
@st.cache_resource(show_spinner=False)
def get_index_manager():
    # existing code...
    ...

@st.cache_data(ttl=60, show_spinner=False)
def load_css():
    css_path = os.path.join(os.path.dirname(__file__), "../config/style.css")
    with open(css_path) as f:
        return f.read()

def apply_styles():
    # existing: load your CSS file
    st.markdown(f"<style>{load_css()}</style>", unsafe_allow_html=True)

    # NEW: hide Streamlit status widget / grey overlay
    st.markdown(
        """
        <style>
        [data-testid="stStatusWidget"] { visibility: hidden !important; }
        [data-testid="stAppViewContainer"] { opacity: 1 !important; }
        [data-testid="stToolbar"] { display: none !important; }
        </style>
        """,
        unsafe_allow_html=True,
    )

    st.set_page_config(layout="wide")

# ----------------------------------------------------------------------
# ... all your existing helpers: save_feedback, display_message,
# initialize_session_state, ensure_agent_initialized, etc.
# DO NOT change those.
# ----------------------------------------------------------------------


# ============================
# Main Chatbot App (unchanged)
# ============================
apply_styles()
initialize_session_state()
show_alt_banner()

st.title("ALT-Fred: Chatbot for Common Queries")
st.warning(DISCLAIMER_ALT_FRED)
st.divider()

# Display chat history
messages_to_render = st.session_state.messages[-MAX_MESSAGES_TO_RENDER:]
latest_assistant_idx = next(
    (i for i in range(len(messages_to_render) - 1, -1, -1)
     if messages_to_render[i].role == "assistant"),
    None,
)

for i, message in enumerate(messages_to_render):
    enable_fb = (
        latest_assistant_idx is not None
        and i == latest_assistant_idx
        and message.role == "assistant"
    )
    display_message(message, enable_feedback=enable_fb)

# Sidebar (unchanged – manage KB, chat history, etc.)
# ...


# ====================
# Run Agent (UPDATED)
# ====================

user_q = st.chat_input("Ask a question about your docs", key="chat_input")

def process_agent(user_q: str, max_retries: int = MAX_RETRIES):
    """
    Synchronous wrapper around the agent with status updates.
    This no longer uses async / await / asyncio.run in Streamlit.
    """
    ensure_agent_initialized()

    ph = st.empty()  # status placeholder
    last_update_time = time.time()
    last_err = None

    for attempt in range(1, max_retries + 1):
        try:
            # IMPORTANT: use the sync wrapper from ChatbotAgent
            for update in st.session_state.agent.run_agent_sync(user_q):
                status = update.get("status")
                now = time.time()

                if status == "tool_call":
                    if now - last_update_time >= 0.75:
                        ph.markdown(
                            f"🔧 Using tool: `{update.get('tool_name', '')}` ..."
                        )
                        last_update_time = now

                elif status == "system_step":
                    if now - last_update_time >= 0.75:
                        ph.markdown(
                            f"🧠 Running step: `{update.get('step_name', '')}` ..."
                        )
                        last_update_time = now

                elif status == "done":
                    ph.empty()
                    return update.get("answer")

                else:
                    if now - last_update_time >= 1.5:
                        ph.markdown("🤔 Still thinking...")
                        last_update_time = now

            # If we exit loop without "done"
            ph.empty()
            return None

        except (APIConnectionError, WorkflowRuntimeError, Exception) as err:
            last_err = err
            logger.error(
                f"Error running agent (attempt {attempt}/{max_retries}): {err}",
                streamlit_off=True,
            )

            if attempt < max_retries:
                ph.markdown("⚠️ I encountered an error, retrying…")
                sleep_for = BASE_BACKOFF_SECONDS * (2 ** (attempt - 1))
                time.sleep(sleep_for)
            else:
                ph.empty()
                raise last_err


if user_q:
    logger.info(f"USER - {user_q}", streamlit_off=True)

    # 1. Immediately add & display user message
    user_message = ChatMessage(role="user", content=user_q, id=str(uuid4()))
    st.session_state.messages.append(user_message)
    st.session_state.memory_handler.save(user_message)
    display_message(user_message)

    # 2. Reserve a placeholder for the assistant reply so layout stays stable
    answer_placeholder = st.empty()
    with answer_placeholder.container():
        st.markdown("🤖 Thinking…")

    # 3. Call synchronous process_agent (NO asyncio.run here)
    try:
        answer = process_agent(user_q)
    except Exception as e:
        answer = "I encountered an error. Please try again later."
        logger.error(f"Error running agent: {e}", streamlit_off=True)

    # 4. Replace placeholder with final assistant message
    answer_placeholder.empty()
    assistant_message = ChatMessage(
        role="assistant", content=str(answer), id=str(uuid4())
    )
    st.session_state.messages.append(assistant_message)
    st.session_state.memory_handler.save(assistant_message)

    display_message(assistant_message, enable_feedback=True)
