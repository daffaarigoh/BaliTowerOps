import threading
import time
from pathlib import Path
from typing import Any

import duckdb

WORKSPACE_DIR = Path(__file__).resolve().parent.parent
STORAGE_DIR = WORKSPACE_DIR / "storage"
DB_PATH = STORAGE_DIR / "balitower.db"

_db_write_lock = threading.RLock()


def get_db_connection(read_only: bool = False, max_retries: int = 15) -> duckdb.DuckDBPyConnection:
    """Get a connection to the DuckDB inventory database with retry logic for file locks."""
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    
    for attempt in range(max_retries):
        try:
            return duckdb.connect(DB_PATH.as_posix(), read_only=read_only)
        except duckdb.IOException as e:
            if attempt == max_retries - 1:
                raise e
            time.sleep(0.1 + 0.05 * attempt)


class DuckDBManager:
    """
    Centralized manager providing serialized write access and safe connection lifecycle.
    Prevents single-writer lock collisions across concurrent requests.
    """
    @staticmethod
    def execute_write(query: str, params: list[Any] | None = None) -> Any:
        """Executes write transaction with serialized process lock."""
        with _db_write_lock:
            conn = get_db_connection(read_only=False)
            try:
                res = conn.execute(query, params or [])
                conn.commit()
                return res
            finally:
                conn.close()

    @staticmethod
    def execute_read(query: str, params: list[Any] | None = None) -> list[Any]:
        """Executes read query safely and ensures connection closure."""
        conn = get_db_connection(read_only=True)
        try:
            return conn.execute(query, params or []).fetchall()
        finally:
            conn.close()

    @staticmethod
    def transaction(func):
        """Executes a callable that receives a write connection under process-wide write lock."""
        with _db_write_lock:
            conn = get_db_connection(read_only=False)
            try:
                result = func(conn)
                conn.commit()
                return result
            finally:
                conn.close()


def ensure_all_tables_initialized(conn: duckdb.DuckDBPyConnection | None = None) -> None:
    """
    Ensures all core persistent tables across all domains (INVENTORY, HR, FINANCE, ADMIN)
    are formally initialized in DuckDB with proper DDL.
    """
    def _create_tables(c):
        existing_tables = set(r[0] for r in c.execute("SHOW TABLES;").fetchall())

        # 1. Procurement & Inventory Domain (usera / INVENTORY)
        if "orders" not in existing_tables:
            c.execute("""
                CREATE TABLE IF NOT EXISTS orders (
                    order_id VARCHAR PRIMARY KEY,
                    pr_number VARCHAR NOT NULL,
                    item_id VARCHAR NOT NULL,
                    vendor_id VARCHAR NOT NULL,
                    quantity BIGINT NOT NULL,
                    unit_price DOUBLE NOT NULL,
                    total_price DOUBLE NOT NULL,
                    status VARCHAR NOT NULL,
                    tenant_id VARCHAR NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)

        if "purchase_requests" not in existing_tables:
            c.execute("""
                CREATE TABLE IF NOT EXISTS purchase_requests (
                    pr_number VARCHAR PRIMARY KEY,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    status VARCHAR DEFAULT 'PENDING',
                    total_amount BIGINT,
                    items_json TEXT,
                    tenant_id VARCHAR DEFAULT 'INVENTORY'
                );
            """)

        # 2. Workflow Requests & Governance (Admin / Multi-tenant)
        if "workflow_requests" not in existing_tables:
            c.execute("""
                CREATE TABLE IF NOT EXISTS workflow_requests (
                    id VARCHAR PRIMARY KEY,
                    username VARCHAR NOT NULL,
                    tenant_id VARCHAR NOT NULL,
                    prompt TEXT NOT NULL,
                    notes TEXT,
                    status VARCHAR DEFAULT 'PENDING',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    reviewed_by VARCHAR,
                    resolved_workflow_id VARCHAR,
                    title VARCHAR
                );
            """)

    if conn is not None:
        _create_tables(conn)
    else:
        execute_db_write(_create_tables)


def execute_db_write(func_or_query, params: list[Any] | None = None) -> Any:
    """Convenience helper for DuckDBManager write operations."""
    if callable(func_or_query):
        return DuckDBManager.transaction(func_or_query)
    return DuckDBManager.execute_write(func_or_query, params)

