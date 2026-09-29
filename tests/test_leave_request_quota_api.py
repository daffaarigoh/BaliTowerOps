import sys
from pathlib import Path
import unittest

WORKSPACE_DIR = Path(__file__).resolve().parent.parent
if str(WORKSPACE_DIR) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_DIR))

from fastapi.testclient import TestClient
from api.main import app
from database.db import get_db_connection

client = TestClient(app)

class TestLeaveRequestQuotaAPI(unittest.TestCase):
    def setUp(self):
        # Login as userb (HR tenant)
        res = client.post("/api/auth/login", json={"username": "userb", "password": "user123"})
        self.assertEqual(res.status_code, 200, f"Login failed: {res.text}")
        token = res.json()["access_token"]
        self.headers = {"Authorization": f"Bearer {token}"}

    def test_budi_santoso_leave_request_rejected_when_exceeding_balance(self):
        """Budi Santoso (balance 10) requesting 11 days of ANNUAL_LEAVE must be rejected with HTTP 400."""
        payload = {
            "employee_id": "EMP-BLT-001",
            "leave_type": "ANNUAL_LEAVE",
            "start_date": "2026-09-30",
            "days_requested": 11,
            "reason": "urusan penting",
            "substitute_employee_id": "EMP-BLT-002"
        }
        res = client.post("/api/balitower/hr/leave-requests", json=payload, headers=self.headers)
        self.assertEqual(res.status_code, 400)
        detail = res.json().get("detail", "")
        self.assertIn("melebihi sisa saldo cuti", detail)
        self.assertIn("10 hari", detail)

    def test_budi_santoso_leave_request_accepted_when_within_balance(self):
        """Budi Santoso requesting 2 days of ANNUAL_LEAVE succeeds."""
        payload = {
            "employee_id": "EMP-BLT-001",
            "leave_type": "ANNUAL_LEAVE",
            "start_date": "2026-09-30",
            "days_requested": 2,
            "reason": "urusan penting singkat",
            "substitute_employee_id": "EMP-BLT-002"
        }
        res = client.post("/api/balitower/hr/leave-requests", json=payload, headers=self.headers)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        leave_id = data.get("leave_id")
        self.assertTrue(leave_id.startswith("LV-2026-"))

        # Clean up created test record
        conn = get_db_connection(read_only=False)
        conn.execute("DELETE FROM leave_requests WHERE leave_id = ?", [leave_id])
        conn.commit()
        conn.close()

if __name__ == "__main__":
    unittest.main()
