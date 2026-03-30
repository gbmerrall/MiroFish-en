"""Tests for GraphMemoryUpdater."""

from unittest.mock import MagicMock, patch


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
        platform="twitter",
        agent_id=1,
        agent_name="Bob",
        action_type="DO_NOTHING",
        action_args={},
        round_num=1,
        timestamp="",
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

    with patch(
        "app.services.graph_memory_updater.GraphMemoryUpdater",
        return_value=mock_updater,
    ):
        mock_updater.start = MagicMock()
        GraphMemoryManager.create_updater("sim-1", "group-abc")

    assert GraphMemoryManager.get_updater("sim-1") is mock_updater
