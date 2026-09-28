import asyncio
import unittest
from agents.workflow_compiler import WorkflowCompiler
from agents.json_executor import JSONExecutionEngine
from agents.autonomous_agent import AutonomousAgent
from database.db import get_db_connection

class TestDomainGuardAndLeaveBalanceValidation(unittest.TestCase):
    def setUp(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

    def tearDown(self):
        self.loop.close()

    # ----------------------------------------------------
    # ISSUE 1 TESTS: Domain Scope Guard on Workflow Creation
    # ----------------------------------------------------
    def test_out_of_domain_bakso_rejected(self):
        """Admin attempting to create out-of-domain food/bakso workflow is rejected."""
        res = self.loop.run_until_complete(
            WorkflowCompiler.preview_and_lint_instruction(
                name="Alur Pemesanan Bakso",
                instruction="Buatkan saya alur pemesanan bakso",
                tenant_id="ALL"
            )
        )
        self.assertFalse(res["success"])
        self.assertTrue(len(res["errors"]) > 0)
        self.assertIn("di luar domain operasional", res["errors"][0])

    def test_out_of_domain_gaming_rejected(self):
        """Admin attempting to create gaming/entertainment workflow is rejected."""
        res = self.loop.run_until_complete(
            WorkflowCompiler.preview_and_lint_instruction(
                name="Order Topup Game",
                instruction="Buatkan alur topup diamond game mobile legend",
                tenant_id="ALL"
            )
        )
        self.assertFalse(res["success"])
        self.assertTrue(len(res["errors"]) > 0)
        self.assertIn("di luar domain operasional", res["errors"][0])

    def test_out_of_domain_personal_errands_rejected(self):
        """Admin attempting to create personal vacation/lifestyle workflow is rejected."""
        res = self.loop.run_until_complete(
            WorkflowCompiler.preview_and_lint_instruction(
                name="Pemesanan Tiket Liburan",
                instruction="Pesan tiket pesawat dan hotel pribadi untuk liburan akhir pekan",
                tenant_id="ALL"
            )
        )
    def test_out_of_domain_kue_rejected(self):
        """Pemeasanan Kue in HR or ALL must be strictly rejected."""
        res_hr = self.loop.run_until_complete(
            WorkflowCompiler.preview_and_lint_instruction(
                name="Pemeasanan Kue",
                instruction="ketika user pesan kue maka akan muncul form",
                tenant_id="HR"
            )
        )
        self.assertFalse(res_hr["success"])
        self.assertTrue(len(res_hr["errors"]) > 0)
        self.assertIn("di luar domain operasional", res_hr["errors"][0])

        res_all = self.loop.run_until_complete(
            WorkflowCompiler.preview_and_lint_instruction(
                name="Pemeasanan Kue",
                instruction="ketika user pesan kue maka akan muncul form",
                tenant_id="ALL"
            )
        )
        self.assertFalse(res_all["success"])
        self.assertTrue(len(res_all["errors"]) > 0)

    def test_cross_tenant_inventory_in_hr_rejected(self):
        """Inventory restock instruction submitted under HR tenant must be rejected."""
        is_valid, msg = WorkflowCompiler.validate_instruction_domain(
            name="Restock Kabel Fiber",
            instruction="Restock kabel fiber optik di gudang logistik",
            tenant_id="HR"
        )
        self.assertFalse(is_valid)
        self.assertIn("di luar wewenang domain HR", msg)

    def test_valid_enterprise_workflow_accepted(self):
        """Valid telecom tower operations instructions are accepted."""
        # Test telecom fiber restock
        is_valid, _ = WorkflowCompiler.validate_instruction_domain(
            name="Pengadaan Kabel Fiber Optic",
            instruction="Restock kabel fiber optik yang kritis di gudang logistik",
            tenant_id="INVENTORY"
        )
        self.assertTrue(is_valid)

        # Test HR rigger candidate filtering
        is_valid_hr, _ = WorkflowCompiler.validate_instruction_domain(
            name="Filter Kandidat Rigger",
            instruction="Filter pelamar rigger tower yang memiliki sertifikat TKPK 1",
            tenant_id="HR"
        )
        self.assertTrue(is_valid_hr)

        # Test Finance tower leasing OPEX
        is_valid_fin, _ = WorkflowCompiler.validate_instruction_domain(
            name="Audit Listrik PLN Menara",
            instruction="Audit pengeluaran tagihan listrik PLN dan sewa lahan site",
            tenant_id="FINANCE"
        )
        self.assertTrue(is_valid_fin)

    # ----------------------------------------------------
    # ISSUE 2 TESTS: Leave Balance Guardrails
    # ----------------------------------------------------
    def test_leave_rejected_when_balance_zero_in_json_executor(self):
        """Employee with leave_balance = 0 (Hendra Gunawan) cannot submit leave."""
        wf = {
            "workflow": "pengajuan_cuti_karyawan",
            "steps": [
                {"type": "tool", "tool": "hr.submit_leave_request"},
                {"type": "tool", "tool": "docgen.compile_leave_pdf"}
            ]
        }
        res = self.loop.run_until_complete(
            JSONExecutionEngine.execute(
                compiled_json=wf,
                tenant_id="HR",
                custom_context={"prompt": "Ajukan cuti tahunan 2 hari untuk Hendra Gunawan"}
            )
        )
        steps = res.get("execution_steps", [])
        self.assertTrue(any(s.get("title") == "Validasi Kuota Saldo Cuti" and s.get("status") == "FAILED" for s in steps))
        self.assertTrue(any(s.get("title") == "Generate Berkas Resmi Cuti (PDF Typst)" and s.get("status") == "SKIPPED" for s in steps))
        self.assertIsNone(res.get("context", {}).get("leave_id"))
        self.assertIn("0 hari", res.get("summary", ""))

    def test_leave_rejected_when_days_requested_exceeds_balance(self):
        """Employee with balance 5 (Yusuf Maulana) asking for 6 days is rejected."""
        wf = {
            "workflow": "pengajuan_cuti_karyawan",
            "steps": [
                {"type": "tool", "tool": "hr.submit_leave_request"},
                {"type": "tool", "tool": "docgen.compile_leave_pdf"}
            ]
        }
        res = self.loop.run_until_complete(
            JSONExecutionEngine.execute(
                compiled_json=wf,
                tenant_id="HR",
                custom_context={"prompt": "Ajukan cuti tahunan 6 hari untuk Yusuf Maulana"}
            )
        )
        steps = res.get("execution_steps", [])
        self.assertTrue(any(s.get("title") == "Validasi Kuota Saldo Cuti" and s.get("status") == "FAILED" for s in steps))
        self.assertIsNone(res.get("context", {}).get("leave_id"))
        self.assertIn("melebihi sisa saldo cuti", res.get("summary", ""))

    def test_leave_accepted_when_balance_sufficient(self):
        """Employee with balance 5 (Yusuf Maulana) asking for 2 days succeeds."""
        wf = {
            "workflow": "pengajuan_cuti_karyawan",
            "steps": [
                {"type": "tool", "tool": "hr.submit_leave_request"}
            ]
        }
        res = self.loop.run_until_complete(
            JSONExecutionEngine.execute(
                compiled_json=wf,
                tenant_id="HR",
                custom_context={"prompt": "Ajukan cuti tahunan 2 hari untuk Yusuf Maulana"}
            )
        )
        steps = res.get("execution_steps", [])
        self.assertTrue(any(s.get("title") == "Submit Leave Request ke DuckDB" and s.get("status") == "COMPLETED" for s in steps))
        created_id = res.get("context", {}).get("leave_id")
        self.assertIsNotNone(created_id)

        # Cleanup created test leave request
        conn = get_db_connection(read_only=False)
        conn.execute("DELETE FROM leave_requests WHERE leave_id = ?", [created_id])
        conn.commit()
        conn.close()

    def test_autonomous_agent_rejects_insufficient_leave(self):
        """AutonomousAgent direct tool call also enforces leave balance validation."""
        # Hendra (balance 0)
        res_hendra = self.loop.run_until_complete(
            AutonomousAgent.execute_tool_process_leave_request(
                {"action": "SUBMIT", "employee_name": "Hendra Gunawan", "days_requested": 1},
                None
            )
        )
        self.assertEqual(res_hendra.get("status"), "FAILED")
        self.assertIn("0 hari", res_hendra.get("error", ""))

        # Yusuf (balance 5) asking 8 days
        res_yusuf = self.loop.run_until_complete(
            AutonomousAgent.execute_tool_process_leave_request(
                {"action": "SUBMIT", "employee_name": "Yusuf Maulana", "days_requested": 8},
                None
            )
        )
        self.assertEqual(res_yusuf.get("status"), "FAILED")
    def test_out_of_the_box_novel_concept_rejected(self):
        """Out-of-the-box non-database requests (helicopter, tickets, catering) are strictly rejected."""
        # Test 1: Ticket pesawat in HR
        res_ticket = self.loop.run_until_complete(
            WorkflowCompiler.preview_and_lint_instruction(
                name="Pemesana Tiket Pesawat",
                instruction="Ketika user meminta pemesanan tiket pesawat akan ditampilkan keseluruhan tiket pesawat yang pending",
                tenant_id="HR"
            )
        )
        self.assertFalse(res_ticket["success"])
        self.assertTrue(len(res_ticket["errors"]) > 0)

        # Test 2: Helicopter rental (novel concept outside company database)
        is_valid_heli, err_heli = self.loop.run_until_complete(
            WorkflowCompiler.evaluate_database_context_with_llm(
                name="Sewa Helikopter",
                instruction="Sewa armada helikopter untuk survei menara telekomunikasi di kepulauan",
                tenant_id="ALL"
            )
        )
        self.assertFalse(is_valid_heli)
        self.assertTrue(len(err_heli) > 0)

        # Test 3: Catering/Food outside enterprise database
        is_valid_food, err_food = self.loop.run_until_complete(
            WorkflowCompiler.evaluate_database_context_with_llm(
                name="Pengadaan Katering Tumpeng",
                instruction="Pesan katering tumpeng 50 porsi untuk peresmian site",
                tenant_id="ALL"
            )
        )
        self.assertFalse(is_valid_food)

    def test_valid_database_context_accepted(self):
        """Legitimate database context operations for telecom infrastructure are accepted."""
        is_valid, msg = self.loop.run_until_complete(
            WorkflowCompiler.evaluate_database_context_with_llm(
                name="Restock Kabel Fiber Optic",
                instruction="Restock kabel fiber optik 24 core yang menipis di gudang logistik",
                tenant_id="INVENTORY"
            )
        )
        self.assertTrue(is_valid)
        self.assertEqual(msg, "")


if __name__ == "__main__":
    unittest.main()

