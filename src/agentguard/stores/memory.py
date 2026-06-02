"""In-memory storage backend."""

from __future__ import annotations

from typing import TYPE_CHECKING

from agentguard.stores.base import BaseStore

if TYPE_CHECKING:
    from agentguard.core.checkpoint import CheckpointData


class MemoryStore(BaseStore):
    """
    In-memory checkpoint storage.

    Fast and simple, but data is lost on restart.
    Useful for testing and short-lived agents.
    """

    def __init__(self) -> None:
        self._data: dict[str, CheckpointData] = {}
        # Monotonic insertion counter used to break timestamp ties.
        # time.time() resolution (~15ms on Windows) is too coarse to order
        # checkpoints created in quick succession, so we track insertion order.
        self._seq: dict[str, int] = {}
        self._counter: int = 0

    def save(self, data: CheckpointData) -> None:
        """Save a checkpoint."""
        self._data[data.id] = data
        self._counter += 1
        self._seq[data.id] = self._counter

    def load(self, checkpoint_id: str) -> CheckpointData | None:
        """Load a checkpoint by ID."""
        return self._data.get(checkpoint_id)

    def delete(self, checkpoint_id: str) -> bool:
        """Delete a checkpoint."""
        if checkpoint_id in self._data:
            del self._data[checkpoint_id]
            self._seq.pop(checkpoint_id, None)
            return True
        return False

    def list(self, limit: int = 100) -> list[CheckpointData]:
        """List checkpoints, newest first."""
        sorted_checkpoints = sorted(
            self._data.values(),
            key=lambda x: (x.timestamp, self._seq.get(x.id, 0)),
            reverse=True,
        )
        return sorted_checkpoints[:limit]

    def clear(self) -> None:
        """Clear all checkpoints."""
        self._data.clear()
        self._seq.clear()
        self._counter = 0
