"""
Zep Graph Memory Update Service
Dynamically updates Agent activities in the simulation to the Zep graph.
"""

import time
import threading
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from datetime import datetime
from queue import Queue, Empty

from zep_cloud.client import Zep

from ..config import Config
from ..utils.logger import get_logger

logger = get_logger('mirofish.zep_graph_memory_updater')


@dataclass
class AgentActivity:
    """Agent activity record"""
    platform: str           # twitter / reddit
    agent_id: int
    agent_name: str
    action_type: str        # CREATE_POST, LIKE_POST, etc.
    action_args: Dict[str, Any]
    round_num: int
    timestamp: str
    
    def to_episode_text(self) -> str:
        """
        Converts the activity into a text description that can be sent to Zep.
        
        Uses a natural language description format so that Zep can extract entities and relationships from it.
        Does not add simulation-related prefixes to avoid misleading the graph update.
        """
        # Generate different descriptions based on different action types
        action_descriptions = {
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
        
        describe_func = action_descriptions.get(self.action_type, self._describe_generic)
        description = describe_func()
        
        # Directly return "agent_name: activity_description" format, without adding simulation prefix
        return f"{self.agent_name}: {description}"
    
    def _describe_create_post(self) -> str:
        content = self.action_args.get("content", "")
        if content:
            return f"posted: '{content}'"
        return "posted a message"
    
    def _describe_like_post(self) -> str:
        """Like post - includes the original post content and author info"""
        post_content = self.action_args.get("post_content", "")
        post_author = self.action_args.get("post_author_name", "")
        
        if post_content and post_author:
            return f"liked {post_author}'s post: '{post_content}'"
        elif post_content:
            return f"liked a post: '{post_content}'"
        elif post_author:
            return f"liked a post by {post_author}"
        return "liked a post"
    
    def _describe_dislike_post(self) -> str:
        """Dislike post - includes the original post content and author info"""
        post_content = self.action_args.get("post_content", "")
        post_author = self.action_args.get("post_author_name", "")
        
        if post_content and post_author:
            return f"disliked {post_author}'s post: '{post_content}'"
        elif post_content:
            return f"disliked a post: '{post_content}'"
        elif post_author:
            return f"disliked a post by {post_author}"
        return "disliked a post"
    
    def _describe_repost(self) -> str:
        """Repost - includes the original post content and author info"""
        original_content = self.action_args.get("original_content", "")
        original_author = self.action_args.get("original_author_name", "")
        
        if original_content and original_author:
            return f"reposted {original_author}'s post: '{original_content}'"
        elif original_content:
            return f"reposted a post: '{original_content}'"
        elif original_author:
            return f"reposted a post by {original_author}"
        return "reposted a message"
    
    def _describe_quote_post(self) -> str:
        """Quote post - includes original post content, author info, and quote comment"""
        original_content = self.action_args.get("original_content", "")
        original_author = self.action_args.get("original_author_name", "")
        quote_content = self.action_args.get("quote_content", "") or self.action_args.get("content", "")
        
        base = ""
        if original_content and original_author:
            base = f"quoted {original_author}'s post '{original_content}'"
        elif original_content:
            base = f"quoted a post '{original_content}'"
        elif original_author:
            base = f"quoted a post by {original_author}"
        else:
            base = "quoted a post"
        
        if quote_content:
            base += f", with a comment: '{quote_content}'"
        return base
    
    def _describe_follow(self) -> str:
        """Follow user - includes the followed user's name"""
        target_user_name = self.action_args.get("target_user_name", "")
        
        if target_user_name:
            return f"followed user '{target_user_name}'"
        return "followed a user"
    
    def _describe_create_comment(self) -> str:
        """Post a comment - includes comment content and post info being commented on"""
        content = self.action_args.get("content", "")
        post_content = self.action_args.get("post_content", "")
        post_author = self.action_args.get("post_author_name", "")
        
        if content:
            if post_content and post_author:
                return f"commented on {post_author}'s post '{post_content}': '{content}'"
            elif post_content:
                return f"commented on post '{post_content}': '{content}'"
            elif post_author:
                return f"commented on {post_author}'s post: '{content}'"
            return f"commented: '{content}'"
        return "posted a comment"
    
    def _describe_like_comment(self) -> str:
        """Like comment - includes comment content and author info"""
        comment_content = self.action_args.get("comment_content", "")
        comment_author = self.action_args.get("comment_author_name", "")
        
        if comment_content and comment_author:
            return f"liked {comment_author}'s comment: '{comment_content}'"
        elif comment_content:
            return f"liked a comment: '{comment_content}'"
        elif comment_author:
            return f"liked a comment by {comment_author}"
        return "liked a comment"
    
    def _describe_dislike_comment(self) -> str:
        """Dislike comment - includes comment content and author info"""
        comment_content = self.action_args.get("comment_content", "")
        comment_author = self.action_args.get("comment_author_name", "")
        
        if comment_content and comment_author:
            return f"disliked {comment_author}'s comment: '{comment_content}'"
        elif comment_content:
            return f"disliked a comment: '{comment_content}'"
        elif comment_author:
            return f"disliked a comment by {comment_author}"
        return "disliked a comment"
    
    def _describe_search(self) -> str:
        """Search posts - includes search keywords"""
        query = self.action_args.get("query", "") or self.action_args.get("keyword", "")
        return f"searched for: '{query}'" if query else "performed a search"
    
    def _describe_search_user(self) -> str:
        """Search user - includes search keywords"""
        query = self.action_args.get("query", "") or self.action_args.get("username", "")
        return f"searched for user '{query}'" if query else "searched for a user"
    
    def _describe_mute(self) -> str:
        """Mute user - includes the muted user's name"""
        target_user_name = self.action_args.get("target_user_name", "")
        
        if target_user_name:
            return f"muted user '{target_user_name}'"
        return "muted a user"
    
    def _describe_generic(self) -> str:
        # Generate generic description for unknown action types
        return f"performed {self.action_type} action"


class ZepGraphMemoryUpdater:
    """
    Zep Graph Memory Updater
    
    Monitors simulation actions log files and updates new agent activities to Zep graph in real-time.
    Groups by platform and sends in batches after accumulating BATCH_SIZE activities.
    
    All meaningful behaviors are updated to Zep, with action_args containing complete context info:
    - Original post content for Like/Dislike
    - Original post content for Repost/Quote
    - Followed/Muted username
    - Original comment content for Like/Dislike
    """
    
    # Batch send size (how many activities to accumulate per platform before sending)
    BATCH_SIZE = 5
    
    # Platform name mapping (for console display)
    PLATFORM_DISPLAY_NAMES = {
        'twitter': 'World 1',
        'reddit': 'World 2',
    }
    
    # Sending interval (seconds) to avoid excessive requests
    SEND_INTERVAL = 0.5
    
    # Retry configuration
    MAX_RETRIES = 3
    RETRY_DELAY = 2  # seconds
    
    def __init__(self, graph_id: str, api_key: Optional[str] = None):
        """
        Initializes the updater
        
        Args:
            graph_id: Zep graph ID
            api_key: Zep API Key (optional, defaults to config)
        """
        self.graph_id = graph_id
        self.api_key = api_key or Config.ZEP_API_KEY
        
        if not self.api_key:
            raise ValueError("ZEP_API_KEY not configured")
        
        self.client = Zep(api_key=self.api_key)
        
        # Activity queue
        self._activity_queue: Queue = Queue()
        
        # Activity buffers grouped by platform (batch send when BATCH_SIZE reached)
        self._platform_buffers: Dict[str, List[AgentActivity]] = {
            'twitter': [],
            'reddit': [],
        }
        self._buffer_lock = threading.Lock()
        
        # Control flags
        self._running = False
        self._worker_thread: Optional[threading.Thread] = None
        
        # Statistics
        self._total_activities = 0  # Number of activities actually added to the queue
        self._total_sent = 0        # Number of batches successfully sent to Zep
        self._total_items_sent = 0  # Number of activities successfully sent to Zep
        self._failed_count = 0      # Number of failed batch sends
        self._skipped_count = 0     # Number of activities skipped/filtered (DO_NOTHING)
        
        logger.info(f"ZepGraphMemoryUpdater initialized: graph_id={graph_id}, batch_size={self.BATCH_SIZE}")
    
    def _get_platform_display_name(self, platform: str) -> str:
        """Gets the display name for a platform"""
        return self.PLATFORM_DISPLAY_NAMES.get(platform.lower(), platform)
    
    def start(self):
        """Starts the background worker thread"""
        if self._running:
            return
        
        self._running = True
        self._worker_thread = threading.Thread(
            target=self._worker_loop,
            daemon=True,
            name=f"ZepMemoryUpdater-{self.graph_id[:8]}"
        )
        self._worker_thread.start()
        logger.info(f"ZepGraphMemoryUpdater started: graph_id={self.graph_id}")
    
    def stop(self):
        """Stops the background worker thread"""
        self._running = False
        
        # Send remaining activities
        self._flush_remaining()
        
        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=10)
        
        logger.info(f"ZepGraphMemoryUpdater stopped: graph_id={self.graph_id}, "
                   f"total_activities={self._total_activities}, "
                   f"batches_sent={self._total_sent}, "
                   f"items_sent={self._total_items_sent}, "
                   f"failed={self._failed_count}, "
                   f"skipped={self._skipped_count}")
    
    def add_activity(self, activity: AgentActivity):
        """
        Adds an agent activity to the queue
        
        All meaningful behaviors are added, including:
        - CREATE_POST
        - CREATE_COMMENT
        - QUOTE_POST
        - SEARCH_POSTS
        - SEARCH_USER
        - LIKE_POST/DISLIKE_POST
        - REPOST
        - FOLLOW
        - MUTE
        - LIKE_COMMENT/DISLIKE_COMMENT
        
        action_args contains complete context info (e.g., original post, username).
        
        Args:
            activity: Agent activity record
        """
        # Skip DO_NOTHING activities
        if activity.action_type == "DO_NOTHING":
            self._skipped_count += 1
            return
        
        self._activity_queue.put(activity)
        self._total_activities += 1
        logger.debug(f"Added activity to Zep queue: {activity.agent_name} - {activity.action_type}")
    
    def add_activity_from_dict(self, data: Dict[str, Any], platform: str):
        """
        Adds an activity from a dictionary
        
        Args:
            data: Parsed dictionary from actions.jsonl
            platform: Platform name (twitter/reddit)
        """
        # Skip entries of event type
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
        """Background worker loop - batches activities by platform and sends to Zep"""
        while self._running or not self._activity_queue.empty():
            try:
                # Try to get an activity from the queue (1-second timeout)
                try:
                    activity = self._activity_queue.get(timeout=1)
                    
                    # Add activity to corresponding platform buffer
                    platform = activity.platform.lower()
                    with self._buffer_lock:
                        if platform not in self._platform_buffers:
                            self._platform_buffers[platform] = []
                        self._platform_buffers[platform].append(activity)
                        
                        # Check if platform has reached batch size
                        if len(self._platform_buffers[platform]) >= self.BATCH_SIZE:
                            batch = self._platform_buffers[platform][:self.BATCH_SIZE]
                            self._platform_buffers[platform] = self._platform_buffers[platform][self.BATCH_SIZE:]
                            # Release lock before sending
                            self._send_batch_activities(batch, platform)
                            # Delay between sends to avoid rate limiting
                            time.sleep(self.SEND_INTERVAL)
                    
                except Empty:
                    pass
                    
            except Exception as e:
                logger.error(f"Worker loop exception: {e}")
                time.sleep(1)
    
    def _send_batch_activities(self, activities: List[AgentActivity], platform: str):
        """
        Sends a batch of activities to the Zep graph (merged into one text)
        
        Args:
            activities: List of Agent activities
            platform: Platform name
        """
        if not activities:
            return
        
        # Merge multiple activities into one text separated by newlines
        episode_texts = [activity.to_episode_text() for activity in activities]
        combined_text = "\n".join(episode_texts)
        
        # Send with retries
        for attempt in range(self.MAX_RETRIES):
            try:
                self.client.graph.add(
                    graph_id=self.graph_id,
                    type="text",
                    data=combined_text
                )
                
                self._total_sent += 1
                self._total_items_sent += len(activities)
                display_name = self._get_platform_display_name(platform)
                logger.info(f"Successfully sent {len(activities)} {display_name} activities to graph {self.graph_id}")
                logger.debug(f"Batch content preview: {combined_text[:200]}...")
                return
                
            except Exception as e:
                if attempt < self.MAX_RETRIES - 1:
                    logger.warning(f"Failed to send batch to Zep (attempt {attempt + 1}/{self.MAX_RETRIES}): {e}")
                    time.sleep(self.RETRY_DELAY * (attempt + 1))
                else:
                    logger.error(f"Failed to send batch to Zep after {self.MAX_RETRIES} attempts: {e}")
                    self._failed_count += 1
    
    def _flush_remaining(self):
        """Sends remaining activities in the queue and buffers"""
        # First process any activities left in the queue and add to buffers
        while not self._activity_queue.empty():
            try:
                activity = self._activity_queue.get_nowait()
                platform = activity.platform.lower()
                with self._buffer_lock:
                    if platform not in self._platform_buffers:
                        self._platform_buffers[platform] = []
                    self._platform_buffers[platform].append(activity)
            except Empty:
                break
        
        # Then send remaining activities in each platform buffer (even if fewer than BATCH_SIZE)
        with self._buffer_lock:
            for platform, buffer in self._platform_buffers.items():
                if buffer:
                    display_name = self._get_platform_display_name(platform)
                    logger.info(f"Sending remaining {len(buffer)} activities for {display_name}")
                    self._send_batch_activities(buffer, platform)
            # Clear all buffers
            for platform in self._platform_buffers:
                self._platform_buffers[platform] = []
    
    def get_stats(self) -> Dict[str, Any]:
        """Gets statistical information"""
        with self._buffer_lock:
            buffer_sizes = {p: len(b) for p, b in self._platform_buffers.items()}
        
        return {
            "graph_id": self.graph_id,
            "batch_size": self.BATCH_SIZE,
            "total_activities": self._total_activities,  # Total activities added to the queue
            "batches_sent": self._total_sent,            # Number of successfully sent batches
            "items_sent": self._total_items_sent,        # Number of successfully sent activities
            "failed_count": self._failed_count,          # Number of failed batch sends
            "skipped_count": self._skipped_count,        # Number of filtered/skipped activities (DO_NOTHING)
            "queue_size": self._activity_queue.qsize(),
            "buffer_sizes": buffer_sizes,                # Platform-specific buffer sizes
            "running": self._running,
        }


class ZepGraphMemoryManager:
    """
    Manages multiple simulated Zep graph memory updaters
    
    Each simulation can have its own updater instance.
    """
    
    _updaters: Dict[str, ZepGraphMemoryUpdater] = {}
    _lock = threading.Lock()
    
    @classmethod
    def create_updater(cls, simulation_id: str, graph_id: str) -> ZepGraphMemoryUpdater:
        """
        Creates a graph memory updater for a simulation
        
        Args:
            simulation_id: Simulation ID
            graph_id: Zep graph ID
            
        Returns:
            ZepGraphMemoryUpdater instance
        """
        with cls._lock:
            # If already exists, stop the old one first
            if simulation_id in cls._updaters:
                cls._updaters[simulation_id].stop()
            
            updater = ZepGraphMemoryUpdater(graph_id)
            updater.start()
            cls._updaters[simulation_id] = updater
            
            logger.info(f"Created graph memory updater: simulation_id={simulation_id}, graph_id={graph_id}")
            return updater
    
    @classmethod
    def get_updater(cls, simulation_id: str) -> Optional[ZepGraphMemoryUpdater]:
        """Gets the updater for a simulation"""
        return cls._updaters.get(simulation_id)
    
    @classmethod
    def stop_updater(cls, simulation_id: str):
        """Stops and removes the updater for a simulation"""
        with cls._lock:
            if simulation_id in cls._updaters:
                cls._updaters[simulation_id].stop()
                del cls._updaters[simulation_id]
                logger.info(f"Stopped graph memory updater: simulation_id={simulation_id}")
    
    # Flag to prevent multiple calls to stop_all
    _stop_all_done = False
    
    @classmethod
    def stop_all(cls):
        """Stops all updaters"""
        # Prevent multiple calls
        if cls._stop_all_done:
            return
        cls._stop_all_done = True
        
        with cls._lock:
            if cls._updaters:
                for simulation_id, updater in list(cls._updaters.items()):
                    try:
                        updater.stop()
                    except Exception as e:
                        logger.error(f"Failed to stop updater: simulation_id={simulation_id}, error={e}")
                cls._updaters.clear()
            logger.info("Stopped all graph memory updaters")
    
    @classmethod
    def get_all_stats(cls) -> Dict[str, Dict[str, Any]]:
        """Gets statistical info for all updaters"""
        return {
            sim_id: updater.get_stats() 
            for sim_id, updater in cls._updaters.items()
        }
