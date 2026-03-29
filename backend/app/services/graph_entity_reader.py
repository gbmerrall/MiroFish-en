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
