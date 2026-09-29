import sys
import unittest
from pathlib import Path

WORKSPACE_DIR = Path(__file__).resolve().parent.parent
if str(WORKSPACE_DIR) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_DIR))

from fastapi.testclient import TestClient
from api.main import app
from docgen.compiler import generate_po_pdf, angka_ke_terbilang

client = TestClient(app)

def login(username: str = "usera", password: str = "user123"):
    res = client.post("/api/auth/login", json={"username": username, "password": password})
    assert res.status_code == 200, f"Login failed: {res.text}"
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


class TestPOPDFGeneration(unittest.TestCase):
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
        conn.execute("DELETE FROM purchase_orders WHERE po_id LIKE 'PO-2026-%';")
        for row in test_pos:
            conn.execute("""
                INSERT INTO purchase_orders (
                    po_id, po_number, supplier_id, item_id, order_quantity, unit_price, total_amount, status, order_date, expected_delivery, actual_delivery, warehouse_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, row)
        conn.commit()
        conn.close()

    @classmethod
    def tearDownClass(cls):
        from database.db import get_db_connection
        conn = get_db_connection(read_only=False)
        conn.execute("DELETE FROM purchase_orders WHERE po_id LIKE 'PO-2026-%';")
        conn.commit()
        conn.close()
        pdf_dir = WORKSPACE_DIR / "storage" / "purchase_orders"
        if pdf_dir.exists():
            for p in ["PO-2026-001.pdf", "PO-2026-006.pdf", "PO-2026-007.pdf"]:
                f = pdf_dir / p
                if f.exists():
                    try:
                        f.unlink()
                    except Exception:
                        pass

    def test_terbilang_helper(self):
        self.assertIn("Enam Puluh Enam Juta", angka_ke_terbilang(66000000))
        self.assertEqual("Tujuh Puluh Tiga Juta Dua Ratus Enam Puluh Ribu Rupiah", angka_ke_terbilang(73260000))
        self.assertEqual("Seratus Delapan Puluh Lima Juta Rupiah", angka_ke_terbilang(185000000))

    def test_direct_po_pdf_compiler(self):
        for po_id in ["PO-2026-001", "PO-2026-006", "PO-2026-007"]:
            pdf_path = generate_po_pdf(po_id)
            path_obj = Path(pdf_path)
            self.assertTrue(path_obj.exists(), f"PDF for {po_id} should exist at {pdf_path}")
            self.assertGreater(path_obj.stat().st_size, 10000, f"PDF file size too small: {path_obj.stat().st_size} bytes")
            with open(path_obj, "rb") as f:
                header = f.read(5)
                self.assertEqual(header, b"%PDF-", f"Expected %PDF- magic bytes, got {header}")

    def test_po_pdf_download_endpoints(self):
        # 1. Inline Preview (for In-App Modal Iframe)
        res_inline = client.get("/api/documents/po/PO-2026-006/download?inline=true")
        self.assertEqual(res_inline.status_code, 200)
        self.assertIn("application/pdf", res_inline.headers["content-type"])
        self.assertIn("inline", res_inline.headers.get("content-disposition", ""))
        self.assertTrue(res_inline.content.startswith(b"%PDF-"))

        # 2. Attachment Download
        res_dl = client.get("/api/documents/po/PO-2026-006/download?download=true")
        self.assertEqual(res_dl.status_code, 200)
        self.assertIn("attachment", res_dl.headers.get("content-disposition", ""))
        self.assertIn("PO-2026-006.pdf", res_dl.headers.get("content-disposition", ""))

    def test_chat_prompt_po_pdf_generation(self):
        headers = login("usera", "user123")
        res = client.post(
            "/api/agent/custom-prompt",
            headers=headers,
            json={"prompt": "Tolong tampilkan dokumen PDF untuk PO-2026-006", "destinations": []}
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["action_type"], "view_po_document")
        self.assertEqual(data["po_id"], "PO-2026-006")
        self.assertEqual(data["pdf_download_url"], "/api/documents/po/PO-2026-006/download")

    def test_purchase_orders_api_fields(self):
        headers = login("usera", "user123")
        res = client.get("/api/balitower/inventory/purchase-orders", headers=headers)
        self.assertEqual(res.status_code, 200)
        pos = res.json()
        self.assertGreaterEqual(len(pos), 8)
        first_po = pos[0]
        self.assertIn("po_id", first_po)
        self.assertIn("po_number", first_po)
        self.assertIn("supplier_name", first_po)
        self.assertIn("total_amount", first_po)


if __name__ == "__main__":
    unittest.main()
