"""
Graph Tools Service for the Report Agent.
Provides search, node/edge retrieval, and insight generation over the Graphiti knowledge graph.
Replaces zep_tools.py.
"""

import asyncio
from dataclasses import dataclass, field
from typing import Any, Optional


from ..utils.graphiti_client import create_graphiti_client
from ..utils.graph_paging import fetch_all_nodes, fetch_all_edges
from ..utils.llm_client import LLMClient
from ..utils.logger import get_logger

logger = get_logger("mirofish.graph_tools")


@dataclass
class SearchResult:
    facts: list[str]
    edges: list[dict[str, Any]]
    nodes: list[dict[str, Any]]
    query: str
    total_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "facts": self.facts,
            "edges": self.edges,
            "nodes": self.nodes,
            "query": self.query,
            "total_count": self.total_count,
        }

    def to_text(self) -> str:
        parts = [
            f"Search Query: {self.query}",
            f"Found {self.total_count} relevant pieces of information",
        ]
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
        return {
            "uuid": self.uuid,
            "name": self.name,
            "labels": self.labels,
            "summary": self.summary,
            "attributes": self.attributes,
        }

    def to_text(self) -> str:
        entity_type = next(
            (label for label in self.labels if label not in ("Entity", "Node")), "Unknown"
        )
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
            "uuid": self.uuid,
            "name": self.name,
            "fact": self.fact,
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
        parts = [
            f"Deep Insight for: {self.query}",
            f"Sub-questions explored: {len(self.sub_queries)}",
            f"Facts retrieved: {len(self.semantic_facts)}",
        ]
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

    def get_all_edges(
        self, group_id: str, include_temporal: bool = True
    ) -> list[EdgeInfo]:
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
                    created_at=getattr(e, "created_at", None),
                    valid_at=getattr(e, "valid_at", None),
                    invalid_at=getattr(e, "invalid_at", None),
                    expired_at=getattr(e, "expired_at", None),
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

        for edge in getattr(results, "edges", []) or []:
            if edge.fact:
                facts.append(edge.fact)
            edges.append(
                {
                    "uuid": edge.uuid or "",
                    "name": edge.name or "",
                    "fact": edge.fact or "",
                    "source_node_uuid": edge.source_node_uuid or "",
                    "target_node_uuid": edge.target_node_uuid or "",
                }
            )

        for node in getattr(results, "nodes", []) or []:
            nodes.append(
                {
                    "uuid": node.uuid or "",
                    "name": node.name or "",
                    "labels": node.labels or [],
                    "summary": node.summary or "",
                }
            )
            if node.summary:
                facts.append(f"[{node.name}]: {node.summary}")

        logger.info(f"Search found {len(facts)} facts")
        return SearchResult(
            facts=facts, edges=edges, nodes=nodes, query=query, total_count=len(facts)
        )

    def _local_search_sync(
        self, group_id: str, query: str, limit: int, scope: str
    ) -> SearchResult:
        """Keyword fallback when Graphiti search is unavailable."""
        logger.info(f"Using local keyword search: query={query[:30]}...")
        all_edges = self.get_all_edges(group_id)
        all_nodes = self.get_all_nodes(group_id)

        query_lower = query.lower()
        keywords = [w for w in query_lower.replace(",", " ").split() if len(w) > 1]

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
                key=lambda x: x[0],
                reverse=True,
            )
            for s, edge in scored[:limit]:
                if s > 0:
                    if edge.fact:
                        facts.append(edge.fact)
                    edges_result.append(edge.to_dict())

        if scope in ("nodes", "both"):
            scored = sorted(
                ((score(n.name) + score(n.summary), n) for n in all_nodes),
                key=lambda x: x[0],
                reverse=True,
            )
            for s, node in scored[:limit]:
                if s > 0:
                    nodes_result.append(node.to_dict())
                    if node.summary:
                        facts.append(f"[{node.name}]: {node.summary}")

        return SearchResult(
            facts=facts,
            edges=edges_result,
            nodes=nodes_result,
            query=query,
            total_count=len(facts),
        )

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
        return [
            e
            for e in all_edges
            if e.source_node_uuid == node_uuid or e.target_node_uuid == node_uuid
        ]

    def get_entities_by_type(self, group_id: str, entity_type: str) -> list[NodeInfo]:
        return [n for n in self.get_all_nodes(group_id) if entity_type in n.labels]

    def get_entity_summary(self, group_id: str, entity_name: str) -> dict[str, Any]:
        search_result = self.search_graph(group_id, entity_name, limit=20)
        all_nodes = self.get_all_nodes(group_id)
        entity_node = next(
            (n for n in all_nodes if n.name.lower() == entity_name.lower()), None
        )
        related_edges = (
            self.get_node_edges(group_id, entity_node.uuid) if entity_node else []
        )
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
            "total_nodes": len(nodes),
            "total_edges": len(edges),
            "entity_types": entity_types,
            "relation_types": relation_types,
        }

    def quick_search(self, group_id: str, query: str, limit: int = 5) -> SearchResult:
        """Simplified search for quick lookups."""
        return self.search_graph(group_id, query, limit=limit, scope="edges")


# Alias for backward compatibility
ZepToolsService = GraphToolsService
