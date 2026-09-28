import json
import re

from core.config import settings
from core.llm_client import ModelGateway, gateway
from core.schema_dictionary import resolve_table_name, TENANT_ALLOWED_TABLES

class WorkflowCompiler:
    VALID_TOOLS = {
        "inventory.crud_record", "inventory.get_low_stock_products", "inventory.get_all_products",
        "inventory.check_specific_stock", "inventory.update_threshold", "inventory.register_product",
        "po.query_orders", "po.approve",
        "hr.crud_record", "hr.mutate_employee", "hr.approve_leave", "hr.submit_leave_request",
        "hr.query_pending_leaves", "hr.filter_candidates",
        "finance.crud_record", "finance.draft_client_onboarding", "finance.approve_client_onboarding",
        "finance.audit_client_onboardings", "finance.revenue_report", "finance.opex_audit", "finance.cashflow_summary",
        "system.check_profile", "system.get_system_info", "system.get_company_guidelines",
        "docgen.compile", "docgen.compile_po", "docgen.compile_leave_pdf", "docgen.compile_invoice_pdf",
        "notification.dispatch", "notification.send_email",
        "agent.reason_and_validate", "calculate_reorder_quantity", "agent.autonomous_reasoning"
    }

    TOOL_ALIASES = {
        "crud_record": "inventory.crud_record",
        "send_email": "notification.send_email",
        "dispatch": "notification.dispatch",
        "compile_pr": "docgen.compile",
        "compile_po": "docgen.compile_po",
        "compile_leave": "docgen.compile_leave_pdf",
        "compile_invoice": "docgen.compile_invoice_pdf",
        "mutate_employee": "hr.mutate_employee",
        "filter_candidates": "hr.filter_candidates",
        "submit_leave": "hr.submit_leave_request",
        "approve_leave": "hr.approve_leave",
        "query_orders": "po.query_orders",
        "get_low_stock": "inventory.get_low_stock_products",
        "get_all_products": "inventory.get_all_products",
        "register_product": "inventory.register_product"
    }

    @classmethod
    async def compile_business_instruction(cls, name: str, instruction: str, tenant_id: str = "ALL") -> dict:
        """
        Translates a natural language business instruction into a structured JSON workflow
        using the 4 Core Agentic Building Blocks.
        """
        system_prompt = """You are a Workflow Compiler for an Enterprise Agentic Inventory & Restock System (PT Bali Towerindo Sentra Tbk).
Convert the user's natural language business instruction into a strict, structured JSON workflow execution definition.

You must build the execution pipeline using the official Agentic Building Blocks:

1. REASONING & VALIDATION (Agent Tasks):
   - {"type": "agent", "task": "agent.reason_and_validate"} -> Validates mandatory parameters, business constraints, or data conditions before mutation.
   - {"type": "agent", "task": "calculate_reorder_quantity"} -> Calculates restock needs, EOQ, safety stock, and supplier budget matching.

2. DYNAMIC DATABASE & DOMAIN OPERATIONS (Tools):
   - {"type": "tool", "tool": "inventory.crud_record", "params": {"action": "create" | "read" | "update" | "delete", "table": "<inventory_table>", "data": {...}, "condition": "<where_clause>"}} -> Dynamic Inventory & Logistics CRUD operations.
   - {"type": "tool", "tool": "hr.crud_record", "params": {"action": "create" | "read" | "update" | "delete", "table": "<hr_table>", "data": {...}, "condition": "<where_clause>"}} -> Dynamic HR database operations (e.g. updating candidate stages, modifying employees).
   - {"type": "tool", "tool": "finance.crud_record", "params": {"action": "create" | "read" | "update" | "delete", "table": "<finance_table>", "data": {...}, "condition": "<where_clause>"}} -> Dynamic Finance database operations (e.g. updating invoices, leases, utilities).
   - {"type": "tool", "tool": "inventory.register_product"} -> Registers and inserts new product items into inventory.
   - {"type": "tool", "tool": "inventory.get_low_stock_products"} -> Queries products below minimum threshold.
   - {"type": "tool", "tool": "inventory.get_all_products"} -> Queries all products for warehouse audits.
   - {"type": "tool", "tool": "inventory.check_specific_stock"} -> Queries specific product stock level.
   - {"type": "tool", "tool": "inventory.update_threshold"} -> Updates product safety threshold.
   - {"type": "tool", "tool": "po.query_orders"} -> Queries Purchase Orders (PO) filtered by status ("ACTIVE", "IN_TRANSIT", "PENDING_APPROVAL", "APPROVED").
   - {"type": "tool", "tool": "po.approve"} -> Approves a Purchase Order and updates its status to "APPROVED".
   - {"type": "tool", "tool": "hr.mutate_employee"} -> Updates an employee's department and job title/position in the DuckDB database.
   - {"type": "tool", "tool": "hr.approve_leave"} -> Approves an employee leave application and deducts leave balance.
   - {"type": "tool", "tool": "hr.submit_leave_request"} -> Records an employee leave application.
   - {"type": "tool", "tool": "hr.query_pending_leaves"} -> Queries all employee leave applications with PENDING_APPROVAL status.
   - {"type": "tool", "tool": "hr.filter_candidates"} -> Filters tower rigger candidates by K3 TKPK certifications.
   - {"type": "tool", "tool": "finance.draft_client_onboarding"} -> Prepares a draft onboarding for a new telecom client operator and contract.
   - {"type": "tool", "tool": "finance.approve_client_onboarding"} -> Approves an onboarding request and activates client, contract, and invoice.
   - {"type": "tool", "tool": "finance.audit_client_onboardings"} -> Queries all pending client onboarding and lease contract requests.
   - {"type": "tool", "tool": "finance.revenue_report"} -> Generates operator revenue and billed accounts receivable report.
   - {"type": "tool", "tool": "finance.opex_audit"} -> Audits operational expenses (PLN electricity, land lease, fuel).
   - {"type": "tool", "tool": "finance.cashflow_summary"} -> Calculates net operational cash flow.

3. NOTIFICATION & DISPATCH (Tools):
   - {"type": "tool", "tool": "notification.dispatch"} or {"type": "tool", "tool": "notification.send_email"} -> Sends email notifications, alert dispatches, or operational reports.

4. DOCUMENT GENERATION (Tools):
   - {"type": "tool", "tool": "docgen.compile"} -> Generates Purchase Requisition (PR) draft documents and Typst PDFs.
   - {"type": "tool", "tool": "docgen.compile_po"} -> Compiles official Purchase Order (PO) PDF documents with PT Bali Towerindo Sentra Tbk letterhead.
   - {"type": "tool", "tool": "docgen.compile_leave_pdf"} -> Compiles official Employee Leave Request PDF documents with PT Bali Towerindo Sentra Tbk letterhead.

DATABASE SCHEMA & UI MAPPING DICTIONARY:
Users only see frontend dashboard labels, NOT physical database columns. When compiling database operations, you MUST map UI names to physical DuckDB columns:

- HR Domain (User B / Tenant HR):
  * UI Tab "K3 Candidates" -> Physical Table: candidates
    - Header "STAGE" -> Column: recruitment_stage (Values: 'APPLIED', 'SCREENED', 'INTERVIEW', 'TRIAL', 'HIRED', 'REJECTED')
    - Header "K3 CERTIFICATE" -> Column: k3_cert_held ('TKPK 1', 'TKPK 2', 'K3 Umum', 'NONE')
    - Header "MEDICAL CHECK" -> Column: medical_checkup_status ('FIT_FOR_HEIGHT', 'PENDING_MCU', 'UNFIT')
    - Header "SCORE" -> Column: technical_score (FLOAT)
    - Header "POSITION" -> Column: job_id
    - Example for updating stage: UPDATE candidates SET recruitment_stage = 'INTERVIEW' WHERE recruitment_stage = 'SCREENED';
  * UI Tab "Employee Directory" -> Physical Table: employees
    - Header "EMPLOYEE ID" -> Column: employee_id (Format: 'EMP-BLT-001' to 'EMP-BLT-012')
    - Header "FULL NAME" -> Column: full_name (Real employees: 'Budi Santoso', 'Fajar Nugraha', 'Dewi Lestari', 'Yusuf Maulana', etc.)
    - Header "DEPARTMENT" -> Column: department ('Field Operations', 'NOC & Infrastructure', 'Finance & Accounting', 'Project Engineering')
    - Header "POSITION" -> Column: job_title (e.g. 'Lead Tower Rigger', 'Tower Climber Specialist', 'NOC Surveillance Specialist')
    - Header "EMPLOYMENT STATUS" / "WORK STATUS" -> Column: employment_status (Values: 'PERMANENT', 'CONTRACT (PKWT)'. STRICT RULE: DO NOT use 'ACTIVE', 'INACTIVE', or 'ON_LEAVE'; employee leave is recorded in leave_requests table! Valid IDs are EMP-BLT-001 to EMP-BLT-012, never use B001 or B002!)
    - Header "SAFETY CERTIFICATION" -> Column: k3_certification
    - Header "LEAVE BALANCE" -> Column: leave_balance (BIGINT)
    - Example for updating employment status: UPDATE employees SET employment_status = 'PERMANENT' WHERE full_name ILIKE '%Fajar Nugraha%' OR employee_id = 'EMP-BLT-007';
  * UI Tab "Leave Requests" -> Physical Table: leave_requests
    - Columns: leave_id, employee_id, leave_type ('ANNUAL_LEAVE', 'SICK_LEAVE', 'SPECIAL_LEAVE', 'MATERNITY_LEAVE'), start_date, end_date, days_requested, approval_status ('APPROVED', 'PENDING_APPROVAL', 'REJECTED')
  * UI Tab "Job Openings" -> Physical Table: job_postings
    - Columns: job_id, job_title, department, required_k3_cert ('TKPK 1', 'TKPK 2', 'K3 Umum', 'NONE'), min_experience_years, quota, status ('OPEN', 'CLOSED')

- Finance Domain (User C / Tenant FINANCE):
  * UI Tab "Invoicing Sewa Menara" -> Physical Table: revenue_invoices
    - Columns: invoice_id, invoice_number, contract_id, client_id, period_covered, total_billed, due_date, payment_status ('PAID', 'UNPAID', 'OVERDUE')
  * UI Tab "Klien Operator" -> Physical Table: telecom_clients
    - Columns: client_id, client_name, client_type, npwp, billing_email, payment_terms
  * UI Tab "Kontrak Sewa (MLA)" -> Physical Table: mla_contracts
    - Columns: contract_id, client_id, site_id, monthly_rate, billing_frequency ('MONTHLY', 'QUARTERLY', 'ANNUALLY'), status ('ACTIVE', 'EXPIRED')
  * UI Tab "Sewa Lahan Site" -> Physical Table: site_land_leases
    - Columns: lease_id, site_id, landowner_name, annual_lease_cost, lease_duration_years, status ('ACTIVE_PAID', 'EXPIRED', 'PENDING_RENEWAL')
  * UI Tab "Biaya Listrik & OPEX Site" -> Physical Table: site_utilities_cost
    - Columns: utility_id, site_id, billing_period, pln_meter_id, pln_kwh_used, pln_cost, genset_fuel_liters, genset_fuel_cost, total_utility_cost, payment_status ('PAID', 'UNPAID')

- Inventory Domain (User A / Tenant INVENTORY):
  * UI Tab "Material Catalog" -> Physical Table: inventory_items
    - Columns: item_id ('BLT-INV-001' to 'BLT-INV-035'), item_code, item_name, category, unit, unit_price, min_stock, safety_stock, lead_time_days, supplier_id
  * UI Tab "Warehouse Balances" -> Physical Table: stock_balances
    - Columns: balance_id, item_id, warehouse_id ('WH-JKT-01', 'WH-BDG-01', 'WH-SBY-01', 'WH-DPS-01', etc.), quantity_on_hand, quantity_reserved, reorder_point, stock_status
  * UI Tab "Purchase Orders" -> Physical Table: purchase_orders
    - Columns: po_id, po_number, supplier_id, item_id, order_quantity, unit_price, total_amount, status ('ORDERED', 'DELIVERED', 'ACTIVE', 'PENDING_APPROVAL', 'APPROVED')
  * UI Tab "Official Purchase Requisitions (PR)" -> Physical Table: purchase_requests
    - Columns: pr_number, created_at, status ('PENDING', 'APPROVED', 'REJECTED'), total_amount, items_json, tenant_id
  * UI Tab "PR Items / Orders" -> Physical Table: orders
    - Columns: order_id, pr_number, item_id, vendor_id, quantity, unit_price, total_price, status, tenant_id

CRITICAL RULES:
- DO NOT use MongoDB syntax. The database is DuckDB SQL.
- Always use physical table and column names from the mapping dictionary above.
- For flexible/unregistered data mutations in HR or Finance, use hr.crud_record, finance.crud_record, or inventory.crud_record with structured action parameters.
- DO NOT use bracket variables like {{step_2_output}}. Data is passed automatically through the engine context.
- Use ONLY the tools and tasks listed above.
- For End-to-End procurement / restock pipelines (from stock inspection to PR / PO draft and email notification), use the sequence: inventory.get_low_stock_products -> calculate_reorder_quantity -> docgen.compile -> notification.dispatch. Do NOT select inventory.update_threshold unless the instruction explicitly asks to re-configure or edit the threshold limit of an item.
- For forwarding/sending existing PRs or querying pending PRs: read from table "purchase_requests" with condition "status = 'PENDING'", then use notification.dispatch without hardcoding email or filename.

Output format MUST be strictly valid JSON:
{
  "workflow": "<workflow_name_slug>",
  "version": 1,
  "steps": [
    ... // Array of step objects
  ],
  "example_prompts": [
    "Contoh kalimat pertanyaan atau instruksi chat bahasa Indonesia 1",
    "Contoh kalimat pertanyaan atau instruksi chat bahasa Indonesia 2"
  ]
}
Generate 2 realistic natural language question prompts in Indonesian that an operator or manager would type in chat to trigger this workflow.
Do not output any markdown formatting or extra commentary outside the JSON.
"""
        gateway = ModelGateway()
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Workflow Name: {name}\n\nInstruction:\n{instruction}"}
        ]
        
        try:
            response_str = await gateway.chat_completion(settings.MODEL_NAME or "qwen-38", messages, temperature=0.1, response_format_json=True)
            json_match = re.search(r'\{.*\}', response_str, re.DOTALL)
            if json_match:
                response_str = json_match.group(0)
            parsed = json.loads(response_str)
            if parsed.get("steps") and len(parsed["steps"]) > 0:
                sanitized, warnings, errors = cls.validate_and_sanitize_workflow(parsed, tenant_id=tenant_id)
                if not errors and sanitized.get("steps"):
                    if not sanitized.get("example_prompts") or not isinstance(sanitized.get("example_prompts"), list) or len(sanitized["example_prompts"]) == 0:
                        sanitized["example_prompts"] = cls.generate_heuristic_examples(name, instruction)
                    return sanitized
                else:
                    print(f"[WORKFLOW COMPILER] Validation issues in LLM output: {errors}. Falling back to heuristic compiler.")
        except Exception as e:
            print(f"[WORKFLOW COMPILER] LLM compilation exception: {e}. Utilizing deterministic heuristic compiler.")

        # Heuristic compiler fallback ensuring high-quality standard compilation
        text_lower = f"{name} {instruction}".lower()
        slug = re.sub(r'[^a-z0-9]+', '_', name.lower()).strip('_')
        
        steps = []
        # Case 0: PR Query / Dispatch Pending PR to Email
        if any(k in text_lower for k in ["kirim pr", "pr pending", "dispatch pr", "email pr", "forward pr"]):
            steps.append({"type": "agent", "task": "agent.reason_and_validate"})
            steps.append({
                "type": "tool",
                "tool": "inventory.crud_record",
                "params": {
                    "action": "read",
                    "table": "purchase_requests",
                    "condition": "status = 'PENDING'"
                }
            })
            steps.append({"type": "tool", "tool": "notification.dispatch"})

        # Case 1: Product Registration & Validation
        if any(k in text_lower for k in ["daftar", "pendaftaran", "tambah barang", "tambah material", "register", "registrasi", "validasi", "catat item", "material baru", "item baru", "sku baru", "produk baru"]):
            steps.append({"type": "agent", "task": "agent.reason_and_validate"})
            steps.append({"type": "tool", "tool": "inventory.register_product"})
            if "email" in text_lower or "notifikasi" in text_lower or "lapor" in text_lower:
                steps.append({"type": "tool", "tool": "notification.dispatch"})
        
        # Case 2: Standard Restock / Procurement (End-to-End) & PR-to-PO Pipeline (HIGHEST PRIORITY OVER THRESHOLD)
        elif any(k in text_lower for k in ["restock", "pengadaan", "reorder", "pipeline", "pr-to-po", "pr to po", "draf pr", "draft pr", "purchase requisition", "beli", "pesan barang", "kritis", "menipis", "habis"]):
            steps.append({"type": "tool", "tool": "inventory.get_low_stock_products"})
            steps.append({"type": "agent", "task": "calculate_reorder_quantity"})
            steps.append({"type": "tool", "tool": "docgen.compile"})
            steps.append({"type": "tool", "tool": "notification.dispatch"})

        # Case 3: Explicit Update Threshold Action (hanya jika ada kata kerja ubah/update/ganti batas)
        elif any(k in text_lower for k in ["update threshold", "ubah threshold", "ganti threshold", "atur threshold", "set threshold", "ubah ambang", "update batas", "ubah batas", "atur batas", "set batas"]):
            steps.append({"type": "tool", "tool": "inventory.update_threshold"})
            if "email" in text_lower or "notifikasi" in text_lower:
                steps.append({"type": "tool", "tool": "notification.dispatch"})
                
        # Case 4: Warehouse Audit
        elif any(k in text_lower for k in ["audit", "seluruh gudang", "semua barang"]):
            steps.append({"type": "tool", "tool": "inventory.get_all_products"})
            steps.append({"type": "tool", "tool": "notification.dispatch"})
            
        # Case 5: Goods Receipt / Penerimaan Fisik Barang
        elif any(k in text_lower for k in ["penerimaan", "kedatangan", "tiba", "sampai", "delivered"]):
            steps.append({"type": "tool", "tool": "inventory.check_specific_stock"})
            steps.append({"type": "tool", "tool": "inventory.crud_record"})
            steps.append({"type": "tool", "tool": "notification.dispatch"})

        # Case HR-1: Mutasi Karyawan / Pindah Jabatan & Departemen
        elif any(k in text_lower for k in ["mutasi", "pindah departemen", "pindah divisi", "pindah jabatan", "rotasi karyawan", "posisi baru", "jabatan baru"]):
            steps.append({"type": "agent", "task": "agent.reason_and_validate"})
            steps.append({"type": "tool", "tool": "hr.mutate_employee"})

        # Case HR-1b: Update Status Kepegawaian (Tetap / PKWT)
        elif any(k in text_lower for k in ["status kerja", "work status", "employment status", "status kepegawaian", "karyawan tetap", "pengangkatan", "pkwt"]):
            steps.append({"type": "agent", "task": "agent.reason_and_validate"})
            steps.append({
                "type": "tool",
                "tool": "hr.crud_record",
                "params": {
                    "action": "update",
                    "table": "employees",
                    "data": {
                        "employment_status": ":target_employment_status"
                    },
                    "condition": "employee_id = :employee_id OR full_name ILIKE :full_name_pattern"
                }
            })

        # Case HR-2: Otorisasi & Persetujuan Cuti Karyawan
        elif ("cuti" in text_lower) and any(k in text_lower for k in ["setujui", "otorisasi", "approve", "pemotongan kuota", "potong kuota", "potong cuti"]):
            steps.append({"type": "tool", "tool": "hr.approve_leave"})
            if any(k in text_lower for k in ["email", "notifikasi", "kirim", "dispatch"]):
                steps.append({"type": "tool", "tool": "notification.send_email"})

        # Case HR-3: Screening & Filter Pelamar K3
        elif any(k in text_lower for k in ["pelamar", "kandidat", "rigger", "tkpk", "screening pelamar"]):
            steps.append({"type": "tool", "tool": "hr.filter_candidates"})

        # Case 6: Purchase Order (PO) Tracking, Approval, and PDF Document Generation
        elif any(k in text_lower for k in ["purchase order", "surat pesanan", "berkas po", "monitoring po", "cetak po"]) or bool(re.search(r'\bpo\b', text_lower)):
            if any(k in text_lower for k in ["setujui", "approve", "persetujuan"]):
                steps.append({"type": "tool", "tool": "po.query_orders"})
                steps.append({"type": "tool", "tool": "po.approve"})
                steps.append({"type": "tool", "tool": "docgen.compile_po"})
            else:
                steps.append({"type": "tool", "tool": "po.query_orders"})
                steps.append({"type": "tool", "tool": "docgen.compile_po"})
            if "email" in text_lower or "notifikasi" in text_lower:
                steps.append({"type": "tool", "tool": "notification.dispatch"})

        # Case 7: Audit / Query Pending Employee Leaves & HR Notification
        elif any(k in text_lower for k in ["pending", "status cuti", "cek cuti", "audit cuti", "rekap cuti", "belum disetujui", "daftar cuti"]):
            steps.append({"type": "tool", "tool": "hr.query_pending_leaves"})
            if any(k in text_lower for k in ["email", "notifikasi", "kirim", "dispatch", "persetujuan", "approve"]):
                from agents.router import extract_recipient_email
                extracted = extract_recipient_email(instruction)
                disp_step = {"type": "tool", "tool": "notification.dispatch"}
                if extracted:
                    disp_step["params"] = {"recipient_email": extracted}
                steps.append(disp_step)

        # Case 8: Employee Leave Request, PDF Compilation & HR Notification
        elif any(k in text_lower for k in ["cuti", "leave", "permohonan cuti", "pengajuan cuti", "izin cuti"]):
            steps.append({"type": "tool", "tool": "hr.submit_leave_request"})
            steps.append({"type": "tool", "tool": "docgen.compile_leave_pdf"})
            if any(k in text_lower for k in ["email", "notifikasi", "kirim", "dispatch", "surat"]):
                from agents.router import extract_recipient_email
                extracted = extract_recipient_email(instruction)
                disp_step = {"type": "tool", "tool": "notification.dispatch"}
                if extracted:
                    disp_step["params"] = {"recipient_email": extracted}
                steps.append(disp_step)

        # Case 9: Telecom Client Onboarding & Tower Lease Contract (Approval Workflow)
        elif any(k in text_lower for k in ["klien baru", "operator baru", "daftar operator", "sewa baru", "kontrak baru", "onboarding", "daftarkan operator", "sewa menara baru", "draft kontrak"]):
            steps.append({"type": "tool", "tool": "finance.draft_client_onboarding"})
            steps.append({"type": "tool", "tool": "notification.send_email"})

        # Case 10: Specific stock check
        elif any(k in text_lower for k in ["spesifik", "cek stok"]):
            steps.append({"type": "tool", "tool": "inventory.check_specific_stock"})

        # Fallback default: Safe general informational agent task (never default to Restock PR)
        else:
            steps.append({
                "type": "agent",
                "task": "agent.reason_and_validate",
                "params": {"instruction": instruction}
            })
            
        return {
            "workflow": slug or "custom_workflow",
            "version": 1,
            "steps": steps,
            "example_prompts": cls.generate_heuristic_examples(name, instruction)
        }

    @classmethod
    def generate_heuristic_examples(cls, name: str, instruction: str) -> list[str]:
        """Generates 1 clean natural language prompt example based on name and instruction."""
        clean_name = re.sub(r'^(?:alur|workflow|pipeline|proses)\s+', '', name, flags=re.IGNORECASE).strip()
        text_lower = f"{name} {instruction}".lower()
        
        # Domain specific prompt templates
        if any(k in text_lower for k in ["cuti", "leave"]):
            return [
                "Ajukan permohonan cuti tahunan karyawan untuk teknisi lapangan"
            ]
        elif any(k in text_lower for k in ["status kerja", "work status", "employment status", "status kepegawaian", "karyawan tetap", "pengangkatan", "pkwt"]):
            return [
                "Ubah status kerja Fajar Nugraha menjadi PERMANENT",
                "Perbarui status kepegawaian karyawan EMP-BLT-011 menjadi PERMANENT"
            ]
        elif any(k in text_lower for k in ["rigger", "pelamar", "kandidat", "rekrutmen"]):
            return [
                "Filter kandidat rigger tower yang memiliki sertifikat TKPK tingkat 1"
            ]
        elif any(k in text_lower for k in ["invoice", "tagihan", "sewa menara", "mla"]):
            return [
                "Tampilkan rekapitulasi invoice sewa menara per operator dan status pembayarannya"
            ]
        elif any(k in text_lower for k in ["listrik", "pln", "genset", "lahan", "sewa tanah"]):
            return [
                "Audit pengeluaran operasional listrik PLN dan sewa lahan menara regional Jawa Barat"
            ]
        elif any(k in text_lower for k in ["arus kas", "cash flow", "kas"]):
            return [
                "Tampilkan ringkasan arus kas masuk dan keluar beserta posisi saldo bersih terkini"
            ]
        elif any(k in text_lower for k in ["penerimaan", "kedatangan", "tiba", "gudang", "po-"]):
            return [
                "Catat penerimaan PO/BLT/2026/09/031 untuk semua gudang"
            ]
        elif any(k in text_lower for k in ["profil", "hak akses", "wewenang", "user"]):
            return [
                "Tampilkan informasi profil akun dan batasan hak akses divisi"
            ]
        elif any(k in text_lower for k in ["kesehatan", "status layanan", "status sistem", "gateway"]):
            return [
                "status kesehatan sistem saat ini"
            ]
        elif any(k in text_lower for k in ["panduan", "sop", "darurat", "kontak"]):
            return [
                "Tampilkan panduan operasional perusahaan dan kontak darurat helpdesk"
            ]
        elif any(k in text_lower for k in ["restock", "pengadaan", "pr-to-po", "kritis", "menipis"]):
            return [
                f"Periksa kondisi stok untuk {clean_name} dan buat draft pengadaan barang"
            ]
        else:
            return [
                f"Jalankan alur kerja {clean_name}"
            ]

    @classmethod
    def validate_and_sanitize_workflow(cls, workflow_def: dict, tenant_id: str = "ALL") -> tuple[dict, list[str], list[str]]:
        """
        Validates tools and table names in workflow definition against valid schema.
        Auto-corrects table names and tool aliases, removes static placeholders,
        and identifies errors or warnings. Strictly clean without emojis.
        """
        if not isinstance(workflow_def, dict):
            return {}, [], ["Format alur kerja tidak valid (bukan JSON object)."]

        sanitized = dict(workflow_def)
        warnings: list[str] = []
        errors: list[str] = []

        steps = sanitized.get("steps", [])
        if not isinstance(steps, list) or len(steps) == 0:
            errors.append("Alur kerja tidak memiliki langkah (steps) eksekusi.")
            return sanitized, warnings, errors

        sanitized_steps = []
        has_pending_pr_read = False

        for idx, step in enumerate(steps, 1):
            if not isinstance(step, dict):
                errors.append(f"Langkah {idx} memiliki format tidak valid.")
                continue

            step_copy = dict(step)
            step_type = step_copy.get("type", "tool")

            if step_type == "agent":
                task_name = step_copy.get("task", "")
                if not task_name:
                    errors.append(f"Langkah {idx}: Agent task tidak boleh kosong.")
                elif task_name not in cls.VALID_TOOLS:
                    if task_name in cls.TOOL_ALIASES:
                        norm = cls.TOOL_ALIASES[task_name]
                        warnings.append(f"Langkah {idx}: Task '{task_name}' dinormalisasi menjadi '{norm}'.")
                        step_copy["task"] = norm
                    else:
                        warnings.append(f"Langkah {idx}: Task '{task_name}' tidak terdaftar resmi, akan diproses sebagai penalaran otonom.")
                sanitized_steps.append(step_copy)

            elif step_type == "tool":
                tool_name = step_copy.get("tool", "")
                if not tool_name:
                    errors.append(f"Langkah {idx}: Nama tool tidak boleh kosong.")
                    continue

                # Auto-correct tool alias
                if tool_name in cls.TOOL_ALIASES:
                    resolved_tool = cls.TOOL_ALIASES[tool_name]
                    warnings.append(f"Langkah {idx}: Tool '{tool_name}' dinormalisasi menjadi '{resolved_tool}'.")
                    tool_name = resolved_tool
                    step_copy["tool"] = resolved_tool

                # Domain prefix fallback if missing domain
                if tool_name not in cls.VALID_TOOLS:
                    tenant_prefix = tenant_id.lower() if tenant_id and tenant_id not in ("ALL", "ADMIN") else ""
                    candidate_tool = f"{tenant_prefix}.{tool_name}" if tenant_prefix else ""
                    if candidate_tool in cls.VALID_TOOLS:
                        warnings.append(f"Langkah {idx}: Tool '{tool_name}' disesuaikan domain menjadi '{candidate_tool}'.")
                        tool_name = candidate_tool
                        step_copy["tool"] = candidate_tool
                    else:
                        errors.append(f"Langkah {idx}: Tool '{tool_name}' tidak terdaftar dalam sistem.")

                # Tenant authorization check
                if tenant_id and tenant_id not in ("ALL", "ADMIN"):
                    normalized_tenant = tenant_id.upper()
                    if normalized_tenant in ("INVENTORY", "TENANT_A"):
                        if tool_name.startswith("hr.") or tool_name.startswith("finance."):
                            errors.append(f"Langkah {idx}: Tool '{tool_name}' di luar wewenang domain Inventory.")
                    elif normalized_tenant in ("HR", "TENANT_B"):
                        if tool_name.startswith("inventory.") or tool_name.startswith("finance.") or tool_name.startswith("po."):
                            errors.append(f"Langkah {idx}: Tool '{tool_name}' di luar wewenang domain HR.")
                    elif normalized_tenant in ("FINANCE", "TENANT_C"):
                        if tool_name.startswith("inventory.") or tool_name.startswith("hr."):
                            errors.append(f"Langkah {idx}: Tool '{tool_name}' di luar wewenang domain Finance.")

                # Params validation & table auto-correction
                params = step_copy.get("params")
                if isinstance(params, dict):
                    params_copy = dict(params)
                    if "table" in params_copy:
                        orig_table = str(params_copy["table"]).strip()
                        resolved_table = resolve_table_name(orig_table, tenant_id=tenant_id)
                        if resolved_table:
                            if resolved_table != orig_table:
                                warnings.append(f"Langkah {idx}: Tabel '{orig_table}' diautokoreksi menjadi '{resolved_table}'.")
                                params_copy["table"] = resolved_table
                            
                            # Verify tenant table permissions
                            if tenant_id and tenant_id not in ("ALL", "ADMIN"):
                                allowed_tables = TENANT_ALLOWED_TABLES.get(tenant_id.upper(), [])
                                if resolved_table not in allowed_tables:
                                    errors.append(f"Langkah {idx}: Tabel '{resolved_table}' di luar hak akses domain {tenant_id}.")
                        else:
                            errors.append(f"Langkah {idx}: Tabel '{orig_table}' tidak ditemukan dalam schema database.")

                        if params_copy.get("table") == "purchase_requests" and params_copy.get("action") == "read":
                            has_pending_pr_read = True

                    # Remove dummy placeholder emails / files from notification step
                    if tool_name in ("notification.dispatch", "notification.send_email"):
                        dummy_emails = [
                            "procurement@balitowerindo.co.id", "user@example.com", "admin@example.com",
                            "test@example.com", "operator@balitowerindo.co.id"
                        ]
                        rec_email = params_copy.get("recipient_email") or params_copy.get("email")
                        if rec_email and any(d in str(rec_email).lower() for d in dummy_emails):
                            params_copy.pop("recipient_email", None)
                            params_copy.pop("email", None)
                            warnings.append(f"Langkah {idx}: Email placeholder statis dihapus agar dinamis sesuai pengirim.")

                        dummy_files = ["pr_pending.pdf", "sample.pdf", "document.pdf", "test.pdf"]
                        att_file = params_copy.get("attachment") or params_copy.get("filename")
                        if att_file and any(d in str(att_file).lower() for d in dummy_files):
                            params_copy.pop("attachment", None)
                            params_copy.pop("filename", None)
                            warnings.append(f"Langkah {idx}: File attachment placeholder statis dihapus.")

                    step_copy["params"] = params_copy

                # Check redundant docgen.compile if reading existing PR
                if has_pending_pr_read and tool_name == "docgen.compile":
                    warnings.append(f"Langkah {idx}: 'docgen.compile' dilewati karena berkas PR telah ada di database.")
                    continue

                sanitized_steps.append(step_copy)

        sanitized["steps"] = sanitized_steps
        return sanitized, warnings, errors

    @classmethod
    async def preview_and_lint_instruction(cls, name: str, instruction: str, tenant_id: str = "ALL") -> dict:
        """
        Compiles and lints a workflow instruction without saving it.
        Provides detailed warnings, errors, and suggestions for administrators.
        Clean output without emojis.
        """
        compiled = await cls.compile_business_instruction(name, instruction, tenant_id=tenant_id)
        sanitized, warnings, errors = cls.validate_and_sanitize_workflow(compiled, tenant_id=tenant_id)

        suggestions: list[str] = []
        if errors:
            suggestions.append("Periksa instruksi dan pastikan operasi serta tabel sesuai dengan domain yang dipilih.")
        else:
            if not warnings:
                suggestions.append("Alur kerja valid, komponen sesuai schema, dan siap untuk disimpan.")
            else:
                suggestions.append("Alur kerja berhasil dioptimasi dengan penyesuaian schema otomatis.")

        # Suggestion for recipient email
        text_lower = f"{name} {instruction}".lower()
        if ("email" in text_lower or "kirim" in text_lower) and not any("@" in word for word in instruction.split()):
            suggestions.append("Instruksi tidak menyebutkan alamat email spesifik. Sistem akan mendeteksi email dari pesan chat runtime.")

        return {
            "success": len(errors) == 0,
            "workflow": sanitized,
            "warnings": warnings,
            "errors": errors,
            "suggestions": suggestions
        }

