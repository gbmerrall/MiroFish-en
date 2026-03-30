"""
Graph Building Service
Builds knowledge graphs from text documents using Graphiti + FalkorDB.
Replaces the Zep-based implementation.
"""

import asyncio
import uuid
import time
import threading
from datetime import datetime, timezone
from typing import Dict, Any, List
from dataclasses import dataclass

from graphiti_core.nodes import EpisodeType

from ..models.task import TaskManager, TaskStatus
from ..utils.graphiti_client import create_graphiti_client
from ..utils.graph_paging import fetch_all_nodes, fetch_all_edges
from ..utils.logger import get_logger
from .text_processor import TextProcessor

logger = get_logger("mirofish.graph_builder")


@dataclass
class GraphInfo:
    """Graph Information Summary"""

    graph_id: str
    node_count: int
    edge_count: int
    entity_types: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "graph_id": self.graph_id,
            "node_count": self.node_count,
            "edge_count": self.edge_count,
            "entity_types": self.entity_types,
        }


class GraphBuilderService:
    """
    Graph Building Service.
    Responsible for processing text chunks into a Graphiti knowledge graph.
    """

    def __init__(self):
        self.task_manager = TaskManager()

    def _run_async(self, coro):
        """Helper to run async code in the worker thread."""
        return asyncio.run(coro)

    def build_graph_async(
        self,
        text: str,
        ontology: Dict[str, Any],
        graph_name: str = "MiroFish Graph",
        chunk_size: int = 500,
        chunk_overlap: int = 50,
        batch_size: int = 5,
    ) -> str:
        """
        Builds a graph asynchronously in a background thread.

        Args:
            text: Input text
            ontology: Ontology definition (Note: Graphiti is schema-less/auto-extracting)
            graph_name: Graph name
            chunk_size: Text chunk size
            chunk_overlap: Chunk overlap size
            batch_size: Number of chunks to send per batch

        Returns:
            Task ID
        """
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
            args=(
                task_id,
                text,
                ontology,
                graph_name,
                chunk_size,
                chunk_overlap,
                batch_size,
            ),
        )
        thread.daemon = True
        thread.start()

        return task_id

    def _build_graph_worker(
        self,
        task_id: str,
        text: str,
        ontology: Dict[str, Any],
        graph_name: str,
        chunk_size: int,
        chunk_overlap: int,
        batch_size: int,
    ):
        """Worker thread for graph construction."""
        try:
            self.task_manager.update_task(
                task_id,
                status=TaskStatus.PROCESSING,
                progress=5,
                message="Initializing Graphiti construction...",
            )

            # 1. Unique namespace for this graph (maps to Graphiti group_id)
            group_id = f"mf_{uuid.uuid4().hex[:12]}"

            # 2. Split text into chunks
            chunks = TextProcessor.split_text(text, chunk_size, chunk_overlap)
            total_chunks = len(chunks)
            self.task_manager.update_task(
                task_id, progress=15, message=f"Text split into {total_chunks} chunks"
            )

            # 3. Process batches
            # Graphiti processes episodes sequentially per group to maintain temporal order.
            # We add episodes one by one or in small batches.
            for i in range(0, total_chunks, batch_size):
                batch = chunks[i : i + batch_size]
                batch_idx = (i // batch_size) + 1
                total_batches = (total_chunks + batch_size - 1) // batch_size

                progress_val = 15 + int((batch_idx / total_batches) * 70)
                self.task_manager.update_task(
                    task_id,
                    progress=progress_val,
                    message=f"Processing batch {batch_idx}/{total_batches}...",
                )

                for chunk_text in batch:
                    self._run_async(self._add_episode(group_id, chunk_text, graph_name))

            # 4. Finalize and get stats
            self.task_manager.update_task(
                task_id, progress=90, message="Retrieving graph statistics..."
            )

            graph_info = self._get_graph_info_sync(group_id)

            self.task_manager.complete_task(
                task_id,
                {
                    "graph_id": group_id,
                    "graph_info": graph_info.to_dict(),
                    "chunks_processed": total_chunks,
                },
            )

            logger.info(
                f"Graph build complete: group_id={group_id}, nodes={graph_info.node_count}"
            )

        except Exception as e:
            logger.error(f"Graph build failed: {e}", exc_info=True)
            self.task_manager.fail_task(task_id, str(e))

    async def _add_episode(self, group_id: str, text: str, graph_name: str):
        """Wraps Graphiti.add_episode"""
        graphiti = create_graphiti_client()
        try:
            await graphiti.add_episode(
                name=f"{graph_name}_{int(time.time())}",
                episode_body=text,
                source=EpisodeType.text,
                source_description=f"Source document: {graph_name}",
                reference_time=datetime.now(timezone.utc),
                group_id=group_id,
            )
        finally:
            await graphiti.close()

    def _get_graph_info_sync(self, group_id: str) -> GraphInfo:
        return asyncio.run(self._async_get_graph_info(group_id))

    async def _async_get_graph_info(self, group_id: str) -> GraphInfo:
        graphiti = create_graphiti_client()
        try:
            nodes = await fetch_all_nodes(graphiti, group_id)
            edges = await fetch_all_edges(graphiti, group_id)

            entity_types = set()
            for node in nodes:
                for label in node.labels or []:
                    if label not in ("Entity", "Node"):
                        entity_types.add(label)

            return GraphInfo(
                graph_id=group_id,
                node_count=len(nodes),
                edge_count=len(edges),
                entity_types=list(entity_types),
            )
        finally:
            await graphiti.close()

    def get_graph_data(self, graph_id: str) -> Dict[str, Any]:
        """Returns full graph nodes and edges for visualization."""
        return asyncio.run(self._async_get_graph_data(graph_id))

    async def _async_get_graph_data(self, graph_id: str) -> Dict[str, Any]:
        graphiti = create_graphiti_client()
        try:
            nodes = await fetch_all_nodes(graphiti, graph_id)
            edges = await fetch_all_edges(graphiti, graph_id)

            node_map = {n.uuid: n.name or "" for n in nodes}

            nodes_data = [
                {
                    "uuid": n.uuid,
                    "name": n.name or "",
                    "labels": n.labels or [],
                    "summary": n.summary or "",
                    "attributes": n.attributes or {},
                }
                for n in nodes
            ]

            edges_data = [
                {
                    "uuid": e.uuid,
                    "name": e.name or "",
                    "fact": e.fact or "",
                    "source_node_uuid": e.source_node_uuid,
                    "target_node_uuid": e.target_node_uuid,
                    "source_node_name": node_map.get(e.source_node_uuid, ""),
                    "target_node_name": node_map.get(e.target_node_uuid, ""),
                    "attributes": e.attributes or {},
                }
                for e in edges
            ]

            return {
                "graph_id": graph_id,
                "nodes": nodes_data,
                "edges": edges_data,
                "node_count": len(nodes_data),
                "edge_count": len(edges_data),
            }
        finally:
            await graphiti.close()

    def delete_graph(self, graph_id: str):
        """Note: Graphiti does not have a single-call 'delete group' yet.
        In FalkorDB we would have to delete all nodes/edges for this group_id.
        For now, this is a no-op to satisfy the interface.
        """
        logger.warning(
            f"delete_graph called for {graph_id} - not yet implemented for Graphiti backend"
        )
