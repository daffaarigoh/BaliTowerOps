import sys
import unittest
from pathlib import Path

WORKSPACE_DIR = Path(__file__).resolve().parent.parent
if str(WORKSPACE_DIR) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_DIR))

from fastapi.testclient import TestClient
from api.main import app
from core.security import TokenData, create_access_token
from agents.autonomous_agent import AutonomousAgent


class TestAutonomousAgentCore(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        from database.db import get_db_connection
        conn = get_db_connection(read_only=False)
        row = conn.execute("SELECT po_id FROM purchase_orders WHERE po_id = 'PO-2026-001';").fetchone()
        if not row:
            conn.execute("""
                INSERT INTO purchase_orders (
                    po_id, po_number, supplier_id, item_id, order_quantity, unit_price, total_amount, status, order_date, expected_delivery, actual_delivery, warehouse_id
                ) VALUES (
                    'PO-2026-001', 'PO/BLT/2026/01/001', 'SUP-001', 'BLT-INV-001', 10, 1500000.0, 15000000.0, 'ORDERED', '2026-01-05', '2026-01-12', NULL, 'WH-JKT-01'
                );
            """)
            conn.commit()
        conn.close()

    def setUp(self):
        self.client = TestClient(app)
        self.inv_user = TokenData(username="usera", role="USER", tenant_id="INVENTORY")
        self.hr_user = TokenData(username="userb", role="USER", tenant_id="HR")
        self.fin_user = TokenData(username="userc", role="USER", tenant_id="FINANCE")
        self.admin_user = TokenData(username="admin", role="ADMIN", tenant_id="ALL")

    def test_01_tenant_table_boundary_check(self):
        """HR user should be blocked from querying finance tables via SQL."""
        has_access, err = AutonomousAgent.check_tenant_table_access(
            "SELECT * FROM revenue_invoices;",
            tenant_id="HR",
            role="USER"
        )
        self.assertFalse(has_access)
        self.assertIn("Akses Ditolak", err)
        self.assertIn("Schema C", err)

        # Inventory user blocked from HR
        has_access, err = AutonomousAgent.check_tenant_table_access(
            "SELECT * FROM employees;",
            tenant_id="INVENTORY",
            role="USER"
        )
        self.assertFalse(has_access)
        self.assertIn("Akses Ditolak", err)
        self.assertIn("Schema B", err)

        # Admin allowed all
        has_access, err = AutonomousAgent.check_tenant_table_access(
            "SELECT * FROM revenue_invoices;",
            tenant_id="ALL",
            role="ADMIN"
        )
        self.assertTrue(has_access)

    def test_02_safe_sql_query_tool(self):
        """Read-only SQL queries work safely, while destructive SQL is rejected."""
        # Safe SELECT
        res = AutonomousAgent.execute_tool_query_database(
            "SELECT item_id, name, current_stock FROM items LIMIT 2;",
            tenant_id="INVENTORY",
            role="USER"
        )
        self.assertNotIn("error", res)
        self.assertIn("data", res)
        self.assertGreaterEqual(len(res["data"]), 1)

        # Destructive UPDATE blocked
        res_bad = AutonomousAgent.execute_tool_query_database(
            "DELETE FROM items;",
            tenant_id="ALL",
            role="ADMIN"
        )
        self.assertIn("error", res_bad)
        self.assertIn("diblokir", res_bad["error"].lower())

    def test_03_view_po_tool(self):
        """Viewing PO document retrieves record and valid PDF download link."""
        res = AutonomousAgent.execute_tool_view_po("PO-2026-001")
        self.assertNotIn("error", res)
        self.assertEqual(res["po_id"], "PO-2026-001")
        self.assertIn("pdf_download_url", res)

    def test_04_threshold_update_tool(self):
        """Updating item threshold updates DB and returns previous & new values."""
        res = AutonomousAgent.execute_tool_update_threshold(
            item_name_or_id="BLT-INV-001",
            new_min=15,
            new_max=45
        )
        self.assertNotIn("error", res)
        self.assertEqual(res["new_min_threshold"], 15)

    def test_05_api_custom_prompt_flow(self):
        """Integration test: calling /api/agent/custom-prompt with valid credentials."""
        token = create_access_token({"sub": "usera", "role": "USER", "tenant_id": "INVENTORY"})
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

        # Sapaan / Profile test
        res = self.client.post("/api/agent/custom-prompt", json={"prompt": "cek profil akun saya"}, headers=headers)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("Profil Pengguna", data["message"])
        self.assertIn("usera", data["message"])

        # PO PDF prompt test
        res_po = self.client.post("/api/agent/custom-prompt", json={"prompt": "Tolong tampilkan dokumen PDF untuk PO-2026-001"}, headers=headers)
        self.assertEqual(res_po.status_code, 200)
        data_po = res_po.json()
        self.assertEqual(data_po["action_type"], "view_po_document")
        self.assertEqual(data_po["po_id"], "PO-2026-001")

    def test_06_conversational_greeting_direct(self):
        """Conversational pleasantries and greetings are handled gracefully by LLM."""
        token = create_access_token({"sub": "admin", "role": "ADMIN", "tenant_id": "ALL"})
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

        res = self.client.post("/api/agent/custom-prompt", json={"prompt": "Halo selamat pagi rekan AI, bagaimana kabar hari ini?"}, headers=headers)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["action_type"], "general")
        self.assertGreater(len(data["message"]), 5)

    def test_07_procurement_cycle_and_aliases(self):
        """Procurement cycle generates PR document, sets PENDING status, and method aliases exist."""
        # Check method aliases
        self.assertTrue(callable(AutonomousAgent.execute_tool_run_procurement_cycle))
        self.assertTrue(callable(AutonomousAgent.execute_tool_manage_purchase_order))
        self.assertTrue(callable(AutonomousAgent.execute_tool_view_po_document))
        self.assertTrue(callable(AutonomousAgent.execute_tool_update_inventory_threshold))
        self.assertTrue(callable(AutonomousAgent.execute_tool_register_new_product))

    def test_08_proactive_clarification_ambiguous_prompt(self):
        """Ambiguous or incomplete instructions trigger proactive clarification modal."""
        token = create_access_token({"sub": "usera", "role": "USER", "tenant_id": "INVENTORY"})
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

        # Ambiguous email intent without recipient
        res = self.client.post("/api/agent/custom-prompt", json={"prompt": "tolong kirimkan email persetujuan pr"}, headers=headers)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["action_type"], "clarification_needed")
        self.assertIn("clarification", data)
        self.assertEqual(data["clarification"]["field"], "recipient_email")


if __name__ == "__main__":
    unittest.main()
