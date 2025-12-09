def process_agent(user_q: str, max_retries: int = MAX_RETRIES):
    ensure_agent_initialized()

    spinner_placeholder = st.empty()
    spinner = spinner_placeholder.container()
    spinner.markdown("🤖 Thinking...")

    last_err = None
    last_update_time = time.time()

    for attempt in range(1, max_retries + 1):
        try:
            # NOTE: use run_agent_sync here
            for update in st.session_state.agent.run_agent_sync(user_q):
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
                    if time.time() - last_update_time > 0.5:
                        spinner_placeholder.empty()
                        spinner = spinner_placeholder.container()
                        spinner.markdown("🤔 Still thinking...")
                        last_update_time = time.time()

            spinner_placeholder.empty()
            return None

        except (APIConnectionError, WorkflowRuntimeError, Exception) as err:
            last_err = err
            logger.error(
                f"Error running agent (attempt {attempt}/{max_retries}): {err}",
                streamlit_off=True,
            )

            spinner_placeholder.empty()
            spinner = spinner_placeholder.container()
            spinner.markdown("⚠️ I encountered an error. Retrying…")

            if attempt < max_retries:
                sleep_for = BASE_BACKOFF_SECONDS * (2 ** (attempt - 1))
                time.sleep(sleep_for)
            else:
                spinner_placeholder.empty()
                raise last_err



import asyncio
import threading
import queue

class ChatbotAgent:
    ...
    async def run_agent(self, user_question):
        # your existing async generator – do not change
        ...
        yield {"status": "done", "answer": response}
        return

    # NEW: synchronous wrapper for Streamlit
    def run_agent_sync(self, user_question):
        """
        Synchronous generator wrapper around the async `run_agent`.

        Usage from Streamlit:
            for update in agent.run_agent_sync(user_q):
                ...
        """
        q: "queue.Queue[dict | None]" = queue.Queue()

        async def _producer():
            # Push all async updates into the queue
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

        # Start the async producer in a background thread
        threading.Thread(target=_run_loop, daemon=True).start()

        # Synchronous consumer: yield updates to the caller
        while True:
            update = q.get()
            if update is None:
                break
            yield update
