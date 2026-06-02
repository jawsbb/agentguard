"""Tests for checkpoint functionality."""

import pytest
import tempfile
from pathlib import Path

from agentguard.core.checkpoint import Checkpoint, CheckpointData
from agentguard.stores.memory import MemoryStore
from agentguard.stores.sqlite import SQLiteStore


@pytest.fixture
def memory_store():
    """Create a memory store for testing."""
    return MemoryStore()


@pytest.fixture
def sqlite_store(tmp_path):
    """Create a SQLite store for testing."""
    db_path = tmp_path / "test.db"
    return SQLiteStore(str(db_path))


@pytest.fixture
def checkpoint(memory_store):
    """Create a checkpoint manager for testing."""
    return Checkpoint(store=memory_store)


class TestCheckpoint:
    """Tests for Checkpoint class."""

    def test_save_creates_checkpoint(self, checkpoint):
        """Test that save creates a checkpoint."""
        state = {"key": "value", "number": 42}
        checkpoint_id = checkpoint.save("test_checkpoint", state)

        assert checkpoint_id is not None
        assert len(checkpoint_id) == 16  # SHA256 prefix

    def test_restore_returns_saved_state(self, checkpoint):
        """Test that restore returns the saved state."""
        original_state = {"files": ["a.py", "b.py"], "context": "test"}
        checkpoint_id = checkpoint.save("test", original_state)

        restored_state = checkpoint.restore(checkpoint_id)

        assert restored_state == original_state

    def test_restore_latest_without_id(self, checkpoint):
        """Test restoring the latest checkpoint without ID."""
        checkpoint.save("first", {"n": 1})
        checkpoint.save("second", {"n": 2})
        checkpoint.save("third", {"n": 3})

        restored = checkpoint.restore()

        assert restored == {"n": 3}

    def test_rollback_steps(self, checkpoint):
        """Test rolling back multiple steps."""
        checkpoint.save("step1", {"step": 1})
        checkpoint.save("step2", {"step": 2})
        checkpoint.save("step3", {"step": 3})

        # Rollback 2 steps (to step1)
        restored = checkpoint.rollback(steps=2)

        assert restored == {"step": 1}

    def test_rollback_too_many_steps_raises(self, checkpoint):
        """Test that rolling back too many steps raises error."""
        checkpoint.save("step1", {"step": 1})

        with pytest.raises(ValueError, match="Cannot rollback"):
            checkpoint.rollback(steps=5)

    def test_guard_context_manager(self, checkpoint):
        """Test the guard context manager."""
        state = {"before": True}

        with checkpoint.guard("test_action", state) as checkpoint_id:
            assert checkpoint_id is not None
            # Action succeeds

        # Should have saved the checkpoint
        history = checkpoint.get_history()
        assert len(history) == 1

    def test_guard_restores_on_exception(self, checkpoint):
        """Test that guard restores state on exception."""
        initial_state = {"status": "initial"}
        checkpoint.save("initial", initial_state)

        try:
            with checkpoint.guard("risky_action", {"status": "in_progress"}):
                raise RuntimeError("Something went wrong")
        except RuntimeError:
            pass

        # State should be restored to pre-exception
        current = checkpoint.restore()
        assert current["status"] == "in_progress"  # Restored to the guard's checkpoint

    def test_get_history(self, checkpoint):
        """Test getting checkpoint history."""
        for i in range(5):
            checkpoint.save(f"checkpoint_{i}", {"index": i})

        history = checkpoint.get_history(limit=3)

        assert len(history) == 3
        # Should be newest first
        assert history[0].state["index"] == 4

    def test_clear_removes_all(self, checkpoint):
        """Test clearing all checkpoints."""
        for i in range(3):
            checkpoint.save(f"checkpoint_{i}", {"i": i})

        checkpoint.clear()

        history = checkpoint.get_history()
        assert len(history) == 0


class TestSQLiteStore:
    """Tests for SQLite store."""

    def test_save_and_load(self, sqlite_store):
        """Test saving and loading checkpoints."""
        data = CheckpointData(
            id="test123",
            name="test_checkpoint",
            timestamp=1234567890.0,
            state={"key": "value"},
            metadata={"tokens": 100},
        )

        sqlite_store.save(data)
        loaded = sqlite_store.load("test123")

        assert loaded is not None
        assert loaded.id == data.id
        assert loaded.name == data.name
        assert loaded.state == data.state
        assert loaded.metadata == data.metadata

    def test_delete(self, sqlite_store):
        """Test deleting checkpoints."""
        data = CheckpointData(
            id="to_delete",
            name="test",
            timestamp=1234567890.0,
            state={},
        )
        sqlite_store.save(data)

        result = sqlite_store.delete("to_delete")
        assert result is True

        loaded = sqlite_store.load("to_delete")
        assert loaded is None

    def test_list_ordered_by_timestamp(self, sqlite_store):
        """Test that list returns checkpoints ordered by timestamp."""
        for i in range(5):
            data = CheckpointData(
                id=f"cp_{i}",
                name=f"checkpoint_{i}",
                timestamp=float(i),
                state={"index": i},
            )
            sqlite_store.save(data)

        listed = sqlite_store.list(limit=10)

        # Should be newest first
        assert listed[0].state["index"] == 4
        assert listed[-1].state["index"] == 0

    def test_persistence(self, tmp_path):
        """Test that data persists across store instances."""
        db_path = tmp_path / "persist.db"

        # Create and save
        store1 = SQLiteStore(str(db_path))
        store1.save(CheckpointData(
            id="persistent",
            name="test",
            timestamp=123.0,
            state={"persisted": True},
        ))

        # Create new instance and load
        store2 = SQLiteStore(str(db_path))
        loaded = store2.load("persistent")

        assert loaded is not None
        assert loaded.state["persisted"] is True
