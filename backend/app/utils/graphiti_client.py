"""
Graphiti client factory for MiroFish.

Creates a configured Graphiti instance backed by FalkorDB.
Each caller is responsible for calling graphiti.close() when done.
Call build_indices_and_constraints() once at application startup via run.py.
"""

from graphiti_core import Graphiti
from graphiti_core.driver.falkordb_driver import FalkorDriver
from graphiti_core.embedder.openai import OpenAIEmbedder, OpenAIEmbedderConfig
from graphiti_core.llm_client.openai_client import OpenAIClient, LLMConfig

from ..config import Config
from .logger import get_logger

logger = get_logger('mirofish.graphiti_client')


def create_graphiti_client() -> Graphiti:
    """Creates a configured Graphiti client using FalkorDB backend.

    Returns:
        A Graphiti instance ready for use. The caller must call
        graphiti.close() when done to release the FalkorDB connection.
    """
    driver = FalkorDriver(
        host=Config.FALKORDB_HOST,
        port=Config.FALKORDB_PORT,
        password=Config.FALKORDB_PASSWORD or None,
        database=Config.FALKORDB_DATABASE,
    )

    embedder = OpenAIEmbedder(
        config=OpenAIEmbedderConfig(
            api_key=Config.EMBEDDING_API_KEY,
            base_url=Config.EMBEDDING_BASE_URL,
            embedding_model=Config.EMBEDDING_MODEL,
        )
    )

    llm_client = OpenAIClient(
        config=LLMConfig(
            api_key=Config.LLM_API_KEY,
            base_url=Config.LLM_BASE_URL,
            model=Config.LLM_MODEL_NAME,
        )
    )

    return Graphiti(
        graph_driver=driver,
        embedder=embedder,
        llm_client=llm_client,
    )


async def initialize_graphiti() -> None:
    """Builds FalkorDB indexes and constraints. Call once at app startup."""
    logger.info("Initializing Graphiti indexes and constraints...")
    graphiti = create_graphiti_client()
    try:
        await graphiti.build_indices_and_constraints()
        logger.info("Graphiti initialization complete")
    finally:
        await graphiti.close()
