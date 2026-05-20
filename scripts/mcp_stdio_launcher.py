#!/usr/bin/env python3
"""Run the insights FastMCP server over stdio, for the Inspect eval.

Production serves this MCP server over HTTP at /{tenant}/mcp, gated by
a per-tenant bearer JWT (insights `app/mcp_auth.py`). This eval's
subject is audit-field honesty, *not* the auth/tenancy layer, so this
launcher runs the very same FastMCP object (`app/mcp_server.py` — tools,
SQL, and the 1024-char `user_intent` Pydantic validation all unchanged)
over stdio, with the tenant pinned for the lifetime of the process.

What it skips vs. production: the bearer-token check and the
per-request `current_tenant` reset. What it keeps: every tool body, the
real per-tenant asyncpg pool, and the real argument validation — i.e.
everything the eval actually measures.

Must run under the insights repo's own virtualenv (it imports `app.*`).
Required env:
    INSIGHTS_REPO            path to the insights checkout
    INSIGHTS_MCP_DSN_<t>     DSN for tenant <t>'s read pool
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tenant", required=True, help="tenant to serve")
    args = parser.parse_args()

    repo = os.environ.get("INSIGHTS_REPO")
    if not repo:
        sys.exit("mcp_stdio_launcher: INSIGHTS_REPO env var is not set")
    if not os.path.isdir(repo):
        sys.exit(f"mcp_stdio_launcher: INSIGHTS_REPO does not exist: {repo}")
    sys.path.insert(0, repo)

    try:
        from app import db, mcp_server
        from app.mcp_auth import current_tenant
    except ImportError as exc:  # pragma: no cover - environment issue
        sys.exit(
            f"mcp_stdio_launcher: cannot import insights app from {repo} "
            f"({exc}). Run this under the insights repo's venv."
        )

    async def run() -> None:
        # Discovers tenants from INSIGHTS_MCP_DSN_* and opens a pool each.
        await db.open_tenant_pools()
        if args.tenant not in db.configured_mcp_tenants():
            sys.exit(
                f"mcp_stdio_launcher: no DB pool for tenant {args.tenant!r} — "
                f"set INSIGHTS_MCP_DSN_{args.tenant} to a valid DSN"
            )
        # Production sets this per-request inside MCPAuthMiddleware. Here
        # one process serves exactly one tenant, so we set it once: the
        # ContextVar is captured by every tool-call task FastMCP spawns.
        current_tenant.set(args.tenant)
        try:
            await mcp_server.mcp.run_stdio_async()
        finally:
            await db.close_tenant_pools()

    asyncio.run(run())


if __name__ == "__main__":
    main()
