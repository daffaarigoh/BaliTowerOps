import sys
import unittest
from pathlib import Path

WORKSPACE_DIR = Path(__file__).resolve().parent.parent
if str(WORKSPACE_DIR) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_DIR))

from fastapi.testclient import TestClient
from api.main import app
from core.security import create_access_token
from database.db import get_db_connection


class TestContextualTenantUnderstanding(unittest.TestCase):

    def setUp(self):
        self.client = TestClient(app)
        self.usera_token = create_access_token({"sub": "usera", "role": "USER", "tenant_id": "INVENTORY"})
        self.userb_token = create_access_token({"sub": "userb", "role": "USER", "tenant_id": "HR"})
        self.userc_token = create_access_token({"sub": "userc", "role": "USER", "tenant_id": "FINANCE"})
        self.admin_token = create_access_token({"sub": "admin", "role": "ADMIN", "tenant_id": "ALL"})

        self.headers_a = {"Authorization": f"Bearer {self.usera_token}", "Content-Type": "application/json"}
        self.headers_b = {"Authorization": f"Bearer {self.userb_token}", "Content-Type": "application/json"}
        self.headers_c = {"Authorization": f"Bearer {self.userc_token}", "Content-Type": "application/json"}
        self.headers_admin = {"Authorization": f"Bearer {self.admin_token}", "Content-Type": "application/json"}

    # =========================================================================
    # USER B (HR) CONTEXT-AWARE UNDERSTANDING TESTS
    # =========================================================================
    def test_userb_hr_mutating_employee_to_finance_succeeds(self):
        """
        User B (HR) mutating an employee to 'Finance & Accounting' with position 'Junior Billing'
        must NOT be blocked by crude 'finance' or 'billing' keywords, because the whole context
        is an HR employee mutation.
        """
        prompt = "Tolong mutasi Budi Santoso ke departemen Finance & Accounting dengan jabatan Junior Billing"
        res = self.client.post("/api/agent/custom-prompt", headers=self.headers_b, json={"prompt": prompt, "destinations": []})
        self.assertEqual(res.status_code, 200)
        data = res.json()
        
        # Must NOT be blocked
        self.assertNotIn("Akses Ditolak", data.get("message", ""))
        self.assertNotEqual(data.get("action_type"), "out_of_scope")
        self.assertEqual(data.get("action_type"), "hr_mutation")

        # Verify DuckDB record is actually updated
        conn = get_db_connection(read_only=True)
        try:
            row = conn.execute("SELECT department, job_title FROM employees WHERE full_name = 'Budi Santoso';").fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row[0], "Finance & Accounting")
            self.assertEqual(row[1], "Junior Billing")
        finally:
            conn.close()

    def test_userb_hr_blocked_when_attempting_inventory_procurement(self):
        """User B (HR) attempting an explicit Inventory procurement PR must be blocked."""
        prompt = "Tolong buatkan PR pengadaan kabel fiber optik 24 core"
        res = self.client.post("/api/agent/custom-prompt", headers=self.headers_b, json={"prompt": prompt, "destinations": []})
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data.get("action_type"), "out_of_scope")
        self.assertIn("Akses Ditolak", data.get("message", ""))
        self.assertIn("Schema A (Divisi Logistik", data.get("message", ""))

    def test_userb_hr_blocked_when_attempting_finance_revenue_report(self):
        """User B (HR) attempting an explicit Finance revenue query must be blocked."""
        prompt = "tampilkan laporan pendapatan sewa menara"
        res = self.client.post("/api/agent/custom-prompt", headers=self.headers_b, json={"prompt": prompt, "destinations": []})
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data.get("action_type"), "out_of_scope")
        self.assertIn("Akses Ditolak", data.get("message", ""))
        self.assertIn("Schema C (Divisi Keuangan)", data.get("message", ""))

    # =========================================================================
    # USER A (INVENTORY) CONTEXT-AWARE UNDERSTANDING TESTS
    # =========================================================================
    def test_usera_inventory_allowed_power_equipment_query(self):
        """
        User A (Inventory) checking stock for power cables and batteries for shelter sites
        must NOT be blocked by electrical or shelter keywords.
        """
        prompt = "Cek persediaan kabel power listrik dan baterai untuk shelter Telkomsel"
        res = self.client.post("/api/agent/custom-prompt", headers=self.headers_a, json={"prompt": prompt, "destinations": []})
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertNotIn("Akses Ditolak", data.get("message", ""))
        self.assertNotEqual(data.get("action_type"), "out_of_scope")

    def test_usera_inventory_blocked_when_attempting_hr_leave_approval(self):
        """User A (Inventory) attempting an explicit HR leave approval must be blocked."""
        prompt = "Setujui permohonan cuti teknisi Dewi Lestari"
        res = self.client.post("/api/agent/custom-prompt", headers=self.headers_a, json={"prompt": prompt, "destinations": []})
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data.get("action_type"), "out_of_scope")
        self.assertIn("Akses Ditolak", data.get("message", ""))
        self.assertIn("Schema B (Divisi HR)", data.get("message", ""))

    def test_usera_inventory_blocked_when_attempting_finance_invoices(self):
        """User A (Inventory) attempting an explicit Finance invoice query must be blocked."""
        prompt = "tampilkan laporan pendapatan sewa menara"
        res = self.client.post("/api/agent/custom-prompt", headers=self.headers_a, json={"prompt": prompt, "destinations": []})
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data.get("action_type"), "out_of_scope")
        self.assertIn("Akses Ditolak", data.get("message", ""))
        self.assertIn("Schema C (Divisi Keuangan)", data.get("message", ""))

    # =========================================================================
    # USER C (FINANCE) CONTEXT-AWARE UNDERSTANDING TESTS
    # =========================================================================
    def test_userc_finance_allowed_warehouse_land_lease_query(self):
        """
        User C (Finance) checking land lease expenses for warehouse Surabaya
        must NOT be blocked by the word 'gudang', because lease audit is Finance's domain.
        """
        prompt = "Berapa total tagihan sewa lahan gudang Surabaya?"
        res = self.client.post("/api/agent/custom-prompt", headers=self.headers_c, json={"prompt": prompt, "destinations": []})
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertNotIn("Akses Ditolak", data.get("message", ""))
        self.assertNotEqual(data.get("action_type"), "out_of_scope")

    def test_userc_finance_blocked_when_attempting_inventory_procurement(self):
        """User C (Finance) attempting an explicit material procurement PR must be blocked."""
        prompt = "Buatkan PR pengadaan material kabel FO"
        res = self.client.post("/api/agent/custom-prompt", headers=self.headers_c, json={"prompt": prompt, "destinations": []})
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data.get("action_type"), "out_of_scope")
        self.assertIn("Akses Ditolak", data.get("message", ""))
        self.assertIn("Schema A (Divisi Logistik", data.get("message", ""))

    def test_userc_finance_blocked_when_attempting_hr_leave_approval(self):
        """User C (Finance) attempting an explicit HR leave approval must be blocked."""
        prompt = "Setujui permohonan cuti teknisi Dewi Lestari"
        res = self.client.post("/api/agent/custom-prompt", headers=self.headers_c, json={"prompt": prompt, "destinations": []})
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data.get("action_type"), "out_of_scope")
        self.assertIn("Akses Ditolak", data.get("message", ""))
        self.assertIn("Schema B (Divisi HR)", data.get("message", ""))

    # =========================================================================
    # ADMIN UNRESTRICTED FULL ACCESS TESTS
    # =========================================================================
    def test_admin_unrestricted_across_all_domains(self):
        """Super Admin has full unrestricted access across all divisions and operations."""
        # 1. Admin can mutate employee to any department
        res_mut = self.client.post(
            "/api/agent/custom-prompt",
            headers=self.headers_admin,
            json={"prompt": "Tolong mutasi Budi Santoso ke departemen Project Engineering dengan jabatan Junior CME", "destinations": []}
        )
        self.assertEqual(res_mut.status_code, 200)
        self.assertNotIn("Akses Ditolak", res_mut.json().get("message", ""))

        # 2. Admin can query finance revenue
        res_fin = self.client.post(
            "/api/agent/custom-prompt",
            headers=self.headers_admin,
            json={"prompt": "tampilkan laporan pendapatan sewa menara", "destinations": []}
        )
        self.assertEqual(res_fin.status_code, 200)
        self.assertNotIn("Akses Ditolak", res_fin.json().get("message", ""))


if __name__ == "__main__":
    unittest.main()
