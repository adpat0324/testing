import pandas as pd

from llama_index.core.tools import FunctionTool
from llama_index.core.workflow import Context
from llama_index.core.agent.workflow import FunctionAgent, ToolCallResult

from llama_index.query_engine import (
    LLMQueryEngine,
    PandasQueryEngine,
    SemanticQueryEngine
)

from app.config.prompts import PULSE_PROMPT
from app.config.logging import Logger


class PulseAgent:
    def __init__(self, df: pd.DataFrame):
        self.df = df
        self.logger = Logger("PULSE_AGENT")

        # manual state object since context.store does not exist in 0.12
        self.state = {"articles": df}

    # -------------------------------------------------------------------------
    # RECOMMEND FUNCTION
    # -------------------------------------------------------------------------
    def recommend(self, user: dict) -> pd.DataFrame:
        self.logger.info(f"Recommending articles for user: {user.get('username')}")

        query_text = f"Regions: {user.get('regions')}"
        semantic_engine = SemanticQueryEngine(df=self.df, verbose=True)

        results = semantic_engine.query(query_text, top_k=5, lambda_=0.01)
        return results

    # -------------------------------------------------------------------------
    # SEMANTIC SEARCH TOOL
    # -------------------------------------------------------------------------
    def semantic_search_tool(self, request: str) -> str:
        df = self.state["articles"]

        semantic_engine = SemanticQueryEngine(df=df, verbose=True)
        new_df = semantic_engine.query(request)

        # update state
        self.state["articles"] = new_df

        return f"Successfully filtered dataframe using semantic query: {request}"

    # -------------------------------------------------------------------------
    # PANDAS FILTER TOOL
    # -------------------------------------------------------------------------
    def pandas_filter_tool(self, request: str) -> str:
        df = self.state["articles"]

        pandas_engine = PandasQueryEngine(df=df, verbose=True)
        new_df = pandas_engine.query(request)

        # update state
        self.state["articles"] = new_df

        return f"Successfully filtered dataframe with pandas query: {request}"

    # -------------------------------------------------------------------------
    # BUILD AGENT
    # -------------------------------------------------------------------------
    def build_agent(self) -> FunctionAgent:
        pandas_tool = FunctionTool.from_defaults(
            fn=self.pandas_filter_tool,
            name="pandas_filter",
            description="Filter articles deterministically using Pandas syntax."
        )

        semantic_tool = FunctionTool.from_defaults(
            fn=self.semantic_search_tool,
            name="semantic_search",
            description="Filter articles semantically."
        )

        # keep original pulse system prompt
        agent = FunctionAgent(
            tools=[pandas_tool, semantic_tool],
            system_prompt=PULSE_PROMPT,
        )

        return agent

    # -------------------------------------------------------------------------
    # FILTER ENTRYPOINT (CALLED BY UI)
    # -------------------------------------------------------------------------
    async def filter(self, query: str) -> pd.DataFrame:
        self.logger.info(f"Filtering articles for query: {query}")

        agent = self.build_agent()
        ctx = Context(agent)

        handler = agent.run(query, ctx=ctx)

        async for ev in handler.stream_events():
            if isinstance(ev, ToolCallResult):
                self.logger.info(
                    f"Call {ev.tool_name} with {ev.tool_kwargs} "
                    f"Returned: {ev.tool_output}",
                    streamlit_off=True
                )

        _response = await handler
        self.logger.info(f"RESPONSE: {_response}", streamlit_off=True)

        # return final DataFrame from manual state
        return self.state["articles"]

