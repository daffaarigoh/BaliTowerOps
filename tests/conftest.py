import sys
import subprocess
from pathlib import Path
try:
    import pytest
except ImportError:
    pytest = None

WORKSPACE_DIR = Path(__file__).resolve().parent.parent
if str(WORKSPACE_DIR) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_DIR))

def seed_test_database_if_needed():
    """
    Guarantees storage/balitower.db exists and contains seeded tables with at least 8 purchase orders.
    """
    db_path = WORKSPACE_DIR / "storage" / "balitower.db"
    generator_script = WORKSPACE_DIR / "scripts" / "generate_balitower_data.py"

    needs_seed = False
    if not db_path.exists() or db_path.stat().st_size < 1000:
        needs_seed = True
    else:
        try:
            from database.db import get_db_connection
            conn = get_db_connection(read_only=True)
            po_count = conn.execute("SELECT COUNT(*) FROM purchase_orders;").fetchone()[0]
            conn.close()
            if po_count < 8:
                needs_seed = True
        except Exception:
            needs_seed = True

    if needs_seed and generator_script.exists():
        subprocess.run([sys.executable, str(generator_script)], check=True)


if pytest is not None:
    @pytest.fixture(scope="session", autouse=True)
    def ensure_test_database():
        """
        Session-wide autouse fixture that guarantees storage/balitower.db
        exists and contains seeded tables before any test runs.
        """
        seed_test_database_if_needed()

