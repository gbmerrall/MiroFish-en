"""Tests for graph_paging utilities."""

from unittest.mock import AsyncMock, MagicMock
import pytest
from graphiti_core.nodes import EntityNode
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
