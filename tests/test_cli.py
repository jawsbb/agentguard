"""Tests for the AgentGuard CLI."""

from typer.testing import CliRunner

from agentguard.cli import app
from agentguard.core.checkpoint import CheckpointData
from agentguard.stores.sqlite import SQLiteStore

runner = CliRunner()


def _seed(db: str) -> None:
    store = SQLiteStore(db)
    store.save(
        CheckpointData(
            id="abc123def4567890",
            name="deploy_prod",
            timestamp=1000.0,
            state={"version": 1},
        )
    )


def test_version():
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert "AgentGuard" in result.output


def test_status_empty(tmp_path):
    result = runner.invoke(app, ["status", "--db", str(tmp_path / "x.db")])
    assert result.exit_code == 0
    assert "No checkpoints" in result.output


def test_status_lists_checkpoint(tmp_path):
    db = str(tmp_path / "x.db")
    _seed(db)
    result = runner.invoke(app, ["status", "--db", db])
    assert result.exit_code == 0
    assert "deploy_prod" in result.output


def test_list(tmp_path):
    db = str(tmp_path / "x.db")
    _seed(db)
    result = runner.invoke(app, ["list", "--db", db])
    assert result.exit_code == 0
    assert "deploy_prod" in result.output


def test_show_by_full_id(tmp_path):
    db = str(tmp_path / "x.db")
    _seed(db)
    result = runner.invoke(app, ["show", "abc123def4567890", "--db", db])
    assert result.exit_code == 0
    assert "deploy_prod" in result.output
    assert "version" in result.output


def test_show_by_prefix(tmp_path):
    db = str(tmp_path / "x.db")
    _seed(db)
    result = runner.invoke(app, ["show", "abc123", "--db", db])
    assert result.exit_code == 0
    assert "deploy_prod" in result.output


def test_show_missing(tmp_path):
    db = str(tmp_path / "x.db")
    _seed(db)
    result = runner.invoke(app, ["show", "doesnotexist", "--db", db])
    assert "not found" in result.output.lower()


def test_rollback_dry_run(tmp_path):
    db = str(tmp_path / "x.db")
    _seed(db)
    result = runner.invoke(app, ["rollback", "abc123", "--db", db, "--dry-run"])
    assert result.exit_code == 0
    assert "Would rollback" in result.output


def test_clear_force(tmp_path):
    db = str(tmp_path / "x.db")
    _seed(db)
    result = runner.invoke(app, ["clear", "--db", db, "--force"])
    assert result.exit_code == 0
    # Store is now empty
    assert SQLiteStore(db).list() == []


def test_stats(tmp_path):
    db = str(tmp_path / "x.db")
    _seed(db)
    result = runner.invoke(app, ["stats", "--db", db])
    assert result.exit_code == 0
    assert "Total checkpoints" in result.output
