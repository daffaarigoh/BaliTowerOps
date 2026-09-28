import asyncio
import unittest
from fastapi.testclient import TestClient
from api.main import app
from core.schema_dictionary import resolve_sql_ui_aliases, get_tenant_allowed_tables
from agents.json_executor import JSONExecutionEngine
from database.db import get_db_connection

client = TestClient(app)


class TestDynamicDatabaseBlocks(unittest.TestCase):
    def test_schema_dictionary_hr_alias_resolution(self):
        """Verify UI-to-DB alias translation for HR domain."""
        sql = "UPDATE k3_candidates SET stage = 'interview' WHERE stage = 'screened';"
        resolved = resolve_sql_ui_aliases(sql, tenant_id="HR")
        self.assertIn("UPDATE candidates", resolved)
        self.assertIn("recruitment_stage = 'INTERVIEW'", resolved)
        self.assertIn("WHERE recruitment_stage = 'SCREENED'", resolved)

    def test_schema_dictionary_finance_alias_resolution(self):
        """Verify UI-to-DB alias translation for Finance domain."""
        sql = "SELECT * FROM invoicing_sewa_menara WHERE status = 'paid';"
        resolved = resolve_sql_ui_aliases(sql, tenant_id="FINANCE")
        self.assertIn("FROM revenue_invoices", resolved)
        self.assertIn("payment_status = 'PAID'", resolved)

    def test_schema_dictionary_inventory_alias_resolution(self):
        """Verify UI-to-DB alias translation for Inventory domain."""
        sql = "SELECT material name, total stock FROM material catalog WHERE sku = 'BLT-001';"
        resolved = resolve_sql_ui_aliases(sql, tenant_id="INVENTORY")
        self.assertIn("FROM inventory_items", resolved)
        self.assertIn("item_name", resolved)
        self.assertIn("current_stock", resolved)
        self.assertIn("item_code", resolved)

    def test_tenant_allowed_tables(self):
        """Verify multi-tenant table whitelist isolation."""
        hr_tables = get_tenant_allowed_tables("HR")
        self.assertIn("candidates", hr_tables)
        self.assertIn("employees", hr_tables)
        self.assertNotIn("revenue_invoices", hr_tables)
        self.assertNotIn("stock_balances", hr_tables)

        fin_tables = get_tenant_allowed_tables("FINANCE")
        self.assertIn("revenue_invoices", fin_tables)
        self.assertIn("telecom_clients", fin_tables)
        self.assertNotIn("candidates", fin_tables)

    def test_dynamic_crud_execution_engine(self):
        """Verify Block 2 executes dynamic universal CRUD safely and persists to DuckDB."""
        wf_definition = {
            "workflow": "test_dynamic_candidate_update",
            "version": 1,
            "steps": [
                {
                    "type": "tool",
                    "tool": "hr.crud_record",
                    "params": {
                        "operation": "execute_sql",
                        "sql": "UPDATE k3_candidates SET stage = 'interview' WHERE stage = 'screened';"
                    }
                }
            ]
        }
        res = asyncio.run(JSONExecutionEngine.execute(
            compiled_json=wf_definition,
            tenant_id="HR",
            custom_context={"prompt": "Ubah semua kandidat screened jadi interview"}
        ))
        self.assertTrue(res.get("context", {}).get("database_crud_success"))

        # Verify DuckDB candidate state
        conn = get_db_connection(read_only=True)
        cands = conn.execute("SELECT recruitment_stage FROM candidates").fetchall()
        conn.close()
        stages = [c[0] for c in cands]
        self.assertNotIn("SCREENED", stages)
        self.assertIn("INTERVIEW", stages)

    def test_structured_crud_action_execution(self):
        """Verify Block 2 executes structured CRUD parameters (action: update/read/create/delete)."""
        wf_structured = {
            "workflow": "test_structured_crud",
            "version": 1,
            "steps": [
                {
                    "type": "tool",
                    "tool": "hr.crud_record",
                    "params": {
                        "action": "update",
                        "table": "candidates",
                        "data": {
                            "recruitment_stage": "INTERVIEW"
                        },
                        "condition": "candidate_id = 'CND-2026-004'"
                    }
                }
            ]
        }
        res = asyncio.run(JSONExecutionEngine.execute(
            compiled_json=wf_structured,
            tenant_id="HR"
        ))
        self.assertTrue(res.get("context", {}).get("database_crud_success"))

    def test_security_forbidden_system_tables(self):
        """Verify that dynamic CRUD rejects attempts to alter system_settings or users."""
        wf_bad = {
            "workflow": "malicious_workflow",
            "version": 1,
            "steps": [
                {
                    "type": "tool",
                    "tool": "hr.crud_record",
                    "params": {
                        "operation": "execute_sql",
                        "sql": "UPDATE system_settings SET value = 'hacked';"
                    }
                }
            ]
        }
        with self.assertRaises(PermissionError):
            asyncio.run(JSONExecutionEngine.execute(
                compiled_json=wf_bad,
                tenant_id="HR"
            ))


if __name__ == "__main__":
    unittest.main()
