import asyncio
import sys
import unittest
from pathlib import Path

WORKSPACE_DIR = Path(__file__).resolve().parent.parent
if str(WORKSPACE_DIR) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_DIR))

from fastapi.testclient import TestClient
from api.main import app
from docgen.compiler import generate_dynamic_report_pdf
from core.dispatcher import dispatcher

client = TestClient(app)


class TestDynamicReportAndEmail(unittest.TestCase):
    def test_dynamic_report_pdf_generation_various_schemas(self):
        # 1. 3 Columns: HR / Personal Schema
        pdf_3col = generate_dynamic_report_pdf(
            title="Laporan Kualifikasi K3 Teknisi Menara",
            headers=["Nama Teknisi", "Sertifikasi K3", "Status"],
            rows=[
                ["Rian Hidayat", "TKPK 1 - Bekerja di Ketinggian", "PASSED"],
                ["Doni Kusuma", "Sertifikasi Listrik Arus Kuat", "CRITICAL"]
            ],
            status="AUDITED"
        )
        p3 = Path(pdf_3col)
        self.assertTrue(p3.exists())
        self.assertGreater(p3.stat().st_size, 10000)
        with open(p3, "rb") as f:
            self.assertEqual(f.read(5), b"%PDF-")

        # 2. 7 Columns: Logistics / Critical Stock Schema
        pdf_7col = generate_dynamic_report_pdf(
            title="Laporan Stok Kritis Inventaris Menara",
            headers=["No", "SKU / ID", "Nama Material", "Stok", "Batas Min", "Status", "Harga Satuan"],
            rows=[
                [1, "CAB-FO-24", "Kabel Fiber Optik ADSS 24 Core", 12, 50, "KRITIS", 15000000],
                [2, "BAT-UPS-48", "Baterai Lithium UPS 48V", 3, 10, "KRITIS", 32000000],
                [3, "CON-SC-APC", "Konektor FO SC/APC Simplex", 40, 100, "MENIPIS", 450000]
            ],
            status="CRITICAL",
            summary_text="Ditemukan 2 material KRITIS dan 1 MENIPIS pada Gudang Regional Jakarta."
        )
        p7 = Path(pdf_7col)
        self.assertTrue(p7.exists())
        self.assertGreater(p7.stat().st_size, 10000)
        with open(p7, "rb") as f:
            self.assertEqual(f.read(5), b"%PDF-")

    def test_dynamic_report_download_api(self):
        # Generate a test report first
        pdf_path = generate_dynamic_report_pdf(
            title="Laporan Uji Download API",
            headers=["Item", "Nilai"],
            rows=[["A", "100"], ["B", "200"]],
            report_id="RPT-TEST-API-001"
        )
        report_file_name = Path(pdf_path).name

        # Test inline preview
        res_inline = client.get(f"/api/documents/reports/{report_file_name}/download?inline=true")
        self.assertEqual(res_inline.status_code, 200)
        self.assertIn("application/pdf", res_inline.headers["content-type"])
        self.assertIn("inline", res_inline.headers.get("content-disposition", ""))
        self.assertTrue(res_inline.content.startswith(b"%PDF-"))

        # Test attachment download
        res_dl = client.get(f"/api/documents/reports/{report_file_name}/download?download=true")
        self.assertEqual(res_dl.status_code, 200)
        self.assertIn("attachment", res_dl.headers.get("content-disposition", ""))

    def test_dispatch_dynamic_report_email(self):
        async def run_email():
            headers = ["SKU", "Material", "Stok", "Status"]
            rows = [
                ["CAB-01", "Kabel FO", 5, "KRITIS"],
                ["SFP-02", "Transceiver 10G", 2, "KRITIS"]
            ]
            res = await dispatcher.dispatch_dynamic_report(
                title="Laporan Otomatis Stok Kritis",
                headers=headers,
                rows=rows,
                recipient_email="operational@balitower.co.id",
                summary_text="Peringatan dini stok di bawah safety threshold."
            )
            return res

        res = asyncio.run(run_email())
        self.assertIn(res.get("status"), ["success", "simulated"])
        self.assertIn("Laporan Otomatis Stok Kritis", res.get("subject", ""))

    def test_admin_portal_route(self):
        res = client.get("/admin")
        self.assertEqual(res.status_code, 200)
        self.assertIn("text/html", res.headers.get("content-type", ""))
        self.assertIn("BaliTower", res.text)

    def test_smtp_attachment_application_pdf_mime(self):
        from unittest.mock import patch, MagicMock
        from core.config import settings

        with patch.object(settings, "SMTP_EMAIL", "test@balitower.co.id"), \
             patch.object(settings, "SMTP_PASSWORD", "testpass"), \
             patch.object(settings, "SMTP_SERVER", "smtp.balitower.co.id"), \
             patch("smtplib.SMTP") as mock_smtp:
            
            mock_server = MagicMock()
            mock_smtp.return_value.__enter__.return_value = mock_server

            dummy_pdf = WORKSPACE_DIR / "storage" / "reports" / "test_mime.pdf"
            dummy_pdf.parent.mkdir(parents=True, exist_ok=True)
            dummy_pdf.write_bytes(b"%PDF-1.7\ntest")

            try:
                async def run_dispatch():
                    return await dispatcher.dispatch_email(
                        recipient_email="test.receiver@balitower.co.id",
                        subject="Uji Lampiran PDF Mime",
                        content_text="Tes lampiran PDF",
                        attachment_path=str(dummy_pdf)
                    )
                
                res = asyncio.run(run_dispatch())
                self.assertEqual(res.get("status"), "success")
                self.assertTrue(mock_server.send_message.called)
                sent_msg = mock_server.send_message.call_args[0][0]
                
                attachments = [p for p in sent_msg.get_payload() if p.get_content_disposition() == "attachment"]
                self.assertEqual(len(attachments), 1)
                attach_part = attachments[0]
                self.assertEqual(attach_part.get_content_type(), "application/pdf")
                self.assertEqual(attach_part.get_filename(), "test_mime.pdf")
            finally:
                if dummy_pdf.exists():
                    dummy_pdf.unlink()


if __name__ == "__main__":
    unittest.main()
