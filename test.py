import os
import datetime
import asyncio
import time
from pathlib import Path
from uuid import uuid4
import streamlit as st

from llama_index.core import Settings
from openai import APIConnectionError
from llama_index.core.workflow.errors import WorkflowRuntimeError

from app.agent.chatbot import ChatbotAgent
from app.agent.query_engine import ConversationCleanerEngine
from app.agent.index import IndexManager
from app.database.store_factory import ChatMessage, get_memory_store, FeedbackStore
from app.config.const import DISCLAIMER_ALT_FRED
from app.config.file_tree import FileTreeSelector
from app.config.util import show_uat_banner
from app.config.logging import Logger

# Set page config as early as possible
st.set_page_config(layout="wide")

logger = Logger(job_name="app", user_id=st.session_state.user_id, use_streamlit=True)
logger.info("Starting Chatbot page.", streamlit_off=True)

MAX_RETRIES = 3
BASE_BACKOFF_SECONDS = 2
MAX_MESSAGES_TO_RENDER = 30  # limit messages rendered to reduce re-render cost

# -------------------------
# Cache helpers
# -------------------------

@st.cache_resource(show_spinner=False)
def get_index_manager():
    return IndexManager()

@st.cache_data(ttl=60, show_spinner=False)
def cached_file_metadata(index_manager):
    try:
        return index_manager.get_file_metadata()
    except Exception:
        return []

@st.cache_resource(show_spinner=False)
def get_cached_memory_handler(user_name, thread_id=None):
    # thread_id may be None for "all threads" handler
    return get_memory_store(user_name=user_name, thread_id=str(thread_id) if thread_id else None)

@st.cache_data(show_spinner=False)
def load_css():
    css_path = Path(os.path.join(os.path.dirname(__file__), "../config/style.css"))
    with open(css_path) as css:
        return css.read()

# -------------------------
# Feedback helper
# -------------------------

def save_feedback(feedback_type="positive"):
    """Send the current conversation to the conversation cleaner agent and add to feedback knowledge base."""
    with st.spinner("Saving feedback..."):
        try:
            thread_id = st.session_state.current_thread
            user_name = st.session_state.user
            
            # Use current session's memory handler/messages for speed
            memory_handler = st.session_state.memory_handler
            messages = memory_handler.get()
            messages = [message.to_dict() for message in messages]
            
            if not messages:
                logger.warning("No messages found in this conversation.", streamlit_off=True)
                return False
            
            # Send to conversation cleaner
            conversation_cleaner = ConversationCleanerEngine()
            cleaned = conversation_cleaner.clean(messages=str(messages), feedback_type=feedback_type)
            
            # Get embedding of row
            embedding = Settings.embed_model.get_text_embedding(cleaned.get("question", ""))
            
            # Save in feedback knowledge base table in sql database
            feedback_store = FeedbackStore()
            feedback_store.save_feedback(user_name, thread_id, feedback_type, str(messages), cleaned, embedding=embedding)
            
            logger.success(f"{feedback_type} feedback saved for user thread {thread_id}", streamlit_off=True)
            return True
        except Exception as e:
            logger.error(f"Failed to save {feedback_type} feedback: {str(e)}", streamlit_off=True)
            return False

# -------------------------
# App formatting helpers
# -------------------------

def apply_styles():
    """Apply the css style to the app."""
    st.markdown(f"<style>{load_css()}</style>", unsafe_allow_html=True)

def display_message(message, enable_feedback=False):
    """Display a message in the chat. Can be either an assistant or user message."""
    if message.role == "assistant":
        st.markdown(
            f"""
            <div class='assistant-container'>
                <div class='assistant-title'>ALT-Fred</div>
                <div class='assistant-message'>{message.content}</div>
            </div>
            """,
            unsafe_allow_html=True
        )
        
        if enable_feedback:
            # Initialize processed_feedback tracking in session state
            if "processed_feedback" not in st.session_state:
                st.session_state.processed_feedback = set()
            
            feedback = st.feedback("thumbs", key=f"feedback_{message.id}")
            # Create unique identifier for this feedback
            feedback_key = f"{message.id}_{feedback}"
            
            # Handle feedback and show notifications only if not already processed
            if feedback == 1 and feedback_key not in st.session_state.processed_feedback:
                logger.info("User provided positive feedback.", streamlit_off=True)
                success = save_feedback("positive")
                if success:
                    st.info("Thank you for your feedback! Your conversation has been saved to help improve ALT-Fred.")
                    st.session_state.processed_feedback.add(feedback_key)
                else:
                    st.error("Failed to save feedback. Please try again.", icon="⚠")
            elif feedback == 0 and feedback_key not in st.session_state.processed_feedback:
                logger.info("User provided negative feedback.", streamlit_off=True)
                success = save_feedback("negative")
                if success:
                    st.info("Thank you for your feedback! Your conversation has been saved to help improve ALT-Fred.")
                    st.session_state.processed_feedback.add(feedback_key)
                else:
                    st.error("Failed to save feedback. Please try again.", icon="⚠")
    elif message.role == "user":
        st.markdown(
            f"""
            <div class='user-container'>
                <div class='user-title'>You</div>
                <div class='user-message'>{message.content}</div>
            </div>
            """,
            unsafe_allow_html=True
        )

# -------------------------
# Streamlit session state handlers
# -------------------------

@st.cache_data(ttl=30, show_spinner=False)
def get_thread_summaries(user_name, max_threads=50):
    """Return last user message per thread, sorted by most recent thread_id, capped."""
    mh = get_cached_memory_handler(user_name=user_name)  # handler for all threads
    df = mh.get_all()[["thread_id", "role", "message", "data"]]
    df = df[df.role == "user"]
    df = df.sort_values(["thread_id", "data"], ascending=False).groupby("thread_id").tail(1)
    df = df.sort_values("thread_id", ascending=False).head(max_threads)
    return [{"thread_id": int(row.thread_id), "last_message": row.message, "data": row.data} for _, row in df.iterrows()]

def load_chats():
    """Load all chat history for the user."""
    logger.info("Loading chat history from database", streamlit_off=True)
    thread_dicts = get_thread_summaries(st.session_state.user, max_threads=50)
    
    # add new chat to history
    if thread_dicts:
        current_num = thread_dicts[0]["thread_id"]
        st.session_state.current_thread = current_num + 1
    else:
        st.session_state.current_thread = 1
    
    st.session_state.thread_history = [{"thread_id": st.session_state.current_thread, "last_message": "New Chat", "data": datetime.datetime.now()}] + thread_dicts

def initialize_session_state():
    """Initialize the session. This runs after every refresh."""
    logger.info("Initializing session state", streamlit_off=True)
    
    if "kb_root" not in st.session_state:
        kb_root = Path("knowledge_base")
        kb_root.mkdir(exist_ok=True)
        st.session_state.kb_root = kb_root
    
    if "index_manager" not in st.session_state:
        st.session_state.index_manager = get_index_manager()
    
    if "chats_loaded" not in st.session_state:
        load_chats()
        st.session_state.chats_loaded = True
    
    if "memory_handler" not in st.session_state:
        st.session_state.memory_handler = get_cached_memory_handler(
            user_name=st.session_state.user,
            thread_id=str(st.session_state.current_thread)
        )
    
    if "messages" not in st.session_state:
        st.session_state.messages = st.session_state.memory_handler.get()

def ensure_agent_initialized():
    """Build the agent only once and reuse tools."""
    if "agent" not in st.session_state or st.session_state.agent is None:
        logger.info("Building agent with cached tools.", streamlit_off=True)
        # limit messages passed to agent to last N messages to reduce context size
        N = 10
        chat_history = [msg.to_llama_message() for msg in st.session_state.messages[-N:]]
        agent = ChatbotAgent(
            messages=chat_history,
            index_manager=st.session_state.index_manager,
            kb_select=st.session_state.get("kb_sel", [])
        )
        agent.build_all_tools()
        st.session_state.agent = agent
        logger.info("Agent initialized with all tools cached", streamlit_off=True)

def clear_chat():
    logger.info(f"Clearing chat history for user thread {st.session_state.current_thread}", streamlit_off=True)
    st.session_state.memory_handler.delete(thread_id=str(st.session_state.current_thread), user_name=st.session_state.user)
    if "messages" in st.session_state:
        del st.session_state.messages
    if "chats_loaded" in st.session_state:
        del st.session_state.chats_loaded
    if "agent" in st.session_state and st.session_state.agent:
        st.session_state.agent.memory.reset()
    st.rerun()

def new_chat():
    logger.info("Initializing new chat for user", streamlit_off=True)
    load_chats()
    if "memory_handler" in st.session_state:
        del st.session_state.memory_handler
    if "messages" in st.session_state:
        del st.session_state.messages
    ensure_agent_initialized()
    # give agent the new memory
    if st.session_state.agent and st.session_state.agent.memory:
        st.session_state.agent.memory.reset()
    st.rerun()

def select_chat(thread_id):
    logger.info(f"User selected new thread {thread_id}", streamlit_off=True)
    st.session_state.current_thread = thread_id
    st.session_state.memory_handler = get_cached_memory_handler(
        user_name=st.session_state.user,
        thread_id=str(st.session_state.current_thread)
    )
    st.session_state.messages = st.session_state.memory_handler.get()
    ensure_agent_initialized()
    # give agent the new memory
    if st.session_state.agent and st.session_state.agent.memory:
        chat_history = [msg.to_llama_message() for msg in st.session_state.messages[-10:]]
        st.session_state.agent.memory.set(chat_history)
    st.rerun()

# -------------------------
# Run Agent with status updates
# -------------------------

async def process_agent(user_q, max_retries=MAX_RETRIES):
    """Process agent with real-time status updates."""
    now = time.time()
    
    if status == "tool_call":
        if now - last_update_time > 0.75:
            ph.markdown(f"🛠️ Using tool: `{update.get('tool_name', '')}`...")
            last_update_time = now
    elif status == "system_step":
        if now - last_update_time > 0.75:
            ph.markdown(f"🔄 Running step: `{update.get('step_name', '')}`...")
            last_update_time = now
    elif status == "done":
        ph.empty()
        return update.get("answer")
    else:
        if now - last_update_time > 1.5:
            ph.markdown("💭 Still thinking...")
            last_update_time = now
    
    ph.empty()
    return None

# -------------------------
# Main Chatbot App
# -------------------------

# Sidebar - Knowledge Base
st.sidebar.markdown("# 📚 **Questions?** [ilia.tsimouri@ubs.com](mailto:ilia.tsimouri@ubs.com)")

st.sidebar.divider()
st.sidebar.header("📂 Manage Knowledge Base", expanded=True)
file_metadata = cached_file_metadata(st.session_state.index_manager)
if not file_metadata:
    st.warning("No files in knowledge base.")
    sel = []
else:
    # Create file tree selector
    tree_selector = FileTreeSelector(file_metadata)
    sel = tree_selector.render(container=st)

# Update document selection
if st.button("Apply Document Selection", type="primary"):
    st.session_state["kb_sel"] = sel
    with st.spinner("Updating document selection..."):
        ensure_agent_initialized()
        st.session_state.agent.update_document_selection(st.session_state.kb_sel)
        logger.success(f"Agent updated with {len(st.session_state.kb_sel)} selected documents.")

# ----------------------------- Chat History ~~~~~~~~~~~~~~~~~~~~~
st.sidebar.divider()
st.sidebar.header("💬 Manage Chats")

col1, col2 = st.sidebar.columns(2)
with col1:
    if st.button("Clear Chat", icon=":material/delete:", key="clear"):
        clear_chat()
with col2:
    if st.button("New Chat", icon=":material/add:", key="new"):
        new_chat()

for thread in st.session_state.thread_history:
    button_label = f"{thread['last_message'][:37]}" if len(thread['last_message']) > 37 else f"{thread['last_message']}"
    widget_key = f"thread_{thread['thread_id']}"
    if st.sidebar.button(button_label, key=widget_key):
        select_chat(thread['thread_id'])

# ----------------------------- Run Agent ~~~~~~~~~~~~~~~~~~~~~
user_q = st.chat_input("Ask a question about your docs:", key="chat_input")

async def process_agent(user_q, max_retries=MAX_RETRIES):
    ensure_agent_initialized()
    # Use a single persistent placeholder to avoid container churn
    ph = st.empty()
    last_update_time = 0.0
    last_err = None
    
    for attempt in range(1, max_retries + 1):
        try:
            answer = asyncio.run(st.session_state.agent.run_agent(user_q))
            except (APIConnectionError, WorkflowRuntimeError, Exception) as err:
            last_err = err
            logger.error(f"Error running agent (attempt {attempt}/{max_retries}): {err}", streamlit_off=True)
            if attempt < max_retries:
                ph.markdown("⚠️ Encountered an error, retrying...")
                sleep_for = BASE_BACKOFF_SECONDS * (2 ** (attempt - 1))
                time.sleep(sleep_for)
            else:
                ph.empty()
                raise last_err
    
    ph.empty()
    return None

if user_q:
    logger.info(f"USER - {user_q}", streamlit_off=True)
    user_message = ChatMessage(role="user", content=user_q, id=str(uuid4()))
    st.session_state.messages.append(user_message)
    # Optionally defer DB writes until after assistant responds to reduce I/O;
    # keeping original behavior is fine as well. Here we write both messages after response.
    
    try:
        answer = asyncio.run(process_agent(user_q))
    except Exception as e:
        answer = "I encountered an error. Please try again later."
        logger.error(f"Error running agent: {e}", streamlit_off=True)
    
    assistant_message = ChatMessage(role="assistant", content=str(answer), id=str(uuid4()))
    st.session_state.messages.append(assistant_message)
    # Persist messages
    st.session_state.memory_handler.save(user_message)
    st.session_state.memory_handler.save(assistant_message)
    
    # Display assistant message with feedback
    display_message(assistant_message, enable_feedback=True)

# ----------------------------- Display Chat History ~~~~~~~~~~~~~~~~~~~~~
# Display chat history (limit to last MAX_MESSAGES_TO_RENDER messages)
messages_to_render = st.session_state.messages[-MAX_MESSAGES_TO_RENDER:]
latest_assistant_idx = None

for idx, msg in enumerate(messages_to_render):
    if msg.role == "assistant":
        latest_assistant_idx = idx

for i, message in enumerate(messages_to_render):
    enable_fb = (latest_assistant_idx is not None) and (i == latest_assistant_idx) and (message.role == "assistant")
    display_message(message, enable_feedback=enable_fb)

# ----------------------------- App Title ~~~~~~~~~~~~~~~~~~~~~
apply_styles()
initialize_session_state()
show_uat_banner()

st.title("ALT-Fred: Chatbot for Common Queries")
st.warning(DISCLAIMER_ALT_FRED)
st.divider()


