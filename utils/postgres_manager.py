"""
Postgres connection manager for the marketing-platform.

All database access must go through this module. Direct psycopg2 usage
elsewhere is prohibited — extend this file instead (see CONSTITUTION.md: DRY).

RLS enforcement contract:
  Every query that touches tenant data must use execute_tenant_query(), which
  sets the Postgres session variable `app.current_tenant_id` inside the
  transaction before the query runs. RLS policies on tenant-scoped tables
  must reference current_setting('app.current_tenant_id') to enforce isolation.
"""

import os
import logging
from contextlib import contextmanager
from contextvars import ContextVar, Token
from typing import Any

import psycopg2
import psycopg2.extras
from psycopg2.pool import ThreadedConnectionPool

logger = logging.getLogger(__name__)

# Per-request tenant context — safe for both threaded and async (asyncio) runtimes.
# The middleware sets this at the start of every request; it is automatically
# isolated per-task/coroutine, so there is no cross-request leakage.
_current_tenant_id: ContextVar[str | None] = ContextVar("current_tenant_id", default=None)


def set_tenant_context(tenant_id: str) -> Token:
    """Set the active tenant for the current request context. Returns a reset token."""
    return _current_tenant_id.set(tenant_id)


def reset_tenant_context(token: Token) -> None:
    """Clear the tenant context using the token returned by set_tenant_context."""
    _current_tenant_id.reset(token)


def get_tenant_context() -> str | None:
    """Return the tenant_id bound to the current request context, or None."""
    return _current_tenant_id.get()

_pool: ThreadedConnectionPool | None = None


def _build_dsn() -> str:
    """Build a DSN from environment variables."""
    return os.environ.get("DATABASE_URL", "postgresql://localhost:5432/postgres")


def _get_pool() -> ThreadedConnectionPool:
    """Return the module-level connection pool, initialising it on first call."""
    global _pool
    if _pool is None:
        min_conn = int(os.environ.get("PG_POOL_MIN", "1"))
        max_conn = int(os.environ.get("PG_POOL_MAX", "10"))

        conn = psycopg2.connect(os.getenv("DATABASE_URL"))
        print(f"Connected to database: {conn.info.dbname}")

        _pool = ThreadedConnectionPool(min_conn, max_conn, dsn=_build_dsn())
        logger.info("Postgres connection pool initialised (min=%d, max=%d).", min_conn, max_conn)
    return _pool


@contextmanager
def get_connection():
    """
    Yield a raw psycopg2 connection from the pool.

    Usage:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(...)
            conn.commit()

    The connection is returned to the pool on exit whether or not an
    exception was raised. Callers are responsible for commit/rollback.
    """
    pool = _get_pool()
    conn = pool.getconn()
    try:
        yield conn
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)


@contextmanager
def get_db_cursor():
    """
    Yield a RealDictCursor for direct use by callers that manage their own SQL.

    Commits on clean exit; rolls back and re-raises on any exception.
    The underlying connection is returned to the pool in both cases.

    Usage:
        with get_db_cursor() as cur:
            cur.execute("SELECT ...")
            rows = cur.fetchall()   # commit happens automatically on exit
    """
    with get_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            try:
                yield cur
                conn.commit()
            except Exception:
                conn.rollback()
                raise


def execute_tenant_query(
    query: str,
    tenant_id: str,
    params: tuple | list | dict | None = None,
) -> list[dict[str, Any]]:
    """
    Execute a query within a tenant-scoped transaction.

    Before running `query`, this wrapper issues:

        SET LOCAL app.current_tenant_id = '<tenant_id>';

    inside the same transaction. Postgres RLS policies that reference
    ``current_setting('app.current_tenant_id')`` will therefore only expose
    rows belonging to this tenant.  ``SET LOCAL`` scopes the variable to the
    current transaction, so it is automatically cleared on commit or rollback —
    there is no risk of tenant context leaking across requests.

    Args:
        query:     The SQL query to execute. Use %s / %(name)s placeholders.
        tenant_id: The tenant whose context must be active for this query.
        params:    Query parameters passed to psycopg2 (tuple, list, or dict).

    Returns:
        A list of rows as dicts (column_name -> value). Empty list for
        statements that produce no rows (INSERT/UPDATE/DELETE).

    Raises:
        ValueError: If tenant_id is empty or None.
        psycopg2.Error: Re-raised on any database error after rollback.
    """
    if not tenant_id:
        raise ValueError("tenant_id must be a non-empty string.")

    with get_connection() as conn:
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                # Enforce RLS: set session variable before the business query.
                cur.execute(
                    "SET LOCAL app.current_tenant_id = %s;",
                    (str(tenant_id),),
                )

                cur.execute(query, params)
                conn.commit()

                try:
                    rows = cur.fetchall()
                    return [dict(row) for row in rows]
                except psycopg2.ProgrammingError:
                    # Statement produced no result set (e.g. INSERT without RETURNING).
                    return []

        except psycopg2.Error:
            conn.rollback()
            logger.exception(
                "Query failed for tenant_id=%r. Transaction rolled back.", tenant_id
            )
            raise
