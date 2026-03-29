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
                mock_graphiti = MagicMock()
                mock_graphiti.close = AsyncMock()
                with patch("app.services.graph_entity_reader.create_graphiti_client", return_value=mock_graphiti):
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
        mock_graphiti = MagicMock()
        mock_graphiti.close = AsyncMock()
        with patch("app.services.graph_entity_reader.create_graphiti_client", return_value=mock_graphiti):
            result = reader.get_all_nodes("group-1")

    assert len(result) == 1
    assert result[0]["uuid"] == "n1"
    assert result[0]["name"] == "Alice"
    assert "labels" in result[0]
