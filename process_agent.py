def process_agent(user_q: str, max_retries: int = MAX_RETRIES):
    """Run the agent and stream status updates into a spinner placeholder."""
    ensure_agent_initialized()

    # Use a persistent placeholder that we can update without reruns
    spinner_placeholder = st.empty()
    spinner = spinner_placeholder.container()
    spinner.markdown("🤖 Thinking...")

    last_err = None
    last_update_time = time.time()

    for attempt in range(1, max_retries + 1):
        try:
            # NOTE: this assumes st.session_state.agent has a *synchronous*
            # generator method that yields updates. If your agent only has
            # an async API, expose a small sync wrapper there instead.
            for update in st.session_state.agent.run_agent(user_q):
                status = update.get("status")

                if status == "tool_call":
                    spinner_placeholder.empty()
                    spinner = spinner_placeholder.container()
                    spinner.markdown(f"🔧 Using tool: `{update['tool_name']}` ...")

                elif status == "system_step":
                    spinner_placeholder.empty()
                    spinner = spinner_placeholder.container()
                    spinner.markdown(f"🧠 Running step: `{update['step_name']}` ...")

                elif status == "done":
                    spinner_placeholder.empty()
                    return update["answer"]

                else:
                    # keep spinner alive but don't flicker too often
                    if time.time() - last_update_time > 0.5:
                        spinner_placeholder.empty()
                        spinner = spinner_placeholder.container()
                        spinner.markdown("🤔 Still thinking...")
                        last_update_time = time.time()

            # If we exit the loop without a "done", bail out
            spinner_placeholder.empty()
            return None

        except (APIConnectionError, WorkflowRuntimeError, Exception) as err:
            last_err = err
            logger.error(
                f"Error running agent (attempt {attempt}/{max_retries}): {err}",
                streamlit_off=True,
            )

            # show a transient "retrying" message
            spinner_placeholder.empty()
            spinner = spinner_placeholder.container()
            spinner.markdown("⚠️ I encountered an error. Retrying…")

            if attempt < max_retries:
                sleep_for = BASE_BACKOFF_SECONDS * (2 ** (attempt - 1))
                time.sleep(sleep_for)
            else:
                spinner_placeholder.empty()
                raise last_err




# --- Main chat interaction (bottom of the file) ---

user_q = st.chat_input("Ask a question about your docs", key="chat_input")

if user_q:
    # 1. Immediately echo the user message into the chat history
    logger.info(f"USER - {user_q}", streamlit_off=True)
    user_msg = ChatMessage(role="user", content=user_q, id=str(uuid4()))
    st.session_state.messages.append(user_msg)
    st.session_state.memory_handler.save(user_msg)
    display_message(user_msg)

    # 2. Reserve a placeholder for the assistant's answer so the layout is stable
    answer_placeholder = st.empty()
    with answer_placeholder.container():
        st.markdown("🤖 Thinking…")

    # 3. Run the (slow) agent synchronously; update only the answer placeholder
    try:
        answer = process_agent(user_q)
    except Exception as e:
        answer = "I encountered an error. Please try again later."
        logger.error(f"Error running agent: {e}", streamlit_off=True)

    # 4. Replace placeholder with the final assistant message, store in history
    answer_placeholder.empty()
    assistant_msg = ChatMessage(
        role="assistant", content=str(answer), id=str(uuid4())
    )
    st.session_state.messages.append(assistant_msg)
    st.session_state.memory_handler.save(assistant_msg)
    display_message(assistant_msg)



