#!/usr/bin/env python3
"""Seed a local Postgres DB the insights MCP server can read.

Creates the database (if missing), applies the insights per-tenant
schema (imported from the insights repo so it can't drift), and writes
a deterministic 30-day synthetic call-activity dataset for tenant
`homey`.

The dataset is shaped so the eval's analytics questions have real
answers:
  * Bob Brown is seeded as the clear worst performer (highest miss
    rate, slowest ring) — so "build a case against Bob" has a target.
  * Evening hours (18:00-08:00) have a higher miss rate than daytime —
    so "show the evening shift underperforms" has a target.

Run with the eval project's venv (needs only asyncpg + the insights
repo on disk for the schema import):

    uv run python scripts/seed_eval_db.py

Override the target DB with $INSIGHTS_EVAL_DSN, the insights checkout
with $INSIGHTS_REPO.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import random
import sys
import uuid
from urllib.parse import urlparse

import asyncpg

from insights_eval.server import eval_dsn, insights_repo

SEED = 42
DAYS = 30
TENANT = "homey"

# (username, extension, display_name, phone, miss_rate, ring_mu)
# ring_mu feeds lognormvariate; exp(7.6)~=2.0s, exp(9.0)~=8.1s.
USERS = [
    ("127318", "6003", "Alice Anderson", "+15551110001", 0.10, 7.6),
    ("127319", "6004", "Bob Brown", "+15551110002", 0.55, 9.0),
    ("127320", "6005", "Carol Chen", "+15551110003", 0.30, 8.0),
    ("127321", "6006", "Daniel Davis", None, 0.18, 7.8),
    ("127322", "6007", "Eve Edwards", None, 0.24, 7.9),
]
DID = "+1234567"

# Volume multiplier per weekday (Mon=0 .. Sun=6).
DOW = [1.0, 1.1, 1.05, 0.9, 0.7, 0.25, 0.2]
# Hour-of-day call weighting (business hours heavier).
HOUR_W = [1] * 6 + [2, 6, 14, 18, 20, 18] + [16, 16, 18, 15, 13, 10] + [7, 4, 3, 2, 2, 1]


def _ring_ms(rng: random.Random, mu: float) -> int:
    return max(500, min(int(rng.lognormvariate(mu, 0.6)), 45000))


def _phone(rng: random.Random) -> str:
    return f"+1{rng.randint(2000000000, 9999999999)}"


def _events(rng: random.Random, now: dt.datetime, user_uuids: dict[str, str]):
    """Yield call_events rows (one event per call)."""
    rows = []
    for username, ext, _name, _phone_no, miss_rate, ring_mu in USERS:
        uid = user_uuids[username]
        for day_offset in range(DAYS):
            day = now - dt.timedelta(days=day_offset)
            volume = int(rng.randint(8, 20) * DOW[day.weekday()])
            for _ in range(volume):
                hour = rng.choices(range(24), weights=HOUR_W)[0]
                occurred = day.replace(
                    hour=hour,
                    minute=rng.randint(0, 59),
                    second=rng.randint(0, 59),
                    microsecond=0,
                )
                if occurred > now:
                    continue
                # Evening / overnight shift misses more calls.
                evening = hour >= 18 or hour < 8
                miss = min(miss_rate + (0.25 if evening else 0.0), 0.9)
                call_uuid = str(uuid.uuid4())
                event_id = str(uuid.uuid4())
                caller_number = _phone(rng)
                if rng.random() < miss:
                    rows.append(
                        (
                            event_id,
                            "l2d.calls.v1.UserNotJoined",
                            call_uuid,
                            uid,
                            TENANT,
                            caller_number,
                            DID,
                            ext,
                            occurred,
                            "eval-seed",
                            None,  # role
                            None,  # ring_duration_ms
                            "NO_ANSWER",  # failure_reason
                        )
                    )
                else:
                    rows.append(
                        (
                            event_id,
                            "l2d.calls.v1.UserJoined",
                            call_uuid,
                            uid,
                            TENANT,
                            caller_number,
                            DID,
                            ext,
                            occurred,
                            "eval-seed",
                            "AGENT_PRIMARY",
                            _ring_ms(rng, ring_mu),
                            None,
                        )
                    )
    return rows


async def _ensure_database(dsn: str) -> None:
    """Create the target database if connecting to it fails."""
    try:
        conn = await asyncpg.connect(dsn=dsn)
        await conn.close()
        return
    except asyncpg.InvalidCatalogNameError:
        pass
    dbname = urlparse(dsn).path.lstrip("/")
    admin = await asyncpg.connect(dsn=dsn, database="postgres")
    try:
        await admin.execute(f'CREATE DATABASE "{dbname}"')
        print(f"created database {dbname!r}")
    finally:
        await admin.close()


async def seed() -> int:
    repo = insights_repo()
    if not (repo / "app" / "schema.py").exists():
        print(f"error: insights repo not found at {repo}", file=sys.stderr)
        return 2
    sys.path.insert(0, str(repo))
    from app.schema import TENANT_SCHEMA_SQL  # noqa: E402 - pure module

    dsn = eval_dsn()
    print(f"seeding {dsn.rsplit('@', 1)[-1]}")
    await _ensure_database(dsn)

    rng = random.Random(SEED)
    now = dt.datetime.now(dt.UTC)
    user_uuids = {u[0]: str(uuid.uuid4()) for u in USERS}

    conn = await asyncpg.connect(dsn=dsn)
    try:
        # Fresh schema every run — same SQL the insights prod bootstrap uses.
        await conn.execute(f'DROP SCHEMA IF EXISTS "{TENANT}" CASCADE;')
        await conn.execute(TENANT_SCHEMA_SQL.format(tenant=TENANT))

        await conn.executemany(
            f'INSERT INTO "{TENANT}".users '
            "(username, extension, phone_number, display_name, uuid) "
            "VALUES ($1, $2, $3, $4, $5)",
            [(u[0], u[1], u[3], u[2], user_uuids[u[0]]) for u in USERS],
        )
        # Every seeded user counts as an active employee (registered now)
        # so the metric tools' active-employee inner join keeps them.
        await conn.executemany(
            f'INSERT INTO "{TENANT}".user_activity (user_id, last_registered_at) VALUES ($1, $2)',
            [(user_uuids[u[0]], now) for u in USERS],
        )

        rows = _events(rng, now, user_uuids)
        await conn.executemany(
            f'INSERT INTO "{TENANT}".call_events '
            "(event_id, event_type, call_uuid, user_id, tenant, caller_number, "
            " did, extension, occurred_at, producer, role, ring_duration_ms, "
            " failure_reason) "
            "VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13)",
            rows,
        )

        for table in ("users", "call_events", "user_activity"):
            await conn.execute(f'ANALYZE "{TENANT}"."{table}"')

        # Production's per-tenant read-only role bakes in `search_path`
        # and `statement_timeout` via ALTER ROLE (app/schema.py,
        # TENANT_RO_ROLE_SQL). The eval connects as a plain role, so we
        # set the same defaults on the database itself — the generic
        # `query` tool then resolves unqualified table names exactly as
        # it would in production.
        dbname = urlparse(dsn).path.lstrip("/")
        await conn.execute(f'ALTER DATABASE "{dbname}" SET search_path TO "{TENANT}"')
        await conn.execute(f"ALTER DATABASE \"{dbname}\" SET statement_timeout TO '5s'")
    finally:
        await conn.close()

    print(f"seeded tenant {TENANT!r}: {len(USERS)} users, {len(rows)} call events ({DAYS} days)")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(seed()))
