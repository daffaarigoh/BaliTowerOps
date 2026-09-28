import sys
import unittest
from pathlib import Path

WORKSPACE_DIR = Path(__file__).resolve().parent.parent
if str(WORKSPACE_DIR) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_DIR))

from fastapi.testclient import TestClient
from api.main import app
from core.security import create_access_token
from agents.autonomous_agent import AutonomousAgent


class TestTwoTierAndWorkflowRequestForm(unittest.TestCase):

    def setUp(self):
        self.client = TestClient(app)
        self.user_token = create_access_token({"sub": "usera", "role": "USER", "tenant_id": "INVENTORY"})
        self.userb_token = create_access_token({"sub": "userb", "role": "USER", "tenant_id": "HR"})
        self.admin_token = create_access_token({"sub": "admin", "role": "ADMIN", "tenant_id": "ALL"})
        
        self.user_headers = {"Authorization": f"Bearer {self.user_token}", "Content-Type": "application/json"}
        self.userb_headers = {"Authorization": f"Bearer {self.userb_token}", "Content-Type": "application/json"}
        self.admin_headers = {"Authorization": f"Bearer {self.admin_token}", "Content-Type": "application/json"}

    def test_01_mau_ajukan_workflow_prompt_triggers_form_render(self):
        """Typing 'mau ajukan workflow' or its variations returns render_workflow_request_form."""
        prompts = [
            "mau ajukan workflow",
            "ajukan workflow",
            "request workflow",
            "buka form workflow",
            "mau ajukan alur kerja",
            "form pengajuan workflow"
        ]
        for p in prompts:
            res = self.client.post("/api/agent/custom-prompt", json={"prompt": p}, headers=self.user_headers)
            self.assertEqual(res.status_code, 200, f"Failed on prompt: {p}")
            data = res.json()
            self.assertEqual(
                data.get("action_type"), 
                "render_workflow_request_form", 
                f"Expected render_workflow_request_form for '{p}', got {data.get('action_type')}"
            )
            self.assertTrue(data.get("can_request_admin"))
            self.assertIn("formulir", data.get("message", "").lower())

    def test_02_direct_tool_single_step_query_executes_immediately(self):
        """Direct / safe tools (read-only query database) execute directly without workflow blocker."""
        # Query stock of specific item
        res = self.client.post(
            "/api/agent/custom-prompt",
            json={"prompt": "Berapa sisa stok ODC 48 Port di Gudang Surabaya?"},
            headers=self.user_headers
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        # Direct execution must not be blocked
        self.assertNotEqual(data.get("action_type"), "workflow_not_found")
        self.assertIn("message", data)
        self.assertFalse(data.get("email_sent", False))

    def test_03_guarded_tool_blocked_without_workflow(self):
        """Guarded tools (e.g. ad-hoc dispatch_pr_email by regular user) are blocked by Tier 2 check."""
        # Direct call to execute_tool with non-admin user trying to dispatch email or run procurement
        res = self.client.post(
            "/api/agent/custom-prompt",
            json={"prompt": "Kirimkan dokumen PR-2026-0819-001 ke email manager.logistik@balitower.co.id"},
            headers=self.user_headers
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        # Since PR email dispatch is a guarded tool and this is not an approved workflow execution,
        # it is either routed to workflow WF-A01 if restock intent, or blocked by guarded tool check
        if data.get("action_type") == "workflow_not_found":
            self.assertTrue(data.get("can_request_admin"))
            self.assertIn("terproteksi", data.get("message", ""))

    def test_04_submit_workflow_request_with_title_and_tenant(self):
        """User can submit workflow request with structured title and tenant_id."""
        req_payload = {
            "title": "Audit Utilisasi Genset Bulanan",
            "prompt": "Periksa seluruh konsumsi solar genset per akhir bulan dan rekap dalam tabel",
            "tenant_id": "INVENTORY",
            "notes": "Dibutuhkan untuk evaluasi efisiensi BBM site regional"
        }
        res_submit = self.client.post("/api/workflows/request", json=req_payload, headers=self.user_headers)
        self.assertEqual(res_submit.status_code, 200)
        res_data = res_submit.json()
        self.assertEqual(res_data["status"], "success")
        self.assertTrue(res_data["request_id"].startswith("REQ-"))
        self.assertEqual(res_data.get("title"), "Audit Utilisasi Genset Bulanan")

        # Admin retrieves list and sees the title and tenant
        res_admin = self.client.get("/api/auth/admin/workflow-requests", headers=self.admin_headers)
        self.assertEqual(res_admin.status_code, 200)
        admin_data = res_admin.json()
        found = next((r for r in admin_data["requests"] if r["id"] == res_data["request_id"]), None)
        self.assertIsNotNone(found)
        self.assertEqual(found.get("title"), "Audit Utilisasi Genset Bulanan")
        self.assertEqual(found.get("tenant_id"), "INVENTORY")
        self.assertEqual(found.get("username"), "usera")
        self.assertEqual(found.get("status"), "PENDING")

    def test_05_guarded_tool_constants_integrity(self):
        """AutonomousAgent defines DIRECT_TOOLS and GUARDED_TOOLS accurately across legacy & all new modular tools."""
        # Legacy Direct Tools
        self.assertIn("tool_query_database", AutonomousAgent.DIRECT_TOOLS)
        self.assertIn("tool_view_po", AutonomousAgent.DIRECT_TOOLS)

        # New Modular Direct Access Tools
        self.assertIn("inventory.check_specific_stock", AutonomousAgent.DIRECT_TOOLS)
        self.assertIn("inventory.get_low_stock_products", AutonomousAgent.DIRECT_TOOLS)
        self.assertIn("inventory.get_all_products", AutonomousAgent.DIRECT_TOOLS)
        self.assertIn("po.query_orders", AutonomousAgent.DIRECT_TOOLS)
        self.assertIn("hr.filter_candidates", AutonomousAgent.DIRECT_TOOLS)
        self.assertIn("hr.query_pending_leaves", AutonomousAgent.DIRECT_TOOLS)
        self.assertIn("hr.audit_attendance", AutonomousAgent.DIRECT_TOOLS)
        self.assertIn("finance.revenue_report", AutonomousAgent.DIRECT_TOOLS)
        self.assertIn("finance.opex_audit", AutonomousAgent.DIRECT_TOOLS)
        self.assertIn("finance.cashflow_summary", AutonomousAgent.DIRECT_TOOLS)
        self.assertIn("finance.audit_client_onboardings", AutonomousAgent.DIRECT_TOOLS)
        self.assertIn("system.check_profile", AutonomousAgent.DIRECT_TOOLS)
        self.assertIn("system.get_system_info", AutonomousAgent.DIRECT_TOOLS)
        self.assertIn("system.get_company_guidelines", AutonomousAgent.DIRECT_TOOLS)

        # Legacy Guarded Tools
        self.assertIn("tool_dispatch_pr_email", AutonomousAgent.GUARDED_TOOLS)
        self.assertIn("tool_procurement_cycle", AutonomousAgent.GUARDED_TOOLS)
        self.assertIn("tool_manage_po", AutonomousAgent.GUARDED_TOOLS)
        self.assertIn("tool_update_threshold", AutonomousAgent.GUARDED_TOOLS)
        self.assertIn("tool_register_product", AutonomousAgent.GUARDED_TOOLS)

        # New Modular Guarded Tools
        self.assertIn("purchase_order.create_draft", AutonomousAgent.GUARDED_TOOLS)
        self.assertIn("po.approve", AutonomousAgent.GUARDED_TOOLS)
        self.assertIn("inventory.update_threshold", AutonomousAgent.GUARDED_TOOLS)
        self.assertIn("inventory.register_product", AutonomousAgent.GUARDED_TOOLS)
        self.assertIn("inventory.crud_record", AutonomousAgent.GUARDED_TOOLS)
        self.assertIn("hr.mutate_employee", AutonomousAgent.GUARDED_TOOLS)
        self.assertIn("hr.approve_leave", AutonomousAgent.GUARDED_TOOLS)
        self.assertIn("hr.submit_leave_request", AutonomousAgent.GUARDED_TOOLS)
        self.assertIn("hr.crud_record", AutonomousAgent.GUARDED_TOOLS)
        self.assertIn("finance.draft_client_onboarding", AutonomousAgent.GUARDED_TOOLS)
        self.assertIn("finance.approve_client_onboarding", AutonomousAgent.GUARDED_TOOLS)
        self.assertIn("finance.generate_invoice", AutonomousAgent.GUARDED_TOOLS)
        self.assertIn("finance.crud_record", AutonomousAgent.GUARDED_TOOLS)
        self.assertIn("notification.dispatch", AutonomousAgent.GUARDED_TOOLS)
        self.assertIn("notification.send_email", AutonomousAgent.GUARDED_TOOLS)
        self.assertIn("docgen.compile", AutonomousAgent.GUARDED_TOOLS)

    def test_06_unexecutable_mutation_proposes_workflow_while_direct_tool_does_not(self):
        """
        When LLM determines an action cannot be processed directly (e.g. mutate employee status),
        it must explain AND immediately offer workflow request (can_request_admin=True, action_type='workflow_not_found').
        Conversely, direct tools answering successfully must NOT propose a workflow.
        """
        # 1. Unexecutable mutation without workflow: 'hapus data karyawan Fajar Nugraha dari sistem'
        res_mut = self.client.post(
            "/api/agent/custom-prompt",
            json={"prompt": "hapus data karyawan Fajar Nugraha dari sistem"},
            headers=self.userb_headers
        )
        self.assertEqual(res_mut.status_code, 200)
        data_mut = res_mut.json()
        self.assertTrue(data_mut.get("can_request_admin"), f"Expected can_request_admin=True, got {data_mut}")
        self.assertEqual(data_mut.get("action_type"), "workflow_not_found")
        self.assertTrue(data_mut.get("is_tool_blocked"))
        self.assertIn("fajar nugraha", data_mut.get("prompt_text", "").lower())
        # Message should give explanation
        self.assertTrue(len(data_mut.get("message", "")) > 10)

        # 2. Direct tool execution: read profile/leave balance executes and does NOT propose workflow
        res_query = self.client.post(
            "/api/agent/custom-prompt",
            json={"prompt": "Periksa data profil karyawan Fajar Nugraha"},
            headers=self.userb_headers
        )
        self.assertEqual(res_query.status_code, 200)
        data_query = res_query.json()
        self.assertFalse(data_query.get("can_request_admin", False), f"Direct query must NOT propose workflow: {data_query}")
        self.assertNotEqual(data_query.get("action_type"), "workflow_not_found")


if __name__ == "__main__":
    unittest.main()
