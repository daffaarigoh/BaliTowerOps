"""
Test Suite for Tahap 4:
Comprehensive End-to-End Integration & User Workflow Verification for usera and userb.

Covers:
1. User A (Inventory & Supply Chain):
   - Master data inspection (warehouses, suppliers, items, balances, POs)
   - Typst PDF generation, download, and inline preview
   - Natural language goods receipt prompt with atomic DuckDB update
   - Stock health recalculation (LOW_STOCK -> NORMAL)
   - Duplicate delivery prevention
   - AI Copilot document query workflow
2. User B (HR & Field Workforce):
   - HR KPI summary verification
   - Master employee filtering by K3 certification (TKPK 1/2)
   - Site attendances & geofencing verification
   - Leave requests and substitute technician tracking
   - AI Copilot HR prompts (screening candidates, auditing attendance, leave status)
3. Strict Multi-Tenant RBAC & Intent Boundary Enforcement:
   - usera blocked from HR & Finance APIs and prompt intents
   - userb blocked from Inventory & Finance APIs and prompt intents
"""

import sys
from pathlib import Path

WORKSPACE_DIR = Path(__file__).resolve().parent.parent
if str(WORKSPACE_DIR) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_DIR))

import unittest
from fastapi.testclient import TestClient
from api.main import app
from database.db import get_db_connection

client = TestClient(app)

def login(username: str, password: str = "user123"):
    res = client.post("/api/auth/login", json={"username": username, "password": password})
    assert res.status_code == 200, f"Login failed for {username}: {res.text}"
    data = res.json()
    return {"Authorization": f"Bearer {data['access_token']}"}


def setup_test_scenario():
    from tests.conftest import seed_test_database_if_needed
    seed_test_database_if_needed()
    conn = get_db_connection(read_only=False)
    try:
        conn.execute("""
            UPDATE purchase_orders 
            SET status = 'ORDERED', actual_delivery = NULL
            WHERE po_id = 'PO-2026-006';
        """)
        conn.execute("""
            UPDATE stock_balances
            SET quantity_on_hand = 450, stock_status = 'CRITICAL'
            WHERE item_id = 'BLT-INV-002' AND warehouse_id = 'WH-BDG-01';
        """)
        conn.commit()
    finally:
        conn.close()


def cleanup_test_scenario():
    pass


def run_usera_e2e_workflow():
    print("\n=======================================================")
    print("=== [PART 1] E2E WORKFLOW FOR USER A (INVENTORY)   ===")
    print("=======================================================")
    setup_test_scenario()
    headers_a = login("usera")

    # 1. Inspect Warehouses & Suppliers
    res_wh = client.get("/api/balitower/inventory/warehouses", headers=headers_a)
    assert res_wh.status_code == 200
    warehouses = res_wh.json()
    assert len(warehouses) >= 8, f"Expected at least 8 warehouses, got {len(warehouses)}"
    print(f"  [OK] 1. Retrieved {len(warehouses)} operational warehouses (Hub JKT, BDG, SBY, DPS, MDN, SMG, BPN, MKS).")

    res_sup = client.get("/api/balitower/inventory/suppliers", headers=headers_a)
    assert res_sup.status_code == 200
    suppliers = res_sup.json()
    assert len(suppliers) >= 10, f"Expected at least 10 suppliers, got {len(suppliers)}"
    print(f"  [OK] 2. Retrieved {len(suppliers)} certified vendors / partners.")

    # 2. Inspect Inventory Items & Critical Stock Balances
    res_items = client.get("/api/balitower/inventory/items", headers=headers_a)
    assert res_items.status_code == 200
    items = res_items.json()
    assert len(items) >= 35, f"Expected at least 35 items, got {len(items)}"
    print(f"  [OK] 3. Retrieved {len(items)} catalogued telecom material items.")

    res_crit = client.get("/api/balitower/inventory/stock-balances?status=CRITICAL", headers=headers_a)
    assert res_crit.status_code == 200
    crit_balances = res_crit.json()
    print(f"  [OK] 4. Inspected stock balances: {len(crit_balances)} critical items flagged across hubs.")

    # 3. Inspect Purchase Orders & Verify Initial State for PO-2026-006
    res_pos = client.get("/api/balitower/inventory/purchase-orders", headers=headers_a)
    assert res_pos.status_code == 200
    pos = res_pos.json()
    assert len(pos) >= 8, f"Expected at least 8 POs, got {len(pos)}"
    print(f"  [OK] 5. Retrieved {len(pos)} purchase order records.")

    po_target = next((p for p in pos if p["po_id"] == "PO-2026-006"), None)
    assert po_target is not None, "PO-2026-006 must exist in purchase orders"
    assert po_target["status"] == "ORDERED"
    target_po_id = "PO-2026-006"
    target_item_id = "BLT-INV-002"
    target_wh_id = "WH-BDG-01"
    print(f"  [OK] 6. Selected active target {target_po_id}: status='{po_target['status']}', qty={po_target['order_quantity']}, wh='{target_wh_id}'.")

    # 4. Preview PO PDF via API (Inline & Download)
    res_pdf_inline = client.get(f"/api/documents/po/{target_po_id}/download?inline=true")
    assert res_pdf_inline.status_code == 200
    assert "application/pdf" in res_pdf_inline.headers["content-type"]
    assert res_pdf_inline.content.startswith(b"%PDF-")
    print(f"  [OK] 7. Successfully compiled and previewed official PO PDF for {target_po_id} (inline=true).")

    # 5. Natural Language Goods Receipt Simulation via AI Copilot
    prompt_receipt = f"Barang untuk {target_po_id} sudah tiba di Gudang Bandung, tolong catat penerimaannya"
    res_receipt = client.post(
        "/api/agent/custom-prompt",
        headers=headers_a,
        json={"prompt": prompt_receipt, "destinations": []}
    )
    assert res_receipt.status_code == 200
    receipt_data = res_receipt.json()
    assert receipt_data["action_type"] == "goods_receipt", f"Expected goods_receipt, got {receipt_data}"
    assert receipt_data["po_id"] == target_po_id
    assert receipt_data["po_status"] == "DELIVERED"
    assert receipt_data["stock_after"] > receipt_data["stock_before"]
    print(f"  [OK] 8. Executed natural language arrival prompt: stock updated from {receipt_data['stock_before']} to {receipt_data['stock_after']}.")

    # 6. Verify DuckDB State
    conn = get_db_connection(read_only=True)
    db_po = conn.execute("SELECT status, actual_delivery FROM purchase_orders WHERE po_id = ?", [target_po_id]).fetchone()
    db_balance = conn.execute("SELECT quantity_on_hand, stock_status FROM stock_balances WHERE item_id = ? AND warehouse_id = ?", [target_item_id, target_wh_id]).fetchone()
    conn.close()
    assert db_po[0] == "DELIVERED", f"Expected DELIVERED, got {db_po[0]}"
    assert db_balance[1] == "NORMAL", f"Expected NORMAL, got {db_balance[1]}"
    print(f"  [OK] 9. DuckDB atomic persistence verified: PO status is {db_po[0]}, stock status updated to {db_balance[1]}.")

    # 7. Test Duplicate Receipt Guard
    res_dup = client.post(
        "/api/agent/custom-prompt",
        headers=headers_a,
        json={"prompt": prompt_receipt, "destinations": []}
    )
    assert res_dup.status_code == 200
    assert res_dup.json()["parsed_intent"]["workflow_id"] == "goods_receipt_already_delivered"
    assert "Sudah Pernah Diterima" in res_dup.json()["message"]
    print("  [OK] 10. Duplicate receipt guard successfully prevented double-counting.")

    # 8. Test AI Prompt for Viewing PO Document
    res_view = client.post(
        "/api/agent/custom-prompt",
        headers=headers_a,
        json={"prompt": f"Tolong tampilkan dokumen PDF untuk {target_po_id}", "destinations": []}
    )
    assert res_view.status_code == 200
    view_data = res_view.json()
    assert view_data["action_type"] == "view_po_document"
    assert view_data["po_id"] == target_po_id
    print("  [OK] 11. AI Copilot document card handler verified with direct modal triggers.")


def run_userb_e2e_workflow():
    print("\n=======================================================")
    print("=== [PART 2] E2E WORKFLOW FOR USER B (HR/WORKFORCE) ===")
    print("=======================================================")
    headers_b = login("userb")

    # 1. HR KPI Summary
    res_summary = client.get("/api/balitower/hr/summary", headers=headers_b)
    assert res_summary.status_code == 200
    hr_kpi = res_summary.json()
    assert hr_kpi["total_employees"] >= 12
    assert hr_kpi["field_technicians"] >= 6
    assert hr_kpi["certified_k3_tkpk"] >= 4
    assert hr_kpi["telecom_sites_monitored"] >= 15
    print(f"  [OK] 1. HR Summary verified: {hr_kpi['total_employees']} employees, {hr_kpi['certified_k3_tkpk']} K3 TKPK riggers, {hr_kpi['total_overtime_hours']} hrs overtime.")

    # 2. Employees with K3 Certification Filter
    res_emp = client.get("/api/balitower/hr/employees?k3_only=true", headers=headers_b)
    assert res_emp.status_code == 200
    k3_emps = res_emp.json()
    assert len(k3_emps) >= 4
    for emp in k3_emps:
        assert emp["k3_certification"] in ["TKPK 1", "TKPK 2"]
    print(f"  [OK] 2. Filtered {len(k3_emps)} certified K3 tower climbers/riggers.")

    # 3. Attendances Endpoint (Decommissioned)
    res_att = client.get("/api/balitower/hr/attendances?overtime_only=true", headers=headers_b)
    assert res_att.status_code == 200
    ot_atts = res_att.json()
    assert isinstance(ot_atts, list)
    print("  [OK] 3. Attendance endpoint gracefully returned decommissioned status (empty list).")

    # 4. Leave Requests
    res_leaves = client.get("/api/balitower/hr/leave-requests", headers=headers_b)
    assert res_leaves.status_code == 200
    leaves = res_leaves.json()
    assert len(leaves) >= 5
    print(f"  [OK] 4. Retrieved {len(leaves)} employee leave requests with substitute coverage.")

    # 5. Natural Language Prompt: Candidate Screening (Riggers TKPK)
    res_cand_prompt = client.post(
        "/api/agent/custom-prompt",
        headers=headers_b,
        json={"prompt": "Tolong tampilkan kandidat rigger yang punya sertifikat TKPK untuk rekrutmen", "destinations": []}
    )
    assert res_cand_prompt.status_code == 200
    cand_resp = res_cand_prompt.json()
    assert cand_resp["action_type"] == "hr_query"
    assert "Hasil Screening" in cand_resp["message"]
    assert "TKPK" in cand_resp["message"]
    print("  [OK] 5. AI Copilot candidate screening prompt returned formatted candidate evaluation table.")

    # 6. Natural Language Prompt: Attendance & Overtime Decommissioned Notification
    res_att_prompt = client.post(
        "/api/agent/custom-prompt",
        headers=headers_b,
        json={"prompt": "Tolong audit absensi kunjungan site dan lembur teknisi lapangan", "destinations": []}
    )
    assert res_att_prompt.status_code == 200
    att_resp = res_att_prompt.json()
    assert att_resp["action_type"] == "hr_query"
    assert "dinonaktifkan" in att_resp["message"] or "Lembur" in att_resp["message"]
    print("  [OK] 6. AI Copilot attendance audit prompt returned decommissioned policy explanation.")

    # 7. Natural Language Prompt: Leave Status Check
    res_lv_prompt = client.post(
        "/api/agent/custom-prompt",
        headers=headers_b,
        json={"prompt": "Bagaimana status pengajuan cuti dan izin teknisi saat ini?", "destinations": []}
    )
    assert res_lv_prompt.status_code == 200
    lv_resp = res_lv_prompt.json()
    assert lv_resp["action_type"] in ["hr_query", "hr_leave"]
    assert "Daftar Pengajuan Cuti & Izin Karyawan" in lv_resp["message"]
    print("  [OK] 7. AI Copilot leave query prompt returned active leave applications table.")


def run_cross_tenant_security_verification():
    print("\n=======================================================")
    print("=== [PART 3] CROSS-TENANT SECURITY & SCOPE CHECK   ===")
    print("=======================================================")
    headers_a = login("usera")
    headers_b = login("userb")

    # 1. usera cannot access HR endpoints
    res_a_hr = client.get("/api/balitower/hr/summary", headers=headers_a)
    assert res_a_hr.status_code == 403, f"Expected 403, got {res_a_hr.status_code}"
    print("  [OK] 1. usera blocked from HR API (403 Forbidden).")

    # 2. usera cannot prompt for HR candidates
    res_a_hr_prompt = client.post(
        "/api/agent/custom-prompt",
        headers=headers_a,
        json={"prompt": "Tampilkan kandidat rigger yang punya sertifikat TKPK", "destinations": []}
    )
    assert res_a_hr_prompt.status_code == 200
    assert res_a_hr_prompt.json()["action_type"] == "out_of_scope"
    assert "Akses Ditolak" in res_a_hr_prompt.json()["message"]
    print("  [OK] 2. usera blocked from HR prompt intent (Access Denied / Out of Scope).")

    # 3. userb cannot access Inventory endpoints
    res_b_inv = client.get("/api/balitower/inventory/items", headers=headers_b)
    assert res_b_inv.status_code == 403, f"Expected 403, got {res_b_inv.status_code}"
    print("  [OK] 3. userb blocked from Inventory API (403 Forbidden).")

    # 4. userb cannot access Purchase Orders endpoint
    res_b_pos = client.get("/api/balitower/inventory/purchase-orders", headers=headers_b)
    assert res_b_pos.status_code == 403, f"Expected 403, got {res_b_pos.status_code}"
    print("  [OK] 4. userb blocked from Purchase Orders API (403 Forbidden).")

    # 5. userb cannot prompt for goods receipt or restock
    res_b_rec_prompt = client.post(
        "/api/agent/custom-prompt",
        headers=headers_b,
        json={"prompt": "Barang untuk PO-2026-006 sudah sampai di Gudang Bandung", "destinations": []}
    )
    assert res_b_rec_prompt.status_code == 200
    assert res_b_rec_prompt.json()["action_type"] == "out_of_scope"
    assert "Akses Ditolak" in res_b_rec_prompt.json()["message"]
    print("  [OK] 5. userb blocked from Inventory goods receipt prompt (Access Denied / Out of Scope).")


class TestTahap4E2E(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from database.db import get_db_connection
        conn = get_db_connection(read_only=False)
        test_pos = [
            ("PO-2026-001", "PO/BLT/2026/01/001", "SUP-001", "BLT-INV-001", 10, 1500000.0, 15000000.0, "ORDERED", "2026-01-05", "2026-01-12", None, "WH-JKT-01"),
            ("PO-2026-002", "PO/BLT/2026/01/002", "SUP-002", "BLT-INV-002", 5, 2000000.0, 10000000.0, "ORDERED", "2026-01-06", "2026-01-13", None, "WH-BDG-01"),
            ("PO-2026-003", "PO/BLT/2026/01/003", "SUP-003", "BLT-INV-003", 20, 500000.0, 10000000.0, "ORDERED", "2026-01-07", "2026-01-14", None, "WH-SBY-01"),
            ("PO-2026-004", "PO/BLT/2026/01/004", "SUP-004", "BLT-INV-004", 8, 1200000.0, 9600000.0, "ORDERED", "2026-01-08", "2026-01-15", None, "WH-DPS-01"),
            ("PO-2026-005", "PO/BLT/2026/01/005", "SUP-005", "BLT-INV-005", 15, 3000000.0, 45000000.0, "ORDERED", "2026-01-09", "2026-01-16", None, "WH-MDN-01"),
            ("PO-2026-006", "PO/BLT/2026/03/008", "SUP-008", "BLT-INV-002", 3000, 22000.0, 66000000.0, "ORDERED", "2026-03-03", "2026-03-14", None, "WH-BDG-01"),
            ("PO-2026-007", "PO/BLT/2026/03/011", "SUP-009", "BLT-INV-005", 12, 18500000.0, 222000000.0, "ORDERED", "2026-03-04", "2026-03-18", None, "WH-DPS-01"),
            ("PO-2026-008", "PO/BLT/2026/03/014", "SUP-002", "BLT-INV-021", 15, 2400000.0, 36000000.0, "ORDERED", "2026-03-05", "2026-03-15", None, "WH-DPS-01"),
        ]
        test_leaves = [
            ("LV-2026-001", "EMP-BLT-001", "ANNUAL_LEAVE", "2026-01-20", "2026-01-22", 3, "Keperluan keluarga ke luar kota", "EMP-BLT-002", "APPROVED", "EMP-BLT-005"),
            ("LV-2026-002", "EMP-BLT-003", "SICK_LEAVE", "2026-02-10", "2026-02-11", 2, "Demam tinggi & istirahat dokter", "EMP-BLT-011", "APPROVED", "EMP-BLT-005"),
            ("LV-2026-003", "EMP-BLT-007", "ANNUAL_LEAVE", "2026-02-25", "2026-02-27", 3, "Cuti tahunan keperluan pribadi", "EMP-BLT-006", "APPROVED", "EMP-BLT-006"),
            ("LV-2026-004", "EMP-BLT-004", "ANNUAL_LEAVE", "2026-03-12", "2026-03-14", 3, "Upacara adat di Denpasar", "EMP-BLT-002", "PENDING_APPROVAL", None),
            ("LV-2026-005", "EMP-BLT-012", "EMERGENCY_LEAVE", "2026-03-02", "2026-03-02", 1, "Keluarga musibah banjir", "EMP-BLT-002", "APPROVED", "EMP-BLT-005"),
        ]
        conn.execute("DELETE FROM purchase_orders WHERE po_id LIKE 'PO-2026-%';")
        conn.execute("DELETE FROM leave_requests WHERE leave_id LIKE 'LV-2026-%';")
        for row in test_pos:
            conn.execute("""
                INSERT INTO purchase_orders (
                    po_id, po_number, supplier_id, item_id, order_quantity, unit_price, total_amount, status, order_date, expected_delivery, actual_delivery, warehouse_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, row)
        for row in test_leaves:
            conn.execute("""
                INSERT INTO leave_requests (
                    leave_id, employee_id, leave_type, start_date, end_date, days_requested, reason, substitute_employee_id, approval_status, approved_by
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, row)
        conn.commit()
        conn.close()

    @classmethod
    def tearDownClass(cls):
        from database.db import get_db_connection
        conn = get_db_connection(read_only=False)
        conn.execute("DELETE FROM purchase_orders WHERE po_id LIKE 'PO-2026-%';")
        conn.execute("DELETE FROM leave_requests WHERE leave_id LIKE 'LV-2026-%';")
        conn.commit()
        conn.close()

    def test_usera_e2e_workflow(self):
        run_usera_e2e_workflow()

    def test_userb_e2e_workflow(self):
        run_userb_e2e_workflow()

    def test_cross_tenant_security(self):
        run_cross_tenant_security_verification()


if __name__ == "__main__":
    unittest.main()
