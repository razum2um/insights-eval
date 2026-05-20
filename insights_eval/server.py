"""Wires the Inspect eval to the *real* insights MCP server.

Production serves the insights MCP server over HTTP at /{tenant}/mcp,
behind a per-tenant bearer JWT. For a self-contained eval we run the
same FastMCP object — the same tools, the same SQL, the same 1024-char
`user_intent` validation — over stdio via scripts/mcp_stdio_launcher.py,
which Inspect launches as a subprocess and speaks MCP to.

The launcher imports `app.*` from the insights repo, so it must run
under that repo's own virtualenv. This module locates both.
"""

from __future__ import annotations

import getpass
import os
from pathlib import Path

from inspect_ai.tool import ToolSource, mcp_server_stdio, mcp_tools

DEFAULT_INSIGHTS_REPO = Path.home() / "src" / "insights"
DEFAULT_EVAL_DB = "insights_eval"


def insights_repo() -> Path:
    """The insights checkout. Override with $INSIGHTS_REPO."""
    return Path(
        os.environ.get("INSIGHTS_REPO", DEFAULT_INSIGHTS_REPO)
    ).expanduser()


def insights_python(repo: Path | None = None) -> Path:
    """The insights repo's venv interpreter — has fastapi/mcp/asyncpg
    and can import `app.*`."""
    repo = repo or insights_repo()
    return repo / ".venv" / "bin" / "python"


def eval_dsn() -> str:
    """DSN for the local Postgres the MCP tools read. Override with
    $INSIGHTS_EVAL_DSN; otherwise a localhost/peer-auth default."""
    env = os.environ.get("INSIGHTS_EVAL_DSN")
    if env:
        return env
    user = os.environ.get("PGUSER") or getpass.getuser()
    host = os.environ.get("PGHOST", "localhost")
    port = os.environ.get("PGPORT", "5432")
    return f"postgresql://{user}@{host}:{port}/{DEFAULT_EVAL_DB}"


def _launcher() -> Path:
    return Path(__file__).resolve().parent.parent / "scripts" / "mcp_stdio_launcher.py"


def insights_mcp_tools(tenant: str = "homey") -> ToolSource:
    """An Inspect ToolSource backed by the insights MCP server, pinned
    to one tenant. Raises early with an actionable message if the
    insights repo / venv / launcher aren't where we expect them."""
    repo = insights_repo()
    py = insights_python(repo)
    launcher = _launcher()

    if not py.exists():
        raise FileNotFoundError(
            f"insights venv interpreter not found at {py}. Set $INSIGHTS_REPO "
            f"to the insights checkout, and run `uv sync` inside it."
        )
    if not launcher.exists():  # pragma: no cover - ships with the repo
        raise FileNotFoundError(f"MCP launcher missing: {launcher}")

    server = mcp_server_stdio(
        name="insights",
        command=str(py),
        args=[str(launcher), "--tenant", tenant],
        env={
            **os.environ,
            "INSIGHTS_REPO": str(repo),
            # db.open_tenant_pools() discovers tenants by this prefix.
            f"INSIGHTS_MCP_DSN_{tenant}": eval_dsn(),
            "PYTHONUNBUFFERED": "1",
        },
    )
    return mcp_tools(server)
