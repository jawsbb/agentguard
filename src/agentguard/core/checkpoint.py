"""Checkpoint system for saving and restoring agent state."""

from __future__ import annotations

import hashlib
import pickle
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Generator, TypeVar

from pydantic import BaseModel, ConfigDict

T = TypeVar("T")


class CheckpointData(BaseModel):
    """Serializable checkpoint data."""

    id: str
    name: str
    timestamp: float
    state: dict[str, Any]
    metadata: dict[str, Any] = {}
    parent_id: str | None = None

    model_config = ConfigDict(arbitrary_types_allowed=True)


@dataclass
class Checkpoint:
    """
    Checkpoint manager for agent state.

    Saves state before risky operations and enables rollback on failure.

    Usage:
        cp = Checkpoint(store=SQLiteStore("agent.db"))

        # Manual checkpoint
        cp.save("before_code_execution", state={"files": [...], "context": {...}})

        # Restore if needed
        cp.restore("before_code_execution")

        # Context manager
        with cp.guard("dangerous_action", state={...}):
            risky_operation()
        # Auto-restores on exception
    """

    store: Any  # Store instance (SQLiteStore, RedisStore, etc.)
    max_checkpoints: int = 100
    _current_state: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self._checkpoint_stack: list[str] = []

    def save(
        self,
        name: str,
        state: dict[str, Any],
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """
        Save a checkpoint.

        Args:
            name: Human-readable checkpoint name
            state: State dictionary to save
            metadata: Optional metadata (tokens used, model, etc.)

        Returns:
            Checkpoint ID
        """
        checkpoint_id = self._generate_id(name)
        parent_id = self._checkpoint_stack[-1] if self._checkpoint_stack else None

        data = CheckpointData(
            id=checkpoint_id,
            name=name,
            timestamp=time.time(),
            state=state,
            metadata=metadata or {},
            parent_id=parent_id,
        )

        self.store.save(data)
        self._checkpoint_stack.append(checkpoint_id)
        self._current_state = state.copy()

        # Prune old checkpoints if needed
        self._prune_if_needed()

        return checkpoint_id

    def restore(self, checkpoint_id: str | None = None) -> dict[str, Any]:
        """
        Restore state from a checkpoint.

        Args:
            checkpoint_id: ID to restore. If None, restores latest.

        Returns:
            Restored state dictionary
        """
        if checkpoint_id is None:
            if not self._checkpoint_stack:
                raise ValueError("No checkpoints to restore")
            checkpoint_id = self._checkpoint_stack[-1]

        data = self.store.load(checkpoint_id)
        if data is None:
            raise ValueError(f"Checkpoint not found: {checkpoint_id}")

        self._current_state = data.state.copy()

        # Trim stack to this checkpoint
        if checkpoint_id in self._checkpoint_stack:
            idx = self._checkpoint_stack.index(checkpoint_id)
            self._checkpoint_stack = self._checkpoint_stack[: idx + 1]

        return self._current_state

    def rollback(self, steps: int = 1) -> dict[str, Any]:
        """
        Rollback N steps.

        Args:
            steps: Number of checkpoints to rollback

        Returns:
            Restored state dictionary
        """
        if steps >= len(self._checkpoint_stack):
            raise ValueError(f"Cannot rollback {steps} steps, only {len(self._checkpoint_stack)} checkpoints exist")

        target_idx = len(self._checkpoint_stack) - steps - 1
        target_id = self._checkpoint_stack[target_idx]
        return self.restore(target_id)

    def get_history(self, limit: int = 10) -> list[CheckpointData]:
        """Get checkpoint history."""
        return self.store.list(limit=limit)

    def clear(self) -> None:
        """Clear all checkpoints."""
        self.store.clear()
        self._checkpoint_stack = []
        self._current_state = {}

    @contextmanager
    def guard(
        self,
        name: str,
        state: dict[str, Any],
        auto_restore: bool = True,
    ) -> Generator[str, None, None]:
        """
        Context manager that auto-restores on exception.

        Args:
            name: Checkpoint name
            state: State to save
            auto_restore: Whether to auto-restore on exception

        Yields:
            Checkpoint ID
        """
        checkpoint_id = self.save(name, state)
        try:
            yield checkpoint_id
        except Exception:
            if auto_restore:
                self.restore(checkpoint_id)
            raise

    def _generate_id(self, name: str) -> str:
        """Generate unique checkpoint ID."""
        timestamp = str(time.time_ns())
        content = f"{name}:{timestamp}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def _prune_if_needed(self) -> None:
        """Remove old checkpoints if over limit."""
        all_checkpoints = self.store.list(limit=self.max_checkpoints + 50)
        if len(all_checkpoints) > self.max_checkpoints:
            to_remove = all_checkpoints[self.max_checkpoints :]
            for cp in to_remove:
                self.store.delete(cp.id)


def checkpoint(
    name: str | None = None,
    capture: list[str] | None = None,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """
    Decorator to checkpoint function state.

    Args:
        name: Checkpoint name (defaults to function name)
        capture: List of argument names to capture in state

    Usage:
        @checkpoint("before_api_call", capture=["prompt", "context"])
        def call_llm(prompt: str, context: dict):
            return llm.complete(prompt)
    """
    from agentguard.core.guard import _get_default_guard

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        checkpoint_name = name or func.__name__

        def wrapper(*args: Any, **kwargs: Any) -> T:
            guard = _get_default_guard()
            if guard is None:
                # No guard configured, just run the function
                return func(*args, **kwargs)

            # Build state from captured args
            state: dict[str, Any] = {"function": func.__name__, "timestamp": time.time()}

            if capture:
                import inspect

                sig = inspect.signature(func)
                params = list(sig.parameters.keys())
                for i, arg in enumerate(args):
                    if i < len(params) and params[i] in capture:
                        state[params[i]] = _safe_serialize(arg)
                for key, value in kwargs.items():
                    if key in capture:
                        state[key] = _safe_serialize(value)

            with guard.checkpoint.guard(checkpoint_name, state):
                return func(*args, **kwargs)

        return wrapper

    return decorator


def _safe_serialize(obj: Any) -> Any:
    """Safely serialize an object for checkpointing."""
    try:
        # Try JSON-serializable first
        import json

        json.dumps(obj)
        return obj
    except (TypeError, ValueError):
        pass

    # Try pickle
    try:
        pickled = pickle.dumps(obj)
        return {"__pickled__": True, "data": pickled.hex()}
    except Exception:
        # Last resort: string representation
        return {"__repr__": True, "value": repr(obj)}
