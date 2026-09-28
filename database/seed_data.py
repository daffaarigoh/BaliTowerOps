import json
import sys
from pathlib import Path

import duckdb

# Fix console encoding on Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Base path resolution
from database.db import DB_PATH, STORAGE_DIR, get_db_connection


def init_db(db_path: Path = DB_PATH):
    """Initialize DuckDB database and create relational tables with Multi-Tenant RLS."""
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)

    db_path_str = db_path.as_posix() if isinstance(db_path, Path) else str(db_path).replace("\\", "/")
    print(f"Connecting to DuckDB at: {db_path_str}")
    conn = duckdb.connect(db_path_str)

    # 1. Create users table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id VARCHAR PRIMARY KEY,
            username VARCHAR NOT NULL UNIQUE,
            password_hash VARCHAR NOT NULL,
            role VARCHAR NOT NULL,
            tenant_id VARCHAR NOT NULL
        );
    """)

    # 2. Create system_settings table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS system_settings (
            key VARCHAR PRIMARY KEY,
            value TEXT NOT NULL
        );
    """)

    # 3. Create items table (Legacy / Shared table)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS items (
            item_id VARCHAR PRIMARY KEY,
            name VARCHAR NOT NULL,
            category VARCHAR NOT NULL,
            current_stock INTEGER NOT NULL,
            min_threshold INTEGER NOT NULL,
            max_threshold INTEGER NOT NULL,
            avg_daily_usage FLOAT NOT NULL,
            lead_time_days INTEGER NOT NULL,
            unit VARCHAR NOT NULL,
            tenant_id VARCHAR NOT NULL
        );
    """)

    # Clean up obsolete attendance/overtime table permanently
    conn.execute("DROP TABLE IF EXISTS attendances;")

    # 4. Create vendors table (PR-to-PO procurement suppliers)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS vendors (
            vendor_id VARCHAR NOT NULL,
            name VARCHAR NOT NULL,
            item_id VARCHAR NOT NULL,
            unit_price FLOAT NOT NULL,
            lead_time_days INTEGER NOT NULL,
            rating FLOAT DEFAULT 5.0,
            tenant_id VARCHAR NOT NULL,
            PRIMARY KEY (vendor_id, item_id)
        );
    """)

    # 5. Create orders table (PR requisition items)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            order_id VARCHAR PRIMARY KEY,
            pr_number VARCHAR NOT NULL,
            item_id VARCHAR NOT NULL,
            vendor_id VARCHAR NOT NULL,
            quantity INTEGER NOT NULL,
            unit_price FLOAT NOT NULL,
            total_price FLOAT NOT NULL,
            status VARCHAR NOT NULL,
            tenant_id VARCHAR NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

    # 6. Create purchase_requests table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS purchase_requests (
            pr_number VARCHAR PRIMARY KEY,
            created_at TIMESTAMP,
            status VARCHAR,
            total_amount BIGINT,
            items_json TEXT,
            tenant_id VARCHAR DEFAULT 'ALL'
        );
    """)

    # 7. Create workflows table with tenant_id support
    conn.execute("""
        CREATE TABLE IF NOT EXISTS workflows (
            id VARCHAR PRIMARY KEY,
            name VARCHAR NOT NULL,
            description TEXT,
            business_instruction TEXT NOT NULL,
            compiled_json TEXT NOT NULL,
            tenant_id VARCHAR DEFAULT 'ALL'
        );
    """)

    # Check and migrate workflows table if tenant_id column is missing
    wf_cols = [d[0] for d in conn.execute("DESCRIBE workflows").fetchall()]
    if "tenant_id" not in wf_cols:
        conn.execute("ALTER TABLE workflows ADD COLUMN tenant_id VARCHAR DEFAULT 'ALL';")
        print("[MIGRATION] Added 'tenant_id' column to workflows table.")

    # Check and migrate purchase_orders table if pr_number column is missing
    existing_tables = set(r[0] for r in conn.execute("SHOW TABLES;").fetchall())
    if "purchase_orders" in existing_tables:
        po_cols = [c[0] for c in conn.execute("DESCRIBE purchase_orders;").fetchall()]
        if "pr_number" not in po_cols:
            conn.execute("ALTER TABLE purchase_orders ADD COLUMN pr_number VARCHAR;")
            print("[MIGRATION] Added 'pr_number' column to purchase_orders table.")

    return conn



def seed_data(conn: duckdb.DuckDBPyConnection):
    """Seed base users, system prompts, workflows, and multi-tenant assets."""
    admin_hash = "$2b$12$reziVbiqV1qNNnELI.rGjeE7dJOMBhtT3C6/J3oP4foGl8JaE7ujm" # admin123
    user_hash = "$2b$12$/GHm/zDxQu4BNJ0DX0VBB.Msd3hWRvLEOl.6eo20LIFxXTiYBoLX." # user123

    # Seed Users
    user_count = conn.execute("SELECT COUNT(*) FROM users;").fetchone()[0]
    if user_count == 0:
        users_data = [
            ("USR-001", "admin", admin_hash, "ADMIN", "ALL"),
            ("USR-002", "usera", user_hash, "USER", "INVENTORY"),
            ("USR-003", "userb", user_hash, "USER", "HR"),
            ("USR-004", "userc", user_hash, "USER", "FINANCE")
        ]
        conn.executemany("INSERT INTO users VALUES (?, ?, ?, ?, ?);", users_data)
        print("[OK] Users seeded.")

    # Seed Default System Prompt
    setting_count = conn.execute("SELECT COUNT(*) FROM system_settings WHERE key = 'system_prompt';").fetchone()[0]
    if setting_count == 0:
        default_prompt = (
            "Anda adalah AutoRestock-Agent, asisten AI spesialis manajemen rantai pasok.\n"
            "Anda bertugas menganalisis stok barang dari database. Anda HANYA menangani barang yang dimiliki oleh pengguna yang sedang meminta informasi.\n"
            "Gunakan bahasa Indonesia yang profesional, jelas, dan sangat membantu."
        )
        conn.execute("INSERT INTO system_settings VALUES ('system_prompt', ?)", [default_prompt])
        print("[OK] System Prompt seeded.")

    # Ensure column tenant_id & example_prompts exist in workflows
    try:
        cols = [r[0] for r in conn.execute("DESCRIBE workflows;").fetchall()]
        if "tenant_id" not in cols:
            conn.execute("ALTER TABLE workflows ADD COLUMN tenant_id VARCHAR DEFAULT 'ALL';")
        if "example_prompts" not in cols:
            conn.execute("ALTER TABLE workflows ADD COLUMN example_prompts TEXT DEFAULT '[]';")
    except Exception:
        pass

    # Purge any obsolete/legacy workflow records permanently
    obsolete_ids = ["WF-001", "WF-002", "WF-003", "WF-004", "WF-005", "WF-006", "WF-205F16", "WF-B01", "WF-B04", "WF-C53592", "WF-DBFB7F"]
    placeholders = ",".join(["?"] * len(obsolete_ids))
    conn.execute(f"DELETE FROM workflows WHERE id IN ({placeholders})", obsolete_ids)

    # Seed Canonical Workflows from data/balitower/workflows.json
    workflows_file = Path(__file__).resolve().parent.parent / "data" / "balitower" / "workflows.json"
    workflows_data = []
    if workflows_file.exists():
        with open(workflows_file, "r", encoding="utf-8") as f:
            wfs_json = json.load(f)
        for w in wfs_json:
            compiled_str = json.dumps(w.get("compiled_json", {})) if isinstance(w.get("compiled_json"), dict) else str(w.get("compiled_json", "{}"))
            ex_prompts_str = json.dumps(w.get("example_prompts", []), ensure_ascii=False)
            workflows_data.append((
                w["id"],
                w["name"],
                w.get("description", ""),
                w.get("business_instruction", ""),
                compiled_str,
                w.get("tenant_id", "ALL"),
                ex_prompts_str
            ))

    existing_wf_ids = set([r[0] for r in conn.execute("SELECT id FROM workflows;").fetchall()])
    new_wfs = [w for w in workflows_data if w[0] not in existing_wf_ids]
    if new_wfs:
        conn.executemany("INSERT INTO workflows (id, name, description, business_instruction, compiled_json, tenant_id, example_prompts) VALUES (?, ?, ?, ?, ?, ?, ?);", new_wfs)
    print(f"[OK] Workflows seeded. (Total: {len(conn.execute('SELECT id FROM workflows').fetchall())})")


if __name__ == "__main__":
    conn = init_db()
    seed_data(conn)
    conn.close()
    print("[SUCCESS] Database initialization and heterogeneous data ingestion completed.")
