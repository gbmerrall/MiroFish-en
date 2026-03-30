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

from ..utils.graphiti_client import create_graphiti_client
from ..utils.logger import get_logger

logger = get_logger("mirofish.graph_memory_updater")


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
        quote = self.action_args.get("quote_content", "") or self.action_args.get(
            "content", ""
        )
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
                return (
                    f'commented on {post_author}\'s post "{post_content}": "{content}"'
                )
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
            "twitter": [],
            "reddit": [],
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
                            batch = self._platform_buffers[platform][: self.BATCH_SIZE]
                            self._platform_buffers[platform] = self._platform_buffers[
                                platform
                            ][self.BATCH_SIZE :]
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
                    logger.warning(f"Batch send attempt {attempt + 1} failed: {e}")
                    time.sleep(self.RETRY_DELAY * (attempt + 1))
                else:
                    logger.error(
                        f"Batch send failed after {self.MAX_RETRIES} retries: {e}"
                    )
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
                    logger.info(
                        f"Flushing {len(buffer)} remaining {platform} activities"
                    )
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
            logger.info(
                f"Created GraphMemoryUpdater: simulation_id={simulation_id}, group_id={group_id}"
            )
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
                logger.info(
                    f"Stopped GraphMemoryUpdater: simulation_id={simulation_id}"
                )

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
