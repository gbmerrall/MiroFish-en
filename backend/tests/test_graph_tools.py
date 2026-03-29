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
