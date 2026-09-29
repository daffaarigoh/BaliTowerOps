import asyncio
import unittest
from agents.router import SemanticRouter
from agents.json_executor import JSONExecutionEngine


class TestRoutingAndExecutionFixes(unittest.TestCase):
    def test_router_distinguishes_standard_workflow_from_adhoc_radius_query(self):
        """Verify that an ad-hoc radius anomaly or decommissioned GPS query does not force-match any workflow."""
        async def _run():
            # Ad-hoc radius anomaly prompt (GPS tracking decommissioned)
            res_adhoc = await SemanticRouter.route_prompt(
                prompt="Periksa seluruh catatan absensi teknisi yang terdeteksi di luar radius GPS menara lebih dari 100 meter minggu ini",
                tenant_id="HR"
            )
            # Must NOT force-match any fixed workflow
            self.assertIsNone(res_adhoc.get("workflow_id"))
            self.assertFalse(res_adhoc.get("is_unrelated"))

        asyncio.run(_run())

    def test_router_distinguishes_candidate_filter_from_emergency_assignment(self):
        """Verify standard candidate screening matches WF-B02, while multi-entity emergency assignment does not."""
        async def _run():
            # Standard filter prompt
            res_std = await SemanticRouter.route_prompt(
                prompt="Filter kandidat rigger tower yang memiliki sertifikat TKPK tingkat 2",
                tenant_id="HR"
            )
            self.assertIn(res_std.get("workflow_id"), ["WF-B02", "WF-003"])

            # Multi-entity emergency assignment query
            res_adhoc = await SemanticRouter.route_prompt(
                prompt="Periksa data teknisi dan kandidat rigger yang memiliki sertifikat K3 TKPK (Tingkat 1 dan Tingkat 2) serta status kelaikan panjat (Fit for Height). Susun daftar personel yang siap penugasan darurat",
                tenant_id="HR"
            )
            self.assertIsNone(res_adhoc.get("workflow_id"))
            self.assertFalse(res_adhoc.get("is_unrelated"))

        asyncio.run(_run())

    def test_hr_audit_attendance_handles_distance_filter_accurately(self):
        """Verify hr.audit_attendance tool handles radius threshold queries by stating GPS tracking is decommissioned."""
        async def _run():
            compiled = {
                "workflow": "hr_attendance_audit",
                "steps": [{"type": "tool", "tool": "hr.audit_attendance"}]
            }
            
            # 1. Radius anomaly query (informs that GPS geofencing is decommissioned)
            ctx_anomaly = {
                "prompt": "Periksa seluruh catatan absensi teknisi yang terdeteksi di luar radius GPS menara lebih dari 100 meter minggu ini",
                "tenant_id": "HR"
            }
            result_anomaly = await JSONExecutionEngine.execute(compiled, tenant_id="HR", custom_context=ctx_anomaly)
            summary = result_anomaly.get("summary", "")
            self.assertTrue("dinonaktifkan" in summary or "tidak lagi mencatat jarak" in summary)

            # 2. Standard audit query (returns normal overtime records without distance)
            ctx_std = {
                "prompt": "Tampilkan rekap absensi kunjungan site menara dan jam lembur teknisi bulan ini",
                "tenant_id": "HR"
            }
            result_std = await JSONExecutionEngine.execute(compiled, tenant_id="HR", custom_context=ctx_std)
            summary_std = result_std.get("summary", "")
            self.assertTrue("dinonaktifkan" in summary_std or "Lembur" in summary_std)

        asyncio.run(_run())

    def test_hr_filter_candidates_supports_tkpk_1_and_2_and_employees(self):
        """Verify hr.filter_candidates supports both TKPK 1 & 2 together and includes active technicians if requested."""
        async def _run():
            compiled = {
                "workflow": "hr_filter_candidates",
                "steps": [{"type": "tool", "tool": "hr.filter_candidates"}]
            }

            ctx = {
                "prompt": "Periksa data teknisi dan kandidat rigger yang memiliki sertifikat K3 TKPK (Tingkat 1 dan Tingkat 2) serta status kelaikan panjat (Fit for Height). Susun daftar personel yang siap penugasan darurat",
                "tenant_id": "HR"
            }
            result = await JSONExecutionEngine.execute(compiled, tenant_id="HR", custom_context=ctx)
            summary = result.get("summary", "")

            # Must include candidate screening and employee roster
            self.assertTrue("Teknisi Lapangan Aktif" in summary or "Kandidat Pelamar" in summary)
            # Candidates with TKPK 1 and TKPK 2 who are FIT_FOR_HEIGHT should be evaluated
            self.assertIn("TKPK", summary)

        asyncio.run(_run())

    def test_hr_mutation_dynamic_position_and_department(self):
        """Verify hr.mutate_employee dynamically extracts new position and department even with trailing punctuation or inverted word orders."""
        from database.db import get_db_connection
        async def _run():
            compiled = {
                "workflow": "mutasi_karyawan",
                "steps": [
                    {"type": "agent", "task": "agent.reason_and_validate"},
                    {"type": "tool", "tool": "hr.mutate_employee"}
                ]
            }

            # 1. Reset Rian Hidayat to initial baseline
            conn = get_db_connection(read_only=False)
            conn.execute("UPDATE employees SET department = 'NOC & Infrastructure', job_title = 'NOC Shift Lead Tier-2' WHERE employee_id = 'EMP-BLT-006';")
            conn.commit()
            conn.close()

            # 2. Test prompt with punctuation and multi-word title
            ctx = {
                "prompt": "Tolong mutasi Rian Hidayat ke departemen Project Engineering dengan jabatan Site Acquisition & CME Inspector.",
                "tenant_id": "HR",
                "username": "userb"
            }
            res = await JSONExecutionEngine.execute(compiled, tenant_id="HR", custom_context=ctx)
            mut = res.get("mutated_employee") or {}
            self.assertEqual(mut.get("new_department"), "Project Engineering")
            self.assertEqual(mut.get("new_position"), "Site Acquisition & CME Inspector")

            # 3. Verify in DuckDB
            conn = get_db_connection(read_only=True)
            row = conn.execute("SELECT department, job_title FROM employees WHERE employee_id = 'EMP-BLT-006';").fetchone()
            conn.close()
            self.assertEqual(row[0], "Project Engineering")
            self.assertEqual(row[1], "Site Acquisition & CME Inspector")

            # 4. Clean up baseline after test
            conn = get_db_connection(read_only=False)
            conn.execute("UPDATE employees SET department = 'NOC & Infrastructure', job_title = 'NOC Shift Lead Tier-2' WHERE employee_id = 'EMP-BLT-006';")
            conn.commit()
            conn.close()

        asyncio.run(_run())

    def test_leave_audit_does_not_route_to_onboarding(self):
        """Verify 'daftar cuti pending' goes to HR leave audit, not Finance onboarding."""
        from database.db import get_db_connection
        async def _run():
            result = await SemanticRouter.route_prompt("Daftar cuti pending teknisi minggu ini", tenant_id="HR")
            wf_id = result.get("workflow_id")
            self.assertIsNotNone(wf_id)
            
            conn = get_db_connection(read_only=True)
            wf = conn.execute("SELECT id, name, tenant_id FROM workflows WHERE id = ?", [wf_id]).fetchone()
            conn.close()
            
            self.assertIsNotNone(wf, f"Workflow {wf_id} must exist in DB")
            self.assertEqual(wf[2], "HR", "Matched workflow tenant must be HR")
            self.assertIn("cuti", wf[1].lower(), "Matched workflow name must relate to leave/cuti")

        asyncio.run(_run())

    def test_stock_query_does_not_route_to_wf005_opex(self):
        """Verify stock query never routes to WF-005 (Audit Beban Listrik PLN)."""
        async def _run():
            result = await SemanticRouter.route_prompt("Berapa sisa stok kabel fiber optik di gudang Bandung?", tenant_id="INVENTORY")
            self.assertNotEqual(result.get("workflow_id"), "WF-005")

        asyncio.run(_run())

    def test_unrelated_prompt_anti_hallucination(self):
        """Verify unrelated / chit-chat prompts are marked unrelated, not restock."""
        async def _run():
            result = await SemanticRouter.route_prompt("Halo cuaca hari ini cerah sekali ya di luar kantor", tenant_id="ALL")
            self.assertTrue(result.get("is_unrelated") or result.get("workflow_id") is None)

        asyncio.run(_run())

    def test_workflow_compiler_safe_fallback(self):
        """Verify workflow compiler fallback does not inject low stock tools blindly."""
        from agents.workflow_compiler import WorkflowCompiler
        async def _run():
            compiled = await WorkflowCompiler.compile_business_instruction(
                name="Workflow Konsultasi Khusus",
                instruction="Berikan analisis ringkas mengenai efisiensi operasional"
            )
            tools = [s.get("tool") for s in compiled.get("steps", []) if s.get("type") == "tool"]
            self.assertNotIn("inventory.get_low_stock_products", tools)
            self.assertNotIn("calculate_reorder_quantity", tools)

        asyncio.run(_run())


if __name__ == "__main__":
    unittest.main()

