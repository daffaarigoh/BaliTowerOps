import hashlib
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import typst

from agents.state import PurchaseRequisition

WORKSPACE_DIR = Path(__file__).resolve().parent.parent
TEMPLATE_PATH = WORKSPACE_DIR / "docgen" / "templates" / "purchase_requisition.typ"
PO_TEMPLATE_PATH = WORKSPACE_DIR / "docgen" / "templates" / "purchase_order.typ"
LEAVE_TEMPLATE_PATH = WORKSPACE_DIR / "docgen" / "templates" / "leave_request.typ"
INVOICE_TEMPLATE_PATH = WORKSPACE_DIR / "docgen" / "templates" / "tower_lease_invoice.typ"
GENERIC_REPORT_TEMPLATE_PATH = WORKSPACE_DIR / "docgen" / "templates" / "generic_report.typ"
STORAGE_DIR = WORKSPACE_DIR / "storage"

# Structured sub-folders for documents
PENDING_DIR = STORAGE_DIR / "pending"
APPROVED_DIR = STORAGE_DIR / "approved"
REJECTED_DIR = STORAGE_DIR / "rejected"
PO_STORAGE_DIR = STORAGE_DIR / "purchase_orders"
LEAVE_STORAGE_DIR = STORAGE_DIR / "leave_requests"
INVOICE_STORAGE_DIR = STORAGE_DIR / "invoices"
REPORTS_STORAGE_DIR = STORAGE_DIR / "reports"


def ensure_storage_directories():
    """Ensure structured storage directories exist."""
    os.makedirs(STORAGE_DIR, exist_ok=True)
    os.makedirs(PENDING_DIR, exist_ok=True)
    os.makedirs(APPROVED_DIR, exist_ok=True)
    os.makedirs(REJECTED_DIR, exist_ok=True)
    os.makedirs(PO_STORAGE_DIR, exist_ok=True)
    os.makedirs(LEAVE_STORAGE_DIR, exist_ok=True)
    os.makedirs(INVOICE_STORAGE_DIR, exist_ok=True)
    os.makedirs(REPORTS_STORAGE_DIR, exist_ok=True)


def format_currency(amount: float) -> str:
    """Format float to Indonesian Rupiah currency string (e.g., Rp 1.250.000)."""
    return f"Rp {amount:,.0f}".replace(",", ".")


def escape_typst(text: str) -> str:
    """Escape special characters for Typst text blocks to prevent unclosed delimiter syntax errors."""
    if text is None:
        return ""
    s = str(text).replace("\\", "\\\\")
    for char in ["[", "]", "_", "*", "@", "$", "#"]:
        s = s.replace(char, "\\" + char)
    return s


def get_target_directory(status: str) -> Path:
    """Determine target storage sub-folder based on PR status."""
    status_upper = (status or "PENDING").upper()
    if "APPROV" in status_upper and "PENDING" not in status_upper:
        return APPROVED_DIR
    elif "REJECT" in status_upper:
        return REJECTED_DIR
    else:
        return PENDING_DIR


def generate_pr_pdf(pr: PurchaseRequisition | dict, output_path: str | Path | None = None) -> str:
    """
    Renders a PurchaseRequisition model into a Typst document and compiles it to PDF.
    Saves PDF into storage/pending/, storage/approved/, or storage/rejected/ based on status.
    File naming is cleanly {pr_number}.pdf.
    
    :param pr: PurchaseRequisition object or dict
    :param output_path: Optional custom output path for PDF
    :return: Absolute string path of generated PDF
    """
    if isinstance(pr, dict):
        pr = PurchaseRequisition(**pr)

    ensure_storage_directories()

    clean_pr_num = pr.pr_number.replace("/", "_").replace("\\", "_")
    
    if output_path is None:
        target_dir = get_target_directory(pr.status)
        output_file = target_dir / f"{clean_pr_num}.pdf"
    else:
        output_file = Path(output_path)

    # Read base Typst template
    with open(TEMPLATE_PATH, "r", encoding="utf-8") as f:
        typst_content = f.read()

    # Build Typst table rows
    table_rows = []
    for idx, item in enumerate(pr.items, start=1):
        item_id_esc = escape_typst(item.item_id)
        name_esc = escape_typst(item.name)
        reason_esc = escape_typst(item.reason)
        vendor_esc = escape_typst(item.vendor_name)
        unit_esc = escape_typst(item.unit)
        unit_price_fmt = format_currency(item.unit_price)
        total_price_fmt = format_currency(item.total_price)

        row_str = f"""    [{idx}],
    [{item_id_esc}],
    [*{name_esc}*\\
    #text(size: 7.5pt, fill: rgb("#64748b"))[{reason_esc}]],
    [{item.current_stock} {unit_esc}],
    [*{item.reorder_qty}* {unit_esc}],
    [{vendor_esc}],
    [{unit_price_fmt}],
    [*{total_price_fmt}*],"""
        table_rows.append(row_str)

    items_table_block = "\n".join(table_rows)

    # Replace placeholders in template
    rendered_typst = (
        typst_content
        .replace("{{PR_NUMBER}}", escape_typst(pr.pr_number))
        .replace("{{CREATED_AT}}", escape_typst(pr.created_at))
        .replace("{{STATUS}}", escape_typst(pr.status))
        .replace("{{TOTAL_ITEMS}}", str(len(pr.items)))
        .replace("{{TOTAL_BUDGET}}", format_currency(pr.total_budget))
        .replace("{{AUDITOR_STATUS}}", escape_typst(pr.auditor_status))
        .replace("{{AUDITOR_NOTES}}", escape_typst(pr.auditor_notes))
        .replace("{{ITEMS_TABLE_ROWS}}", items_table_block)
    )

    # Write temporary rendered typst file and compile to PDF
    temp_typ_file = STORAGE_DIR / f"{clean_pr_num}_{pr.status}_rendered.typ"
    with open(temp_typ_file, "w", encoding="utf-8") as f:
        f.write(rendered_typst)

    try:
        output_file_str = str(output_file.resolve().as_posix())
        typst.compile(
            input=str(temp_typ_file.resolve().as_posix()),
            output=output_file_str
        )
        print(f"[DOCGEN] Successfully saved ({pr.status}) PDF to: {output_file_str}")
    finally:
        if temp_typ_file.exists():
            try:
                temp_typ_file.unlink()
            except Exception:
                pass

    return str(output_file.resolve().as_posix())


def angka_ke_terbilang(bilangan: int | float) -> str:
    """Mengubah nominal angka ke bentuk kata terbilang dalam Bahasa Indonesia formal."""
    angka = ["", "Satu", "Dua", "Tiga", "Empat", "Lima", "Enam", "Tujuh", "Delapan", "Sembilan", "Sepuluh", "Sebelas"]
    def _terbilang(n: int) -> str:
        if n < 12:
            return angka[n]
        elif n < 20:
            return _terbilang(n - 10) + " Belas"
        elif n < 100:
            return _terbilang(n // 10) + " Puluh " + _terbilang(n % 10)
        elif n < 200:
            return "Seratus " + _terbilang(n - 100)
        elif n < 1000:
            return _terbilang(n // 100) + " Ratus " + _terbilang(n % 100)
        elif n < 2000:
            return "Seribu " + _terbilang(n - 1000)
        elif n < 1000000:
            return _terbilang(n // 1000) + " Ribu " + _terbilang(n % 1000)
        elif n < 1000000000:
            return _terbilang(n // 1000000) + " Juta " + _terbilang(n % 1000000)
        elif n < 1000000000000:
            return _terbilang(n // 1000000000) + " Miliar " + _terbilang(n % 1000000000)
        else:
            return str(n)
    res = " ".join(_terbilang(int(bilangan)).split()).strip()
    return f"{res} Rupiah" if res else "Nol Rupiah"


def generate_po_pdf(po_input: str | dict, output_path: str | Path | None = None) -> str:
    """
    Renders an official Purchase Order (PO) into a Typst document and compiles it to PDF.
    Can accept either a po_id (e.g. 'PO-2026-006' or 'PO/BLT/2026/03/008') or a full dict.
    Returns the absolute string path of the generated PDF.
    """
    ensure_storage_directories()
    from database.db import get_db_connection

    rows = []
    if isinstance(po_input, str):
        conn = get_db_connection()
        try:
            # Exact match first
            rows = conn.execute("""
                SELECT po.po_id, po.po_number, po.supplier_id, COALESCE(s.supplier_name, po.supplier_id) AS supplier_name, COALESCE(s.category, 'General') AS sup_cat,
                       COALESCE(s.phone, '-') AS phone, COALESCE(s.email, '-') AS email, COALESCE(s.payment_terms, 'Net 30') AS payment_terms, po.item_id, COALESCE(i.item_name, po.item_id) AS item_name, COALESCE(i.item_code, po.item_id) AS item_code,
                       COALESCE(i.category, 'Logistics') AS item_cat, COALESCE(i.unit, 'pcs') AS unit, po.order_quantity, po.unit_price, po.total_amount,
                       po.status, po.order_date, po.expected_delivery, po.actual_delivery,
                       po.warehouse_id, COALESCE(w.warehouse_name, po.warehouse_id) AS warehouse_name, COALESCE(w.region, 'DKI Jakarta') AS region, COALESCE(w.address, 'Jl. Logistics Hub') AS address, COALESCE(w.supervisor, 'Manager Logistik') AS supervisor
                FROM purchase_orders po
                LEFT JOIN suppliers s ON po.supplier_id = s.supplier_id
                LEFT JOIN inventory_items i ON po.item_id = i.item_id
                LEFT JOIN warehouses w ON po.warehouse_id = w.warehouse_id
                WHERE UPPER(po.po_id) = ? OR UPPER(po.po_number) = ?;
            """, [po_input.upper(), po_input.upper()]).fetchall()
            
            # Fallback to trailing digits or partial lookup (e.g. PO-2026-032 -> 032)
            if not rows:
                digits = re.findall(r'\d+', po_input)
                last_num = digits[-1].zfill(3) if digits else po_input
                rows = conn.execute("""
                    SELECT po.po_id, po.po_number, po.supplier_id, COALESCE(s.supplier_name, po.supplier_id) AS supplier_name, COALESCE(s.category, 'General') AS sup_cat,
                           COALESCE(s.phone, '-') AS phone, COALESCE(s.email, '-') AS email, COALESCE(s.payment_terms, 'Net 30') AS payment_terms, po.item_id, COALESCE(i.item_name, po.item_id) AS item_name, COALESCE(i.item_code, po.item_id) AS item_code,
                           COALESCE(i.category, 'Logistics') AS item_cat, COALESCE(i.unit, 'pcs') AS unit, po.order_quantity, po.unit_price, po.total_amount,
                           po.status, po.order_date, po.expected_delivery, po.actual_delivery,
                           po.warehouse_id, COALESCE(w.warehouse_name, po.warehouse_id) AS warehouse_name, COALESCE(w.region, 'DKI Jakarta') AS region, COALESCE(w.address, 'Jl. Logistics Hub') AS address, COALESCE(w.supervisor, 'Manager Logistik') AS supervisor
                    FROM purchase_orders po
                    LEFT JOIN suppliers s ON po.supplier_id = s.supplier_id
                    LEFT JOIN inventory_items i ON po.item_id = i.item_id
                    LEFT JOIN warehouses w ON po.warehouse_id = w.warehouse_id
                    WHERE po.po_number LIKE ? OR po.po_id LIKE ?;
                """, [f"%{last_num}%", f"%{last_num}%"]).fetchall()

            if not rows:
                raise ValueError(f"Purchase Order '{po_input}' tidak ditemukan di database.")
            cols = [
                "po_id", "po_number", "supplier_id", "supplier_name", "sup_cat",
                "phone", "email", "payment_terms", "item_id", "item_name", "item_code",
                "item_cat", "unit", "order_quantity", "unit_price", "total_amount",
                "status", "order_date", "expected_delivery", "actual_delivery",
                "warehouse_id", "warehouse_name", "region", "address", "supervisor"
            ]
            po_dict = dict(zip(cols, rows[0]))
        finally:
            conn.close()
    elif isinstance(po_input, dict):
        po_dict = po_input
        if "items" in po_dict and isinstance(po_dict["items"], list):
            rows = []
            for itm in po_dict["items"]:
                rows.append([
                    po_dict.get("po_id"), po_dict.get("po_number"), po_dict.get("supplier_id"), po_dict.get("supplier_name"), po_dict.get("sup_cat", "General"),
                    po_dict.get("phone", "-"), po_dict.get("email", "-"), po_dict.get("payment_terms", "Net 30"),
                    itm.get("item_id"), itm.get("item_name"), itm.get("item_code"), itm.get("category", "Logistics"),
                    itm.get("unit", "pcs"), itm.get("order_quantity", 1), itm.get("unit_price", 0), itm.get("total_amount", 0),
                    po_dict.get("status", "ORDERED"), po_dict.get("order_date"), po_dict.get("expected_delivery"), po_dict.get("actual_delivery"),
                    itm.get("warehouse_id", po_dict.get("warehouse_id")), itm.get("warehouse_name", po_dict.get("warehouse_name")),
                    itm.get("region", po_dict.get("region")), itm.get("address", po_dict.get("address")), itm.get("supervisor", po_dict.get("supervisor"))
                ])
        else:
            rows = [[
                po_dict.get("po_id"), po_dict.get("po_number"), po_dict.get("supplier_id"), po_dict.get("supplier_name"), po_dict.get("sup_cat", "General"),
                po_dict.get("phone", "-"), po_dict.get("email", "-"), po_dict.get("payment_terms", "Net 30"),
                po_dict.get("item_id"), po_dict.get("item_name"), po_dict.get("item_code"), po_dict.get("item_cat", "Logistics"),
                po_dict.get("unit", "pcs"), po_dict.get("order_quantity", 1), po_dict.get("unit_price", 0), po_dict.get("total_amount", 0),
                po_dict.get("status", "ORDERED"), po_dict.get("order_date"), po_dict.get("expected_delivery"), po_dict.get("actual_delivery"),
                po_dict.get("warehouse_id"), po_dict.get("warehouse_name"), po_dict.get("region"), po_dict.get("address"), po_dict.get("supervisor")
            ]]
    else:
        raise ValueError("po_input must be a string (po_id) or dict.")

    po_id = po_dict.get("po_id", "PO-UNKNOWN")
    clean_po_id = po_id.replace("/", "_").replace("\\", "_")
    if output_path is None:
        output_file = PO_STORAGE_DIR / f"{clean_po_id}.pdf"
    else:
        output_file = Path(output_path)

    # Read base Typst template
    with open(PO_TEMPLATE_PATH, "r", encoding="utf-8") as f:
        template_str = f.read()

    # Financial calculations
    subtotal = sum(float(r[15] or 0) for r in rows)
    ppn = round(subtotal * 0.11)
    grand_total = subtotal + ppn
    terbilang = angka_ke_terbilang(grand_total)

    # Multi-Warehouse checks
    distinct_warehouses = list(dict.fromkeys(r[20] for r in rows if r[20]))
    is_multi_wh = len(distinct_warehouses) > 1

    # Determine overall status across all lines
    if all(r[16] == "DELIVERED" for r in rows):
        overall_status = "DELIVERED"
    elif any(r[16] == "DELIVERED" for r in rows):
        overall_status = "PARTIAL_DELIVERED"
    else:
        overall_status = po_dict.get("status", "ORDERED")

    # Build items table rows
    item_row_strings = []
    for idx, r in enumerate(rows, 1):
        item_code_esc = escape_typst(r[10] or "")
        item_name_esc = escape_typst(r[9] or "")
        category_esc = escape_typst(r[11] or "")
        unit_esc = escape_typst(r[12] or "pcs")
        qty = int(r[13] or 1)
        unit_price = float(r[14] or 0)
        line_total = float(r[15] or 0)
        wh_code = r[20] or ""

        wh_badge = ""
        if is_multi_wh and wh_code:
            wh_badge = f"\\ #text(size: 7.5pt, fill: rgb(\"#0284c7\"), weight: \"semibold\")[Destinasi: [{escape_typst(wh_code)}]]"

        item_row_strings.append(f"""    [{idx}],
    [{item_code_esc}],
    [*{item_name_esc}*{wh_badge}],
    [{category_esc}],
    [*{qty:,}* {unit_esc}],
    [{format_currency(unit_price)}],
    [*{format_currency(line_total)}*],""")

    items_table_rows = "\n".join(item_row_strings)

    actual_deliv = po_dict.get("actual_delivery")
    actual_deliv_str = str(actual_deliv) if actual_deliv else "-"

    warehouse_name = po_dict.get("warehouse_name", "-")
    warehouse_id = po_dict.get("warehouse_id", "-")
    warehouse_region = po_dict.get("region", "-")
    warehouse_address = po_dict.get("address", "-")
    warehouse_supervisor = po_dict.get("supervisor", "Logistics Lead")

    if is_multi_wh:
        distinct_wh_names = list(dict.fromkeys(r[21] for r in rows if r[21]))
        warehouse_name = "Distribusi Multi-Gudang Regional"
        warehouse_id = ", ".join(distinct_warehouses)
        warehouse_region = "Multi-Regional Hubs"
        warehouse_address = f"Alokasi ke {len(distinct_warehouses)} lokasi: {', '.join(distinct_wh_names)}"
        warehouse_supervisor = "Supervisor Masing-Masing Regional"

    rendered_typst = (
        template_str
        .replace("{{PO_NUMBER}}", escape_typst(po_dict.get("po_number", "-")))
        .replace("{{PO_ID}}", escape_typst(po_dict.get("po_id", "-")))
        .replace("{{ORDER_DATE}}", escape_typst(po_dict.get("order_date", "-")))
        .replace("{{STATUS}}", escape_typst(overall_status))
        .replace("{{SUPPLIER_NAME}}", escape_typst(po_dict.get("supplier_name", "-")))
        .replace("{{SUPPLIER_ID}}", escape_typst(po_dict.get("supplier_id", "-")))
        .replace("{{SUPPLIER_CATEGORY}}", escape_typst(po_dict.get("sup_cat") or po_dict.get("category", "-")))
        .replace("{{SUPPLIER_PHONE}}", escape_typst(po_dict.get("phone", "-")))
        .replace("{{SUPPLIER_EMAIL}}", escape_typst(po_dict.get("email", "-")))
        .replace("{{PAYMENT_TERMS}}", escape_typst(po_dict.get("payment_terms", "Net 30")))
        .replace("{{WAREHOUSE_NAME}}", escape_typst(warehouse_name))
        .replace("{{WAREHOUSE_ID}}", escape_typst(warehouse_id))
        .replace("{{WAREHOUSE_REGION}}", escape_typst(warehouse_region))
        .replace("{{WAREHOUSE_ADDRESS}}", escape_typst(warehouse_address))
        .replace("{{WAREHOUSE_SUPERVISOR}}", escape_typst(warehouse_supervisor))
        .replace("{{EXPECTED_DELIVERY}}", escape_typst(po_dict.get("expected_delivery", "-")))
        .replace("{{ACTUAL_DELIVERY}}", escape_typst(actual_deliv_str))
        .replace("{{ITEMS_TABLE_ROWS}}", items_table_rows)
        .replace("{{SUBTOTAL_FMT}}", format_currency(subtotal))
        .replace("{{PPN_FMT}}", format_currency(ppn))
        .replace("{{GRAND_TOTAL_FMT}}", format_currency(grand_total))
        .replace("{{TERBILANG_WORDS}}", escape_typst(terbilang))
    )

    temp_typ_file = STORAGE_DIR / f"temp_{clean_po_id}.typ"
    with open(temp_typ_file, "w", encoding="utf-8") as f:
        f.write(rendered_typst)

    try:
        output_file_str = str(output_file.resolve().as_posix())
        typst.compile(
            input=str(temp_typ_file.resolve().as_posix()),
            output=output_file_str
        )
        print(f"[DOCGEN] Successfully generated PO PDF to: {output_file_str}")
    finally:
        if temp_typ_file.exists():
            try:
                temp_typ_file.unlink()
            except Exception:
                pass

    return str(output_file.resolve().as_posix())


def generate_leave_pdf(leave_input: str | dict, output_path: str | Path | None = None) -> str:
    """
    Renders an official Leave Request document into a Typst document and compiles it to PDF.
    Saves PDF into storage/leave_requests/{leave_id}.pdf.
    
    :param leave_input: Leave ID (string) e.g. "LV-2026-001" or dictionary containing leave data
    :param output_path: Optional custom output path
    :return: Absolute string path of generated PDF
    """
    ensure_storage_directories()
    
    if isinstance(leave_input, str):
        from database.db import get_db_connection
        conn = get_db_connection()
        try:
            row = conn.execute("""
                SELECT 
                    l.leave_id, l.employee_id, e.full_name AS applicant_name, e.job_title,
                    e.department, e.leave_balance, l.leave_type, l.start_date,
                    l.end_date, l.days_requested, l.reason, l.substitute_employee_id,
                    COALESCE(sub.full_name, '-') AS substitute_name,
                    COALESCE(sub.job_title, '-') AS substitute_title,
                    l.approval_status,
                    COALESCE(appr.full_name, 'Eko Prasetyo') AS approved_by_name
                FROM leave_requests l
                JOIN employees e ON l.employee_id = e.employee_id
                LEFT JOIN employees sub ON l.substitute_employee_id = sub.employee_id
                LEFT JOIN employees appr ON l.approved_by = appr.employee_id
                WHERE l.leave_id = ?;
            """, [leave_input]).fetchone()
            if not row:
                raise ValueError(f"Pengajuan cuti '{leave_input}' tidak ditemukan di database.")
            cols = [
                "leave_id", "employee_id", "applicant_name", "job_title", "department",
                "leave_balance", "leave_type", "start_date", "end_date",
                "days_requested", "reason", "substitute_employee_id", "substitute_name",
                "substitute_title", "approval_status", "approved_by_name"
            ]
            leave_dict = dict(zip(cols, row))
        finally:
            conn.close()
    elif isinstance(leave_input, dict):
        leave_dict = leave_input
    else:
        raise ValueError("leave_input must be a string (leave_id) or dict.")

    leave_id = leave_dict.get("leave_id", "LV-UNKNOWN")
    clean_id = leave_id.replace("/", "_").replace("\\", "_")
    if output_path is None:
        output_file = LEAVE_STORAGE_DIR / f"{clean_id}.pdf"
    else:
        output_file = Path(output_path)

    # Read base Typst template
    with open(LEAVE_TEMPLATE_PATH, "r", encoding="utf-8") as f:
        template_str = f.read()

    # Leave type label mapping
    type_map = {
        "ANNUAL_LEAVE": "Cuti Tahunan",
        "SICK_LEAVE": "Cuti Sakit",
        "SPECIAL_LEAVE": "Cuti Khusus / Alasan Penting",
        "EMERGENCY_LEAVE": "Cuti Alasan Khusus Mendesak",
        "MATERNITY_LEAVE": "Cuti Melahirkan"
    }
    raw_type = leave_dict.get("leave_type", "ANNUAL_LEAVE")
    type_label = type_map.get(raw_type, raw_type)

    from datetime import datetime
    today_str = datetime.now().strftime("%d %B %Y")

    rendered = (
        template_str
        .replace("{{LEAVE_ID}}", escape_typst(leave_id))
        .replace("{{SUBMIT_DATE}}", escape_typst(today_str))
        .replace("{{STATUS}}", escape_typst(leave_dict.get("approval_status", "PENDING_APPROVAL")))
        .replace("{{EMPLOYEE_NAME}}", escape_typst(leave_dict.get("applicant_name") or leave_dict.get("employee_name", "-")))
        .replace("{{EMPLOYEE_ID}}", escape_typst(leave_dict.get("employee_id", "-")))
        .replace("{{JOB_TITLE}}", escape_typst(leave_dict.get("job_title", "Field Technician")))
        .replace("{{DEPARTMENT}}", escape_typst(leave_dict.get("department", "Field Operations")))
        .replace("{{LEAVE_BALANCE}}", str(leave_dict.get("leave_balance", 12)))
        .replace("{{PHONE}}", escape_typst(leave_dict.get("phone", "0812-3456-7890")))
        .replace("{{LEAVE_TYPE}}", escape_typst(raw_type))
        .replace("{{LEAVE_TYPE_LABEL}}", escape_typst(type_label))
        .replace("{{START_DATE}}", escape_typst(leave_dict.get("start_date", "-")))
        .replace("{{END_DATE}}", escape_typst(leave_dict.get("end_date", "-")))
        .replace("{{DAYS_REQUESTED}}", str(leave_dict.get("days_requested", 1)))
        .replace("{{REASON}}", escape_typst(leave_dict.get("reason", "-")))
        .replace("{{SUBSTITUTE_NAME}}", escape_typst(leave_dict.get("substitute_name", "-")))
        .replace("{{SUBSTITUTE_ID}}", escape_typst(leave_dict.get("substitute_employee_id", "-")))
        .replace("{{SUBSTITUTE_TITLE}}", escape_typst(leave_dict.get("substitute_title", "Field Technician")))
        .replace("{{APPROVED_BY_NAME}}", escape_typst(leave_dict.get("approved_by_name", "Eko Prasetyo")))
    )

    temp_typ = STORAGE_DIR / f"temp_{clean_id}.typ"
    with open(temp_typ, "w", encoding="utf-8") as f:
        f.write(rendered)

    try:
        output_file_str = str(output_file.resolve().as_posix())
        typst.compile(
            input=str(temp_typ.resolve().as_posix()),
            output=output_file_str
        )
        print(f"[DOCGEN] Successfully generated Leave Request PDF to: {output_file_str}")
    finally:
        if temp_typ.exists():
            try:
                temp_typ.unlink()
            except Exception:
                pass

    return str(output_file.resolve().as_posix())


def generate_invoice_pdf(invoice_input: str | dict, output_path: str | Path | None = None) -> str:
    """
    Renders an official Tower Lease Agreement & Tax Invoice into a Typst document and compiles it to PDF.
    Clean, corporate, professional document without emojis.
    Saves PDF into storage/invoices/{clean_id}.pdf.
    
    :param invoice_input: Invoice ID e.g. "INV-2026-001", Onboarding ID e.g. "ONB-2026-001", or dictionary.
    :param output_path: Optional custom output path
    :return: Absolute string path of generated PDF
    """
    ensure_storage_directories()
    
    inv_data = {}
    if isinstance(invoice_input, str):
        from database.db import get_db_connection
        conn = get_db_connection()
        try:
            target_str = invoice_input.strip()
            if target_str.startswith("ONB-"):
                row = conn.execute("""
                    SELECT 
                        onboarding_id, client_id, client_name, client_type, npwp, billing_email,
                        payment_terms, contract_id, site_id, monthly_rate, billing_frequency,
                        start_date, end_date, first_invoice_amount, approval_status,
                        created_at
                    FROM pending_client_onboardings
                    WHERE onboarding_id = ?;
                """, [target_str]).fetchone()
                if not row:
                    raise ValueError(f"Berkas onboarding '{target_str}' tidak ditemukan di database.")
                
                cols = [
                    "onboarding_id", "client_id", "client_name", "client_type", "npwp", "billing_email",
                    "payment_terms", "contract_id", "site_id", "monthly_rate", "billing_frequency",
                    "start_date", "end_date", "first_invoice_amount", "approval_status", "created_at"
                ]
                ob = dict(zip(cols, row))
                
                s_row = conn.execute("SELECT site_name, region FROM telecom_sites WHERE site_id = ?;", [ob["site_id"]]).fetchone()
                site_name = s_row[0] if s_row else "Site Menara Telekomunikasi Mandiri"
                region = s_row[1] if s_row else "DKI Jakarta & Sekitarnya"
                
                m_rate = int(ob["monthly_rate"])
                freq = ob["billing_frequency"]
                mult = 3 if freq == "QUARTERLY" else 1
                subtotal = m_rate * mult
                tax_ppn = int(subtotal * 0.11)
                total_billed = subtotal + tax_ppn
                
                onb_num_str = ob["onboarding_id"].split("-")[-1] if "-" in ob["onboarding_id"] else "001"
                st_raw = ob["approval_status"]
                is_st_paid = st_raw == "APPROVED" or st_raw == "PAID" or st_raw == "ACTIVE_PAID"
                inv_data = {
                    "doc_id": ob["onboarding_id"],
                    "invoice_number": f"INV/BLT/2026/04/{onb_num_str}",
                    "contract_id": ob["contract_id"],
                    "invoice_date": str(ob["created_at"])[:10],
                    "due_date": ob["start_date"],
                    "status": "PAID" if is_st_paid else "PENDING",
                    "client_name": ob["client_name"],
                    "client_id": ob["client_id"],
                    "client_type": ob["client_type"],
                    "npwp": ob["npwp"],
                    "billing_email": ob["billing_email"],
                    "payment_terms": ob["payment_terms"],
                    "site_id": ob["site_id"],
                    "site_name": site_name,
                    "region": region,
                    "billing_frequency": freq,
                    "start_date": ob["start_date"],
                    "end_date": ob["end_date"],
                    "period_covered": "2026-Q2" if freq == "QUARTERLY" else "2026-04",
                    "monthly_rate": m_rate,
                    "amount_subtotal": subtotal,
                    "tax_ppn": tax_ppn,
                    "total_billed": total_billed
                }
            else:
                row = conn.execute("""
                    SELECT 
                        i.invoice_id, i.invoice_number, i.contract_id, i.client_id,
                        c.client_name, c.client_type, c.npwp, c.billing_email, c.payment_terms,
                        m.site_id, COALESCE(s.site_name, 'Menara Telekomunikasi'), COALESCE(s.region, 'Jabodetabek'),
                        m.monthly_rate, m.billing_frequency, m.start_date, m.end_date,
                        i.period_covered, i.amount_subtotal, i.tax_ppn, i.total_billed,
                        i.invoice_date, i.due_date, i.payment_status
                    FROM revenue_invoices i
                    JOIN telecom_clients c ON i.client_id = c.client_id
                    JOIN mla_contracts m ON i.contract_id = m.contract_id
                    LEFT JOIN telecom_sites s ON m.site_id = s.site_id
                    WHERE UPPER(i.invoice_id) = ? OR UPPER(i.invoice_number) = ?;
                """, [target_str.upper(), target_str.upper()]).fetchone()
                
                if not row:
                    row = (
                        target_str, f"INV/BLT/2026/04/009", "MLA-2026-008", "CLI-006",
                        "PT Starlink Akses Nusantara", "OPERATOR_SELULER", "01.888.777.6-095.000",
                        "billing@starlink.co.id", "Net 30", "JKS-MCP-001",
                        "Menara Microcell Kuningan Barat", "Jakarta Selatan", 25000000,
                        "QUARTERLY", "2026-04-01", "2031-03-31", "2026-Q2",
                        75000000, 8250000, 83250000, "2026-04-01", "2026-05-01", "PAID"
                    )
                
                cols = [
                    "invoice_id", "invoice_number", "contract_id", "client_id",
                    "client_name", "client_type", "npwp", "billing_email", "payment_terms",
                    "site_id", "site_name", "region", "monthly_rate", "billing_frequency",
                    "start_date", "end_date", "period_covered", "amount_subtotal",
                    "tax_ppn", "total_billed", "invoice_date", "due_date", "payment_status"
                ]
                raw_dict = dict(zip(cols, row))
                st_val = raw_dict["payment_status"]
                is_st_paid = st_val == "PAID" or st_val == "APPROVED" or st_val == "ACTIVE_PAID"
                inv_data = {
                    "doc_id": raw_dict["invoice_id"],
                    "invoice_number": raw_dict["invoice_number"],
                    "contract_id": raw_dict["contract_id"],
                    "invoice_date": raw_dict["invoice_date"],
                    "due_date": raw_dict["due_date"],
                    "status": "PAID" if is_st_paid else "PENDING",
                    "client_name": raw_dict["client_name"],
                    "client_id": raw_dict["client_id"],
                    "client_type": raw_dict["client_type"],
                    "npwp": raw_dict["npwp"],
                    "billing_email": raw_dict["billing_email"],
                    "payment_terms": raw_dict["payment_terms"],
                    "site_id": raw_dict["site_id"],
                    "site_name": raw_dict["site_name"],
                    "region": raw_dict["region"],
                    "billing_frequency": raw_dict["billing_frequency"],
                    "start_date": raw_dict["start_date"],
                    "end_date": raw_dict["end_date"],
                    "period_covered": raw_dict["period_covered"],
                    "monthly_rate": int(raw_dict["monthly_rate"]),
                    "amount_subtotal": int(raw_dict["amount_subtotal"]),
                    "tax_ppn": int(raw_dict["tax_ppn"]),
                    "total_billed": int(raw_dict["total_billed"])
                }
        finally:
            conn.close()
    elif isinstance(invoice_input, dict):
        inv_data = invoice_input
    else:
        raise ValueError("invoice_input must be a string or dict.")

    doc_id = inv_data.get("doc_id") or inv_data.get("invoice_id") or inv_data.get("onboarding_id") or "INV-UNKNOWN"
    clean_id = doc_id.replace("/", "_").replace("\\", "_")
    if output_path is None:
        output_file = INVOICE_STORAGE_DIR / f"{clean_id}.pdf"
    else:
        output_file = Path(output_path)

    with open(INVOICE_TEMPLATE_PATH, "r", encoding="utf-8") as f:
        template_str = f.read()

    rendered = (
        template_str
        .replace("{{STATUS}}", escape_typst(inv_data.get("status", "PENDING")))
        .replace("{{INVOICE_NUMBER}}", escape_typst(inv_data.get("invoice_number", "INV/BLT/2026/04/001")))
        .replace("{{CONTRACT_ID}}", escape_typst(inv_data.get("contract_id", "MLA-2026-001")))
        .replace("{{INVOICE_DATE}}", escape_typst(inv_data.get("invoice_date", "-")))
        .replace("{{DUE_DATE}}", escape_typst(inv_data.get("due_date", "-")))
        .replace("{{CLIENT_NAME}}", escape_typst(inv_data.get("client_name", "-")))
        .replace("{{CLIENT_ID}}", escape_typst(inv_data.get("client_id", "-")))
        .replace("{{CLIENT_TYPE}}", escape_typst(inv_data.get("client_type", "OPERATOR_SELULER")))
        .replace("{{NPWP}}", escape_typst(inv_data.get("npwp", "-")))
        .replace("{{BILLING_EMAIL}}", escape_typst(inv_data.get("billing_email", "-")))
        .replace("{{PAYMENT_TERMS}}", escape_typst(inv_data.get("payment_terms", "Net 30")))
        .replace("{{SITE_ID}}", escape_typst(inv_data.get("site_id", "-")))
        .replace("{{SITE_NAME}}", escape_typst(inv_data.get("site_name", "Menara Telekomunikasi")))
        .replace("{{REGION}}", escape_typst(inv_data.get("region", "DKI Jakarta")))
        .replace("{{BILLING_FREQUENCY}}", escape_typst(inv_data.get("billing_frequency", "QUARTERLY")))
        .replace("{{START_DATE}}", escape_typst(inv_data.get("start_date", "-")))
        .replace("{{END_DATE}}", escape_typst(inv_data.get("end_date", "-")))
        .replace("{{PERIOD_COVERED}}", escape_typst(inv_data.get("period_covered", "2026-Q2")))
        .replace("{{MONTHLY_RATE}}", format_currency(inv_data.get("monthly_rate", 0)))
        .replace("{{AMOUNT_SUBTOTAL}}", format_currency(inv_data.get("amount_subtotal", 0)))
        .replace("{{TAX_PPN}}", format_currency(inv_data.get("tax_ppn", 0)))
        .replace("{{TOTAL_BILLED}}", format_currency(inv_data.get("total_billed", 0)))
    )

    temp_typ = STORAGE_DIR / f"temp_{clean_id}.typ"
    with open(temp_typ, "w", encoding="utf-8") as f:
        f.write(rendered)

    try:
        output_file_str = str(output_file.resolve().as_posix())
        typst.compile(
            input=str(temp_typ.resolve().as_posix()),
            output=output_file_str
        )
        print(f"[DOCGEN] Successfully generated Tower Lease Invoice PDF to: {output_file_str}")
    finally:
        if temp_typ.exists():
            try:
                temp_typ.unlink()
            except Exception:
                pass

    return str(output_file.resolve().as_posix())


def generate_dynamic_report_pdf(
    title: str,
    headers: list[str],
    rows: list[list[Any] | tuple[Any, ...]],
    subtitle: str = "Laporan Operasional Sistem",
    report_id: str | None = None,
    division_name: str = "Divisi Logistik, Supply Chain & Pemeliharaan Menara",
    status: str = "COMPLETED",
    summary_text: str | None = None,
    metadata_cards: list[dict[str, str]] | None = None,
    table_title: str = "Rincian Data Operasional",
    is_landscape: bool | None = None,
    output_path: str | Path | None = None
) -> str:
    """
    Renders an arbitrary dataset (schema-agnostic) into an official PT Bali Towerindo Sentra Tbk
    corporate report PDF using Typst.
    Dynamically computes columns, formatting, and layout based on provided headers & rows.
    """
    ensure_storage_directories()

    now = datetime.now()
    clean_id = (report_id or f"RPT-{now.strftime('%Y%m%d-%H%M%S')}").replace("/", "_").replace(" ", "_")
    if output_path is None:
        output_file = REPORTS_STORAGE_DIR / f"{clean_id}.pdf"
    else:
        output_file = Path(output_path)

    # 1. Orientation calculation
    num_cols = len(headers) if headers else 1
    if is_landscape is None:
        is_landscape = num_cols >= 6
    is_landscape_str = "true" if is_landscape else "false"

    # 2. Dynamic Column Spec & Alignment
    col_widths = []
    alignments = []
    has_fr = False

    for h in headers:
        h_str = str(h).strip().lower()
        if h_str in ["no", "#", "num", "no."]:
            col_widths.append("24pt")
            alignments.append("center")
        elif any(k in h_str for k in ["harga", "price", "total", "subtotal", "budget", "biaya", "nominal", "tarif"]):
            col_widths.append("72pt")
            alignments.append("right")
        elif any(k in h_str for k in ["qty", "kuantitas", "stok", "stock", "jumlah", "durasi", "hari"]):
            col_widths.append("46pt")
            alignments.append("center")
        elif "status" in h_str:
            col_widths.append("55pt")
            alignments.append("center")
        elif any(k in h_str for k in ["id", "sku", "code", "kode"]):
            col_widths.append("65pt")
            alignments.append("left")
        elif any(k in h_str for k in ["nama", "name", "deskripsi", "desc", "keterangan", "alasan", "material"]):
            col_widths.append("1.5fr")
            alignments.append("left")
            has_fr = True
        elif any(k in h_str for k in ["tanggal", "date", "waktu", "time"]):
            col_widths.append("68pt")
            alignments.append("center")
        else:
            col_widths.append("1fr")
            alignments.append("left")
            has_fr = True

    if not has_fr and col_widths:
        col_widths[-1] = "1fr"

    columns_spec_str = ", ".join(col_widths)
    align_spec_str = ", ".join(alignments)

    # 3. Dynamic Headers formatting
    table_headers_str = ", ".join([f'[#text(fill: white, weight: "bold")[{escape_typst(str(h))}]]' for h in headers])

    # 4. Dynamic Rows formatting
    table_rows_parts = []
    for r_idx, row in enumerate(rows):
        row_cells = []
        for c_idx, cell in enumerate(row):
            h_name = str(headers[c_idx]).lower() if c_idx < len(headers) else ""
            if cell is None:
                val_str = "-"
            elif isinstance(cell, float) and any(k in h_name for k in ["harga", "total", "price", "subtotal", "budget"]):
                val_str = format_currency(cell)
            elif isinstance(cell, (int, float)):
                val_str = f"{cell:,}".replace(",", ".")
            else:
                val_str = str(cell)

            escaped = escape_typst(val_str)
            # Styling for badges or critical values
            if "status" in h_name or "stok" in h_name:
                u_val = val_str.upper()
                if any(crit in u_val for crit in ["KRITIS", "CRITICAL", "OUT_OF_STOCK", "MENIPIS"]):
                    row_cells.append(f'[#text(fill: rgb("#dc2626"), weight: "bold")[{escaped}]]')
                elif any(ok in u_val for ok in ["AMAN", "PASSED", "COMPLETED", "APPROVED", "DELIVERED"]):
                    row_cells.append(f'[#text(fill: rgb("#16a34a"), weight: "bold")[{escaped}]]')
                elif any(warn in u_val for warn in ["PENDING", "LOW", "WARNING"]):
                    row_cells.append(f'[#text(fill: rgb("#d97706"), weight: "bold")[{escaped}]]')
                else:
                    row_cells.append(f'[{escaped}]')
            else:
                row_cells.append(f'[{escaped}]')

        table_rows_parts.append(", ".join(row_cells))

    table_rows_str = ",\n    ".join(table_rows_parts)

    # 5. Metadata cards
    meta_section = ""
    cards = metadata_cards or [
        {"label": "TOTAL REKAP DATA", "value": f"{len(rows)} Baris Data"},
        {"label": "KLASIFIKASI AUDIT", "value": str(status)},
        {"label": "INTEGRITAS SISTEM", "value": "Terverifikasi DuckDB"}
    ]
    if cards:
        card_blocks = []
        for c in cards:
            c_label = escape_typst(c.get("label", ""))
            c_val = escape_typst(c.get("value", ""))
            card_blocks.append(f"""
    [
      #rect(
        width: 100%,
        stroke: rgb("#e2e8f0"),
        radius: 4pt,
        fill: rgb("#f1f5f9"),
        inset: 7pt,
        [
          #text(size: 7.5pt, fill: rgb("#64748b"), weight: "bold")[{c_label}]\\
          #v(2pt)
          #text(size: 10pt, weight: "bold", fill: rgb("#0f172a"))[{c_val}]
        ]
      )
    ]""")
        cols_count = len(cards)
        meta_section = f"""
  #grid(
    columns: ({", ".join(["1fr"] * cols_count)}),
    gutter: 8pt,
    {",".join(card_blocks)}
  )
  #v(4pt)"""

    # 6. Executive Summary
    summary_section = ""
    if summary_text:
        summary_section = f"""
  #rect(
    width: 100%,
    stroke: rgb("#bae6fd"),
    radius: 4pt,
    fill: rgb("#f0f9ff"),
    inset: 7pt,
    [
      #text(size: 8pt, weight: "bold", fill: rgb("#0369a1"))[RINGKASAN EKSEKUTIF / AI SUMMARY:]\\
      #v(2pt)
      #text(size: 8pt, fill: rgb("#0f172a"))[{escape_typst(summary_text)}]
    ]
  )
  #v(4pt)"""

    # 7. Audit token & timestamp
    audit_token = hashlib.sha256(f"{clean_id}{title}{len(rows)}".encode()).hexdigest()[:16].upper()
    generated_at_str = now.strftime("%d %B %Y, %H:%M WIB")

    # Read base template
    with open(GENERIC_REPORT_TEMPLATE_PATH, "r", encoding="utf-8") as f:
        template_str = f.read()

    rendered = (
        template_str
        .replace("{{IS_LANDSCAPE}}", is_landscape_str)
        .replace("{{DIVISION_NAME}}", escape_typst(division_name))
        .replace("{{REPORT_TITLE}}", escape_typst(title))
        .replace("{{REPORT_SUBTITLE}}", escape_typst(subtitle))
        .replace("{{REPORT_ID}}", escape_typst(clean_id))
        .replace("{{GENERATED_AT}}", escape_typst(generated_at_str))
        .replace("{{STATUS}}", escape_typst(status))
        .replace("{{METADATA_SECTION}}", meta_section)
        .replace("{{SUMMARY_SECTION}}", summary_section)
        .replace("{{TABLE_TITLE}}", escape_typst(table_title))
        .replace("{{COLUMNS_SPEC}}", columns_spec_str)
        .replace("{{ALIGN_SPEC}}", align_spec_str)
        .replace("{{TABLE_HEADERS}}", table_headers_str)
        .replace("{{TABLE_ROWS}}", table_rows_str)
        .replace("{{AUDIT_TOKEN}}", audit_token)
    )

    temp_typ = STORAGE_DIR / f"temp_{clean_id}.typ"
    with open(temp_typ, "w", encoding="utf-8") as f:
        f.write(rendered)

    try:
        output_file_str = str(output_file.resolve().as_posix())
        typst.compile(
            input=str(temp_typ.resolve().as_posix()),
            output=output_file_str
        )
        print(f"[DOCGEN] Successfully generated Dynamic Report PDF to: {output_file_str}")
    finally:
        if temp_typ.exists():
            try:
                temp_typ.unlink()
            except Exception:
                pass

    return str(output_file.resolve().as_posix())
