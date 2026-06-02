"""Base store interface."""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agentguard.core.checkpoint import CheckpointData


class BaseStore(ABC):
    """Abstract base class for checkpoint storage."""

    @abstractmethod
    def save(self, data: "CheckpointData") -> None:
        """Save a checkpoint."""
        pass

    @abstractmethod
    def load(self, checkpoint_id: str) -> "CheckpointData | None":
        """Load a checkpoint by ID."""
        pass

    @abstractmethod
    def delete(self, checkpoint_id: str) -> bool:
        """Delete a checkpoint. Returns True if deleted."""
        pass

    @abstractmethod
    def list(self, limit: int = 100) -> list["CheckpointData"]:
        """List checkpoints, newest first."""
        pass

    @abstractmethod
    def clear(self) -> None:
        """Clear all checkpoints."""
        pass
