import pandas as pd

from llama_index.core.tools import FunctionTool
from llama_index.core.agent import FunctionAgent
from llama_index.core.query_engine import (
    LLMPandasQueryEngine,
    PandasQueryEngine,
    SemanticQueryEngine,
)

from app.config.prompts import PULSE_PROMPT
from app.config.logging import Logger


class PulseAgent:
    def __init__(self, df: pd.DataFrame):
        self.df = df
        self._logger = Logger("PULSE_AGENT")

    # =================================================================
    # RECOMMEND METHOD (kept exactly as before)
    # =================================================================
    def recommend(self, user: dict) -> pd.DataFrame:
        self._logger.info(f"Recommending articles for user: {user.get('username')}")

        query_text = f"Regions: {user.get('regions')}"
        semantic_query_engine = SemanticQueryEngine(df=self.df, verbose=True)

        results = semantic_query_engine.query(query_text)

        return results

    # =================================================================
    # TOOL FUNCTIONS
    # =================================================================
    async def semantic_search_tool(self, df: pd.DataFrame, request: str) -> pd.DataFrame:
        """Semantic search over the dataframe."""
        self._logger.info(f"Semantic search: {request}")

        semantic_query_engine = SemanticQueryEngine(df=df, verbose=True)
        result_df = semantic_query_engine.query(request)

        return result_df

    async def pandas_filter_tool(self, df: pd.DataFrame, request: str) -> pd.DataFrame:
        """Deterministic Pandas query."""
        self._logger.info(f"Pandas filter: {request}")

        pandas_engine = PandasQueryEngine(df=df, verbose=True)
        result_df = pandas_engine.query(request)

        return result_df

    async def llm_pandas_filter_tool(self, df: pd.DataFrame, request: str) -> pd.DataFrame:
        """LLM-assisted Pandas reasoning."""
        self._logger.info(f"LLM Pandas filter: {request}")

        llm_pandas_engine = LLMPandasQueryEngine(df=df, verbose=True)
        result_df = llm_pandas_engine.query(request)

        return result_df

    # =================================================================
    # BUILD AGENT (unchanged except removal of initial_state)
    # =================================================================
    def build_agent(self):
        pandas_tool = FunctionTool.from_defaults(
            fn=self.pandas_filter_tool,
            name="pandas_filter",
            description="Filter articles deterministically using Pandas syntax."
        )

        semantic_tool = FunctionTool.from_defaults(
            fn=self.semantic_search_tool,
            name="semantic_search",
            description="Filter articles semantically using embeddings."
        )

        llm_pandas_tool = FunctionTool.from_defaults(
            fn=self.llm_pandas_filter_tool,
            name="llm_pandas_filter",
            description="Use LLM-assisted Pandas filtering."
        )

        agent = FunctionAgent(
            tools=[pandas_tool, semantic_tool, llm_pandas_tool],
            system_prompt=PULSE_PROMPT,
        )

        return agent

    # =================================================================
    # MAIN ENTRY – returns filtered DataFrame (Context removed)
    # =================================================================
    async def filter(self, query: str) -> pd.DataFrame:
        self._logger.info(f"Filtering articles for query: {query}")

        agent = self.build_agent()

        # ✅ Pass state to agent directly since 0.12 has no Context.store
        response = await agent.arun(query, df=self.df)

        # If the selected tool returns a dataframe
        if isinstance(response, pd.DataFrame):
            return response

        # If tool returns something else (string, list, dict, etc.)
        self._logger.warning(
            f"Agent returned non-DataFrame ({type(response)}). Returning original dataframe."
        )
        return self.df

