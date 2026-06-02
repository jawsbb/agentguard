"""SQLite storage backend."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import TYPE_CHECKING

from agentguard.stores.base import BaseStore

if TYPE_CHECKING:
    from agentguard.core.checkpoint import CheckpointData


class SQLiteStore(BaseStore):
    """
    SQLite-based checkpoint storage.

    Zero configuration, works out of the box.
    Suitable for local development and single-agent deployments.
    """

    def __init__(self, path: str = "agentguard.db") -> None:
        """
        Initialize SQLite store.

        Args:
            path: Path to SQLite database file
        """
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        """Initialize database schema."""
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS checkpoints (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    timestamp REAL NOT NULL,
                    state TEXT NOT NULL,
                    metadata TEXT,
                    parent_id TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_timestamp
                ON checkpoints(timestamp DESC)
            """)
            conn.commit()

    def _connect(self) -> sqlite3.Connection:
        """Get database connection."""
        conn = sqlite3.connect(str(self.path))
        conn.row_factory = sqlite3.Row
        return conn

    def save(self, data: "CheckpointData") -> None:
        """Save a checkpoint."""
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO checkpoints
                (id, name, timestamp, state, metadata, parent_id)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    data.id,
                    data.name,
                    data.timestamp,
                    json.dumps(data.state),
                    json.dumps(data.metadata),
                    data.parent_id,
                ),
            )
            conn.commit()

    def load(self, checkpoint_id: str) -> "CheckpointData | None":
        """Load a checkpoint by ID."""
        from agentguard.core.checkpoint import CheckpointData

        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM checkpoints WHERE id = ?",
                (checkpoint_id,),
            ).fetchone()

        if row is None:
            return None

        return CheckpointData(
            id=row["id"],
            name=row["name"],
            timestamp=row["timestamp"],
            state=json.loads(row["state"]),
            metadata=json.loads(row["metadata"]) if row["metadata"] else {},
            parent_id=row["parent_id"],
        )

    def delete(self, checkpoint_id: str) -> bool:
        """Delete a checkpoint."""
        with self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM checkpoints WHERE id = ?",
                (checkpoint_id,),
            )
            conn.commit()
            return cursor.rowcount > 0

    def list(self, limit: int = 100) -> list["CheckpointData"]:
        """List checkpoints, newest first."""
        from agentguard.core.checkpoint import CheckpointData

        with self._connect() as conn:
            # Tie-break on rowid (insertion order): time.time() is too coarse
            # to order checkpoints saved within the same clock tick.
            rows = conn.execute(
                "SELECT * FROM checkpoints ORDER BY timestamp DESC, rowid DESC LIMIT ?",
                (limit,),
            ).fetchall()

        return [
            CheckpointData(
                id=row["id"],
                name=row["name"],
                timestamp=row["timestamp"],
                state=json.loads(row["state"]),
                metadata=json.loads(row["metadata"]) if row["metadata"] else {},
                parent_id=row["parent_id"],
            )
            for row in rows
        ]

    def clear(self) -> None:
        """Clear all checkpoints."""
        with self._connect() as conn:
            conn.execute("DELETE FROM checkpoints")
            conn.commit()

    def vacuum(self) -> None:
        """Reclaim disk space."""
        with self._connect() as conn:
            conn.execute("VACUUM")
