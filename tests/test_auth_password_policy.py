import sys
import unittest
import uuid
from pathlib import Path

WORKSPACE_DIR = Path(__file__).resolve().parent.parent
if str(WORKSPACE_DIR) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_DIR))

from fastapi import HTTPException
from fastapi.testclient import TestClient
from api.main import app
from api.routers.auth_routes import validate_password_strength
from core.security import TokenData, get_current_admin


class TestPasswordPolicy(unittest.TestCase):

    def setUp(self):
        self.client = TestClient(app)
        def _override_admin():
            return TokenData(username="admin", role="ADMIN", tenant_id="ALL")
        app.dependency_overrides[get_current_admin] = _override_admin

    def tearDown(self):
        app.dependency_overrides.clear()

    def test_validate_password_strength_unit(self):
        """Test validate_password_strength function directly."""
        # Less than 8 characters
        with self.assertRaises(HTTPException) as ctx:
            validate_password_strength("Short1")
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("at least 8 characters", ctx.exception.detail)

        # 8 chars but only letters
        with self.assertRaises(HTTPException) as ctx:
            validate_password_strength("AllLettersOnly")
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("both letters and numbers", ctx.exception.detail)

        # 8 chars but only digits
        with self.assertRaises(HTTPException) as ctx:
            validate_password_strength("1234567890")
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("both letters and numbers", ctx.exception.detail)

        # Valid combination
        try:
            validate_password_strength("BaliTower2026")
        except HTTPException:
            self.fail("validate_password_strength raised HTTPException unexpectedly for valid password!")

    def test_create_user_password_policy(self):
        """Test POST /api/auth/admin/users rejects weak passwords and accepts strong ones."""
        # 1. Short password (< 8 chars)
        res_short = self.client.post("/api/auth/admin/users", json={
            "username": f"testuser_{uuid.uuid4().hex[:6]}",
            "password": "Abc1",
            "role": "USER",
            "tenant_id": "INVENTORY"
        })
        self.assertEqual(res_short.status_code, 400)
        self.assertIn("at least 8 characters", res_short.json()["detail"])

        # 2. Only letters (>= 8 chars)
        res_letters = self.client.post("/api/auth/admin/users", json={
            "username": f"testuser_{uuid.uuid4().hex[:6]}",
            "password": "OnlyLettersLong",
            "role": "USER",
            "tenant_id": "INVENTORY"
        })
        self.assertEqual(res_letters.status_code, 400)
        self.assertIn("both letters and numbers", res_letters.json()["detail"])

        # 3. Only numbers (>= 8 chars)
        res_digits = self.client.post("/api/auth/admin/users", json={
            "username": f"testuser_{uuid.uuid4().hex[:6]}",
            "password": "9876543210",
            "role": "USER",
            "tenant_id": "INVENTORY"
        })
        self.assertEqual(res_digits.status_code, 400)
        self.assertIn("both letters and numbers", res_digits.json()["detail"])

        # 4. Valid password
        uname = f"testuser_{uuid.uuid4().hex[:6]}"
        res_valid = self.client.post("/api/auth/admin/users", json={
            "username": uname,
            "password": "BaliTower2026",
            "role": "USER",
            "tenant_id": "INVENTORY"
        })
        self.assertEqual(res_valid.status_code, 200)
        user_id = res_valid.json().get("user_id")
        self.assertIsNotNone(user_id)

        # 5. Update user with weak password
        res_update_weak = self.client.put(f"/api/auth/admin/users/{user_id}", json={
            "password": "weak"
        })
        self.assertEqual(res_update_weak.status_code, 400)

        # 6. Update user with strong password
        res_update_strong = self.client.put(f"/api/auth/admin/users/{user_id}", json={
            "password": "UpdatedBaliTower2026"
        })
        self.assertEqual(res_update_strong.status_code, 200)


if __name__ == "__main__":
    unittest.main()
