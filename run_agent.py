async def process_agent(user_q):
    # Create a live placeholder for dynamic updates
    status_placeholder = st.empty()

    # Display initial spinner text
    with status_placeholder.container():
        st.info("💭 Thinking...")

    async for update in st.session_state.agent.run_agent(user_q):
        if update["status"] == "tool_call":
            # Update spinner text dynamically
            status_placeholder.info(f"⚙️ Using tool **{update['tool_name']}**...")
        elif update["status"] == "done":
            # Clear the spinner and return the answer
            status_placeholder.empty()
            return update["answer"]

    # Cleanup if something breaks
    status_placeholder.empty()
    return None



chat_input

if user_q:
    message = ChatMessage(role="user", content=user_q, id=str(uuid4()))
    st.session_state.messages.append(message)
    st.session_state.memory_handler.save(message)
    display_message(message)

    # Dynamic spinner now handled in process_agent
    answer = asyncio.run(process_agent(user_q))

    message = ChatMessage(role="assistant", content=str(answer), id=str(uuid4()))
    st.session_state.messages.append(message)
    st.session_state.memory_handler.save(message)
    display_message(message)


status_placeholder.info(f"⚙️ Using tool **{update['tool_name']}**... please wait")
await asyncio.sleep(0.1)
