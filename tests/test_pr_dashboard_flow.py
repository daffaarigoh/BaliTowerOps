import unittest
from fastapi.testclient import TestClient
from api.main import app
from core.security import create_access_token
from api.routers.approval_routes import PR_STORE, _ensure_pr_in_store

class TestPrDashboardFlow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        cls.token = create_access_token({"sub": "usera", "role": "USER", "tenant_id": "INVENTORY"})
        cls.headers = {"Authorization": f"Bearer {cls.token}", "Content-Type": "application/json"}

    def test_pr_creation_and_email_flow(self):
        # 1. User prompts PR creation
        res = self.client.post("/api/agent/custom-prompt", json={"prompt": "buatkan pr nya dong"}, headers=self.headers)
        self.assertEqual(res.status_code, 200)
        data = res.json()

        self.assertEqual(data.get("action_type"), "review_prs")
        prs = data.get("prs") or data.get("generated_prs") or []
        self.assertTrue(len(prs) > 0, "PRs list should not be empty")

        pr0 = prs[0]
        self.assertTrue(isinstance(pr0, dict), "PR item must be a dictionary")
        pr_number = pr0.get("pr_number")
        self.assertTrue(pr_number.startswith("PR-"), f"Invalid PR number: {pr_number}")
        self.assertEqual(pr0.get("email_sent"), False)
        self.assertGreater(len(pr0.get("items", [])), 0)
        self.assertGreater(pr0.get("grand_total", 0), 0)

        # 2. Dispatch email to logistics manager
        dispatch_res = self.client.post("/api/approval/dispatch-email", json={
            "pr_number": pr_number,
            "recipient_email": "manager.logistik@balitower.co.id"
        }, headers=self.headers)
        self.assertEqual(dispatch_res.status_code, 200)
        dispatch_data = dispatch_res.json()
        self.assertEqual(dispatch_data.get("status"), "success")
        self.assertEqual(dispatch_data.get("recipient_email"), "manager.logistik@balitower.co.id")

        # 3. Verify in store
        stored_pr = _ensure_pr_in_store(pr_number)
        self.assertIsNotNone(stored_pr)
        self.assertTrue(stored_pr.email_sent)

if __name__ == "__main__":
    unittest.main()
