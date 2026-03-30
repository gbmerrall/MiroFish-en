# Zep → Graphiti + FalkorDB Migration Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace Zep Cloud (SaaS) as the knowledge graph and memory layer with self-hosted Graphiti + FalkorDB, eliminating the external `ZEP_API_KEY` dependency.

**Architecture:** Graphiti (Python library) handles entity extraction from text and semantic graph search; FalkorDB (Redis-based property graph DB, runs locally via Docker) is the backing store. All four Zep-specific backend files are replaced with Graphiti equivalents. Async Graphiti calls are bridged to MiroFish's sync/threaded Flask model using `asyncio.run()` for one-shot callers and a persistent event loop thread for the long-running memory updater.

**Tech Stack:** `graphiti-core[falkordb]` 0.x, FalkorDB 1.1.2+, Python 3.11+, Docker

---

## File Map

**Create:**
- `backend/app/utils/graphiti_client.py` — Graphiti client factory (FalkorDB driver + embedder + LLM config)
- `backend/app/utils/graph_paging.py` — pagination over `get_by_group_ids` (replaces `zep_paging.py`)
- `backend/app/services/graph_entity_reader.py` — node/edge reading and entity filtering (replaces `zep_entity_reader.py`)
- `backend/app/services/graph_memory_updater.py` — simulation activity → Graphiti episodes (replaces `zep_graph_memory_updater.py`)
- `backend/app/services/graph_tools.py` — search tools for ReportAgent (replaces `zep_tools.py`)
- `backend/tests/__init__.py`
- `backend/tests/test_graph_paging.py`
- `backend/tests/test_graph_entity_reader.py`
- `backend/tests/test_graph_memory_updater.py`
- `backend/tests/test_graph_tools.py`
- `backend/tests/test_graph_builder.py`

**Modify:**
- `backend/pyproject.toml` — swap `zep-cloud` → `graphiti-core[falkordb]`
- `backend/app/config.py` — replace `ZEP_API_KEY` with `FALKORDB_*` + `EMBEDDING_*`
- `.env.example` — update vars
- `backend/app/services/graph_builder.py` — replace Zep client with Graphiti
- `backend/app/services/oasis_profile_generator.py` — swap `Zep` + `ZepEntityReader` imports
- `backend/app/services/simulation_manager.py` — swap `ZepEntityReader` import
- `backend/app/services/simulation_config_generator.py` — swap `ZepEntityReader` import
- `backend/app/services/simulation_runner.py` — swap `ZepGraphMemoryManager` import
- `backend/app/services/report_agent.py` — swap `ZepToolsService` import
- `backend/app/services/__init__.py` — update exports
- `backend/app/api/simulation.py` — swap `ZepEntityReader` import
- `backend/app/api/report.py` — swap `ZepToolsService` import
- `backend/run.py` — add startup `build_indices_and_constraints()` call
- `docker-compose.yml` — add FalkorDB service

**Delete (Task 10):**
- `backend/app/utils/zep_paging.py`
- `backend/app/services/zep_entity_reader.py`
- `backend/app/services/zep_graph_memory_updater.py`
- `backend/app/services/zep_tools.py`

---

## Task 1: Dependencies and Configuration

**Files:**
- Modify: `backend/pyproject.toml`
- Modify: `backend/app/config.py`
- Modify: `.env.example`

- [ ] **Step 1: Update pyproject.toml**

In `backend/pyproject.toml`, replace `"zep-cloud==3.13.0"` with:
```toml
"graphiti-core[falkordb]>=0.3.0",
```
Remove the old zep-cloud line entirely.

- [ ] **Step 2: Install new deps**

```bash
cd backend && uv sync
```
Expected: resolves without error, `graphiti-core` and `falkordb` appear in output.

- [ ] **Step 3: Replace config.py Zep section with FalkorDB + Embedding**

Replace the content of `backend/app/config.py` with:

```python
"""
Configuration Management
Loads configurations uniformly from the project root's .env file.
"""

import os
from dotenv import load_dotenv

project_root_env = os.path.join(os.path.dirname(__file__), '../../.env')

if os.path.exists(project_root_env):
    load_dotenv(project_root_env, override=True)
else:
    load_dotenv(override=True)


class Config:
    """Flask Configuration Class"""

    SECRET_KEY = os.environ.get('SECRET_KEY', 'mirofish-secret-key')
    DEBUG = os.environ.get('FLASK_DEBUG', 'True').lower() == 'true'
    JSON_AS_ASCII = False

    # LLM configuration (unified OpenAI format)
    LLM_API_KEY = os.environ.get('LLM_API_KEY')
    LLM_BASE_URL = os.environ.get('LLM_BASE_URL', 'https://api.openai.com/v1')
    LLM_MODEL_NAME = os.environ.get('LLM_MODEL_NAME', 'gpt-4o-mini')

    # FalkorDB configuration
    FALKORDB_HOST = os.environ.get('FALKORDB_HOST', 'localhost')
    FALKORDB_PORT = int(os.environ.get('FALKORDB_PORT', '6379'))
    FALKORDB_PASSWORD = os.environ.get('FALKORDB_PASSWORD', '')
    FALKORDB_DATABASE = os.environ.get('FALKORDB_DATABASE', 'mirofish')

    # Embedding configuration (for Graphiti semantic search)
    # Must point to an OpenAI-compatible /embeddings endpoint.
    # Defaults to OpenAI — change if your LLM provider supports embeddings.
    EMBEDDING_API_KEY = os.environ.get('EMBEDDING_API_KEY') or os.environ.get('LLM_API_KEY')
    EMBEDDING_BASE_URL = os.environ.get('EMBEDDING_BASE_URL', 'https://api.openai.com/v1')
    EMBEDDING_MODEL = os.environ.get('EMBEDDING_MODEL', 'text-embedding-3-small')

    # File upload configuration
    MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 50MB
    UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), '../uploads')
    ALLOWED_EXTENSIONS = {'pdf', 'md', 'txt', 'markdown'}

    # Text processing configuration
    DEFAULT_CHUNK_SIZE = 500
    DEFAULT_CHUNK_OVERLAP = 50

    # OASIS simulation configuration
    OASIS_DEFAULT_MAX_ROUNDS = int(os.environ.get('OASIS_DEFAULT_MAX_ROUNDS', '10'))
    OASIS_SIMULATION_DATA_DIR = os.path.join(os.path.dirname(__file__), '../uploads/simulations')

    OASIS_TWITTER_ACTIONS = [
        'CREATE_POST', 'LIKE_POST', 'REPOST', 'FOLLOW', 'DO_NOTHING', 'QUOTE_POST'
    ]
    OASIS_REDDIT_ACTIONS = [
        'LIKE_POST', 'DISLIKE_POST', 'CREATE_POST', 'CREATE_COMMENT',
        'LIKE_COMMENT', 'DISLIKE_COMMENT', 'SEARCH_POSTS', 'SEARCH_USER',
        'TREND', 'REFRESH', 'DO_NOTHING', 'FOLLOW', 'MUTE'
    ]

    # Report Agent configuration
    REPORT_AGENT_MAX_TOOL_CALLS = int(os.environ.get('REPORT_AGENT_MAX_TOOL_CALLS', '5'))
    REPORT_AGENT_MAX_REFLECTION_ROUNDS = int(os.environ.get('REPORT_AGENT_MAX_REFLECTION_ROUNDS', '2'))
    REPORT_AGENT_TEMPERATURE = float(os.environ.get('REPORT_AGENT_TEMPERATURE', '0.5'))

    @classmethod
    def validate(cls):
        """Validates necessary configurations"""
        errors = []
        if not cls.LLM_API_KEY:
            errors.append("LLM_API_KEY is not configured")
        if not cls.EMBEDDING_API_KEY:
            errors.append("EMBEDDING_API_KEY is not configured (or set LLM_API_KEY)")
        return errors
```

- [ ] **Step 4: Update .env.example**

Replace the `ZEP_API_KEY` section with:
```env
# ===== FalkorDB Graph Database Configuration =====
# Run FalkorDB locally via Docker (see docker-compose.yml)
FALKORDB_HOST=localhost
FALKORDB_PORT=6379
FALKORDB_PASSWORD=
FALKORDB_DATABASE=mirofish

# ===== Embedding API Configuration =====
# Required for Graphiti semantic search. Must be an OpenAI-compatible /embeddings endpoint.
# If your LLM provider supports embeddings, set EMBEDDING_BASE_URL to match.
# Otherwise use OpenAI's API directly (default).
EMBEDDING_API_KEY=your_openai_api_key_here
EMBEDDING_BASE_URL=https://api.openai.com/v1
EMBEDDING_MODEL=text-embedding-3-small
```

- [ ] **Step 5: Commit**

```bash
cd /Users/graeme/Code/MiroFish
git add backend/pyproject.toml backend/app/config.py .env.example
git commit -m "feat: replace Zep config with FalkorDB and Embedding config"
```

---

## Task 2: Graphiti Client Factory

**Files:**
- Create: `backend/app/utils/graphiti_client.py`

- [ ] **Step 1: Create the factory module**

Create `backend/app/utils/graphiti_client.py`:

```python
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
```

> **Note:** If you get `ImportError` on any of the above imports, check the exact import paths with context7 (`/getzep/graphiti` library). The class names are stable but module paths may differ between versions. Common alternatives: `graphiti_core.llm_client.openai` instead of `graphiti_core.llm_client.openai_client`.

- [ ] **Step 2: Update run.py to call initialize_graphiti at startup**

Open `backend/run.py` and replace its content with:

```python
"""
MiroFish Backend Startup Entry
"""

import asyncio
import os
import sys

if sys.platform == 'win32':
    os.environ.setdefault('PYTHONIOENCODING', 'utf-8')
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from app.config import Config


def main():
    """Main function"""
    errors = Config.validate()
    if errors:
        print("Configuration error:")
        for err in errors:
            print(f"  - {err}")
        print("\nPlease check the configuration in the .env file")
        sys.exit(1)

    # Initialize Graphiti indexes in FalkorDB (idempotent, safe to run on every startup)
    from app.utils.graphiti_client import initialize_graphiti
    asyncio.run(initialize_graphiti())

    app = create_app()

    host = os.environ.get('FLASK_HOST', '0.0.0.0')
    port = int(os.environ.get('FLASK_PORT', 5001))
    debug = Config.DEBUG

    app.run(host=host, port=port, debug=debug, threaded=True)


if __name__ == '__main__':
    main()
```

- [ ] **Step 3: Smoke test the factory (requires FalkorDB running)**

If FalkorDB is not running yet, skip this step and return after Task 9.

```bash
cd backend && uv run python -c "
import asyncio
from app.utils.graphiti_client import initialize_graphiti
asyncio.run(initialize_graphiti())
print('OK')
"
```
Expected: `Graphiti initialization complete` then `OK`.

- [ ] **Step 4: Commit**

```bash
git add backend/app/utils/graphiti_client.py backend/run.py
git commit -m "feat: add Graphiti client factory with FalkorDB driver"
```

---

## Task 3: Graph Paging Utilities

Replaces `backend/app/utils/zep_paging.py`.

**Files:**
- Create: `backend/app/utils/graph_paging.py`
- Create: `backend/tests/__init__.py`
- Create: `backend/tests/test_graph_paging.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/__init__.py` (empty).

Create `backend/tests/test_graph_paging.py`:

```python
"""Tests for graph_paging utilities."""

from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from graphiti_core.nodes import EntityNode, EpisodicNode
from graphiti_core.edges import EntityEdge


def _make_node(uuid: str, name: str) -> EntityNode:
    node = MagicMock(spec=EntityNode)
    node.uuid = uuid
    node.name = name
    node.labels = ["Entity"]
    node.summary = ""
    node.attributes = {}
    return node


def _make_edge(uuid: str, source: str, target: str) -> EntityEdge:
    edge = MagicMock(spec=EntityEdge)
    edge.uuid = uuid
    edge.name = "RELATES_TO"
    edge.fact = "test fact"
    edge.source_node_uuid = source
    edge.target_node_uuid = target
    edge.created_at = None
    edge.valid_at = None
    edge.invalid_at = None
    edge.expired_at = None
    return edge


@pytest.mark.asyncio
async def test_fetch_all_nodes_single_page():
    """fetch_all_nodes returns all nodes when result fits in one page."""
    from app.utils.graph_paging import fetch_all_nodes

    nodes = [_make_node(f"uuid-{i}", f"Node{i}") for i in range(3)]
    graphiti = MagicMock()
    graphiti._driver = MagicMock()
    graphiti._driver.entity_node = MagicMock()
    graphiti._driver.entity_node.get_by_group_ids = AsyncMock(return_value=nodes)

    result = await fetch_all_nodes(graphiti, "group-1")

    assert len(result) == 3
    graphiti._driver.entity_node.get_by_group_ids.assert_called_once_with(
        ["group-1"], limit=100, uuid_cursor=None
    )


@pytest.mark.asyncio
async def test_fetch_all_nodes_paginates():
    """fetch_all_nodes follows cursor pagination across multiple pages."""
    from app.utils.graph_paging import fetch_all_nodes

    page1 = [_make_node(f"uuid-{i}", f"Node{i}") for i in range(100)]
    page2 = [_make_node(f"uuid-{i+100}", f"Node{i+100}") for i in range(5)]

    call_count = 0

    async def mock_get(group_ids, limit, uuid_cursor):
        nonlocal call_count
        call_count += 1
        if uuid_cursor is None:
            return page1
        return page2

    graphiti = MagicMock()
    graphiti._driver = MagicMock()
    graphiti._driver.entity_node = MagicMock()
    graphiti._driver.entity_node.get_by_group_ids = mock_get

    result = await fetch_all_nodes(graphiti, "group-1")

    assert len(result) == 105
    assert call_count == 2


@pytest.mark.asyncio
async def test_fetch_all_edges_single_page():
    """fetch_all_edges returns all edges when result fits in one page."""
    from app.utils.graph_paging import fetch_all_edges

    edges = [_make_edge(f"e-{i}", f"src-{i}", f"tgt-{i}") for i in range(3)]
    graphiti = MagicMock()
    graphiti._driver = MagicMock()
    graphiti._driver.entity_edge = MagicMock()
    graphiti._driver.entity_edge.get_by_group_ids = AsyncMock(return_value=edges)

    result = await fetch_all_edges(graphiti, "group-1")

    assert len(result) == 3
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd backend && uv run pytest tests/test_graph_paging.py -v
```
Expected: `ImportError: cannot import name 'fetch_all_nodes' from 'app.utils.graph_paging'` (module not yet created).

- [ ] **Step 3: Implement graph_paging.py**

Create `backend/app/utils/graph_paging.py`:

```python
"""Graph pagination utilities for Graphiti + FalkorDB.

Encapsulates cursor-based pagination over entity nodes and edges,
returning the complete list transparently to the caller.
"""

from __future__ import annotations

from typing import Any

from graphiti_core import Graphiti

from .logger import get_logger

logger = get_logger('mirofish.graph_paging')

_DEFAULT_PAGE_SIZE = 100
_MAX_NODES = 2000


async def fetch_all_nodes(
    graphiti: Graphiti,
    group_id: str,
    page_size: int = _DEFAULT_PAGE_SIZE,
    max_items: int = _MAX_NODES,
) -> list[Any]:
    """Fetches all entity nodes for a group with cursor pagination.

    Args:
        graphiti: Graphiti client instance.
        group_id: The graph namespace (maps to Zep's graph_id).
        page_size: Results per page.
        max_items: Hard cap on total items returned.

    Returns:
        List of EntityNode objects.
    """
    all_nodes: list[Any] = []
    cursor: str | None = None
    page_num = 0

    while True:
        page_num += 1
        batch = await graphiti._driver.entity_node.get_by_group_ids(
            [group_id], limit=page_size, uuid_cursor=cursor
        )

        if not batch:
            break

        all_nodes.extend(batch)

        if len(all_nodes) >= max_items:
            all_nodes = all_nodes[:max_items]
            logger.warning(
                f"Node count reached limit ({max_items}), stopping pagination for group {group_id}"
            )
            break

        if len(batch) < page_size:
            break

        cursor = getattr(batch[-1], 'uuid', None)
        if cursor is None:
            logger.warning(f"Node missing uuid field, stopping pagination at {len(all_nodes)} nodes")
            break

    logger.debug(f"fetch_all_nodes: {len(all_nodes)} nodes retrieved for group {group_id}")
    return all_nodes


async def fetch_all_edges(
    graphiti: Graphiti,
    group_id: str,
    page_size: int = _DEFAULT_PAGE_SIZE,
) -> list[Any]:
    """Fetches all entity edges for a group with cursor pagination.

    Args:
        graphiti: Graphiti client instance.
        group_id: The graph namespace.
        page_size: Results per page.

    Returns:
        List of EntityEdge objects.
    """
    all_edges: list[Any] = []
    cursor: str | None = None
    page_num = 0

    while True:
        page_num += 1
        batch = await graphiti._driver.entity_edge.get_by_group_ids(
            [group_id], limit=page_size, uuid_cursor=cursor
        )

        if not batch:
            break

        all_edges.extend(batch)

        if len(batch) < page_size:
            break

        cursor = getattr(batch[-1], 'uuid', None)
        if cursor is None:
            logger.warning(f"Edge missing uuid field, stopping pagination at {len(all_edges)} edges")
            break

    logger.debug(f"fetch_all_edges: {len(all_edges)} edges retrieved for group {group_id}")
    return all_edges
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
cd backend && uv run pytest tests/test_graph_paging.py -v
```
Expected: 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/utils/graph_paging.py backend/tests/
git commit -m "feat: add graph_paging utilities using Graphiti driver API"
```

---

## Task 4: Graph Entity Reader

Replaces `backend/app/services/zep_entity_reader.py`.

**Files:**
- Create: `backend/app/services/graph_entity_reader.py`
- Create: `backend/tests/test_graph_entity_reader.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_graph_entity_reader.py`:

```python
"""Tests for GraphEntityReader."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import pytest


def _make_node(uuid: str, name: str, labels: list[str]) -> MagicMock:
    node = MagicMock()
    node.uuid = uuid
    node.name = name
    node.labels = labels
    node.summary = f"Summary of {name}"
    node.attributes = {}
    return node


def _make_edge(uuid: str, src: str, tgt: str, name: str = "RELATES_TO") -> MagicMock:
    edge = MagicMock()
    edge.uuid = uuid
    edge.name = name
    edge.fact = f"fact about {uuid}"
    edge.source_node_uuid = src
    edge.target_node_uuid = tgt
    edge.attributes = {}
    return edge


def test_filter_defined_entities_keeps_typed_nodes():
    """filter_defined_entities keeps nodes with custom labels, drops pure Entity nodes."""
    from app.services.graph_entity_reader import GraphEntityReader

    nodes = [
        _make_node("n1", "Alice", ["Entity", "Person"]),
        _make_node("n2", "Acme", ["Entity"]),  # should be dropped
        _make_node("n3", "Bob", ["Entity", "Person"]),
    ]
    edges = []

    reader = GraphEntityReader.__new__(GraphEntityReader)

    with patch("app.services.graph_entity_reader.asyncio") as mock_asyncio:
        mock_asyncio.run.side_effect = lambda coro: asyncio.get_event_loop().run_until_complete(coro)

        with patch("app.services.graph_entity_reader.fetch_all_nodes", new=AsyncMock(return_value=nodes)):
            with patch("app.services.graph_entity_reader.fetch_all_edges", new=AsyncMock(return_value=edges)):
                with patch("app.services.graph_entity_reader.create_graphiti_client"):
                    result = reader.filter_defined_entities("group-1")

    assert result.filtered_count == 2
    assert result.total_count == 3
    assert "Person" in result.entity_types
    names = {e.name for e in result.entities}
    assert names == {"Alice", "Bob"}


def test_get_all_nodes_returns_dicts():
    """get_all_nodes returns list of dicts with expected keys."""
    from app.services.graph_entity_reader import GraphEntityReader

    nodes = [_make_node("n1", "Alice", ["Entity", "Person"])]

    reader = GraphEntityReader.__new__(GraphEntityReader)

    with patch("app.services.graph_entity_reader.fetch_all_nodes", new=AsyncMock(return_value=nodes)):
        with patch("app.services.graph_entity_reader.create_graphiti_client"):
            result = reader.get_all_nodes("group-1")

    assert len(result) == 1
    assert result[0]["uuid"] == "n1"
    assert result[0]["name"] == "Alice"
    assert "labels" in result[0]
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd backend && uv run pytest tests/test_graph_entity_reader.py -v
```
Expected: `ImportError` — module not yet created.

- [ ] **Step 3: Implement graph_entity_reader.py**

Create `backend/app/services/graph_entity_reader.py`:

```python
"""
Graph Entity Reading and Filtering Service.
Reads nodes/edges from the Graphiti knowledge graph and filters by entity type.
Replaces zep_entity_reader.py.
"""

import asyncio
from dataclasses import dataclass, field
from typing import Any, Optional

from graphiti_core import Graphiti

from ..utils.graphiti_client import create_graphiti_client
from ..utils.graph_paging import fetch_all_nodes, fetch_all_edges
from ..utils.logger import get_logger

logger = get_logger('mirofish.graph_entity_reader')


@dataclass
class EntityNode:
    """Entity node data structure."""
    uuid: str
    name: str
    labels: list[str]
    summary: str
    attributes: dict[str, Any]
    related_edges: list[dict[str, Any]] = field(default_factory=list)
    related_nodes: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "uuid": self.uuid,
            "name": self.name,
            "labels": self.labels,
            "summary": self.summary,
            "attributes": self.attributes,
            "related_edges": self.related_edges,
            "related_nodes": self.related_nodes,
        }

    def get_entity_type(self) -> Optional[str]:
        """Returns the first non-default label, or None."""
        for label in self.labels:
            if label not in ("Entity", "Node"):
                return label
        return None


@dataclass
class FilteredEntities:
    """Filtered entity set result."""
    entities: list[EntityNode]
    entity_types: set[str]
    total_count: int
    filtered_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "entities": [e.to_dict() for e in self.entities],
            "entity_types": list(self.entity_types),
            "total_count": self.total_count,
            "filtered_count": self.filtered_count,
        }


class GraphEntityReader:
    """
    Reads and filters entities from the Graphiti knowledge graph.

    Each public method creates a short-lived Graphiti connection, performs
    the operation, and closes the connection. Safe to call from Flask request
    handlers (no running event loop assumed).
    """

    def get_all_nodes(self, group_id: str) -> list[dict[str, Any]]:
        """Returns all nodes for the group as plain dicts."""
        return asyncio.run(self._async_get_all_nodes(group_id))

    async def _async_get_all_nodes(self, group_id: str) -> list[dict[str, Any]]:
        graphiti = create_graphiti_client()
        try:
            nodes = await fetch_all_nodes(graphiti, group_id)
            return [
                {
                    "uuid": node.uuid,
                    "name": node.name or "",
                    "labels": node.labels or [],
                    "summary": node.summary or "",
                    "attributes": node.attributes or {},
                }
                for node in nodes
            ]
        finally:
            await graphiti.close()

    def get_all_edges(self, group_id: str) -> list[dict[str, Any]]:
        """Returns all edges for the group as plain dicts."""
        return asyncio.run(self._async_get_all_edges(group_id))

    async def _async_get_all_edges(self, group_id: str) -> list[dict[str, Any]]:
        graphiti = create_graphiti_client()
        try:
            edges = await fetch_all_edges(graphiti, group_id)
            return [
                {
                    "uuid": edge.uuid,
                    "name": edge.name or "",
                    "fact": edge.fact or "",
                    "source_node_uuid": edge.source_node_uuid or "",
                    "target_node_uuid": edge.target_node_uuid or "",
                    "attributes": edge.attributes or {},
                }
                for edge in edges
            ]
        finally:
            await graphiti.close()

    def get_node_edges(self, node_uuid: str) -> list[dict[str, Any]]:
        """Returns all edges connected to a given node UUID."""
        # Graphiti does not have a direct per-node edge lookup without group context.
        # Callers that need this should use filter_defined_entities or get_all_edges.
        logger.warning(
            "get_node_edges called without group_id — this is a no-op in the Graphiti backend. "
            "Use get_all_edges(group_id) and filter client-side."
        )
        return []

    def filter_defined_entities(
        self,
        group_id: str,
        defined_entity_types: Optional[list[str]] = None,
        enrich_with_edges: bool = True,
    ) -> FilteredEntities:
        """Filters nodes to those with custom entity type labels.

        Nodes whose Labels only contain 'Entity' or 'Node' are dropped.
        If defined_entity_types is provided, only those types are kept.
        """
        return asyncio.run(
            self._async_filter_entities(group_id, defined_entity_types, enrich_with_edges)
        )

    async def _async_filter_entities(
        self,
        group_id: str,
        defined_entity_types: Optional[list[str]],
        enrich_with_edges: bool,
    ) -> FilteredEntities:
        graphiti = create_graphiti_client()
        try:
            raw_nodes = await fetch_all_nodes(graphiti, group_id)
            raw_edges = await fetch_all_edges(graphiti, group_id) if enrich_with_edges else []
        finally:
            await graphiti.close()

        all_nodes = [
            {
                "uuid": n.uuid,
                "name": n.name or "",
                "labels": n.labels or [],
                "summary": n.summary or "",
                "attributes": n.attributes or {},
            }
            for n in raw_nodes
        ]

        all_edges = [
            {
                "uuid": e.uuid,
                "name": e.name or "",
                "fact": e.fact or "",
                "source_node_uuid": e.source_node_uuid or "",
                "target_node_uuid": e.target_node_uuid or "",
            }
            for e in raw_edges
        ]

        node_map = {n["uuid"]: n for n in all_nodes}
        total_count = len(all_nodes)
        filtered_entities = []
        entity_types_found: set[str] = set()

        for node in all_nodes:
            custom_labels = [l for l in node["labels"] if l not in ("Entity", "Node")]
            if not custom_labels:
                continue

            if defined_entity_types:
                matching = [l for l in custom_labels if l in defined_entity_types]
                if not matching:
                    continue
                entity_type = matching[0]
            else:
                entity_type = custom_labels[0]

            entity_types_found.add(entity_type)

            entity = EntityNode(
                uuid=node["uuid"],
                name=node["name"],
                labels=node["labels"],
                summary=node["summary"],
                attributes=node["attributes"],
            )

            if enrich_with_edges:
                related_edges = []
                related_node_uuids: set[str] = set()

                for edge in all_edges:
                    if edge["source_node_uuid"] == node["uuid"]:
                        related_edges.append({
                            "direction": "outgoing",
                            "edge_name": edge["name"],
                            "fact": edge["fact"],
                            "target_node_uuid": edge["target_node_uuid"],
                        })
                        related_node_uuids.add(edge["target_node_uuid"])
                    elif edge["target_node_uuid"] == node["uuid"]:
                        related_edges.append({
                            "direction": "incoming",
                            "edge_name": edge["name"],
                            "fact": edge["fact"],
                            "source_node_uuid": edge["source_node_uuid"],
                        })
                        related_node_uuids.add(edge["source_node_uuid"])

                entity.related_edges = related_edges
                entity.related_nodes = [
                    {
                        "uuid": node_map[uid]["uuid"],
                        "name": node_map[uid]["name"],
                        "labels": node_map[uid]["labels"],
                        "summary": node_map[uid].get("summary", ""),
                    }
                    for uid in related_node_uuids
                    if uid in node_map
                ]

            filtered_entities.append(entity)

        logger.info(
            f"filter_defined_entities: {total_count} total, {len(filtered_entities)} matched, "
            f"types={entity_types_found}"
        )
        return FilteredEntities(
            entities=filtered_entities,
            entity_types=entity_types_found,
            total_count=total_count,
            filtered_count=len(filtered_entities),
        )

    def get_entity_with_context(
        self, group_id: str, entity_uuid: str
    ) -> Optional[EntityNode]:
        """Returns a single entity enriched with its connected edges and nodes."""
        result = self.filter_defined_entities(group_id, enrich_with_edges=True)
        for entity in result.entities:
            if entity.uuid == entity_uuid:
                return entity
        return None

    def get_entities_by_type(
        self,
        group_id: str,
        entity_type: str,
        enrich_with_edges: bool = True,
    ) -> list[EntityNode]:
        """Returns all entities of the specified type."""
        result = self.filter_defined_entities(
            group_id, defined_entity_types=[entity_type], enrich_with_edges=enrich_with_edges
        )
        return result.entities


# Alias for backward compatibility within services/__init__.py
ZepEntityReader = GraphEntityReader
```

- [ ] **Step 4: Run tests**

```bash
cd backend && uv run pytest tests/test_graph_entity_reader.py -v
```
Expected: 2 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/graph_entity_reader.py backend/tests/test_graph_entity_reader.py
git commit -m "feat: add GraphEntityReader backed by Graphiti+FalkorDB"
```

---

## Task 5: Graph Memory Updater

Replaces `backend/app/services/zep_graph_memory_updater.py`.

**Files:**
- Create: `backend/app/services/graph_memory_updater.py`
- Create: `backend/tests/test_graph_memory_updater.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_graph_memory_updater.py`:

```python
"""Tests for GraphMemoryUpdater."""

import time
from unittest.mock import AsyncMock, MagicMock, patch
import pytest


def test_agent_activity_to_episode_text_create_post():
    """AgentActivity formats CREATE_POST correctly."""
    from app.services.graph_memory_updater import AgentActivity

    activity = AgentActivity(
        platform="twitter",
        agent_id=1,
        agent_name="Alice",
        action_type="CREATE_POST",
        action_args={"content": "Hello world"},
        round_num=1,
        timestamp="2024-01-01T00:00:00",
    )
    text = activity.to_episode_text()
    assert text == 'Alice: posted: "Hello world"'


def test_agent_activity_skips_do_nothing():
    """add_activity skips DO_NOTHING actions and increments skipped count."""
    from app.services.graph_memory_updater import GraphMemoryUpdater

    with patch("app.services.graph_memory_updater.create_graphiti_client"):
        with patch("app.services.graph_memory_updater.asyncio"):
            updater = GraphMemoryUpdater.__new__(GraphMemoryUpdater)
            updater._skipped_count = 0
            updater._total_activities = 0
            updater._activity_queue = MagicMock()
            updater._activity_queue.put = MagicMock()

    from app.services.graph_memory_updater import AgentActivity
    activity = AgentActivity(
        platform="twitter", agent_id=1, agent_name="Bob",
        action_type="DO_NOTHING", action_args={}, round_num=1, timestamp="",
    )

    updater.add_activity(activity)

    updater._activity_queue.put.assert_not_called()
    assert updater._skipped_count == 1


def test_graph_memory_manager_creates_and_retrieves_updater():
    """GraphMemoryManager create_updater stores and get_updater retrieves it."""
    from app.services.graph_memory_updater import GraphMemoryManager

    # Reset class state between tests
    GraphMemoryManager._updaters.clear()
    GraphMemoryManager._stop_all_done = False

    mock_updater = MagicMock()
    mock_updater.stop = MagicMock()

    with patch("app.services.graph_memory_updater.GraphMemoryUpdater", return_value=mock_updater):
        mock_updater.start = MagicMock()
        result = GraphMemoryManager.create_updater("sim-1", "group-abc")

    assert GraphMemoryManager.get_updater("sim-1") is mock_updater
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd backend && uv run pytest tests/test_graph_memory_updater.py -v
```
Expected: `ImportError`.

- [ ] **Step 3: Implement graph_memory_updater.py**

Create `backend/app/services/graph_memory_updater.py`:

```python
"""
Graph Memory Updater Service.
Monitors simulation agent activities and writes them to Graphiti as episodes.
Replaces zep_graph_memory_updater.py.

Threading model: GraphMemoryUpdater owns a dedicated asyncio event loop thread.
All Graphiti async calls are submitted to that loop via run_coroutine_threadsafe().
"""

import asyncio
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from queue import Empty, Queue
from typing import Any, Optional

from graphiti_core.nodes import EpisodeType

from ..config import Config
from ..utils.graphiti_client import create_graphiti_client
from ..utils.logger import get_logger

logger = get_logger('mirofish.graph_memory_updater')


@dataclass
class AgentActivity:
    """Agent activity record. Produces natural-language episode text for Graphiti."""
    platform: str
    agent_id: int
    agent_name: str
    action_type: str
    action_args: dict[str, Any]
    round_num: int
    timestamp: str

    def to_episode_text(self) -> str:
        """Converts activity to natural language for Graphiti entity extraction."""
        handlers = {
            "CREATE_POST": self._describe_create_post,
            "LIKE_POST": self._describe_like_post,
            "DISLIKE_POST": self._describe_dislike_post,
            "REPOST": self._describe_repost,
            "QUOTE_POST": self._describe_quote_post,
            "FOLLOW": self._describe_follow,
            "CREATE_COMMENT": self._describe_create_comment,
            "LIKE_COMMENT": self._describe_like_comment,
            "DISLIKE_COMMENT": self._describe_dislike_comment,
            "SEARCH_POSTS": self._describe_search,
            "SEARCH_USER": self._describe_search_user,
            "MUTE": self._describe_mute,
        }
        describe = handlers.get(self.action_type, self._describe_generic)
        return f"{self.agent_name}: {describe()}"

    def _describe_create_post(self) -> str:
        content = self.action_args.get("content", "")
        return f'posted: "{content}"' if content else "posted"

    def _describe_like_post(self) -> str:
        content = self.action_args.get("post_content", "")
        author = self.action_args.get("post_author_name", "")
        if content and author:
            return f'liked {author}\'s post: "{content}"'
        elif content:
            return f'liked a post: "{content}"'
        elif author:
            return f"liked a post by {author}"
        return "liked a post"

    def _describe_dislike_post(self) -> str:
        content = self.action_args.get("post_content", "")
        author = self.action_args.get("post_author_name", "")
        if content and author:
            return f'disliked {author}\'s post: "{content}"'
        elif content:
            return f'disliked a post: "{content}"'
        elif author:
            return f"disliked a post by {author}"
        return "disliked a post"

    def _describe_repost(self) -> str:
        content = self.action_args.get("original_content", "")
        author = self.action_args.get("original_author_name", "")
        if content and author:
            return f'reposted {author}\'s post: "{content}"'
        elif content:
            return f'reposted a post: "{content}"'
        elif author:
            return f"reposted a post by {author}"
        return "reposted a post"

    def _describe_quote_post(self) -> str:
        content = self.action_args.get("original_content", "")
        author = self.action_args.get("original_author_name", "")
        quote = self.action_args.get("quote_content", "") or self.action_args.get("content", "")
        if content and author:
            base = f'quoted {author}\'s post "{content}"'
        elif content:
            base = f'quoted a post "{content}"'
        elif author:
            base = f"quoted a post by {author}"
        else:
            base = "quoted a post"
        return f'{base} and commented: "{quote}"' if quote else base

    def _describe_follow(self) -> str:
        target = self.action_args.get("target_user_name", "")
        return f'followed user "{target}"' if target else "followed a user"

    def _describe_create_comment(self) -> str:
        content = self.action_args.get("content", "")
        post_content = self.action_args.get("post_content", "")
        post_author = self.action_args.get("post_author_name", "")
        if content:
            if post_content and post_author:
                return f'commented on {post_author}\'s post "{post_content}": "{content}"'
            elif post_content:
                return f'commented on the post "{post_content}": "{content}"'
            elif post_author:
                return f'commented on {post_author}\'s post: "{content}"'
            return f'commented: "{content}"'
        return "created a comment"

    def _describe_like_comment(self) -> str:
        content = self.action_args.get("comment_content", "")
        author = self.action_args.get("comment_author_name", "")
        if content and author:
            return f'liked {author}\'s comment: "{content}"'
        elif content:
            return f'liked a comment: "{content}"'
        elif author:
            return f"liked a comment by {author}"
        return "liked a comment"

    def _describe_dislike_comment(self) -> str:
        content = self.action_args.get("comment_content", "")
        author = self.action_args.get("comment_author_name", "")
        if content and author:
            return f'disliked {author}\'s comment: "{content}"'
        elif content:
            return f'disliked a comment: "{content}"'
        elif author:
            return f"disliked a comment by {author}"
        return "disliked a comment"

    def _describe_search(self) -> str:
        q = self.action_args.get("query", "") or self.action_args.get("keyword", "")
        return f'searched for "{q}"' if q else "performed a search"

    def _describe_search_user(self) -> str:
        q = self.action_args.get("query", "") or self.action_args.get("username", "")
        return f'searched for user "{q}"' if q else "searched for a user"

    def _describe_mute(self) -> str:
        target = self.action_args.get("target_user_name", "")
        return f'muted user "{target}"' if target else "muted a user"

    def _describe_generic(self) -> str:
        return f"performed a {self.action_type} action"


PLATFORM_DISPLAY_NAMES = {"twitter": "World 1", "reddit": "World 2"}


class GraphMemoryUpdater:
    """
    Writes batched agent activities to Graphiti as text episodes.

    Owns a dedicated asyncio event loop running in a background thread.
    Graphiti async calls are submitted to that loop via run_coroutine_threadsafe().
    """

    BATCH_SIZE = 5
    SEND_INTERVAL = 0.5
    MAX_RETRIES = 3
    RETRY_DELAY = 2

    def __init__(self, group_id: str):
        self.group_id = group_id

        # Persistent event loop for all async Graphiti calls
        self._loop = asyncio.new_event_loop()
        self._loop_thread = threading.Thread(
            target=self._loop.run_forever,
            daemon=True,
            name=f"GraphMemUpdater-{group_id[:8]}",
        )
        self._loop_thread.start()

        self._activity_queue: Queue = Queue()
        self._platform_buffers: dict[str, list[AgentActivity]] = {
            "twitter": [], "reddit": []
        }
        self._buffer_lock = threading.Lock()
        self._running = False
        self._worker_thread: Optional[threading.Thread] = None

        self._total_activities = 0
        self._total_sent = 0
        self._total_items_sent = 0
        self._failed_count = 0
        self._skipped_count = 0

        logger.info(f"GraphMemoryUpdater initialized: group_id={group_id}")

    def _run_async(self, coro, timeout: float = 60.0):
        """Submit a coroutine to the updater's event loop and wait for result."""
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return future.result(timeout=timeout)

    def start(self):
        """Starts the background worker thread."""
        if self._running:
            return
        self._running = True
        self._worker_thread = threading.Thread(
            target=self._worker_loop,
            daemon=True,
            name=f"GraphMemUpdater-worker-{self.group_id[:8]}",
        )
        self._worker_thread.start()
        logger.info(f"GraphMemoryUpdater started: group_id={self.group_id}")

    def stop(self):
        """Stops the worker and flushes remaining activities."""
        self._running = False
        self._flush_remaining()
        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=10)
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._loop_thread.join(timeout=5)
        logger.info(
            f"GraphMemoryUpdater stopped: group_id={self.group_id}, "
            f"total_activities={self._total_activities}, "
            f"batches_sent={self._total_sent}, items_sent={self._total_items_sent}, "
            f"failed={self._failed_count}, skipped={self._skipped_count}"
        )

    def add_activity(self, activity: AgentActivity):
        """Enqueues an agent activity (DO_NOTHING is silently dropped)."""
        if activity.action_type == "DO_NOTHING":
            self._skipped_count += 1
            return
        self._activity_queue.put(activity)
        self._total_activities += 1

    def add_activity_from_dict(self, data: dict[str, Any], platform: str):
        """Constructs and enqueues an AgentActivity from a raw action dict."""
        if "event_type" in data:
            return
        activity = AgentActivity(
            platform=platform,
            agent_id=data.get("agent_id", 0),
            agent_name=data.get("agent_name", ""),
            action_type=data.get("action_type", ""),
            action_args=data.get("action_args", {}),
            round_num=data.get("round", 0),
            timestamp=data.get("timestamp", datetime.now().isoformat()),
        )
        self.add_activity(activity)

    def _worker_loop(self):
        """Drains the activity queue, batching by platform."""
        while self._running or not self._activity_queue.empty():
            try:
                try:
                    activity = self._activity_queue.get(timeout=1)
                    platform = activity.platform.lower()
                    with self._buffer_lock:
                        if platform not in self._platform_buffers:
                            self._platform_buffers[platform] = []
                        self._platform_buffers[platform].append(activity)
                        if len(self._platform_buffers[platform]) >= self.BATCH_SIZE:
                            batch = self._platform_buffers[platform][:self.BATCH_SIZE]
                            self._platform_buffers[platform] = self._platform_buffers[platform][self.BATCH_SIZE:]
                            self._send_batch(batch, platform)
                            time.sleep(self.SEND_INTERVAL)
                except Empty:
                    pass
            except Exception as e:
                logger.error(f"Worker loop exception: {e}")
                time.sleep(1)

    def _send_batch(self, activities: list[AgentActivity], platform: str):
        """Writes a batch of activities to Graphiti as a single text episode."""
        if not activities:
            return

        combined_text = "\n".join(a.to_episode_text() for a in activities)
        display_name = PLATFORM_DISPLAY_NAMES.get(platform, platform)

        for attempt in range(self.MAX_RETRIES):
            try:
                self._run_async(self._async_add_episode(combined_text, platform))
                self._total_sent += 1
                self._total_items_sent += len(activities)
                logger.info(
                    f"Sent {len(activities)} {display_name} activities to graph {self.group_id}"
                )
                return
            except Exception as e:
                if attempt < self.MAX_RETRIES - 1:
                    logger.warning(f"Batch send attempt {attempt+1} failed: {e}")
                    time.sleep(self.RETRY_DELAY * (attempt + 1))
                else:
                    logger.error(f"Batch send failed after {self.MAX_RETRIES} retries: {e}")
                    self._failed_count += 1

    async def _async_add_episode(self, text: str, platform: str):
        graphiti = create_graphiti_client()
        try:
            await graphiti.add_episode(
                name=f"sim-{platform}-{int(time.time())}",
                episode_body=text,
                source=EpisodeType.text,
                source_description=f"MiroFish simulation activity ({platform})",
                reference_time=datetime.now(timezone.utc),
                group_id=self.group_id,
            )
        finally:
            await graphiti.close()

    def _flush_remaining(self):
        """Drains the queue and sends all remaining buffered activities."""
        while not self._activity_queue.empty():
            try:
                activity = self._activity_queue.get_nowait()
                platform = activity.platform.lower()
                with self._buffer_lock:
                    self._platform_buffers.setdefault(platform, []).append(activity)
            except Empty:
                break

        with self._buffer_lock:
            for platform, buffer in self._platform_buffers.items():
                if buffer:
                    logger.info(f"Flushing {len(buffer)} remaining {platform} activities")
                    self._send_batch(buffer, platform)
            for platform in self._platform_buffers:
                self._platform_buffers[platform] = []

    def get_stats(self) -> dict[str, Any]:
        with self._buffer_lock:
            buffer_sizes = {p: len(b) for p, b in self._platform_buffers.items()}
        return {
            "group_id": self.group_id,
            "batch_size": self.BATCH_SIZE,
            "total_activities": self._total_activities,
            "batches_sent": self._total_sent,
            "items_sent": self._total_items_sent,
            "failed_count": self._failed_count,
            "skipped_count": self._skipped_count,
            "queue_size": self._activity_queue.qsize(),
            "buffer_sizes": buffer_sizes,
            "running": self._running,
        }


class GraphMemoryManager:
    """Manages GraphMemoryUpdater instances per simulation."""

    _updaters: dict[str, GraphMemoryUpdater] = {}
    _lock = threading.Lock()
    _stop_all_done = False

    @classmethod
    def create_updater(cls, simulation_id: str, group_id: str) -> GraphMemoryUpdater:
        """Creates (or replaces) the updater for a simulation."""
        with cls._lock:
            if simulation_id in cls._updaters:
                cls._updaters[simulation_id].stop()
            updater = GraphMemoryUpdater(group_id)
            updater.start()
            cls._updaters[simulation_id] = updater
            logger.info(f"Created GraphMemoryUpdater: simulation_id={simulation_id}, group_id={group_id}")
            return updater

    @classmethod
    def get_updater(cls, simulation_id: str) -> Optional[GraphMemoryUpdater]:
        return cls._updaters.get(simulation_id)

    @classmethod
    def stop_updater(cls, simulation_id: str):
        with cls._lock:
            if simulation_id in cls._updaters:
                cls._updaters[simulation_id].stop()
                del cls._updaters[simulation_id]
                logger.info(f"Stopped GraphMemoryUpdater: simulation_id={simulation_id}")

    @classmethod
    def stop_all(cls):
        if cls._stop_all_done:
            return
        cls._stop_all_done = True
        with cls._lock:
            for sim_id, updater in list(cls._updaters.items()):
                try:
                    updater.stop()
                except Exception as e:
                    logger.error(f"Failed to stop updater {sim_id}: {e}")
            cls._updaters.clear()
        logger.info("Stopped all GraphMemoryUpdaters")

    @classmethod
    def get_all_stats(cls) -> dict[str, dict[str, Any]]:
        return {sid: u.get_stats() for sid, u in cls._updaters.items()}


# Aliases for backward compatibility
ZepGraphMemoryUpdater = GraphMemoryUpdater
ZepGraphMemoryManager = GraphMemoryManager
```

- [ ] **Step 4: Run tests**

```bash
cd backend && uv run pytest tests/test_graph_memory_updater.py -v
```
Expected: 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/graph_memory_updater.py backend/tests/test_graph_memory_updater.py
git commit -m "feat: add GraphMemoryUpdater backed by Graphiti episodes"
```

---

## Task 6: Graph Tools Service

Replaces `backend/app/services/zep_tools.py`.

**Files:**
- Create: `backend/app/services/graph_tools.py`
- Create: `backend/tests/test_graph_tools.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_graph_tools.py`:

```python
"""Tests for GraphToolsService."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import pytest


def _make_edge(uuid, fact, src="s1", tgt="t1", name="RELATES"):
    e = MagicMock()
    e.uuid = uuid
    e.name = name
    e.fact = fact
    e.source_node_uuid = src
    e.target_node_uuid = tgt
    e.created_at = None
    e.valid_at = None
    e.invalid_at = None
    e.expired_at = None
    return e


def _make_node(uuid, name, labels=None):
    n = MagicMock()
    n.uuid = uuid
    n.name = name
    n.labels = labels or ["Entity"]
    n.summary = f"Summary of {name}"
    n.attributes = {}
    return n


@pytest.fixture()
def mock_graphiti():
    graphiti = MagicMock()
    graphiti.close = AsyncMock()
    graphiti.search = AsyncMock(return_value=MagicMock(edges=[], nodes=[]))
    return graphiti


def test_search_graph_returns_facts(mock_graphiti):
    """search_graph extracts facts from edge search results."""
    from app.services.graph_tools import GraphToolsService

    edge = _make_edge("e1", "Alice knows Bob")
    mock_graphiti.search = AsyncMock(
        return_value=MagicMock(edges=[edge], nodes=[])
    )

    with patch("app.services.graph_tools.create_graphiti_client", return_value=mock_graphiti):
        svc = GraphToolsService()
        result = svc.search_graph("group-1", "Alice")

    assert "Alice knows Bob" in result.facts
    assert result.total_count == 1


def test_get_graph_statistics_counts_entity_types(mock_graphiti):
    """get_graph_statistics counts entity type distribution correctly."""
    from app.services.graph_tools import GraphToolsService

    nodes = [
        _make_node("n1", "Alice", ["Entity", "Person"]),
        _make_node("n2", "Bob", ["Entity", "Person"]),
        _make_node("n3", "Acme", ["Entity", "Organization"]),
    ]
    edges = [_make_edge("e1", "fact")]

    with patch("app.services.graph_tools.fetch_all_nodes", new=AsyncMock(return_value=nodes)):
        with patch("app.services.graph_tools.fetch_all_edges", new=AsyncMock(return_value=edges)):
            with patch("app.services.graph_tools.create_graphiti_client", return_value=mock_graphiti):
                svc = GraphToolsService()
                stats = svc.get_graph_statistics("group-1")

    assert stats["entity_types"]["Person"] == 2
    assert stats["entity_types"]["Organization"] == 1
    assert stats["total_nodes"] == 3


def test_quick_search_delegates_to_search_graph(mock_graphiti):
    """quick_search calls search_graph and returns same result."""
    from app.services.graph_tools import GraphToolsService

    with patch("app.services.graph_tools.create_graphiti_client", return_value=mock_graphiti):
        svc = GraphToolsService()
        with patch.object(svc, "search_graph") as mock_search:
            mock_search.return_value = MagicMock(total_count=3)
            result = svc.quick_search("group-1", "test query", limit=5)

    mock_search.assert_called_once_with("group-1", "test query", limit=5, scope="edges")
    assert result.total_count == 3
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd backend && uv run pytest tests/test_graph_tools.py -v
```
Expected: `ImportError`.

- [ ] **Step 3: Implement graph_tools.py**

Create `backend/app/services/graph_tools.py`:

```python
"""
Graph Tools Service for the Report Agent.
Provides search, node/edge retrieval, and insight generation over the Graphiti knowledge graph.
Replaces zep_tools.py.
"""

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from graphiti_core import Graphiti

from ..utils.graphiti_client import create_graphiti_client
from ..utils.graph_paging import fetch_all_nodes, fetch_all_edges
from ..utils.llm_client import LLMClient
from ..utils.logger import get_logger

logger = get_logger('mirofish.graph_tools')


@dataclass
class SearchResult:
    facts: list[str]
    edges: list[dict[str, Any]]
    nodes: list[dict[str, Any]]
    query: str
    total_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "facts": self.facts, "edges": self.edges,
            "nodes": self.nodes, "query": self.query, "total_count": self.total_count,
        }

    def to_text(self) -> str:
        parts = [f"Search Query: {self.query}", f"Found {self.total_count} relevant pieces of information"]
        if self.facts:
            parts.append("\n### Related Facts:")
            parts.extend(f"{i}. {f}" for i, f in enumerate(self.facts, 1))
        return "\n".join(parts)


@dataclass
class NodeInfo:
    uuid: str
    name: str
    labels: list[str]
    summary: str
    attributes: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {"uuid": self.uuid, "name": self.name, "labels": self.labels,
                "summary": self.summary, "attributes": self.attributes}

    def to_text(self) -> str:
        entity_type = next((l for l in self.labels if l not in ("Entity", "Node")), "Unknown")
        return f"Entity: {self.name} (Type: {entity_type})\nSummary: {self.summary}"


@dataclass
class EdgeInfo:
    uuid: str
    name: str
    fact: str
    source_node_uuid: str
    target_node_uuid: str
    created_at: Any = None
    valid_at: Any = None
    invalid_at: Any = None
    expired_at: Any = None

    @property
    def is_expired(self) -> bool:
        return bool(self.expired_at)

    @property
    def is_invalid(self) -> bool:
        return bool(self.invalid_at)

    def to_dict(self) -> dict[str, Any]:
        return {
            "uuid": self.uuid, "name": self.name, "fact": self.fact,
            "source_node_uuid": self.source_node_uuid,
            "target_node_uuid": self.target_node_uuid,
            "created_at": str(self.created_at) if self.created_at else None,
            "valid_at": str(self.valid_at) if self.valid_at else None,
            "invalid_at": str(self.invalid_at) if self.invalid_at else None,
            "expired_at": str(self.expired_at) if self.expired_at else None,
        }


@dataclass
class InsightForgeResult:
    query: str
    simulation_requirement: str
    sub_queries: list[str]
    semantic_facts: list[str] = field(default_factory=list)
    entity_insights: list[dict[str, Any]] = field(default_factory=list)
    relationship_chains: list[str] = field(default_factory=list)

    def to_text(self) -> str:
        parts = [f"Deep Insight for: {self.query}",
                 f"Sub-questions explored: {len(self.sub_queries)}",
                 f"Facts retrieved: {len(self.semantic_facts)}"]
        if self.semantic_facts:
            parts.append("\n### Key Facts:")
            parts.extend(f"- {f}" for f in self.semantic_facts[:20])
        return "\n".join(parts)


@dataclass
class PanoramaResult:
    query: str
    all_nodes: list[NodeInfo] = field(default_factory=list)
    all_edges: list[EdgeInfo] = field(default_factory=list)
    active_facts: list[str] = field(default_factory=list)
    historical_facts: list[str] = field(default_factory=list)
    total_nodes: int = 0
    total_edges: int = 0
    active_count: int = 0
    historical_count: int = 0

    def to_text(self) -> str:
        parts = [
            f"Panorama Search: {self.query}",
            f"Graph: {self.total_nodes} nodes, {self.total_edges} edges",
            f"Active facts: {self.active_count}, Historical: {self.historical_count}",
        ]
        if self.active_facts:
            parts.append("\n### Active Facts:")
            parts.extend(f"- {f}" for f in self.active_facts[:20])
        return "\n".join(parts)


@dataclass
class InterviewResult:
    interview_requirement: str
    agents_interviewed: list[str] = field(default_factory=list)
    interview_records: list[dict[str, Any]] = field(default_factory=list)
    summary: str = ""

    def to_text(self) -> str:
        return (
            f"Interview Requirement: {self.interview_requirement}\n"
            f"Agents interviewed: {', '.join(self.agents_interviewed)}\n"
            f"Summary: {self.summary}"
        )


class GraphToolsService:
    """
    Search and retrieval tools for the Report Agent.

    Public methods are synchronous (safe to call from Flask handlers).
    Each method creates a short-lived Graphiti connection via asyncio.run().
    """

    MAX_RETRIES = 3
    RETRY_DELAY = 2.0

    def __init__(self, llm_client: Optional[LLMClient] = None):
        self._llm_client = llm_client
        logger.info("GraphToolsService initialized")

    @property
    def llm(self) -> LLMClient:
        if self._llm_client is None:
            self._llm_client = LLMClient()
        return self._llm_client

    # ---- Low-level node/edge access ----

    def get_all_nodes(self, group_id: str) -> list[NodeInfo]:
        return asyncio.run(self._async_get_all_nodes(group_id))

    async def _async_get_all_nodes(self, group_id: str) -> list[NodeInfo]:
        graphiti = create_graphiti_client()
        try:
            raw = await fetch_all_nodes(graphiti, group_id)
            return [
                NodeInfo(
                    uuid=n.uuid or "",
                    name=n.name or "",
                    labels=n.labels or [],
                    summary=n.summary or "",
                    attributes=n.attributes or {},
                )
                for n in raw
            ]
        finally:
            await graphiti.close()

    def get_all_edges(self, group_id: str, include_temporal: bool = True) -> list[EdgeInfo]:
        return asyncio.run(self._async_get_all_edges(group_id))

    async def _async_get_all_edges(self, group_id: str) -> list[EdgeInfo]:
        graphiti = create_graphiti_client()
        try:
            raw = await fetch_all_edges(graphiti, group_id)
            return [
                EdgeInfo(
                    uuid=e.uuid or "",
                    name=e.name or "",
                    fact=e.fact or "",
                    source_node_uuid=e.source_node_uuid or "",
                    target_node_uuid=e.target_node_uuid or "",
                    created_at=getattr(e, 'created_at', None),
                    valid_at=getattr(e, 'valid_at', None),
                    invalid_at=getattr(e, 'invalid_at', None),
                    expired_at=getattr(e, 'expired_at', None),
                )
                for e in raw
            ]
        finally:
            await graphiti.close()

    # ---- Search ----

    def search_graph(
        self, group_id: str, query: str, limit: int = 10, scope: str = "edges"
    ) -> SearchResult:
        """Semantic search over the knowledge graph using Graphiti's hybrid search."""
        logger.info(f"Graph search: group_id={group_id}, query={query[:50]}...")
        return asyncio.run(self._async_search_graph(group_id, query, limit, scope))

    async def _async_search_graph(
        self, group_id: str, query: str, limit: int, scope: str
    ) -> SearchResult:
        graphiti = create_graphiti_client()
        try:
            results = await graphiti.search(
                query=query,
                group_ids=[group_id],
                num_results=limit,
            )
        except Exception as e:
            logger.warning(f"Graphiti search failed, falling back to local search: {e}")
            await graphiti.close()
            return self._local_search_sync(group_id, query, limit, scope)
        finally:
            await graphiti.close()

        facts = []
        edges = []
        nodes = []

        for edge in getattr(results, 'edges', []) or []:
            if edge.fact:
                facts.append(edge.fact)
            edges.append({
                "uuid": edge.uuid or "",
                "name": edge.name or "",
                "fact": edge.fact or "",
                "source_node_uuid": edge.source_node_uuid or "",
                "target_node_uuid": edge.target_node_uuid or "",
            })

        for node in getattr(results, 'nodes', []) or []:
            nodes.append({
                "uuid": node.uuid or "",
                "name": node.name or "",
                "labels": node.labels or [],
                "summary": node.summary or "",
            })
            if node.summary:
                facts.append(f"[{node.name}]: {node.summary}")

        logger.info(f"Search found {len(facts)} facts")
        return SearchResult(facts=facts, edges=edges, nodes=nodes, query=query, total_count=len(facts))

    def _local_search_sync(
        self, group_id: str, query: str, limit: int, scope: str
    ) -> SearchResult:
        """Keyword fallback when Graphiti search is unavailable."""
        logger.info(f"Using local keyword search: query={query[:30]}...")
        all_edges = self.get_all_edges(group_id)
        all_nodes = self.get_all_nodes(group_id)

        query_lower = query.lower()
        keywords = [w for w in query_lower.replace(',', ' ').split() if len(w) > 1]

        def score(text: str) -> int:
            if not text:
                return 0
            t = text.lower()
            if query_lower in t:
                return 100
            return sum(10 for k in keywords if k in t)

        facts, edges_result, nodes_result = [], [], []

        if scope in ("edges", "both"):
            scored = sorted(
                ((score(e.fact) + score(e.name), e) for e in all_edges),
                key=lambda x: x[0], reverse=True
            )
            for s, edge in scored[:limit]:
                if s > 0:
                    if edge.fact:
                        facts.append(edge.fact)
                    edges_result.append(edge.to_dict())

        if scope in ("nodes", "both"):
            scored = sorted(
                ((score(n.name) + score(n.summary), n) for n in all_nodes),
                key=lambda x: x[0], reverse=True
            )
            for s, node in scored[:limit]:
                if s > 0:
                    nodes_result.append(node.to_dict())
                    if node.summary:
                        facts.append(f"[{node.name}]: {node.summary}")

        return SearchResult(facts=facts, edges=edges_result, nodes=nodes_result,
                            query=query, total_count=len(facts))

    # ---- Higher-level tools ----

    def get_node_detail(self, node_uuid: str) -> Optional[NodeInfo]:
        return asyncio.run(self._async_get_node_detail(node_uuid))

    async def _async_get_node_detail(self, node_uuid: str) -> Optional[NodeInfo]:
        graphiti = create_graphiti_client()
        try:
            node = await graphiti._driver.entity_node.get_by_uuid(node_uuid)
            if not node:
                return None
            return NodeInfo(
                uuid=node.uuid or "",
                name=node.name or "",
                labels=node.labels or [],
                summary=node.summary or "",
                attributes=node.attributes or {},
            )
        except Exception as e:
            logger.error(f"Failed to get node {node_uuid}: {e}")
            return None
        finally:
            await graphiti.close()

    def get_node_edges(self, group_id: str, node_uuid: str) -> list[EdgeInfo]:
        all_edges = self.get_all_edges(group_id)
        return [e for e in all_edges
                if e.source_node_uuid == node_uuid or e.target_node_uuid == node_uuid]

    def get_entities_by_type(self, group_id: str, entity_type: str) -> list[NodeInfo]:
        return [n for n in self.get_all_nodes(group_id) if entity_type in n.labels]

    def get_entity_summary(self, group_id: str, entity_name: str) -> dict[str, Any]:
        search_result = self.search_graph(group_id, entity_name, limit=20)
        all_nodes = self.get_all_nodes(group_id)
        entity_node = next((n for n in all_nodes if n.name.lower() == entity_name.lower()), None)
        related_edges = self.get_node_edges(group_id, entity_node.uuid) if entity_node else []
        return {
            "entity_name": entity_name,
            "entity_info": entity_node.to_dict() if entity_node else None,
            "related_facts": search_result.facts,
            "related_edges": [e.to_dict() for e in related_edges],
            "total_relations": len(related_edges),
        }

    def get_graph_statistics(self, group_id: str) -> dict[str, Any]:
        nodes = self.get_all_nodes(group_id)
        edges = self.get_all_edges(group_id)
        entity_types: dict[str, int] = {}
        for node in nodes:
            for label in node.labels:
                if label not in ("Entity", "Node"):
                    entity_types[label] = entity_types.get(label, 0) + 1
        relation_types: dict[str, int] = {}
        for edge in edges:
            relation_types[edge.name] = relation_types.get(edge.name, 0) + 1
        return {
            "group_id": group_id,
            "total_nodes": len(nodes),
            "total_edges": len(edges),
            "entity_types": entity_types,
            "relation_types": relation_types,
        }

    def get_simulation_context(
        self, group_id: str, simulation_requirement: str, limit: int = 30
    ) -> dict[str, Any]:
        search_result = self.search_graph(group_id, simulation_requirement, limit=limit)
        stats = self.get_graph_statistics(group_id)
        all_nodes = self.get_all_nodes(group_id)
        entities = [
            {"name": n.name, "type": next((l for l in n.labels if l not in ("Entity", "Node")), ""), "summary": n.summary}
            for n in all_nodes
            if any(l not in ("Entity", "Node") for l in n.labels)
        ]
        return {
            "simulation_requirement": simulation_requirement,
            "related_facts": search_result.facts,
            "graph_statistics": stats,
            "entities": entities[:limit],
            "total_entities": len(entities),
        }

    def insight_forge(
        self, group_id: str, query: str, simulation_requirement: str,
        report_context: str = "", max_sub_queries: int = 5,
    ) -> InsightForgeResult:
        """Deep multi-angle retrieval using LLM-generated sub-questions."""
        logger.info(f"InsightForge: {query[:50]}...")
        result = InsightForgeResult(query=query, simulation_requirement=simulation_requirement, sub_queries=[])

        sub_queries = self._generate_sub_queries(query, simulation_requirement, report_context, max_sub_queries)
        result.sub_queries = sub_queries

        all_facts: list[str] = []
        seen: set[str] = set()

        for sq in sub_queries:
            for fact in self.search_graph(group_id, sq, limit=15, scope="edges").facts:
                if fact not in seen:
                    all_facts.append(fact)
                    seen.add(fact)

        for fact in self.search_graph(group_id, query, limit=20, scope="edges").facts:
            if fact not in seen:
                all_facts.append(fact)
                seen.add(fact)

        result.semantic_facts = all_facts

        # Entity enrichment
        all_nodes = self.get_all_nodes(group_id)
        node_map = {n.name.lower(): n for n in all_nodes}
        mentioned_entities = []
        for fact in all_facts[:30]:
            for name, node in node_map.items():
                if name in fact.lower() and node not in mentioned_entities:
                    mentioned_entities.append(node)
                    if len(mentioned_entities) >= 10:
                        break

        result.entity_insights = [
            {"name": n.name, "type": n.get_entity_type(), "summary": n.summary}
            for n in mentioned_entities
        ]

        logger.info(f"InsightForge complete: {len(all_facts)} facts, {len(mentioned_entities)} entities")
        return result

    def panorama_search(
        self, group_id: str, query: str, include_expired: bool = True, limit: int = 50,
    ) -> PanoramaResult:
        """Breadth-first view: all nodes and edges including historical/expired."""
        logger.info(f"PanoramaSearch: {query[:50]}...")
        result = PanoramaResult(query=query)

        all_nodes = self.get_all_nodes(group_id)
        all_edges = self.get_all_edges(group_id, include_temporal=True)
        node_map = {n.uuid: n for n in all_nodes}

        result.all_nodes = all_nodes
        result.all_edges = all_edges
        result.total_nodes = len(all_nodes)
        result.total_edges = len(all_edges)

        active_facts, historical_facts = [], []
        for edge in all_edges:
            if not edge.fact:
                continue
            if edge.is_expired or edge.is_invalid:
                ts = f"[{edge.valid_at or 'Unknown'} - {edge.invalid_at or edge.expired_at or 'Unknown'}]"
                historical_facts.append(f"{ts} {edge.fact}")
            else:
                active_facts.append(edge.fact)

        query_lower = query.lower()
        keywords = [w for w in query_lower.replace(',', ' ').split() if len(w) > 1]

        def relevance(fact: str) -> int:
            fl = fact.lower()
            return 100 if query_lower in fl else sum(10 for k in keywords if k in fl)

        active_facts.sort(key=relevance, reverse=True)
        historical_facts.sort(key=relevance, reverse=True)

        result.active_facts = active_facts[:limit]
        result.historical_facts = historical_facts[:limit] if include_expired else []
        result.active_count = len(active_facts)
        result.historical_count = len(historical_facts)

        logger.info(f"PanoramaSearch: {result.active_count} active, {result.historical_count} historical")
        return result

    def quick_search(self, group_id: str, query: str, limit: int = 10) -> SearchResult:
        """Simple semantic search — direct wrapper around search_graph."""
        return self.search_graph(group_id, query, limit=limit, scope="edges")

    def interview_agents(
        self, simulation_id: str, interview_requirement: str,
        simulation_requirement: str = "", max_agents: int = 5,
        custom_questions: Optional[list[str]] = None,
    ) -> InterviewResult:
        """Interviews running OASIS agents. Delegates to the simulation API."""
        # This method talks to the OASIS simulation directly (not to the graph).
        # The logic is unchanged from zep_tools.py — only the class it lives in changed.
        from .simulation_runner import SimulationRunner
        result = InterviewResult(interview_requirement=interview_requirement)

        profiles = self._load_agent_profiles(simulation_id)
        if not profiles:
            result.summary = "No agent profiles found for this simulation."
            return result

        selected = self._select_agents_for_interview(profiles, interview_requirement, max_agents)
        questions = custom_questions or self._generate_interview_questions(
            interview_requirement, selected, simulation_requirement
        )

        interview_records = []
        for agent in selected:
            agent_name = agent.get("name", "Unknown")
            try:
                runner = SimulationRunner.get_runner(simulation_id)
                if runner:
                    responses = runner.interview_agent(agent.get("agent_id"), questions)
                    interview_records.append({
                        "agent_name": agent_name,
                        "questions": questions,
                        "responses": responses,
                    })
            except Exception as e:
                logger.warning(f"Failed to interview agent {agent_name}: {e}")

        result.agents_interviewed = [a.get("name", "") for a in selected]
        result.interview_records = interview_records
        result.summary = self._generate_interview_summary(interview_requirement, interview_records)
        return result

    def _generate_sub_queries(
        self, query: str, simulation_requirement: str, report_context: str, max_queries: int
    ) -> list[str]:
        prompt = (
            f"Decompose the following question into {max_queries} focused sub-questions "
            f"for searching a knowledge graph.\n\n"
            f"Simulation context: {simulation_requirement}\n"
            f"Report context: {report_context[:300] if report_context else 'N/A'}\n"
            f"Main question: {query}\n\n"
            f"Return only the sub-questions, one per line, no numbering."
        )
        try:
            response = self.llm.chat(prompt)
            lines = [l.strip() for l in response.strip().split('\n') if l.strip()]
            return lines[:max_queries]
        except Exception as e:
            logger.warning(f"Sub-query generation failed: {e}")
            return [query]

    def _load_agent_profiles(self, simulation_id: str) -> list[dict[str, Any]]:
        import json
        import os
        from ..config import Config
        profiles_path = os.path.join(
            Config.OASIS_SIMULATION_DATA_DIR, simulation_id, "agent_profiles.json"
        )
        if not os.path.exists(profiles_path):
            return []
        try:
            with open(profiles_path, encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Failed to load agent profiles: {e}")
            return []

    def _select_agents_for_interview(
        self, profiles: list[dict], requirement: str, max_agents: int
    ) -> list[dict]:
        if len(profiles) <= max_agents:
            return profiles
        prompt = (
            f"Select the {max_agents} most relevant agents for this interview requirement:\n"
            f"{requirement}\n\nAgents:\n"
            + "\n".join(f"- {p.get('name', '')} ({p.get('role', '')})" for p in profiles)
            + f"\n\nReturn only the names, one per line."
        )
        try:
            response = self.llm.chat(prompt)
            selected_names = {l.strip().lower() for l in response.strip().split('\n') if l.strip()}
            return [p for p in profiles if p.get('name', '').lower() in selected_names][:max_agents]
        except Exception:
            return profiles[:max_agents]

    def _generate_interview_questions(
        self, requirement: str, agents: list[dict], simulation_req: str
    ) -> list[str]:
        prompt = (
            f"Generate 3 interview questions for agents in a simulation.\n"
            f"Simulation requirement: {simulation_req}\n"
            f"Interview requirement: {requirement}\n"
            f"Return only the questions, one per line."
        )
        try:
            response = self.llm.chat(prompt)
            return [l.strip() for l in response.strip().split('\n') if l.strip()][:3]
        except Exception:
            return [requirement]

    def _generate_interview_summary(
        self, requirement: str, records: list[dict[str, Any]]
    ) -> str:
        if not records:
            return "No interviews conducted."
        combined = "\n\n".join(
            f"Agent: {r['agent_name']}\n" + "\n".join(
                f"Q: {q}\nA: {a}" for q, a in zip(r.get('questions', []), r.get('responses', []))
            )
            for r in records
        )
        prompt = (
            f"Summarize these agent interviews in 2-3 paragraphs.\n"
            f"Interview requirement: {requirement}\n\n{combined[:3000]}"
        )
        try:
            return self.llm.chat(prompt)
        except Exception:
            return f"Interviewed {len(records)} agents regarding: {requirement}"


# Alias for backward compatibility
ZepToolsService = GraphToolsService
```

- [ ] **Step 4: Run tests**

```bash
cd backend && uv run pytest tests/test_graph_tools.py -v
```
Expected: 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/graph_tools.py backend/tests/test_graph_tools.py
git commit -m "feat: add GraphToolsService backed by Graphiti search"
```

---

## Task 7: Rewrite graph_builder.py

**Files:**
- Modify: `backend/app/services/graph_builder.py`
- Create: `backend/tests/test_graph_builder.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_graph_builder.py`:

```python
"""Tests for GraphBuilderService with Graphiti backend."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import pytest


def test_create_graph_returns_valid_group_id():
    """create_graph returns a non-empty group_id string starting with 'mirofish_'."""
    from app.services.graph_builder import GraphBuilderService

    with patch("app.services.graph_builder.create_graphiti_client"):
        svc = GraphBuilderService.__new__(GraphBuilderService)
        from app.models.task import TaskManager
        svc.task_manager = TaskManager()

    group_id = svc.create_graph("Test Graph")
    assert group_id.startswith("mirofish_")
    assert len(group_id) > 10


def test_delete_graph_calls_driver_delete(mock_graphiti=None):
    """delete_graph calls delete_by_group_id on all three namespaces."""
    from app.services.graph_builder import GraphBuilderService

    graphiti = MagicMock()
    graphiti.close = AsyncMock()
    graphiti._driver = MagicMock()
    graphiti._driver.entity_node = MagicMock()
    graphiti._driver.entity_node.delete_by_group_id = AsyncMock()
    graphiti._driver.entity_edge = MagicMock()
    graphiti._driver.entity_edge.delete_by_group_id = AsyncMock()
    graphiti._driver.episodic_node = MagicMock()
    graphiti._driver.episodic_node.delete_by_group_id = AsyncMock()

    with patch("app.services.graph_builder.create_graphiti_client", return_value=graphiti):
        svc = GraphBuilderService.__new__(GraphBuilderService)
        from app.models.task import TaskManager
        svc.task_manager = TaskManager()
        svc.delete_graph("group-xyz")

    graphiti._driver.entity_node.delete_by_group_id.assert_called_once_with("group-xyz")
    graphiti._driver.entity_edge.delete_by_group_id.assert_called_once_with("group-xyz")
    graphiti._driver.episodic_node.delete_by_group_id.assert_called_once_with("group-xyz")
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd backend && uv run pytest tests/test_graph_builder.py -v
```
Expected: FAIL — `GraphBuilderService` still imports from zep_cloud.

- [ ] **Step 3: Rewrite graph_builder.py**

Replace the entire content of `backend/app/services/graph_builder.py`:

```python
"""
Graph Building Service.
Builds knowledge graphs from text documents using Graphiti + FalkorDB.
Replaces the Zep Cloud implementation.
"""

import asyncio
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from graphiti_core.nodes import EpisodeType, RawEpisode

from ..utils.graphiti_client import create_graphiti_client
from ..utils.graph_paging import fetch_all_nodes, fetch_all_edges
from ..config import Config
from ..models.task import TaskManager, TaskStatus
from ..utils.logger import get_logger
from .text_processor import TextProcessor

logger = get_logger('mirofish.graph_builder')


@dataclass
class GraphInfo:
    """Graph information summary."""
    graph_id: str
    node_count: int
    edge_count: int
    entity_types: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "graph_id": self.graph_id,
            "node_count": self.node_count,
            "edge_count": self.edge_count,
            "entity_types": self.entity_types,
        }


class GraphBuilderService:
    """
    Builds a Graphiti knowledge graph from a text document.

    Workflow:
    1. create_graph() — generates a group_id (no API call needed)
    2. set_ontology() — converts ontology dict to Pydantic entity types; stored locally
    3. add_text_batches() — calls graphiti.add_episode_bulk() with chunked text
    4. get_graph_data() / delete_graph() — read/delete by group_id
    """

    def __init__(self):
        self.task_manager = TaskManager()
        self._entity_types: dict[str, type] = {}

    def build_graph_async(
        self,
        text: str,
        ontology: dict[str, Any],
        graph_name: str = "MiroFish Graph",
        chunk_size: int = 500,
        chunk_overlap: int = 50,
        batch_size: int = 3,
    ) -> str:
        """Starts async graph building and returns a task_id for polling."""
        task_id = self.task_manager.create_task(
            task_type="graph_build",
            metadata={
                "graph_name": graph_name,
                "chunk_size": chunk_size,
                "text_length": len(text),
            },
        )
        thread = threading.Thread(
            target=self._build_graph_worker,
            args=(task_id, text, ontology, graph_name, chunk_size, chunk_overlap, batch_size),
            daemon=True,
        )
        thread.start()
        return task_id

    def _build_graph_worker(
        self, task_id: str, text: str, ontology: dict[str, Any],
        graph_name: str, chunk_size: int, chunk_overlap: int, batch_size: int,
    ):
        """Worker thread: runs the full async build inside a dedicated event loop."""
        asyncio.run(
            self._async_build(task_id, text, ontology, graph_name, chunk_size, chunk_overlap, batch_size)
        )

    async def _async_build(
        self, task_id: str, text: str, ontology: dict[str, Any],
        graph_name: str, chunk_size: int, chunk_overlap: int, batch_size: int,
    ):
        try:
            self.task_manager.update_task(task_id, status=TaskStatus.PROCESSING, progress=5,
                                          message="Starting graph build...")

            group_id = self.create_graph(graph_name)
            self.task_manager.update_task(task_id, progress=10, message=f"Graph ID: {group_id}")

            entity_types = self._build_entity_types(ontology)
            self.task_manager.update_task(task_id, progress=15, message="Ontology prepared")

            chunks = TextProcessor.split_text(text, chunk_size, chunk_overlap)
            total_chunks = len(chunks)
            self.task_manager.update_task(task_id, progress=20,
                                          message=f"Text split into {total_chunks} chunks")

            def on_progress(msg: str, prog: float):
                self.task_manager.update_task(task_id, progress=20 + int(prog * 60), message=msg)

            graphiti = create_graphiti_client()
            try:
                await self._add_episodes(graphiti, group_id, chunks, entity_types, on_progress)
            finally:
                await graphiti.close()

            self.task_manager.update_task(task_id, progress=85, message="Retrieving graph info...")
            graph_info = await self._get_graph_info_async(group_id)

            self.task_manager.complete_task(task_id, {
                "graph_id": group_id,
                "graph_info": graph_info.to_dict(),
                "chunks_processed": total_chunks,
            })

        except Exception as e:
            import traceback
            self.task_manager.fail_task(task_id, f"{e}\n{traceback.format_exc()}")

    async def _add_episodes(
        self, graphiti, group_id: str, chunks: list[str],
        entity_types: dict[str, type], progress_callback: Optional[Callable],
    ):
        """Adds text chunks to Graphiti as bulk episodes."""
        total = len(chunks)
        bulk_episodes = [
            RawEpisode(
                name=f"chunk_{i}",
                content=chunk,
                source=EpisodeType.text,
                source_description="MiroFish document content",
                reference_time=datetime.now(timezone.utc),
            )
            for i, chunk in enumerate(chunks)
        ]

        # Process in batches to allow progress reporting
        batch_size = 5
        for start in range(0, total, batch_size):
            batch = bulk_episodes[start:start + batch_size]
            await graphiti.add_episode_bulk(batch)
            if progress_callback:
                progress = (start + len(batch)) / total
                progress_callback(
                    f"Processed {start + len(batch)}/{total} chunks", progress
                )

    # ---- Public helpers ----

    def create_graph(self, name: str) -> str:
        """Returns a new group_id. No API call needed — Graphiti uses group_id implicitly."""
        return f"mirofish_{uuid.uuid4().hex[:16]}"

    def set_ontology(self, group_id: str, ontology: dict[str, Any]):
        """Converts ontology dict to Pydantic entity types. Stored locally for add_episode calls."""
        self._entity_types = self._build_entity_types(ontology)
        logger.info(f"Ontology prepared: {list(self._entity_types.keys())}")

    def _build_entity_types(self, ontology: dict[str, Any]) -> dict[str, type]:
        """Converts ontology entity definitions to Pydantic BaseModel subclasses."""
        from pydantic import BaseModel, Field
        from typing import Optional as Opt

        RESERVED = {'uuid', 'name', 'group_id', 'name_embedding', 'summary', 'created_at'}
        entity_types = {}

        for entity_def in ontology.get("entity_types", []):
            name = entity_def["name"]
            description = entity_def.get("description", f"A {name} entity.")
            attrs: dict[str, Any] = {"__doc__": description}
            annotations: dict[str, Any] = {}

            for attr_def in entity_def.get("attributes", []):
                attr_name = attr_def["name"]
                if attr_name.lower() in RESERVED:
                    attr_name = f"entity_{attr_name}"
                attr_desc = attr_def.get("description", attr_name)
                attrs[attr_name] = Field(description=attr_desc, default=None)
                annotations[attr_name] = Opt[str]

            attrs["__annotations__"] = annotations
            entity_class = type(name, (BaseModel,), attrs)
            entity_class.__doc__ = description
            entity_types[name] = entity_class

        return entity_types

    def add_text_batches(
        self, group_id: str, chunks: list[str], batch_size: int = 3,
        progress_callback: Optional[Callable] = None,
    ) -> list[str]:
        """Public method for incremental text ingestion. Returns empty list (no episode UUIDs needed)."""
        asyncio.run(
            self._add_episodes_simple(group_id, chunks, progress_callback)
        )
        return []

    async def _add_episodes_simple(
        self, group_id: str, chunks: list[str], progress_callback: Optional[Callable]
    ):
        graphiti = create_graphiti_client()
        try:
            await self._add_episodes(graphiti, group_id, chunks, self._entity_types, progress_callback)
        finally:
            await graphiti.close()

    def get_graph_data(self, group_id: str) -> dict[str, Any]:
        """Returns full graph data as dicts for frontend visualization."""
        return asyncio.run(self._async_get_graph_data(group_id))

    async def _async_get_graph_data(self, group_id: str) -> dict[str, Any]:
        graphiti = create_graphiti_client()
        try:
            nodes = await fetch_all_nodes(graphiti, group_id)
            edges = await fetch_all_edges(graphiti, group_id)
        finally:
            await graphiti.close()

        node_map = {n.uuid: n.name or "" for n in nodes}

        nodes_data = [
            {
                "uuid": n.uuid,
                "name": n.name or "",
                "labels": n.labels or [],
                "summary": n.summary or "",
                "attributes": n.attributes or {},
                "created_at": str(n.created_at) if getattr(n, 'created_at', None) else None,
            }
            for n in nodes
        ]

        edges_data = [
            {
                "uuid": e.uuid,
                "name": e.name or "",
                "fact": e.fact or "",
                "fact_type": e.name or "",
                "source_node_uuid": e.source_node_uuid or "",
                "target_node_uuid": e.target_node_uuid or "",
                "source_node_name": node_map.get(e.source_node_uuid, ""),
                "target_node_name": node_map.get(e.target_node_uuid, ""),
                "attributes": e.attributes if hasattr(e, 'attributes') else {},
                "created_at": str(e.created_at) if getattr(e, 'created_at', None) else None,
                "valid_at": str(e.valid_at) if getattr(e, 'valid_at', None) else None,
                "invalid_at": str(e.invalid_at) if getattr(e, 'invalid_at', None) else None,
                "expired_at": str(e.expired_at) if getattr(e, 'expired_at', None) else None,
                "episodes": [],
            }
            for e in edges
        ]

        return {
            "graph_id": group_id,
            "nodes": nodes_data,
            "edges": edges_data,
            "node_count": len(nodes_data),
            "edge_count": len(edges_data),
        }

    def delete_graph(self, group_id: str):
        """Deletes all nodes, edges, and episodic nodes for the group."""
        asyncio.run(self._async_delete_graph(group_id))

    async def _async_delete_graph(self, group_id: str):
        graphiti = create_graphiti_client()
        try:
            await graphiti._driver.entity_node.delete_by_group_id(group_id)
            await graphiti._driver.entity_edge.delete_by_group_id(group_id)
            await graphiti._driver.episodic_node.delete_by_group_id(group_id)
            logger.info(f"Deleted graph: group_id={group_id}")
        finally:
            await graphiti.close()

    async def _get_graph_info_async(self, group_id: str) -> GraphInfo:
        graphiti = create_graphiti_client()
        try:
            nodes = await fetch_all_nodes(graphiti, group_id)
            edges = await fetch_all_edges(graphiti, group_id)
        finally:
            await graphiti.close()

        entity_types = set()
        for node in nodes:
            for label in (node.labels or []):
                if label not in ("Entity", "Node"):
                    entity_types.add(label)

        return GraphInfo(
            graph_id=group_id,
            node_count=len(nodes),
            edge_count=len(edges),
            entity_types=list(entity_types),
        )
```

- [ ] **Step 4: Run tests**

```bash
cd backend && uv run pytest tests/test_graph_builder.py -v
```
Expected: 2 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/graph_builder.py backend/tests/test_graph_builder.py
git commit -m "feat: rewrite graph_builder to use Graphiti+FalkorDB"
```

---

## Task 8: Update Import Sites

Update all files that still reference `zep_*` classes.

**Files:**
- Modify: `backend/app/services/__init__.py`
- Modify: `backend/app/services/simulation_runner.py`
- Modify: `backend/app/services/simulation_manager.py`
- Modify: `backend/app/services/simulation_config_generator.py`
- Modify: `backend/app/services/oasis_profile_generator.py`
- Modify: `backend/app/services/report_agent.py`
- Modify: `backend/app/api/simulation.py`
- Modify: `backend/app/api/report.py`

- [ ] **Step 1: Update services/__init__.py**

In `backend/app/services/__init__.py`, replace the two Zep import blocks:

```python
# Replace this:
from .zep_entity_reader import ZepEntityReader, EntityNode, FilteredEntities
# ...
from .zep_graph_memory_updater import (
    ZepGraphMemoryUpdater,
    ZepGraphMemoryManager,
    AgentActivity
)

# With this:
from .graph_entity_reader import GraphEntityReader, EntityNode, FilteredEntities
from .graph_memory_updater import (
    GraphMemoryUpdater,
    GraphMemoryManager,
    AgentActivity
)
```

Also update `__all__`:
```python
# Replace 'ZepEntityReader' with 'GraphEntityReader'
# Replace 'ZepGraphMemoryUpdater' with 'GraphMemoryUpdater'
# Replace 'ZepGraphMemoryManager' with 'GraphMemoryManager'
```

- [ ] **Step 2: Update simulation_runner.py**

In `backend/app/services/simulation_runner.py`:

```python
# Replace:
from .zep_graph_memory_updater import ZepGraphMemoryManager
# With:
from .graph_memory_updater import GraphMemoryManager

# Replace all occurrences of ZepGraphMemoryManager with GraphMemoryManager (4 occurrences):
# Line ~377: ZepGraphMemoryManager.create_updater(...)  →  GraphMemoryManager.create_updater(...)
# Line ~554: ZepGraphMemoryManager.stop_updater(...)    →  GraphMemoryManager.stop_updater(...)
# Line ~810: ZepGraphMemoryManager.stop_updater(...)    →  GraphMemoryManager.stop_updater(...)
# Line ~1204: ZepGraphMemoryManager.stop_all()          →  GraphMemoryManager.stop_all()
```

Use the Edit tool to make each replacement individually. Run `grep -n ZepGraphMemoryManager backend/app/services/simulation_runner.py` first to confirm line numbers.

- [ ] **Step 3: Update simulation_manager.py**

In `backend/app/services/simulation_manager.py`:

```python
# Replace:
from .zep_entity_reader import ZepEntityReader, FilteredEntities
# With:
from .graph_entity_reader import GraphEntityReader, FilteredEntities

# Replace:
reader = ZepEntityReader()
# With:
reader = GraphEntityReader()
```

Run `grep -n ZepEntityReader backend/app/services/simulation_manager.py` to find exact lines.

- [ ] **Step 4: Update simulation_config_generator.py**

In `backend/app/services/simulation_config_generator.py`:

```python
# Replace:
from .zep_entity_reader import EntityNode, ZepEntityReader
# With:
from .graph_entity_reader import EntityNode, GraphEntityReader
```

Run `grep -n ZepEntityReader backend/app/services/simulation_config_generator.py` to find and update any instantiations too.

- [ ] **Step 5: Update oasis_profile_generator.py**

In `backend/app/services/oasis_profile_generator.py`, find and update:

```python
# Replace:
from zep_cloud.client import Zep
# ...
from .zep_entity_reader import EntityNode, ZepEntityReader

# With:
from .graph_entity_reader import EntityNode, GraphEntityReader
from ..utils.graphiti_client import create_graphiti_client
```

Replace `Zep(api_key=...)` client usage with `create_graphiti_client()`.

Replace `ZepEntityReader()` with `GraphEntityReader()`.

The `_search_zep_for_entity` method should use `GraphToolsService.search_graph()` instead of the direct Zep client:

```python
def _search_zep_for_entity(self, entity: EntityNode) -> dict[str, Any]:
    """Search graph for entity-related context."""
    if not self.graph_id:
        return {}
    from .graph_tools import GraphToolsService
    try:
        tools = GraphToolsService()
        result = tools.search_graph(self.graph_id, entity.name, limit=10)
        return {"facts": result.facts, "edges": result.edges}
    except Exception as e:
        logger.warning(f"Graph search failed for entity {entity.name}: {e}")
        return {}
```

- [ ] **Step 6: Update report_agent.py**

In `backend/app/services/report_agent.py`:

```python
# Replace:
from .zep_tools import (
    ZepToolsService,
    ...
)
# With:
from .graph_tools import (
    GraphToolsService,
    SearchResult,
    InsightForgeResult,
    PanoramaResult,
    InterviewResult,
    NodeInfo,
    EdgeInfo,
)
```

Replace all `ZepToolsService` → `GraphToolsService`, `zep_tools` → `GraphToolsService` in the constructor and type annotations.

Run `grep -n "ZepToolsService\|zep_tools" backend/app/services/report_agent.py` to find all occurrences.

- [ ] **Step 7: Update api/simulation.py**

In `backend/app/api/simulation.py`:

```python
# Replace:
from ..services.zep_entity_reader import ZepEntityReader
# With:
from ..services.graph_entity_reader import GraphEntityReader

# Replace all:
reader = ZepEntityReader()
# With:
reader = GraphEntityReader()
```

Run `grep -n "ZepEntityReader" backend/app/api/simulation.py` (5 occurrences expected).

- [ ] **Step 8: Update api/report.py**

In `backend/app/api/report.py`:

```python
# Replace (2 occurrences):
from ..services.zep_tools import ZepToolsService
tools = ZepToolsService()
# With:
from ..services.graph_tools import GraphToolsService
tools = GraphToolsService()
```

- [ ] **Step 9: Verify no remaining zep_cloud imports**

```bash
grep -rn "from zep_cloud\|from .zep_\|from ..services.zep_\|from ..utils.zep_\|ZepEntityReader\|ZepGraphMemoryManager\|ZepToolsService" backend/app --include="*.py"
```
Expected: no output (zero matches).

- [ ] **Step 10: Run all tests**

```bash
cd backend && uv run pytest tests/ -v
```
Expected: all tests pass.

- [ ] **Step 11: Commit**

```bash
git add backend/app/services/ backend/app/api/
git commit -m "feat: update all import sites to use Graphiti-backed services"
```

---

## Task 9: Docker Infrastructure

**Files:**
- Modify: `docker-compose.yml`

- [ ] **Step 1: Add FalkorDB service to docker-compose.yml**

Replace `docker-compose.yml` content with:

```yaml
services:
  falkordb:
    image: falkordb/falkordb:latest
    container_name: mirofish-falkordb
    ports:
      - "6379:6379"
    volumes:
      - falkordb_data:/data
    restart: unless-stopped

  mirofish:
    image: ghcr.io/666ghj/mirofish:latest
    # Accelerated image (if pulling is slow, you can replace the address above)
    # image: ghcr.nju.edu.cn/666ghj/mirofish:latest
    container_name: mirofish
    env_file:
      - .env
    ports:
      - "3000:3000"
      - "5001:5001"
    restart: unless-stopped
    volumes:
      - ./backend/uploads:/app/backend/uploads
    depends_on:
      - falkordb
    environment:
      - FALKORDB_HOST=falkordb
      - FALKORDB_PORT=6379

volumes:
  falkordb_data:
```

- [ ] **Step 2: For local source development, start FalkorDB only**

```bash
docker compose up falkordb -d
```
Expected: FalkorDB container starts, port 6379 available.

- [ ] **Step 3: Run startup smoke test**

```bash
cd backend && uv run python run.py &
sleep 5
curl http://localhost:5001/health
kill %1
```
Expected: `{"service": "MiroFish Backend", "status": "ok"}`.

- [ ] **Step 4: Commit**

```bash
git add docker-compose.yml
git commit -m "feat: add FalkorDB service to docker-compose"
```

---

## Task 10: Delete Old Zep Files and Final Cleanup

- [ ] **Step 1: Delete old Zep-specific files**

```bash
rm backend/app/utils/zep_paging.py
rm backend/app/services/zep_entity_reader.py
rm backend/app/services/zep_graph_memory_updater.py
rm backend/app/services/zep_tools.py
```

- [ ] **Step 2: Confirm no remaining references**

```bash
grep -rn "zep_paging\|zep_entity_reader\|zep_graph_memory\|zep_tools\|zep_cloud" backend/ --include="*.py"
```
Expected: zero matches.

- [ ] **Step 3: Run full test suite**

```bash
cd backend && uv run pytest tests/ -v
```
Expected: all tests pass.

- [ ] **Step 4: Start server and verify health**

```bash
cd /Users/graeme/Code/MiroFish && npm run backend &
sleep 5
curl http://localhost:5001/health
kill %1
```
Expected: `{"service": "MiroFish Backend", "status": "ok"}`.

- [ ] **Step 5: Update CLAUDE.md**

In `CLAUDE.md`, update the Data Storage section:
- Replace Zep Cloud description with Graphiti + FalkorDB
- Remove `ZEP_API_KEY` references
- Add `FALKORDB_*` and `EMBEDDING_*` config docs
- Remove the "Dependency risk" note about Zep CE sunset

- [ ] **Step 6: Final commit**

```bash
git add -A
git commit -m "feat: complete migration from Zep Cloud to Graphiti+FalkorDB"
```

---

## Known Limitations

1. **Entity type guidance in bulk ingestion**: `add_episode_bulk()` does not accept `entity_types`. Graphiti will still extract entities, but without the ontology's type constraints. To enforce types, switch `_add_episodes()` to use sequential `add_episode()` calls with `entity_types=entity_types`. This is slower but more accurate.

2. **Embedding provider**: Graphiti semantic search requires an OpenAI-compatible `/embeddings` endpoint. Providers like Groq and DeepSeek do not offer this. If the user's primary LLM is not OpenAI-compatible for embeddings, they must set `EMBEDDING_API_KEY` and `EMBEDDING_BASE_URL` to point to a provider that does (e.g., OpenAI directly).

3. **`get_node_edges()` without group context**: The old Zep API had `graph.node.get_entity_edges(node_uuid)`. Graphiti requires group context to traverse edges. The new `get_node_edges(group_id, node_uuid)` fetches all edges and filters client-side — correct but slower for large graphs.

4. **`_wait_for_episodes()` removed**: Zep CE required polling for episode processing. Graphiti's `add_episode_bulk()` is synchronous/awaitable — it returns when extraction is complete.
