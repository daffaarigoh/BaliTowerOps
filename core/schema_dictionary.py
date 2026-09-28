"""
Core Semantic UI-to-Database Schema Dictionary
Maps user-facing dashboard tabs, column headers, and status badges to physical DuckDB tables, columns, and enums.
Ensures operational staff (HR, Finance, Inventory) can issue natural language instructions based on what they see in the UI,
while the agentic engine automatically resolves them to accurate database SQL.
"""

import re
from typing import Dict, Any, List

# Multi-Tenant Allowed Physical Tables
TENANT_ALLOWED_TABLES: Dict[str, List[str]] = {
    "HR": ["candidates", "employees", "job_postings", "leave_requests", "telecom_sites", "attendances"],
    "TENANT_B": ["candidates", "employees", "job_postings", "leave_requests", "telecom_sites", "attendances"],
    "FINANCE": ["revenue_invoices", "telecom_clients", "mla_contracts", "site_land_leases", "site_utilities_cost", "telecom_sites", "warehouses"],
    "TENANT_C": ["revenue_invoices", "telecom_clients", "mla_contracts", "site_land_leases", "site_utilities_cost", "telecom_sites", "warehouses"],
    "INVENTORY": ["inventory_items", "items", "stock_balances", "warehouses", "suppliers", "purchase_orders", "purchase_requests", "orders", "telecom_sites"],
    "TENANT_A": ["inventory_items", "items", "stock_balances", "warehouses", "suppliers", "purchase_orders", "purchase_requests", "orders", "telecom_sites"],
    "ALL": [
        "candidates", "employees", "job_postings", "leave_requests", "attendances",
        "revenue_invoices", "telecom_clients", "mla_contracts", "site_land_leases", "site_utilities_cost",
        "inventory_items", "items", "stock_balances", "warehouses", "suppliers", "purchase_orders", "purchase_requests", "orders", "telecom_sites"
    ]
}

# UI Label to Physical Table Name Mapping
UI_TABLE_MAP: Dict[str, str] = {
    # HR Domain (User B)
    "k3_candidates": "candidates",
    "k3 candidates": "candidates",
    "kandidat k3": "candidates",
    "kandidat": "candidates",
    "pelamar": "candidates",
    "recruitment": "candidates",
    "candidates": "candidates",
    "employee directory": "employees",
    "direktori karyawan": "employees",
    "karyawan": "employees",
    "pegawai": "employees",
    "employees": "employees",
    "leave requests": "leave_requests",
    "leave request": "leave_requests",
    "pengajuan cuti": "leave_requests",
    "cuti": "leave_requests",
    "leave_requests": "leave_requests",
    "job openings": "job_postings",
    "lowongan kerja": "job_postings",
    "lowongan": "job_postings",
    "job_postings": "job_postings",

    # Finance Domain (User C)
    "invoicing sewa menara": "revenue_invoices",
    "tower lease invoices": "revenue_invoices",
    "invoicing": "revenue_invoices",
    "tagihan": "revenue_invoices",
    "invoice": "revenue_invoices",
    "invoices": "revenue_invoices",
    "revenue_invoices": "revenue_invoices",
    "client operators": "telecom_clients",
    "klien operator": "telecom_clients",
    "operator": "telecom_clients",
    "klien": "telecom_clients",
    "telecom_clients": "telecom_clients",
    "mla tower contracts": "mla_contracts",
    "kontrak sewa (mla)": "mla_contracts",
    "kontrak mla": "mla_contracts",
    "mla contracts": "mla_contracts",
    "kontrak": "mla_contracts",
    "mla_contracts": "mla_contracts",
    "site land leases": "site_land_leases",
    "sewa lahan site": "site_land_leases",
    "sewa lahan": "site_land_leases",
    "land lease": "site_land_leases",
    "site_land_leases": "site_land_leases",
    "power & generator cost": "site_utilities_cost",
    "biaya listrik & opex site": "site_utilities_cost",
    "biaya listrik": "site_utilities_cost",
    "beban listrik": "site_utilities_cost",
    "opex site": "site_utilities_cost",
    "utilitas": "site_utilities_cost",
    "site_utilities_cost": "site_utilities_cost",

    # Inventory Domain (User A)
    "material catalog": "inventory_items",
    "katalog material": "inventory_items",
    "inventory items": "inventory_items",
    "inventory_items": "inventory_items",
    "items": "items",
    "warehouse stock": "stock_balances",
    "warehouse balances": "stock_balances",
    "stok gudang": "stock_balances",
    "stock_balances": "stock_balances",
    "gudang & lokasi": "warehouses",
    "warehouses": "warehouses",
    "gudang": "warehouses",
    "daftar supplier": "suppliers",
    "suppliers": "suppliers",
    "purchase orders": "purchase_orders",
    "pesanan pembelian": "purchase_orders",
    "purchase_orders": "purchase_orders",
    "po": "purchase_orders",

    # Purchase Requisitions (PR)
    "official purchase requisitions (pr)": "purchase_requests",
    "official purchase requisitions": "purchase_requests",
    "purchase requisitions": "purchase_requests",
    "purchase requisition": "purchase_requests",
    "purchase requests": "purchase_requests",
    "purchase request": "purchase_requests",
    "purchase_requests": "purchase_requests",
    "purchase_requisition": "purchase_requests",
    "pr": "purchase_requests",
    "draf pr": "purchase_requests",
    "daftar pr": "purchase_requests",
    "orders": "orders",
    "order": "orders"
}

# UI Column Headers to Physical Columns (per Table)
UI_COLUMN_MAP: Dict[str, Dict[str, str]] = {
    "inventory_items": {
        "sku": "item_code",
        "sku / code": "item_code",
        "code": "item_code",
        "material name": "item_name",
        "item name": "item_name",
        "nama material": "item_name",
        "nama barang": "item_name",
        "category": "category",
        "kategori": "category",
        "total stock": "current_stock",
        "physical stock": "current_stock",
        "stok": "current_stock",
        "min rop": "min_stock",
        "min stock": "min_stock",
        "min threshold": "min_stock",
        "safety stock": "safety_stock",
        "price": "unit_price",
        "price (idr)": "unit_price",
        "unit price": "unit_price",
        "unit price (idr)": "unit_price",
        "harga": "unit_price",
        "harga satuan": "unit_price",
        "supplier": "supplier_id",
        "supplier vendor": "supplier_id"
    },
    "items": {
        "sku": "item_id",
        "sku / code": "item_id",
        "code": "item_id",
        "material name": "name",
        "item name": "name",
        "nama material": "name",
        "nama barang": "name",
        "category": "category",
        "kategori": "category",
        "total stock": "current_stock",
        "physical stock": "current_stock",
        "stok": "current_stock",
        "min rop": "min_threshold",
        "max rop": "max_threshold",
        "min threshold": "min_threshold",
        "max threshold": "max_threshold",
        "price": "unit_price",
        "price (idr)": "unit_price",
        "unit price": "unit_price",
        "harga": "unit_price",
        "harga satuan": "unit_price"
    },
    "stock_balances": {
        "balance id": "balance_id",
        "material name": "item_id",
        "item name": "item_id",
        "warehouse": "warehouse_id",
        "gudang": "warehouse_id",
        "physical stock": "quantity_on_hand",
        "stok fisik": "quantity_on_hand",
        "reserved": "quantity_reserved",
        "reorder point": "reorder_point",
        "status": "stock_status",
        "stock status": "stock_status",
        "last stocktake": "last_stock_take_date"
    },
    "warehouses": {
        "warehouse id": "warehouse_id",
        "warehouse name": "warehouse_name",
        "nama gudang": "warehouse_name",
        "type": "warehouse_type",
        "tipe": "warehouse_type",
        "region": "region",
        "wilayah": "region",
        "facility address": "address",
        "address": "address",
        "alamat": "address",
        "capacity": "capacity_sqm",
        "capacity (m²)": "capacity_sqm",
        "supervisor": "supervisor"
    },
    "suppliers": {
        "supplier id": "supplier_id",
        "company name": "supplier_name",
        "supplier name": "supplier_name",
        "nama supplier": "supplier_name",
        "procurement category": "category",
        "kategori": "category",
        "pic contact": "contact_person",
        "contact person": "contact_person",
        "phone / email": "phone",
        "phone": "phone",
        "email": "email",
        "rating": "rating",
        "payment terms": "payment_terms"
    },
    "purchase_orders": {
        "po number": "po_number",
        "po no.": "po_number",
        "po no": "po_number",
        "nomor po": "po_number",
        "supplier": "supplier_id",
        "vendor": "supplier_id",
        "order quantity": "order_quantity",
        "jumlah pesanan": "order_quantity",
        "unit price": "unit_price",
        "total amount": "total_amount",
        "total cost": "total_amount",
        "total biaya": "total_amount",
        "status": "status",
        "order date": "order_date"
    },
    "candidates": {
        "candidate": "full_name",
        "candidate id": "candidate_id",
        "stage": "recruitment_stage",
        "recruitment stage": "recruitment_stage",
        "status": "recruitment_stage",
        "tahap": "recruitment_stage",
        "k3 certificate": "k3_cert_held",
        "k3 cert": "k3_cert_held",
        "sertifikat k3": "k3_cert_held",
        "sertifikat": "k3_cert_held",
        "cert": "k3_cert_held",
        "medical check": "medical_checkup_status",
        "medical checkup": "medical_checkup_status",
        "mcu": "medical_checkup_status",
        "score": "technical_score",
        "technical score": "technical_score",
        "nilai": "technical_score",
        "skor": "technical_score",
        "position": "job_id",
        "posisi": "job_id",
        "jabatan": "job_id",
        "name": "full_name",
        "nama": "full_name",
        "full name": "full_name",
        "nama lengkap": "full_name"
    },
    "employees": {
        "employee id": "employee_id",
        "id karyawan": "employee_id",
        "nik": "employee_id",
        "name": "full_name",
        "nama": "full_name",
        "full name": "full_name",
        "nama lengkap": "full_name",
        "dept": "department",
        "department": "department",
        "departemen": "department",
        "divisi": "department",
        "role": "job_title",
        "position": "job_title",
        "posisi": "job_title",
        "jabatan": "job_title",
        "work status": "employment_status",
        "status kerja": "employment_status",
        "employment status": "employment_status",
        "safety certification": "k3_certification",
        "k3 certification": "k3_certification",
        "sertifikat k3": "k3_certification",
        "sisa cuti": "leave_balance",
        "saldo cuti": "leave_balance",
        "kuota cuti": "leave_balance",
        "leave balance": "leave_balance",
        "status": "employment_status",
        "status kepegawaian": "employment_status"
    },
    "leave_requests": {
        "request no.": "leave_id",
        "request no": "leave_id",
        "no permohonan": "leave_id",
        "leave id": "leave_id",
        "applicant": "employee_id",
        "pemohon": "employee_id",
        "leave type": "leave_type",
        "jenis cuti": "leave_type",
        "days": "days_requested",
        "hari": "days_requested",
        "reason": "reason",
        "alasan": "reason",
        "cover person": "substitute_employee_id",
        "pengganti": "substitute_employee_id",
        "status": "approval_status"
    },
    "job_postings": {
        "job id": "job_id",
        "open position": "job_title",
        "position": "job_title",
        "posisi": "job_title",
        "department": "department",
        "departemen": "department",
        "k3 requirement": "required_k3_cert",
        "min. experience": "min_experience_years",
        "min experience": "min_experience_years",
        "openings": "quota",
        "quota": "quota",
        "kuota": "quota",
        "location": "location",
        "lokasi": "location",
        "status": "status"
    },
    "revenue_invoices": {
        "invoice no.": "invoice_number",
        "invoice no": "invoice_number",
        "invoice number": "invoice_number",
        "nomor invoice": "invoice_number",
        "no invoice": "invoice_number",
        "client operator": "client_id",
        "operator": "client_id",
        "klien": "client_id",
        "client name": "client_id",
        "period": "period_covered",
        "period covered": "period_covered",
        "periode": "period_covered",
        "total billed": "total_billed",
        "total billed (idr)": "total_billed",
        "total amount": "total_billed",
        "nominal": "total_billed",
        "total": "total_billed",
        "jumlah": "total_billed",
        "due date": "due_date",
        "jatuh tempo": "due_date",
        "tanggal jatuh tempo": "due_date",
        "status": "payment_status",
        "payment status": "payment_status",
        "status pembayaran": "payment_status"
    },
    "telecom_clients": {
        "client id": "client_id",
        "operator name": "client_name",
        "client name": "client_name",
        "nama operator": "client_name",
        "client type": "client_type",
        "tax id (npwp)": "npwp",
        "tax id": "npwp",
        "npwp": "npwp",
        "billing email": "billing_email",
        "payment terms": "payment_terms"
    },
    "mla_contracts": {
        "contract id": "contract_id",
        "nomor kontrak": "contract_id",
        "client operator": "client_id",
        "klien": "client_id",
        "tower site": "site_id",
        "site": "site_id",
        "monthly rate": "monthly_rate",
        "monthly rate (idr)": "monthly_rate",
        "rate bulanan": "monthly_rate",
        "biaya bulanan": "monthly_rate",
        "sewa": "monthly_rate",
        "billing cycle": "billing_frequency",
        "billing frequency": "billing_frequency",
        "status": "status",
        "contract status": "status",
        "status kontrak": "status"
    },
    "site_land_leases": {
        "lease id": "lease_id",
        "tower site": "site_id",
        "site": "site_id",
        "region": "region",
        "land owner": "landowner_name",
        "pemilik lahan": "landowner_name",
        "annual rent": "annual_lease_cost",
        "annual rent (idr)": "annual_lease_cost",
        "annual lease cost": "annual_lease_cost",
        "duration": "lease_duration_years",
        "status": "status"
    },
    "site_utilities_cost": {
        "utility id": "utility_id",
        "tower site": "site_id",
        "site": "site_id",
        "period": "billing_period",
        "periode": "billing_period",
        "pln meter id": "pln_meter_id",
        "pln power": "pln_cost",
        "pln power (idr)": "pln_cost",
        "pln cost": "pln_cost",
        "biaya listrik": "pln_cost",
        "generator fuel": "genset_fuel_cost",
        "generator fuel (idr)": "genset_fuel_cost",
        "fuel cost": "genset_fuel_cost",
        "total utilities": "total_utility_cost",
        "total utilities (idr)": "total_utility_cost",
        "payment status": "payment_status",
        "status": "payment_status"
    }
}

# Enum Value Normalization (Case-insensitive to DB uppercase)
VALUE_NORMALIZATIONS: Dict[str, str] = {
    # Candidate Stages
    "'applied'": "'APPLIED'",
    "'screened'": "'SCREENED'",
    "'interview'": "'INTERVIEW'",
    "'trial'": "'TRIAL'",
    "'hired'": "'HIRED'",
    "'rejected'": "'REJECTED'",
    '"applied"': "'APPLIED'",
    '"screened"': "'SCREENED'",
    '"interview"': "'INTERVIEW'",
    '"trial"': "'TRIAL'",
    '"hired"': "'HIRED'",
    '"rejected"': "'REJECTED'",

    # MCU Status
    "'fit_for_height'": "'FIT_FOR_HEIGHT'",
    "'pending_mcu'": "'PENDING_MCU'",
    "'unfit'": "'UNFIT'",

    # Invoice Status
    "'paid'": "'PAID'",
    "'unpaid'": "'UNPAID'",
    "'overdue'": "'OVERDUE'",

    # PO Status
    "'ordered'": "'ORDERED'",
    "'active'": "'ACTIVE'",
    "'delivered'": "'DELIVERED'",
    "'pending_approval'": "'PENDING_APPROVAL'",
    "'approved'": "'APPROVED'",

    # Employee Employment Status
    "'permanent'": "'PERMANENT'",
    '"permanent"': "'PERMANENT'",
    "'tetap'": "'PERMANENT'",
    '"tetap"': "'PERMANENT'",
    "'karyawan tetap'": "'PERMANENT'",
    '"karyawan tetap"': "'PERMANENT'",
    "'contract'": "'CONTRACT (PKWT)'",
    '"contract"': "'CONTRACT (PKWT)'",
    "'kontrak'": "'CONTRACT (PKWT)'",
    '"kontrak"': "'CONTRACT (PKWT)'",
    "'pkwt'": "'CONTRACT (PKWT)'",
    '"pkwt"': "'CONTRACT (PKWT)'",
    "'contract (pkwt)'": "'CONTRACT (PKWT)'",
    '"contract (pkwt)"': "'CONTRACT (PKWT)'"
}


def resolve_sql_ui_aliases(sql: str, tenant_id: str = "ALL") -> str:
    """
    Translates UI-centric aliases into physical DuckDB SQL.
    Example:
      UPDATE k3_candidates SET stage = 'interview' WHERE stage = 'screened';
    Translates to:
      UPDATE candidates SET recruitment_stage = 'INTERVIEW' WHERE recruitment_stage = 'SCREENED';
    """
    if not sql or not isinstance(sql, str):
        return sql

    resolved = sql.strip()

    # 1. Resolve Table Aliases
    for ui_table, physical_table in UI_TABLE_MAP.items():
        patterns = [rf'\b{re.escape(ui_table)}\b']
        if " " in ui_table:
            patterns.append(rf'\b{re.escape(ui_table.replace(" ", "_"))}\b')
            clean_token = re.sub(r'[^a-zA-Z0-9]+', '_', ui_table).strip('_')
            if clean_token:
                patterns.append(rf'\b{re.escape(clean_token)}\b')
        for pat in patterns:
            resolved = re.sub(pat, physical_table, resolved, flags=re.IGNORECASE)

    # Detect target table in the query
    detected_table = None
    for tbl in ["candidates", "employees", "job_postings", "leave_requests",
                "revenue_invoices", "telecom_clients", "mla_contracts", "site_land_leases", "site_utilities_cost",
                "inventory_items", "items", "stock_balances", "warehouses", "suppliers", "purchase_orders"]:
        if re.search(rf'\b{tbl}\b', resolved, re.IGNORECASE):
            detected_table = tbl
            break

    # 2. Resolve Column Aliases for detected table
    if detected_table and detected_table in UI_COLUMN_MAP:
        col_mappings = UI_COLUMN_MAP[detected_table]
        # Sort by key length descending to avoid prefix collision (e.g. 'unit price (idr)' before 'unit price')
        sorted_cols = sorted(col_mappings.items(), key=lambda x: len(x[0]), reverse=True)
        for ui_col, physical_col in sorted_cols:
            if ui_col == physical_col:
                continue
            # Match column in SET col = ..., WHERE col = ..., SELECT col, ORDER BY col, etc.
            pattern = rf'(\bSET\s+|\bWHERE\s+|\bAND\s+|\bOR\s+|\b,\s*|\bSELECT\s+|\bBY\s+)(["`]?{re.escape(ui_col)}["`]?)(\s*(=|<|>|LIKE|ILIKE|IN|\,|FROM|\bASC\b|\bDESC\b|\)|\s))'
            def _replace_col(m):
                return f"{m.group(1)}{physical_col}{m.group(3)}"
            resolved = re.sub(pattern, _replace_col, resolved, flags=re.IGNORECASE)

    # 3. Normalize Enum Values
    for lower_val, upper_val in VALUE_NORMALIZATIONS.items():
        pattern = re.escape(lower_val)
        resolved = re.sub(pattern, upper_val, resolved, flags=re.IGNORECASE)

    return resolved


def get_tenant_allowed_tables(tenant_id: str) -> List[str]:
    """Returns the whitelist of physical tables a given tenant is authorized to query/update."""
    t_clean = (tenant_id or "ALL").upper()
    return TENANT_ALLOWED_TABLES.get(t_clean, TENANT_ALLOWED_TABLES["ALL"])


def resolve_table_name(table_input: str, tenant_id: str = "ALL") -> str | None:
    """
    Auto-corrects table names (e.g. 'purchase_requisitions' -> 'purchase_requests')
    using semantic mapping and synonym dictionary. Returns None if table is completely unknown.
    """
    if not table_input or not isinstance(table_input, str):
        return None

    clean_name = table_input.strip().lower()
    clean_slug = re.sub(r'[^a-z0-9]+', '_', clean_name).strip('_')
    clean_spaced = re.sub(r'[^a-z0-9]+', ' ', clean_name).strip()

    # 1. Check direct physical table existence
    all_physical = TENANT_ALLOWED_TABLES["ALL"]
    if clean_name in all_physical:
        return clean_name
    if clean_slug in all_physical:
        return clean_slug

    # 2. Check UI_TABLE_MAP
    if clean_name in UI_TABLE_MAP:
        return UI_TABLE_MAP[clean_name]
    if clean_slug in UI_TABLE_MAP:
        return UI_TABLE_MAP[clean_slug]
    if clean_spaced in UI_TABLE_MAP:
        return UI_TABLE_MAP[clean_spaced]

    # 3. Fuzzy matching for common plural/singular or prefix mismatches
    for k, v in UI_TABLE_MAP.items():
        if clean_slug == k or clean_spaced == k or clean_name.startswith(k) or k.startswith(clean_name):
            return v
    for p in all_physical:
        if clean_slug.startswith(p) or p.startswith(clean_slug):
            return p

    return None

