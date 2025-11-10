import pandas as pd
from llama_index.core.tools import FunctionTool
from llama_index.core.agent import FunctionAgent
from llama_index.core.query_engine import (
    LLMPandasQueryEngine,
    PandasQueryEngine,
    SemanticQueryEngine
)
from app.config.logging import Logger

class PulseAgent:
    def __init__(self, df: pd.DataFrame):
        self.df = df
        self._logger = Logger("PULSE_AGENT")

    # ----------------------------------------------
    # TOOLS (no Context argument in 0.12!)
    # ----------------------------------------------
    def semantic_search_tool(self, df: pd.DataFrame, request: str):
        """Run semantic search on the dataframe."""
        semantic_query_engine = SemanticQueryEngine(df=df, verbose=True)
        result_df = semantic_query_engine.query(request)
        return result_df

    def pandas_filter_tool(self, df: pd.DataFrame, request: str):
        """Run deterministic Pandas filter on the dataframe."""
        pandas_engine = PandasQueryEngine(df=df, verbose=True)
        new_df = pandas_engine.query(request)
        return new_df

    # ----------------------------------------------
    # AGENT SETUP FOR 0.12.x
    # ----------------------------------------------
    def build_agent(self):

        semantic_tool = FunctionTool.from_defaults(
            fn=self.semantic_search_tool,
            name="semantic_search",
            description="Filter articles using semantic search."
        )

        pandas_tool = FunctionTool.from_defaults(
            fn=self.pandas_filter_tool,
            name="pandas_filter",
            description="Filter dataframe deterministically using Pandas syntax."
        )

        agent = FunctionAgent(
            tools=[semantic_tool, pandas_tool],
            system_prompt="You are an article filtering system."
        )

        return agent

    # ----------------------------------------------
    # MAIN ENTRY POINT (filter)
    # ----------------------------------------------
    async def filter(self, query: str) -> pd.DataFrame:
        """Filter articles using agent."""
        self._logger.info(f"Filtering articles for query: {query}")

        agent = self.build_agent()

        # In 0.12, you must pass df manually in kwargs
        response = await agent.arun(
            query,
            df=self.df
        )

        # agent returns actual df or string → guarantee df result
        if isinstance(response, pd.DataFrame):
            return response
        
        # If string returned
        self._logger.warning("Agent returned non-DataFrame output.")
        return self.df
