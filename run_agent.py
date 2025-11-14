import streamlit as st
import asyncio
import time

async def process_agent(user_q):
    # Use a persistent placeholder that can re-render
    spinner_placeholder = st.empty()
    spinner = spinner_placeholder.container()

    # Initial spinner
    spinner.markdown("💭 *Thinking...*")

    # Track timing for dynamic progress
    last_update_time = time.time()

    async for update in st.session_state.agent.run_agent(user_q):

        # === TOOL CALL PHASE ===
        if update["status"] == "tool_call":
            # Replace spinner text only if >0.5s since last update to avoid flicker
            if time.time() - last_update_time > 0.5:
                spinner_placeholder.empty()
                spinner = spinner_placeholder.container()
                spinner.markdown(f"⚙️ *Using tool:* `{update['tool_name']}` ...")
            last_update_time = time.time()

        # === DONE PHASE ===
        elif update["status"] == "done":
            # Replace spinner text with success message
            spinner_placeholder.empty()
            spinner = spinner_placeholder.container()
            spinner.markdown("✅ *Done!*")
            await asyncio.sleep(0.5)  # small grace period so user sees completion
            spinner_placeholder.empty()
            return update["answer"]

        # Optional: handle other statuses
        else:
            # Keep spinner alive during in-between messages
            if time.time() - last_update_time > 0.5:
                spinner.markdown("💭 *Still thinking...*")
            last_update_time = time.time()

    # Cleanup
    spinner_placeholder.empty()
    return None


status_placeholder.info(f"⚙️ Using tool **{update['tool_name']}**... please wait")
await asyncio.sleep(0.1)
