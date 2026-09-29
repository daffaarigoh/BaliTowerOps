import sys
import unittest
from pathlib import Path

WORKSPACE_DIR = Path(__file__).resolve().parent.parent
if str(WORKSPACE_DIR) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_DIR))

from fastapi.testclient import TestClient
from api.main import app
from core.security import TokenData, get_current_admin, get_current_user, create_access_token


class TestWorkflowRequests(unittest.TestCase):

    def setUp(self):
        self.client = TestClient(app)
        self.user_token = create_access_token({"sub": "usera", "role": "USER", "tenant_id": "INVENTORY"})
        self.admin_token = create_access_token({"sub": "admin", "role": "ADMIN", "tenant_id": "ALL"})
        self.user_headers = {"Authorization": f"Bearer {self.user_token}", "Content-Type": "application/json"}
        self.admin_headers = {"Authorization": f"Bearer {self.admin_token}", "Content-Type": "application/json"}
        self.created_req_ids = []

    def tearDown(self):
        for req_id in getattr(self, "created_req_ids", []):
            try:
                self.client.delete(f"/api/auth/admin/workflow-requests/{req_id}", headers=self.admin_headers)
            except Exception:
                pass

    @classmethod
    def tearDownClass(cls):
        """Guarantee no test workflow requests linger in the database."""
        try:
            from database.db import get_db_connection
            conn = get_db_connection(read_only=False)
            conn.execute("""
                DELETE FROM workflow_requests 
                WHERE prompt IN (
                    'Tolong buatkan alur verifikasi genset diesel site per bulan',
                    'Permintaan tes tolak',
                    'Permintaan akan dihapus',
                    'Permintaan batch 1',
                    'Permintaan batch 2'
                );
            """)
            conn.close()
        except Exception:
            pass

    def test_regular_user_cannot_create_workflow_directly(self):
        """Ensure standard users (USER role) are blocked from creating workflows directly."""
        payload = {
            "name": "Bypass Workflow Creation",
            "description": "Attempt by non-admin",
            "business_instruction": "Tarik semua data barang",
            "tenant_id": "INVENTORY"
        }
        res = self.client.post("/api/auth/admin/workflows", json=payload, headers=self.user_headers)
        self.assertEqual(res.status_code, 403)

    def test_workflow_request_lifecycle(self):
        """
        End-to-end lifecycle:
        1. User submits workflow request
        2. Admin views pending requests and sees badge count
        3. Admin creates workflow resolving the request
        4. Request status updates to COMPLETED
        """
        # 1. User submits a request
        req_payload = {
            "prompt": "Tolong buatkan alur verifikasi genset diesel site per bulan",
            "notes": "Dibutuhkan untuk audit rutin tim operasional"
        }
        res_submit = self.client.post("/api/workflows/request", json=req_payload, headers=self.user_headers)
        self.assertEqual(res_submit.status_code, 200)
        submit_data = res_submit.json()
        self.assertEqual(submit_data["status"], "success")
        req_id = submit_data["request_id"]
        self.created_req_ids.append(req_id)
        self.assertTrue(req_id.startswith("REQ-"))

        wf_id = None
        try:
            # 2. Admin retrieves requests list
            res_admin_list = self.client.get("/api/auth/admin/workflow-requests", headers=self.admin_headers)
            self.assertEqual(res_admin_list.status_code, 200)
            list_data = res_admin_list.json()
            self.assertGreaterEqual(list_data["pending_count"], 1)
            found_req = next((r for r in list_data["requests"] if r["id"] == req_id), None)
            self.assertIsNotNone(found_req)
            self.assertEqual(found_req["username"], "usera")
            self.assertEqual(found_req["tenant_id"], "INVENTORY")
            self.assertEqual(found_req["status"], "PENDING")

            # 3. Admin creates a workflow to resolve this request
            unique_wf_name = f"Audit Utilisasi Genset Bulanan {req_id}"
            wf_payload = {
                "name": unique_wf_name,
                "description": "Pemeriksaan konsumsi solar dan genset site",
                "business_instruction": "Tarik data barang genset dan saldo stok barang gudang logistik",
                "tenant_id": "INVENTORY",
                "resolving_request_id": req_id
            }
            res_create_wf = self.client.post("/api/auth/admin/workflows", json=wf_payload, headers=self.admin_headers)
            self.assertEqual(res_create_wf.status_code, 200)
            created_wf_data = res_create_wf.json()
            wf_id = created_wf_data["workflow_id"]

            # 4. Check that request is now COMPLETED
            res_after = self.client.get("/api/auth/admin/workflow-requests", headers=self.admin_headers)
            self.assertEqual(res_after.status_code, 200)
            updated_req = next((r for r in res_after.json()["requests"] if r["id"] == req_id), None)
            self.assertIsNotNone(updated_req)
            self.assertEqual(updated_req["status"], "COMPLETED")
            self.assertEqual(updated_req["resolved_workflow_id"], wf_id)
        finally:
            # Cleanup created workflow and request to keep test environment pristine
            if wf_id:
                self.client.delete(f"/api/auth/admin/workflows/{wf_id}", headers=self.admin_headers)
            self.client.delete(f"/api/auth/admin/workflow-requests/{req_id}", headers=self.admin_headers)

    def test_admin_manual_status_update(self):
        """Admin can reject or update request status."""
        res_submit = self.client.post(
            "/api/workflows/request", 
            json={"prompt": "Permintaan tes tolak"}, 
            headers=self.user_headers
        )
        self.assertEqual(res_submit.status_code, 200)
        req_id = res_submit.json()["request_id"]
        self.created_req_ids.append(req_id)

        try:
            # Admin rejects
            res_reject = self.client.post(
                f"/api/auth/admin/workflow-requests/{req_id}/status",
                json={"status": "REJECTED"},
                headers=self.admin_headers
            )
            self.assertEqual(res_reject.status_code, 200)

            # Verify
            res_list = self.client.get("/api/auth/admin/workflow-requests", headers=self.admin_headers)
            req = next((r for r in res_list.json()["requests"] if r["id"] == req_id), None)
            self.assertEqual(req["status"], "REJECTED")
        finally:
            self.client.delete(f"/api/auth/admin/workflow-requests/{req_id}", headers=self.admin_headers)

    def test_workflow_creation_prompt_detection_for_user(self):
        """User asking to create workflow is intercepted with workflow_not_found & can_request_admin."""
        prompt_payload = {
            "prompt": "Tolong buatkan workflow baru untuk rekap invoice vendor",
            "destinations": [],
            "history": []
        }
        res = self.client.post("/api/agent/custom-prompt", json=prompt_payload, headers=self.user_headers)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["action_type"], "workflow_not_found")
        self.assertTrue(data.get("can_request_admin"))

    def test_admin_delete_single_workflow_request(self):
        """Admin can delete an individual workflow request."""
        # 1. Create request
        res = self.client.post("/api/workflows/request", json={"prompt": "Permintaan akan dihapus"}, headers=self.user_headers)
        req_id = res.json()["request_id"]

        # 2. Admin deletes this request
        del_res = self.client.delete(f"/api/auth/admin/workflow-requests/{req_id}", headers=self.admin_headers)
        self.assertEqual(del_res.status_code, 200)
        self.assertEqual(del_res.json()["status"], "success")

        # 3. Verify it is gone
        list_res = self.client.get("/api/auth/admin/workflow-requests", headers=self.admin_headers)
        ids = [r["id"] for r in list_res.json()["requests"]]
        self.assertNotIn(req_id, ids)

    def test_admin_clear_all_workflow_requests(self):
        """Admin can clear all workflow requests at once."""
        # 1. Create a few requests
        self.client.post("/api/workflows/request", json={"prompt": "Permintaan batch 1"}, headers=self.user_headers)
        self.client.post("/api/workflows/request", json={"prompt": "Permintaan batch 2"}, headers=self.user_headers)

        # 2. Admin clears all
        clear_res = self.client.delete("/api/auth/admin/workflow-requests", headers=self.admin_headers)
        self.assertEqual(clear_res.status_code, 200)
        self.assertEqual(clear_res.json()["status"], "success")
        self.assertGreaterEqual(clear_res.json()["deleted_count"], 2)

        # 3. Verify table is completely empty
        list_res = self.client.get("/api/auth/admin/workflow-requests", headers=self.admin_headers)
        self.assertEqual(len(list_res.json()["requests"]), 0)
        self.assertEqual(list_res.json()["pending_count"], 0)

    def test_non_admin_cannot_delete_or_clear_requests(self):
        """Standard user role cannot delete or clear workflow requests."""
        del_res = self.client.delete("/api/auth/admin/workflow-requests/REQ-123456", headers=self.user_headers)
        self.assertEqual(del_res.status_code, 403)

        clear_res = self.client.delete("/api/auth/admin/workflow-requests", headers=self.user_headers)
        self.assertEqual(clear_res.status_code, 403)

    def test_admin_reset_workflows_to_defaults(self):
        """Admin can call reset-defaults which safely restores missing workflows (does not delete existing ones)."""
        # Get count before
        before_res = self.client.get("/api/auth/admin/workflows", headers=self.admin_headers)
        count_before = len(before_res.json())
        self.assertGreater(count_before, 0)

        # Call reset - should succeed without deleting anything
        res = self.client.post("/api/auth/admin/workflows/reset-defaults", headers=self.admin_headers)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["status"], "success")

        # Count should be >= before (only adds, never removes)
        after_res = self.client.get("/api/auth/admin/workflows", headers=self.admin_headers)
        count_after = len(after_res.json())
        self.assertGreaterEqual(count_after, count_before)


if __name__ == "__main__":
    unittest.main()
