import sys
import unittest
from pathlib import Path

# Base path resolution
WORKSPACE_DIR = Path(__file__).resolve().parent.parent
if str(WORKSPACE_DIR) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_DIR))

from fastapi.testclient import TestClient

from api.main import app
from core.observability import tracer
from core.schemas import PurchaseRequisitionDoc, RestockItem
from core.security import TokenData, get_current_admin, get_current_user
from database.db import get_db_connection
from docgen.compiler import generate_pr_pdf


def override_get_current_user():
    return TokenData(username="test_admin", role="ADMIN", tenant_id="ALL")


class TestBaliTowerOpsPipeline(unittest.TestCase):

    def setUp(self):
        app.dependency_overrides[get_current_user] = override_get_current_user
        app.dependency_overrides[get_current_admin] = override_get_current_user
        self.client = TestClient(app)
        self.client.post("/api/approval/reset")
        conn = get_db_connection(read_only=False)
        conn.execute("UPDATE stock_balances SET quantity_on_hand = 450, stock_status = 'CRITICAL' WHERE item_id = 'BLT-INV-002' AND warehouse_id = 'WH-BDG-01';")
        conn.commit()
        conn.close()

    def tearDown(self):
        app.dependency_overrides.clear()

    def test_dashboard_ui_served(self):
        """Verifies that GET / serves the interactive HTML dashboard."""
        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)
        self.assertTrue("BaliTower" in res.text or "balitower" in res.text.lower())

    def test_inventory_summary_endpoint(self):
        """Verifies GET /api/stream/inventory-summary using real tenant data."""
        res = self.client.get("/api/stream/inventory-summary")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertGreaterEqual(data["total_sku"], 1)
        self.assertIn("items", data)

    def test_observability_tracer(self):
        """Verifies tracer span management and metrics recording."""
        trace = tracer.start_trace(trace_id="test-trace-01")
        span = tracer.start_span("span-01", "Test-Planner-Node", "qwen-38")
        tracer.end_span(span, output_payload={"status": "ok"}, tokens=150)
        finished_trace = tracer.end_trace(trace, verdict="PASSED")

        self.assertEqual(finished_trace.trace_id, "test-trace-01")
        self.assertEqual(finished_trace.total_tokens_estimated, 150)
        self.assertEqual(finished_trace.compliance_verdict, "PASSED")
        self.assertGreaterEqual(len(finished_trace.spans), 1)

    def test_pdf_generation_typst(self):
        """Verifies Typst engine produces a valid PDF file."""
        sample_pr = PurchaseRequisitionDoc(
            pr_number="PR-TEST-001",
            created_at="2026-08-19 10:00",
            items=[
                RestockItem(
                    item_id="ITEM-01",
                    name="Test Item Baut",
                    reorder_qty=100,
                    unit="pcs",
                    vendor_id="VEND-01",
                    vendor_name="PT. Vendor Test",
                    unit_price=1000.0,
                    total_price=100000.0,
                    reason="Test reorder"
                )
            ],
            total_budget=100000.0,
            auditor_status="PASSED",
            auditor_notes="Valid test budget"
        )
        pdf_path_str = generate_pr_pdf(sample_pr, output_path=WORKSPACE_DIR / "storage" / "documents" / "PR_TEST_001.pdf")
        pdf_path = Path(pdf_path_str)
        self.assertTrue(pdf_path.exists())
        self.assertGreater(pdf_path.stat().st_size, 0)

    def test_full_pipeline_cycles_and_approval(self):
        """Tests full end-to-end multi-agent restock cycle, approval, rejection, and PDF download."""
        # 1. Test GET /api/inventory/items
        res_items = self.client.get("/api/inventory/items")
        self.assertEqual(res_items.status_code, 200)
        items = res_items.json()
        self.assertGreaterEqual(len(items), 5)

        # 2. Test POST /api/agent/run-cycle (Cycle 1: For Approval)
        res_cycle1 = self.client.post("/api/agent/run-cycle")
        self.assertEqual(res_cycle1.status_code, 200)
        pr_data1 = res_cycle1.json()
        pr1_number = pr_data1["pr_number"]
        self.assertGreaterEqual(len(pr_data1["items"]), 1)

        # 3. Test POST /api/agent/approve (APPROVE Action)
        res_approve = self.client.post("/api/agent/approve", json={
            "pr_number": pr1_number,
            "action": "APPROVE",
            "approver_name": "Chief Operations Officer",
            "notes": "Approved for vendor procurement"
        })
        self.assertEqual(res_approve.status_code, 200)
        self.assertEqual(res_approve.json()["status"], "APPROVED")

        # 4. Test Download of Approved PDF
        res_download_appr = self.client.get(f"/api/documents/pr/{pr1_number}/download")
        self.assertEqual(res_download_appr.status_code, 200)
        self.assertEqual(res_download_appr.headers["content-type"], "application/pdf")

        # 5. Test POST /api/agent/run-cycle (Cycle 2: For Rejection)
        res_cycle2 = self.client.post("/api/agent/run-cycle")
        self.assertEqual(res_cycle2.status_code, 200)
        pr2_number = res_cycle2.json()["pr_number"]

        # 6. Test POST /api/agent/approve (REJECT Action)
        res_reject = self.client.post("/api/agent/approve", json={
            "pr_number": pr2_number,
            "action": "REJECT",
            "approver_name": "Finance Director",
            "notes": "Budget allocation delayed"
        })
        self.assertEqual(res_reject.status_code, 200)
        self.assertEqual(res_reject.json()["status"], "REJECTED")

        # 7. Test Download of Rejected PDF
        res_download_rej = self.client.get(f"/api/documents/pr/{pr2_number}/download")
        self.assertEqual(res_download_rej.status_code, 200)
        self.assertEqual(res_download_rej.headers["content-type"], "application/pdf")

        # 8. Test Threshold Customizer Endpoint (PATCH /api/inventory/items/...)
        first_item_id = items[0]["item_id"]
        original_min = items[0].get("min_threshold", 2000)
        res_threshold = self.client.patch(f"/api/inventory/items/{first_item_id}", json={
            "min_threshold": 80
        })
        self.assertEqual(res_threshold.status_code, 200)
        # Restore original min threshold so live dashboard data is preserved
        self.client.patch(f"/api/inventory/items/{first_item_id}", json={
            "min_threshold": original_min
        })

        # 9. Test Prompt Templates Endpoint (GET /api/agent/prompt-templates)
        res_templates = self.client.get("/api/agent/prompt-templates")
        self.assertEqual(res_templates.status_code, 200)
        self.assertGreaterEqual(len(res_templates.json()), 4)

    def test_warehouse_allocation_on_approval(self):
        """Verifies that PR approval correctly preserves distinct warehouse destinations across multiple locations."""
        from api.routers.approval_routes import PR_STORE, sync_approved_pr_to_purchase_orders

        # Test Case 1: Explicit warehouse_id in PR items
        pr_num = "PR-TEST-WH-001"
        pr_doc = PurchaseRequisitionDoc(
            pr_number=pr_num,
            created_at="2026-09-17 10:00",
            items=[
                RestockItem(
                    item_id="BLT-INV-003",
                    name="Fiber Patch Cord SC-UPC 3M (Bandung)",
                    warehouse_id="WH-BDG-01",
                    warehouse_name="Gudang Bandung",
                    reorder_qty=30,
                    unit="pcs",
                    vendor_id="SUP-001",
                    vendor_name="PT Bali Vendor Utama",
                    unit_price=15000.0,
                    total_price=450000.0,
                    reason="Low stock Bandung"
                ),
                RestockItem(
                    item_id="BLT-INV-003",
                    name="Fiber Patch Cord SC-UPC 3M (Jakarta Sunter)",
                    warehouse_id="WH-JKT-01",
                    warehouse_name="Gudang Sunter",
                    reorder_qty=40,
                    unit="pcs",
                    vendor_id="SUP-001",
                    vendor_name="PT Bali Vendor Utama",
                    unit_price=15000.0,
                    total_price=600000.0,
                    reason="Low stock Jakarta"
                ),
                RestockItem(
                    item_id="BLT-INV-003",
                    name="Fiber Patch Cord SC-UPC 3M (Semarang)",
                    warehouse_id="WH-SMG-01",
                    warehouse_name="Gudang Semarang",
                    reorder_qty=32,
                    unit="pcs",
                    vendor_id="SUP-001",
                    vendor_name="PT Bali Vendor Utama",
                    unit_price=15000.0,
                    total_price=480000.0,
                    reason="Low stock Semarang"
                )
            ],
            total_budget=1530000.0,
            auditor_status="PASSED",
            auditor_notes="Valid multi-warehouse restock",
            status="APPROVED"
        )
        PR_STORE[pr_num] = pr_doc

        conn = get_db_connection(read_only=False)
        po_ids = sync_approved_pr_to_purchase_orders(conn, pr_num, pr_doc)
        conn.commit()
        self.assertTrue(len(po_ids) > 0)

        rows = conn.execute("SELECT warehouse_id, order_quantity FROM purchase_orders WHERE pr_number = ? ORDER BY order_quantity ASC;", [pr_num]).fetchall()
        wh_set = {r[0] for r in rows}
        self.assertEqual(len(rows), 3)
        self.assertEqual(wh_set, {"WH-BDG-01", "WH-JKT-01", "WH-SMG-01"})

        # Test Case 2: Fallback when warehouse_id is None - should allocate across different warehouses
        pr_num2 = "PR-TEST-WH-FALLBACK"
        pr_doc2 = PurchaseRequisitionDoc(
            pr_number=pr_num2,
            created_at="2026-09-17 10:00",
            items=[
                RestockItem(
                    item_id="BLT-INV-003",
                    name="Fiber Patch Cord SC-UPC 3M",
                    warehouse_id=None,
                    reorder_qty=10,
                    unit="pcs",
                    vendor_id="SUP-001",
                    vendor_name="PT Bali Vendor Utama",
                    unit_price=15000.0,
                    total_price=150000.0,
                    reason="Fallback restock 1"
                ),
                RestockItem(
                    item_id="BLT-INV-003",
                    name="Fiber Patch Cord SC-UPC 3M",
                    warehouse_id=None,
                    reorder_qty=20,
                    unit="pcs",
                    vendor_id="SUP-001",
                    vendor_name="PT Bali Vendor Utama",
                    unit_price=15000.0,
                    total_price=300000.0,
                    reason="Fallback restock 2"
                )
            ],
            total_budget=450000.0,
            auditor_status="PASSED",
            status="APPROVED"
        )
        po_ids2 = sync_approved_pr_to_purchase_orders(conn, pr_num2, pr_doc2)
        conn.commit()
        rows2 = conn.execute("SELECT warehouse_id FROM purchase_orders WHERE pr_number = ?;", [pr_num2]).fetchall()
        assigned_whs = [r[0] for r in rows2]
        # Must not assign both items to the exact same warehouse if multiple need restock
        self.assertEqual(len(assigned_whs), 2)
        self.assertNotEqual(assigned_whs[0], assigned_whs[1], "Fallback must distribute across distinct warehouses")
        conn.close()


if __name__ == "__main__":
    unittest.main()
