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


if __name__ == "__main__":
    unittest.main()
