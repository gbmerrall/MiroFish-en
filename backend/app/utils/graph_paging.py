"""Graph pagination utilities for Graphiti + FalkorDB.

Encapsulates cursor-based pagination over entity nodes and edges,
returning the complete list transparently to the caller.
"""

from __future__ import annotations

from typing import Any

from graphiti_core import Graphiti

from .logger import get_logger

logger = get_logger("mirofish.graph_paging")

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

        cursor = getattr(batch[-1], "uuid", None)
        if cursor is None:
            logger.warning(
                f"Node missing uuid field, stopping pagination at {len(all_nodes)} nodes"
            )
            break

    logger.debug(
        f"fetch_all_nodes: {len(all_nodes)} nodes retrieved for group {group_id}"
    )
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

        cursor = getattr(batch[-1], "uuid", None)
        if cursor is None:
            logger.warning(
                f"Edge missing uuid field, stopping pagination at {len(all_edges)} edges"
            )
            break

    logger.debug(
        f"fetch_all_edges: {len(all_edges)} edges retrieved for group {group_id}"
    )
    return all_edges
