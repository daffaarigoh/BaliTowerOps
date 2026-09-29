import sys
import unittest
from pathlib import Path

WORKSPACE_DIR = Path(__file__).resolve().parent.parent
if str(WORKSPACE_DIR) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_DIR))

from fastapi.testclient import TestClient
from api.main import app
from core.security import create_access_token


class TestWorkflowProposalScenarios(unittest.TestCase):

    def setUp(self):
        self.client = TestClient(app)
        self.userb_token = create_access_token({"sub": "userb", "role": "USER", "tenant_id": "HR"})
        self.usera_token = create_access_token({"sub": "usera", "role": "USER", "tenant_id": "INVENTORY"})
        self.admin_token = create_access_token({"sub": "admin", "role": "ADMIN", "tenant_id": "ALL"})
        
        self.headers_b = {"Authorization": f"Bearer {self.userb_token}", "Content-Type": "application/json"}
        self.headers_a = {"Authorization": f"Bearer {self.usera_token}", "Content-Type": "application/json"}
        self.headers_admin = {"Authorization": f"Bearer {self.admin_token}", "Content-Type": "application/json"}

    def test_greeting_halo_does_not_propose_workflow(self):
        """Greeting 'halo' must answer politely without proposing a workflow (can_request_admin is False)."""
        res = self.client.post(
            "/api/agent/custom-prompt",
            headers=self.headers_b,
            json={"prompt": "halo", "destinations": []}
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertFalse(data.get("can_request_admin", False), f"Expected can_request_admin=False for greeting, got {data}")
        msg_lower = data.get("message", "").lower()
        self.assertTrue(any(w in msg_lower for w in ["membantu", "bantu", "halo"]))

    def test_greeting_terimakasih_does_not_propose_workflow(self):
        """Thanks 'terima kasih banyak' must not propose a workflow (can_request_admin is False)."""
        res = self.client.post(
            "/api/agent/custom-prompt",
            headers=self.headers_b,
            json={"prompt": "terima kasih banyak ya bot", "destinations": []}
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertFalse(data.get("can_request_admin", False), f"Expected can_request_admin=False for thanks, got {data}")

    def test_out_of_domain_refusal_does_not_propose_workflow(self):
        """Out of domain prompt must be refused politely without proposing a workflow."""
        res = self.client.post(
            "/api/agent/custom-prompt",
            headers=self.headers_b,
            json={"prompt": "Bagaimana cara membuat rendang daging sapi khas Padang?", "destinations": []}
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data.get("action_type"), "out_of_scope")
        self.assertIn("Maaf", data.get("message", ""))
        self.assertFalse(data.get("can_request_admin", False), "Out of domain queries must NOT offer workflow proposal card")

    def test_operational_unstandardized_query_proposes_workflow(self):
        """
        When user requests to create a new workflow or triggers a blocked guarded action,
        system must intercept with action_type='workflow_not_found' and can_request_admin=True.
        Direct read queries must NOT propose workflow.
        """
        # 1. Direct safe query does NOT propose workflow
        res_direct = self.client.post(
            "/api/agent/custom-prompt",
            headers=self.headers_b,
            json={"prompt": "Periksa daftar masa berlaku lisensi K3 teknisi", "destinations": []}
        )
        self.assertEqual(res_direct.status_code, 200)
        self.assertFalse(res_direct.json().get("can_request_admin", False))

        # 2. Requesting a new workflow DOES propose workflow
        res = self.client.post(
            "/api/agent/custom-prompt",
            headers=self.headers_b,
            json={"prompt": "Tolong buatkan alur kerja baru untuk audit berkala kontrak kerja PKWT teknisi lapangan", "destinations": []}
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data.get("action_type"), "workflow_not_found")
        self.assertTrue(data.get("can_request_admin", False), f"Expected can_request_admin=True, got {data}")
        self.assertIn("kontrak", data.get("prompt_text", "").lower())

    def test_admin_workflow_requests_synchronization(self):
        """
        Admin endpoint /api/auth/admin/workflow-requests must return all submitted requests
        and accurately reflect pending count so admin.html updates immediately.
        """
        # 1. User B submits an operational workflow request
        unique_prompt = "Audit utilisasi konsumsi BBM genset darurat menara regional Denpasar"
        res_sub = self.client.post(
            "/api/workflows/request",
            headers=self.headers_b,
            json={"prompt": unique_prompt, "notes": "Pengajuan dari user B"}
        )
        self.assertEqual(res_sub.status_code, 200)
        req_id = res_sub.json()["request_id"]
        self.assertTrue(req_id.startswith("REQ-"))

        try:
            # 2. Admin fetches requests
            res_admin = self.client.get("/api/auth/admin/workflow-requests", headers=self.headers_admin)
            self.assertEqual(res_admin.status_code, 200)
            admin_data = res_admin.json()
            self.assertEqual(admin_data["status"], "success")
            self.assertGreaterEqual(admin_data["pending_count"], 1)

            found = next((r for r in admin_data["requests"] if r["id"] == req_id), None)
            self.assertIsNotNone(found, f"Request {req_id} must be in admin list")
            self.assertEqual(found["username"], "userb")
            self.assertEqual(found["tenant_id"], "HR")
            self.assertEqual(found["status"], "PENDING")
            self.assertEqual(found["prompt"], unique_prompt)
        finally:
            self.client.delete(f"/api/auth/admin/workflow-requests/{req_id}", headers=self.headers_admin)

    @classmethod
    def tearDownClass(cls):
        try:
            from database.db import get_db_connection
            conn = get_db_connection(read_only=False)
            conn.execute("DELETE FROM workflow_requests WHERE prompt LIKE '%BBM genset darurat menara regional Denpasar%'")
            conn.close()
        except Exception:
            pass


if __name__ == "__main__":
    unittest.main()
