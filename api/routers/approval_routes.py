from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from core.schemas import PurchaseItemRequest, PurchaseRequisitionDoc
from core.security import TokenData, get_current_user

router = APIRouter(prefix="/api/approval", tags=["Human-in-the-Loop Approval"])


# --- Default PR Data Factory (Single Source of Truth) ---

DEFAULT_PR_ITEMS = [
    PurchaseItemRequest(
        item_id="ITM-001", name="Microcontroller STM32F401",
        reorder_qty=76, unit="pcs", vendor_id="VND-001",
        vendor_name="PT. Elektronika Jaya Prima",
        unit_price=65000.0, total_price=4940000.0,
        reason="Stok fisik 12 pcs di bawah safety threshold (50 pcs). Burn rate 8.5/hari."
    ),
    PurchaseItemRequest(
        item_id="ITM-002", name="ESP32-WROOM-32D Module",
        reorder_qty=52, unit="pcs", vendor_id="VND-002",
        vendor_name="CV. Komponen Nusantara",
        unit_price=39500.0, total_price=2054000.0,
        reason="Stok fisik 8 pcs di bawah safety threshold (40 pcs). Burn rate 6.0/hari."
    ),
    PurchaseItemRequest(
        item_id="ITM-003", name="Thermal Paste Arctic MX-4 4g",
        reorder_qty=33, unit="tube", vendor_id="VND-003",
        vendor_name="PT. Sumber Makmur Fastener",
        unit_price=48000.0, total_price=1584000.0,
        reason="Stok fisik 5 tube di bawah safety threshold (25 tube). Burn rate 3.2/hari."
    ),
    PurchaseItemRequest(
        item_id="ITM-004", name="Cardboard Box 30x20x15cm",
        reorder_qty=190, unit="pcs", vendor_id="VND-004",
        vendor_name="PT. Kemasan Indah Perkasa",
        unit_price=4200.0, total_price=798000.0,
        reason="Stok fisik 35 pcs di bawah safety threshold (150 pcs). Burn rate 25/hari."
    ),
    PurchaseItemRequest(
        item_id="ITM-005", name="Bubble Wrap Roll 50m x 50cm",
        reorder_qty=17, unit="roll", vendor_id="VND-004",
        vendor_name="PT. Kemasan Indah Perkasa",
        unit_price=72000.0, total_price=1224000.0,
        reason="Stok fisik 4 roll di bawah safety threshold (15 roll). Burn rate 2.0/hari."
    )
]


def _create_default_pr(pr_number: str = "PR-2026-0819-001", status: str = "PENDING") -> PurchaseRequisitionDoc:
    """Factory function to create a default PR document. Single source of truth."""
    return PurchaseRequisitionDoc(
        pr_number=pr_number,
        created_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
        items=DEFAULT_PR_ITEMS,
        total_budget=10600000.0,
        auditor_status="PASSED",
        auditor_notes="Compliance check: Total PR Rp 10.600.000 sesuai alokasi pengadaan inventaris Q3.",
        pdf_path=f"/storage/documents/{pr_number.replace('-', '_')}.pdf",
        status=status
    )


# In-memory PR Store
PR_STORE: dict[str, PurchaseRequisitionDoc] = {}


class ApprovalActionPayload(BaseModel):
    pr_number: str
    action: str = "APPROVE"  # APPROVE | REJECT
    manager_name: str | None = "Warehouse Manager"
    notes: str | None = None


class DispatchEmailPayload(BaseModel):
    pr_number: str
    recipient_email: str | None = None
    manager_name: str | None = "Manager Logistik"


# --- Helper: Synchronize Approved PR to purchase_orders Table ---

def sync_approved_pr_to_purchase_orders(conn, pr_number: str, pr: PurchaseRequisitionDoc | None = None) -> list[str]:
    """
    Ensures that for an APPROVED Purchase Requisition, official Purchase Orders (PO)
    are created and recorded in the purchase_orders table if not already present,
    and their official Typst PDFs are compiled.
    """
    import re
    from datetime import datetime, timedelta
    from pathlib import Path

    existing_tables = set(r[0] for r in conn.execute("SHOW TABLES;").fetchall())
    if "purchase_orders" not in existing_tables:
        return []

    po_cols = [c[0] for c in conn.execute("DESCRIBE purchase_orders;").fetchall()]
    if "pr_number" not in po_cols:
        try:
            conn.execute("ALTER TABLE purchase_orders ADD COLUMN pr_number VARCHAR;")
        except Exception as alter_err:
            print(f"[sync_approved_pr_to_purchase_orders] Column check note: {alter_err}")

    existing_pos = conn.execute("SELECT po_id FROM purchase_orders WHERE pr_number = ?;", [pr_number]).fetchall()
    created_po_ids = []

    if existing_pos:
        conn.execute("UPDATE purchase_orders SET status = 'ORDERED' WHERE pr_number = ?;", [pr_number])
        created_po_ids = [r[0] for r in existing_pos]
    else:
        # Determine items from pr object or from DuckDB orders table
        items_to_create = []
        if pr and getattr(pr, "items", None):
            for it in pr.items:
                items_to_create.append({
                    "item_id": it.item_id,
                    "vendor_id": getattr(it, "vendor_id", "SUP-001"),
                    "quantity": int(getattr(it, "reorder_qty", 1)),
                    "unit_price": int(getattr(it, "unit_price", 0)),
                    "total_price": int(getattr(it, "total_price", 0)),
                    "warehouse_id": getattr(it, "warehouse_id", None) or (it.get("warehouse_id") if isinstance(it, dict) else None),
                    "warehouse_name": getattr(it, "warehouse_name", None) or (it.get("warehouse_name") if isinstance(it, dict) else None)
                })
        else:
            ord_rows = conn.execute("""
                SELECT item_id, vendor_id, quantity, unit_price, total_price 
                FROM orders 
                WHERE pr_number = ?;
            """, [pr_number]).fetchall()
            for o_it, o_ven, o_qty, o_prc, o_tot in ord_rows:
                items_to_create.append({
                    "item_id": o_it,
                    "vendor_id": o_ven or "SUP-001",
                    "quantity": int(o_qty or 1),
                    "unit_price": int(o_prc or 0),
                    "total_price": int(o_tot or 0),
                    "warehouse_id": None,
                    "warehouse_name": None
                })

        # Also check purchase_requests if still empty
        if not items_to_create and "purchase_requests" in existing_tables:
            pr_req = conn.execute("SELECT items_json FROM purchase_requests WHERE pr_number = ?;", [pr_number]).fetchone()
            if pr_req and pr_req[0]:
                import json
                try:
                    parsed_items = json.loads(pr_req[0])
                    for pit in parsed_items:
                        items_to_create.append({
                            "item_id": pit.get("item_id"),
                            "vendor_id": pit.get("vendor_id", "SUP-001"),
                            "quantity": int(pit.get("quantity", 1)),
                            "unit_price": int(pit.get("unit_price", 0)),
                            "total_price": int(pit.get("total_price", 0)),
                            "warehouse_id": pit.get("warehouse_id"),
                            "warehouse_name": pit.get("warehouse_name")
                        })
                except Exception:
                    pass

        # Determine next sequential counter for po_id
        all_pos = conn.execute("SELECT po_id FROM purchase_orders;").fetchall()
        current_max = 0
        for (pid_val,) in all_pos:
            digits = re.findall(r'\d+', str(pid_val))
            if digits:
                val = int(digits[-1])
                if val > current_max:
                    current_max = val

        today_s = datetime.now().strftime("%Y-%m-%d")
        delivery_s = (datetime.now() + timedelta(days=10)).strftime("%Y-%m-%d")
        month_s = datetime.now().strftime("%Y/%m")

        # 1 Consolidated PO per PR document
        new_po_id = f"PO-2026-{(current_max + 1):03d}"
        new_po_num = f"PO/BLT/{month_s}/{(30 + current_max + 1):03d}"

        assigned_warehouses: dict[str, set[str]] = {}

        for idx, item in enumerate(items_to_create, 1):
            # Resolve valid supplier_id from inventory_items
            sup_id = item["vendor_id"]
            if not sup_id or not str(sup_id).startswith("SUP-"):
                sup_row = conn.execute("SELECT supplier_id FROM inventory_items WHERE item_id = ?;", [item["item_id"]]).fetchone()
                sup_id = sup_row[0] if sup_row and sup_row[0] else "SUP-001"

            target_wh = item.get("warehouse_id")
            if not target_wh:
                item_assigned = assigned_warehouses.get(item["item_id"], set())
                # Resolve warehouse_id from stock_balances that has critical/low stock
                wh_rows = conn.execute("""
                    SELECT warehouse_id FROM stock_balances 
                    WHERE item_id = ? AND (stock_status IN ('CRITICAL', 'LOW_STOCK') OR quantity_on_hand <= reorder_point)
                    ORDER BY quantity_on_hand ASC;
                """, [item["item_id"]]).fetchall()

                candidate_wh = None
                for (r_wh,) in wh_rows:
                    if r_wh not in item_assigned:
                        candidate_wh = r_wh
                        break

                if not candidate_wh:
                    all_wh_rows = conn.execute("SELECT warehouse_id FROM stock_balances WHERE item_id = ? ORDER BY quantity_on_hand ASC;", [item["item_id"]]).fetchall()
                    for (r_wh,) in all_wh_rows:
                        if r_wh not in item_assigned:
                            candidate_wh = r_wh
                            break
                    if not candidate_wh and all_wh_rows:
                        candidate_wh = all_wh_rows[0][0]

                target_wh = candidate_wh or "WH-BDG-01"

            assigned_warehouses.setdefault(item["item_id"], set()).add(target_wh)

            conn.execute("""
                INSERT INTO purchase_orders (
                    po_id, po_number, supplier_id, item_id, order_quantity, unit_price, total_amount, status, order_date, expected_delivery, actual_delivery, warehouse_id, pr_number
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'ORDERED', ?, ?, NULL, ?, ?);
            """, [
                new_po_id, new_po_num, sup_id, item["item_id"],
                item["quantity"], item["unit_price"], item["total_price"],
                today_s, delivery_s, target_wh, pr_number
            ])
        created_po_ids.append(new_po_id)

    # Pre-compile official Typst PO PDFs
    try:
        from docgen.compiler import generate_po_pdf
        for p_id in created_po_ids:
            generate_po_pdf(p_id)
    except Exception as po_err:
        pass

    # Synchronize to CSV file for persistence across server restarts
    try:
        inv_csv = Path("data/balitower/01_inventory/purchase_orders.csv")
        if inv_csv.parent.exists():
            df_pos = conn.execute("SELECT * FROM purchase_orders").df()
            df_pos.to_csv(inv_csv, index=False)
    except Exception:
        pass

    return created_po_ids


# --- Helper: Update DuckDB order status & optionally add stock ---

def _update_db_status(pr_number: str, action: str, pr: PurchaseRequisitionDoc | None = None) -> str:
    """Updates DuckDB orders table and POs atomically, ensuring serialized write and idempotency."""
    try:
        import uuid
        from database.db import execute_db_write
        is_approve = str(action).upper() in ["APPROVE", "APPROVED"]
        db_status = "APPROVED" if is_approve else "REJECTED"

        def _transaction_ops(conn):
            existing_tables = set(r[0] for r in conn.execute("SHOW TABLES;").fetchall())
            if "orders" not in existing_tables:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS orders (
                        order_id VARCHAR PRIMARY KEY,
                        pr_number VARCHAR,
                        item_id VARCHAR,
                        vendor_id VARCHAR,
                        quantity INTEGER,
                        unit_price DOUBLE,
                        total_price DOUBLE,
                        status VARCHAR,
                        tenant_id VARCHAR
                    );
                """)

            # Check if order already exists and its current status
            existing_order = conn.execute("SELECT status FROM orders WHERE pr_number = ? LIMIT 1;", [pr_number]).fetchone()

            if existing_order:
                conn.execute("UPDATE orders SET status = ? WHERE pr_number = ?;", [db_status, pr_number])
            elif pr and pr.items:
                insert_orders_params = [
                    (f"ORD-{uuid.uuid4().hex[:8].upper()}", pr_number, it.item_id, it.vendor_id, it.reorder_qty, it.unit_price, it.total_price, db_status, pr.tenant_id or "ALL")
                    for it in pr.items
                ]
                conn.executemany("""
                    INSERT INTO orders (order_id, pr_number, item_id, vendor_id, quantity, unit_price, total_price, status, tenant_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
                """, insert_orders_params)

            # Synchronize Purchase Orders (PO) in purchase_orders table: status becomes ORDERED
            if "purchase_orders" in existing_tables:
                if is_approve:
                    sync_approved_pr_to_purchase_orders(conn, pr_number, pr)
                else:
                    po_cols = [c[0] for c in conn.execute("DESCRIBE purchase_orders;").fetchall()]
                    if "pr_number" in po_cols:
                        conn.execute("UPDATE purchase_orders SET status = 'REJECTED' WHERE pr_number = ?;", [pr_number])

            if "purchase_requests" in existing_tables:
                conn.execute("UPDATE purchase_requests SET status = ? WHERE pr_number = ?;", [db_status, pr_number])

        execute_db_write(_transaction_ops)

        if is_approve:
            return "<strong>Purchase Order Resmi Berhasil Diterbitkan (Status: ORDERED). Saldo fisik gudang akan bertambah otomatis saat barang tiba (Goods Receipt / DELIVERED).</strong>"
        return "<strong>Stok Fisik Inventaris Tetap (Tidak Ada Penambahan).</strong>"
    except Exception as e:
        return f"Catatan database: {e!s}"


def _regenerate_pdf(pr: PurchaseRequisitionDoc):
    """Regenerates Typst PDF with the current PR status and removes stale pending files."""
    try:
        from core.config import settings
        from docgen.compiler import generate_pr_pdf
        clean_pr_num = pr.pr_number.replace("/", "_").replace("\\", "_")
        clean_filename = f"{pr.pr_number.replace('-', '_')}.pdf"
        
        # 1. Generate to structured target dir (e.g. storage/approved/ or storage/rejected/)
        payload = pr.model_dump()
        target_file = generate_pr_pdf(payload)
        pr.pdf_path = target_file
        
        # 2. Also generate into storage/documents/ and ensure both naming variants exist in target dir
        settings.DOCUMENTS_DIR.mkdir(parents=True, exist_ok=True)
        generate_pr_pdf(payload, output_path=settings.DOCUMENTS_DIR / clean_filename)
        generate_pr_pdf(payload, output_path=settings.DOCUMENTS_DIR / f"{clean_pr_num}.pdf")
        
        status_upper = pr.status.upper()
        if "APPROV" in status_upper:
            settings.APPROVED_DIR.mkdir(parents=True, exist_ok=True)
            generate_pr_pdf(payload, output_path=settings.APPROVED_DIR / f"{clean_pr_num}.pdf")
            generate_pr_pdf(payload, output_path=settings.APPROVED_DIR / clean_filename)
        elif "REJECT" in status_upper:
            settings.REJECTED_DIR.mkdir(parents=True, exist_ok=True)
            generate_pr_pdf(payload, output_path=settings.REJECTED_DIR / f"{clean_pr_num}.pdf")
            generate_pr_pdf(payload, output_path=settings.REJECTED_DIR / clean_filename)
        
        # 3. Clean up old pending files so it won't be served by cache/download
        for pfile in [settings.PENDING_DIR / f"{clean_pr_num}.pdf", settings.PENDING_DIR / clean_filename]:
            if pfile.exists():
                try:
                    pfile.unlink()
                except Exception as e:
                    print(f"[REGENERATE PDF WARN] Failed to delete stale pending PDF {pfile}: {e}")
    except Exception as e:
        print(f"[REGENERATE PDF ERROR] {e}")


def persist_pr_to_db(pr: PurchaseRequisitionDoc):
    """Persists a PurchaseRequisitionDoc into DuckDB purchase_requests table with write serialization."""
    try:
        import json
        from database.db import execute_db_write

        def _write_pr(conn):
            existing_tables = set(r[0] for r in conn.execute("SHOW TABLES;").fetchall())
            if "purchase_requests" in existing_tables:
                items_data = [item.model_dump() if hasattr(item, "model_dump") else item.dict() for item in pr.items]
                conn.execute("""
                    INSERT OR REPLACE INTO purchase_requests (pr_number, created_at, status, total_amount, items_json, tenant_id)
                    VALUES (?, ?, ?, ?, ?, ?);
                """, [
                    pr.pr_number,
                    datetime.now(),
                    pr.status,
                    int(pr.total_budget),
                    json.dumps(items_data),
                    getattr(pr, "tenant_id", "ALL")
                ])

        execute_db_write(_write_pr)
    except Exception as e:
        print(f"[persist_pr_to_db] Error saving PR {pr.pr_number} to DB: {e}")


def _ensure_pr_in_store(pr_number: str) -> PurchaseRequisitionDoc | None:
    """Gets a PR from store, reconstructing from DuckDB orders or purchase_requests if missing."""
    pr = PR_STORE.get(pr_number)
    if pr:
        return pr

    # Try reconstructing from DuckDB orders or purchase_requests
    try:
        from database.db import get_db_connection
        conn = get_db_connection(read_only=True)
        existing_tables = set(r[0] for r in conn.execute("SHOW TABLES;").fetchall())

        # 1. Try orders table first
        order_rows = []
        if "orders" in existing_tables:
            if "vendors" in existing_tables:
                vendor_join = "LEFT JOIN vendors v ON o.vendor_id = v.vendor_id AND o.item_id = v.item_id"
                vendor_col = "v.name as vendor_name"
            elif "suppliers" in existing_tables:
                vendor_join = "LEFT JOIN suppliers v ON o.vendor_id = v.supplier_id"
                vendor_col = "v.supplier_name as vendor_name"
            else:
                vendor_join = ""
                vendor_col = "'Vendor Terdaftar' as vendor_name"

            item_join = "LEFT JOIN items i ON o.item_id = i.item_id"
            if "inventory_items" in existing_tables:
                item_join += " LEFT JOIN inventory_items bt ON o.item_id = bt.item_id"
                item_name_col = "COALESCE(i.name, bt.item_name, 'Material ' || o.item_id) as item_name"
                item_unit_col = "COALESCE(i.unit, bt.unit, 'pcs') as unit"
            else:
                item_name_col = "COALESCE(i.name, 'Material ' || o.item_id) as item_name"
                item_unit_col = "COALESCE(i.unit, 'pcs') as unit"

            order_rows = conn.execute(f"""
                SELECT o.pr_number, o.item_id, o.vendor_id, o.quantity, o.unit_price, o.total_price, o.status, o.tenant_id,
                       {item_name_col}, {item_unit_col}, {vendor_col}
                FROM orders o
                {item_join}
                {vendor_join}
                WHERE o.pr_number = ?;
            """, [pr_number]).fetchall()

        if order_rows:
            conn.close()
            items = []
            total_budget = 0.0
            db_status = order_rows[0][6] or "PENDING"
            tenant_id = order_rows[0][7] or "ALL"

            for row in order_rows:
                qty = row[3]
                uprice = row[4]
                tprice = row[5] or (qty * uprice)
                total_budget += tprice
                items.append(PurchaseItemRequest(
                    item_id=row[1],
                    name=row[8] or f"Item {row[1]}",
                    reorder_qty=qty,
                    unit=row[9] or "pcs",
                    vendor_id=row[2] or "VND-001",
                    vendor_name=row[10] or "Vendor Terdaftar",
                    unit_price=uprice,
                    total_price=tprice,
                    reason="Reconstructed from DuckDB orders"
                ))

            clean_filename = f"{pr_number.replace('-', '_')}.pdf"
            pr_doc = PurchaseRequisitionDoc(
                pr_number=pr_number,
                created_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
                items=items,
                total_budget=total_budget,
                auditor_status="PASSED",
                auditor_notes="Compliance check: Sesuai alokasi pengadaan inventaris.",
                pdf_path=f"/storage/documents/{clean_filename}",
                status=db_status,
                tenant_id=tenant_id
            )
            PR_STORE[pr_number] = pr_doc
            return pr_doc

        # 2. Try purchase_requests table if not found in orders
        if "purchase_requests" in existing_tables:
            pr_row = conn.execute(
                "SELECT pr_number, created_at, status, total_amount, items_json, tenant_id FROM purchase_requests WHERE pr_number = ?;",
                [pr_number]
            ).fetchone()
            conn.close()
            if pr_row:
                import json
                items = []
                try:
                    raw_items = json.loads(pr_row[4]) if pr_row[4] else []
                    for it in raw_items:
                        items.append(PurchaseItemRequest(
                            item_id=it.get("item_id", "ITM-000"),
                            name=it.get("item_name") or it.get("name", "Material Item"),
                            reorder_qty=int(it.get("quantity") or it.get("reorder_qty", 1)),
                            unit=it.get("unit", "pcs"),
                            warehouse_id=it.get("warehouse_id"),
                            warehouse_name=it.get("warehouse_name"),
                            vendor_id=it.get("vendor_id", "VND-001"),
                            vendor_name=it.get("vendor_name", "Vendor Terdaftar"),
                            unit_price=float(it.get("unit_price", 0.0)),
                            total_price=float(it.get("total_price", 0.0)),
                            reason=it.get("reason", "Generated by AI Agent")
                        ))
                except Exception as parse_err:
                    print(f"[_ensure_pr_in_store] Error parsing items_json: {parse_err}")

                clean_filename = f"{pr_number.replace('-', '_')}.pdf"
                pr_doc = PurchaseRequisitionDoc(
                    pr_number=pr_number,
                    created_at=str(pr_row[1]) if pr_row[1] else datetime.now().strftime("%Y-%m-%d %H:%M"),
                    items=items,
                    total_budget=float(pr_row[3] or 0.0),
                    auditor_status="PASSED",
                    auditor_notes="Compliance check: Sesuai alokasi pengadaan inventaris.",
                    pdf_path=f"/storage/documents/{clean_filename}",
                    status=pr_row[2] or "PENDING",
                    tenant_id=pr_row[5] or "ALL"
                )
                PR_STORE[pr_number] = pr_doc
                return pr_doc
        else:
            conn.close()
    except Exception as e:
        print(f"[_ensure_pr_in_store] Error loading from DB: {e}")

    return None


# --- API Endpoints ---

@router.get("/list", response_model=list[PurchaseRequisitionDoc])
async def get_all_requisitions(response: Response, current_user: TokenData = Depends(get_current_user)):
    """Returns list of active purchase requisitions filtered by tenant."""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    # Sync PRs from DuckDB orders and purchase_requests
    try:
        from database.db import get_db_connection
        conn = get_db_connection(read_only=True)
        existing_tables = set(r[0] for r in conn.execute("SHOW TABLES;").fetchall())
        pr_rows = []
        if "orders" in existing_tables:
            pr_rows.extend(conn.execute("SELECT DISTINCT pr_number, status FROM orders;").fetchall())
        if "purchase_requests" in existing_tables:
            pr_rows.extend(conn.execute("SELECT DISTINCT pr_number, status FROM purchase_requests;").fetchall())
        conn.close()
        for pr_num, db_status in pr_rows:
            if pr_num:
                pr = _ensure_pr_in_store(pr_num)
                if pr and db_status and pr.status != db_status:
                    pr.status = db_status
    except Exception as e:
        print(f"[get_all_requisitions] Error syncing from DB: {e}")

    if current_user.role == "ADMIN":
        return list(PR_STORE.values())

    return [pr for pr in PR_STORE.values() if pr.tenant_id == current_user.tenant_id or pr.tenant_id == "ALL"]


@router.get("/quick-action", response_class=HTMLResponse)
async def quick_approval_action(
    pr_number: str,
    action: str = "APPROVE",
    manager_name: str = "Manager",
    notes: str | None = None
):
    """
    Direct one-click approval/rejection endpoint used by Email interactive action buttons.
    Returns a responsive HTML confirmation landing page.
    """
    clean_action = action.strip().upper()
    pr = _ensure_pr_in_store(pr_number)

    items_updated_summary = []

    if clean_action == "APPROVE":
        if pr:
            pr.status = "APPROVED"
            items_updated_summary = [
                f"<li><strong>{item.name}</strong>: {item.reorder_qty} {item.unit} (PO Diterbitkan ke Vendor &mdash; Menunggu Kedatangan Fisik Gudang)</li>"
                for item in pr.items
            ]
        stock_delta_info = _update_db_status(pr_number, "APPROVED", pr)
        status_badge = '<span style="background: #DCFCE7; color: #166534; border: 1px solid #86EFAC; padding: 6px 14px; border-radius: 6px; font-weight: 700; font-size: 11.5px; letter-spacing: 0.05em; text-transform: uppercase;">STATUS: DISETUJUI (APPROVED)</span>'
        title_color = "#0F172A"
        heading_text = "Otorisasi Pengadaan Berhasil Dicatatkan"
        desc_text = f"Dokumen Purchase Requisition <strong>{pr_number}</strong> telah resmi disetujui. Sistem telah memproses pengesahan dan Purchase Order (PO) resmi kini siap diteruskan ke rekanan vendor terpilih untuk pengiriman material."
    else:
        if pr:
            pr.status = "REJECTED"
        stock_delta_info = _update_db_status(pr_number, "REJECTED", pr)
        status_badge = '<span style="background: #FEE2E2; color: #991B1B; border: 1px solid #FCA5A5; padding: 6px 14px; border-radius: 6px; font-weight: 700; font-size: 11.5px; letter-spacing: 0.05em; text-transform: uppercase;">STATUS: DITOLAK (REJECTED)</span>'
        title_color = "#0F172A"
        heading_text = "Pengadaan Barang Ditolak"
        desc_text = f"Dokumen Purchase Requisition <strong>{pr_number}</strong> telah ditolak. Alokasi anggaran dibatalkan dan kuantitas stok gudang tetap dipertahankan."

    if pr:
        _regenerate_pdf(pr)

    pdf_download_url = f"/api/documents/pr/{pr_number}/download"
    items_html = "".join(items_updated_summary) if items_updated_summary else "<li>Daftar barang tercatat dalam basis data logistik.</li>"

    html_content = f"""<!DOCTYPE html>
<html lang="id">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Konfirmasi Otorisasi | {pr_number}</title>
    <style>
        * {{ box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
            background-color: #F1F5F9;
            color: #0F172A;
            margin: 0;
            padding: 32px 16px;
            display: flex;
            align-items: center;
            justify-content: center;
            min-height: 100vh;
            -webkit-font-smoothing: antialiased;
        }}
        .receipt-card {{
            background: #FFFFFF;
            border: 1px solid #CBD5E1;
            border-radius: 8px;
            max-width: 620px;
            width: 100%;
            overflow: hidden;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05), 0 2px 4px -2px rgba(0, 0, 0, 0.05);
        }}
        .receipt-header {{
            background: #0F172A;
            color: #FFFFFF;
            padding: 22px 28px;
            border-bottom: 3px solid #2563EB;
        }}
        .corp-name {{
            font-size: 14px;
            font-weight: 700;
            letter-spacing: 0.08em;
            text-transform: uppercase;
            color: #F8FAFC;
            margin: 0;
        }}
        .corp-dept {{
            font-size: 12px;
            color: #94A3B8;
            margin: 4px 0 0 0;
        }}
        .receipt-body {{
            padding: 32px 28px;
        }}
        .status-container {{
            margin-bottom: 20px;
        }}
        h1 {{
            font-size: 20px;
            font-weight: 700;
            color: {title_color};
            margin: 0 0 10px 0;
            line-height: 1.3;
        }}
        p.lead-desc {{
            color: #475569;
            font-size: 13.5px;
            line-height: 1.6;
            margin: 0 0 20px 0;
        }}
        .meta-table {{
            width: 100%;
            border-collapse: collapse;
            margin: 18px 0;
            font-size: 13px;
        }}
        .meta-table td {{
            padding: 10px 12px;
            border-bottom: 1px solid #E2E8F0;
        }}
        .meta-label {{
            color: #64748B;
            width: 40%;
            font-weight: 500;
        }}
        .meta-val {{
            color: #0F172A;
            font-weight: 600;
            text-align: right;
            font-family: 'Consolas', monospace;
        }}
        .items-box {{
            background: #F8FAFC;
            border: 1px solid #E2E8F0;
            border-radius: 6px;
            padding: 16px;
            margin: 20px 0;
            font-size: 13px;
        }}
        .items-box-title {{
            font-size: 11px;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            color: #475569;
            margin-bottom: 10px;
        }}
        .items-box ul {{
            margin: 0;
            padding-left: 20px;
            line-height: 1.6;
            color: #334155;
        }}
        .btn-row {{
            display: flex;
            gap: 12px;
            margin-top: 28px;
            flex-wrap: wrap;
        }}
        .btn {{
            flex: 1;
            min-width: 140px;
            padding: 12px 18px;
            border-radius: 6px;
            font-size: 13px;
            font-weight: 600;
            text-decoration: none;
            text-align: center;
            transition: background 0.15s ease;
        }}
        .btn-primary {{
            background: #0F172A;
            color: #FFFFFF !important;
            border: 1px solid #0F172A;
        }}
        .btn-primary:hover {{
            background: #1E293B;
        }}
        .btn-secondary {{
            background: #FFFFFF;
            color: #334155 !important;
            border: 1px solid #CBD5E1;
        }}
        .btn-secondary:hover {{
            background: #F8FAFC;
        }}
        .receipt-footer {{
            background: #F8FAFC;
            border-top: 1px solid #E2E8F0;
            padding: 16px 28px;
            font-size: 11.5px;
            color: #64748B;
            text-align: center;
        }}
    </style>
</head>
<body>
    <div class="receipt-card">
        <div class="receipt-header">
            <h2 class="corp-name">PT Bali Towerindo Sentra Tbk</h2>
            <p class="corp-dept">Enterprise Operations Command Center &mdash; Procurement System</p>
        </div>
        <div class="receipt-body">
            <div class="status-container">
                {status_badge}
            </div>
            <h1>{heading_text}</h1>
            <p class="lead-desc">{desc_text}</p>

            <table class="meta-table">
                <tr>
                    <td class="meta-label">Nomor Purchase Requisition</td>
                    <td class="meta-val">{pr_number}</td>
                </tr>
                <tr>
                    <td class="meta-label">Otorisator / Penyetuju</td>
                    <td class="meta-val">{manager_name}</td>
                </tr>
                <tr>
                    <td class="meta-label">Waktu Pengesahan</td>
                    <td class="meta-val">{datetime.now().strftime('%d %b %Y, %H:%M WIB')}</td>
                </tr>
                <tr>
                    <td class="meta-label">Tindak Lanjut Sistem</td>
                    <td class="meta-val" style="color: #15803D;">{'Penerbitan PO Resmi' if clean_action == 'APPROVE' else 'Pengadaan Dibatalkan'}</td>
                </tr>
            </table>

            {'<div class="items-box"><div class="items-box-title">Alokasi Material yang Divalidasi:</div><ul>' + items_html + '</ul></div>' if clean_action == 'APPROVE' else ''}

            <div class="btn-row">
                <a href="{pdf_download_url}" class="btn btn-secondary" target="_blank">Unduh Dokumen PDF Resmi</a>
                <a href="/" class="btn btn-primary">Buka Web Dashboard</a>
            </div>
        </div>
        <div class="receipt-footer">
            Dokumen resmi ini disahkan secara elektronik melalui sistem terintegrasi DuckDB Enterprise.
        </div>
    </div>
</body>
</html>"""
    return HTMLResponse(content=html_content)


@router.get("/leave-quick-action", response_class=HTMLResponse)
async def quick_leave_approval_action(
    leave_id: str,
    action: str = "APPROVE",
    manager_name: str = "Eko Prasetyo (HR & GA Lead)",
    request: Request = None
):
    """
    Direct one-click approval/rejection endpoint used by HR Leave Email interactive action buttons.
    Updates DuckDB leave_requests and employees tables, regenerates the official Typst PDF,
    and returns a responsive corporate HTML confirmation landing page.
    """
    from database.db import get_db_connection
    from core.config import settings, get_base_url

    base_url = get_base_url(request)

    clean_action = action.strip().upper()
    is_approve = clean_action in ["APPROVE", "APPROVED"]
    db_status = "APPROVED" if is_approve else "REJECTED"

    conn = get_db_connection(read_only=False)
    try:
        row = conn.execute("""
            SELECT 
                l.leave_id,
                l.employee_id,
                e.full_name AS applicant_name,
                e.job_title,
                e.department,
                e.leave_balance,
                l.leave_type,
                l.start_date,
                l.end_date,
                l.days_requested,
                l.reason,
                COALESCE(sub.full_name, '-') AS substitute_name,
                l.approval_status
            FROM leave_requests l
            JOIN employees e ON l.employee_id = e.employee_id
            LEFT JOIN employees sub ON l.substitute_employee_id = sub.employee_id
            WHERE l.leave_id = ?;
        """, [leave_id]).fetchone()

        if not row:
            return HTMLResponse(
                content=f"""<!DOCTYPE html>
<html>
<head><title>Dokumen Tidak Ditemukan | {leave_id}</title></head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #F1F5F9; display: flex; align-items: center; justify-content: center; min-height: 100vh; margin: 0;">
    <div style="background: #FFFFFF; border: 1px solid #CBD5E1; border-radius: 8px; padding: 32px; max-width: 480px; text-align: center; box-shadow: 0 2px 4px rgba(0,0,0,0.06);">
        <h2 style="color: #0F172A; margin-top: 0;">Dokumen Tidak Ditemukan</h2>
        <p style="color: #475569; font-size: 14px;">Pengajuan cuti nomor <strong>{leave_id}</strong> tidak ditemukan di basis data operasional.</p>
        <a href="{base_url}/" style="display: inline-block; margin-top: 16px; background: #0F172A; color: #FFFFFF; padding: 10px 20px; border-radius: 6px; text-decoration: none; font-size: 13px;">Buka Dashboard</a>
    </div>
</body>
</html>""",
                status_code=404
            )

        cols = [
            "leave_id", "employee_id", "applicant_name", "job_title", "department",
            "leave_balance", "leave_type", "start_date", "end_date", "days_requested",
            "reason", "substitute_name", "current_status"
        ]
        leave_info = dict(zip(cols, row))

        # Check balance and update approval status in leave_requests
        prev_status = leave_info.get("current_status")
        updated_balance = leave_info.get("leave_balance", 0)
        days = max(1, int(leave_info.get("days_requested", 1)))
        rejection_reason = ""

        if is_approve and prev_status != "APPROVED":
            cur_bal = int(leave_info.get("leave_balance") or 0)
            if cur_bal < days:
                is_approve = False
                db_status = "REJECTED"
                rejection_reason = f"Saldo cuti ({cur_bal} hari) tidak mencukupi untuk permohonan {days} hari."
                conn.execute(
                    "UPDATE leave_requests SET approval_status = 'REJECTED', approved_by = 'EMP-BLT-005' WHERE leave_id = ?;",
                    [leave_id]
                )
            else:
                conn.execute(
                    "UPDATE leave_requests SET approval_status = 'APPROVED', approved_by = 'EMP-BLT-005' WHERE leave_id = ?;",
                    [leave_id]
                )
                conn.execute(
                    "UPDATE employees SET leave_balance = ? WHERE employee_id = ?;",
                    [cur_bal - days, leave_info["employee_id"]]
                )
                fresh_bal = conn.execute("SELECT leave_balance FROM employees WHERE employee_id = ?;", [leave_info["employee_id"]]).fetchone()
                if fresh_bal:
                    updated_balance = fresh_bal[0]
                    leave_info["leave_balance"] = updated_balance
        elif not is_approve:
            conn.execute(
                "UPDATE leave_requests SET approval_status = ?, approved_by = 'EMP-BLT-005' WHERE leave_id = ?;",
                [db_status, leave_id]
            )

        conn.commit()
    finally:
        conn.close()

    # Regenerate Typst PDF to reflect official approved status
    try:
        from docgen.compiler import generate_leave_pdf
        generate_leave_pdf(leave_id)
    except Exception as pdf_err:
        print(f"[WARN] Failed to re-compile leave PDF: {pdf_err}")

    # Render confirmation landing page
    if is_approve:
        status_badge = '<span style="background: #DCFCE7; color: #166534; border: 1px solid #86EFAC; padding: 6px 14px; border-radius: 6px; font-weight: 700; font-size: 11.5px; letter-spacing: 0.05em; text-transform: uppercase;">STATUS: DISETUJUI (APPROVED)</span>'
        heading_text = "Otorisasi Cuti Karyawan Berhasil Disahkan"
        desc_text = f"Permohonan cuti untuk <strong>{leave_info['applicant_name']}</strong> ({leave_id}) telah resmi disetujui. Status pada sistem database HR dan berkas resmi PDF telah diperbarui secara otomatis."
    else:
        status_badge = '<span style="background: #FEE2E2; color: #991B1B; border: 1px solid #FCA5A5; padding: 6px 14px; border-radius: 6px; font-weight: 700; font-size: 11.5px; letter-spacing: 0.05em; text-transform: uppercase;">STATUS: DITOLAK (REJECTED)</span>'
        heading_text = "Pengajuan Cuti Karyawan Ditolak"
        if rejection_reason:
            desc_text = f"Permohonan cuti untuk <strong>{leave_info['applicant_name']}</strong> ({leave_id}) ditolak: {rejection_reason}"
        else:
            desc_text = f"Permohonan cuti untuk <strong>{leave_info['applicant_name']}</strong> ({leave_id}) telah ditolak. Kuota hak cuti tahunan karyawan tetap utuh."

    type_map = {
        "ANNUAL_LEAVE": "Cuti Tahunan",
        "SICK_LEAVE": "Cuti Sakit",
        "SPECIAL_LEAVE": "Cuti Khusus / Alasan Penting",
        "EMERGENCY_LEAVE": "Cuti Alasan Mendesak",
        "MATERNITY_LEAVE": "Cuti Melahirkan"
    }
    raw_type = str(leave_info.get("leave_type", "ANNUAL_LEAVE")).upper()
    type_label = type_map.get(raw_type, raw_type)
    pdf_download_url = f"/api/documents/leave/{leave_id}/download?inline=true"

    html_content = f"""<!DOCTYPE html>
<html lang="id">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Konfirmasi Otorisasi Cuti | {leave_id}</title>
    <style>
        * {{ box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
            background-color: #F1F5F9;
            color: #0F172A;
            margin: 0;
            padding: 32px 16px;
            display: flex;
            align-items: center;
            justify-content: center;
            min-height: 100vh;
            -webkit-font-smoothing: antialiased;
        }}
        .receipt-card {{
            background: #FFFFFF;
            border: 1px solid #CBD5E1;
            border-radius: 8px;
            max-width: 620px;
            width: 100%;
            overflow: hidden;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05), 0 2px 4px -2px rgba(0, 0, 0, 0.05);
        }}
        .receipt-header {{
            background: #0F172A;
            color: #FFFFFF;
            padding: 22px 28px;
            border-bottom: 3px solid #2563EB;
        }}
        .corp-name {{
            font-size: 14px;
            font-weight: 700;
            letter-spacing: 0.08em;
            text-transform: uppercase;
            color: #F8FAFC;
            margin: 0;
        }}
        .corp-dept {{
            font-size: 12px;
            color: #94A3B8;
            margin: 4px 0 0 0;
        }}
        .receipt-body {{
            padding: 32px 28px;
        }}
        .status-container {{
            margin-bottom: 20px;
        }}
        h1 {{
            font-size: 20px;
            font-weight: 700;
            color: #0F172A;
            margin: 0 0 10px 0;
            line-height: 1.3;
        }}
        p.lead-desc {{
            color: #475569;
            font-size: 13.5px;
            line-height: 1.6;
            margin: 0 0 20px 0;
        }}
        .meta-table {{
            width: 100%;
            border-collapse: collapse;
            margin: 18px 0;
            font-size: 13px;
        }}
        .meta-table td {{
            padding: 10px 12px;
            border-bottom: 1px solid #E2E8F0;
        }}
        .meta-label {{
            color: #64748B;
            width: 40%;
            font-weight: 500;
        }}
        .meta-val {{
            color: #0F172A;
            font-weight: 600;
            text-align: right;
        }}
        .btn-row {{
            display: flex;
            gap: 12px;
            margin-top: 28px;
            flex-wrap: wrap;
        }}
        .btn {{
            flex: 1;
            min-width: 140px;
            padding: 12px 18px;
            border-radius: 6px;
            font-size: 13px;
            font-weight: 600;
            text-decoration: none;
            text-align: center;
            transition: background 0.15s ease;
        }}
        .btn-primary {{
            background: #0F172A;
            color: #FFFFFF !important;
            border: 1px solid #0F172A;
        }}
        .btn-primary:hover {{
            background: #1E293B;
        }}
        .btn-secondary {{
            background: #FFFFFF;
            color: #334155 !important;
            border: 1px solid #CBD5E1;
        }}
        .btn-secondary:hover {{
            background: #F8FAFC;
        }}
        .receipt-footer {{
            background: #F8FAFC;
            border-top: 1px solid #E2E8F0;
            padding: 16px 28px;
            font-size: 11.5px;
            color: #94A3B8;
            text-align: center;
        }}
    </style>
</head>
<body>
    <div class="receipt-card">
        <div class="receipt-header">
            <h2 class="corp-name">PT Bali Towerindo Sentra Tbk</h2>
            <p class="corp-dept">Divisi Human Resources & Field Operations</p>
        </div>
        <div class="receipt-body">
            <div class="status-container">
                {status_badge}
            </div>
            <h1>{heading_text}</h1>
            <p class="lead-desc">{desc_text}</p>

            <table class="meta-table">
                <tr>
                    <td class="meta-label">Nomor Dokumen Cuti</td>
                    <td class="meta-val" style="font-family: 'Consolas', monospace; color: #1D4ED8;">{leave_id}</td>
                </tr>
                <tr>
                    <td class="meta-label">Karyawan Pemohon</td>
                    <td class="meta-val">{leave_info['applicant_name']} ({leave_info['employee_id']})</td>
                </tr>
                <tr>
                    <td class="meta-label">Posisi & Departemen</td>
                    <td class="meta-val">{leave_info['job_title']} ({leave_info['department']})</td>
                </tr>
                <tr>
                    <td class="meta-label">Jenis Permohonan</td>
                    <td class="meta-val">{type_label}</td>
                </tr>
                <tr>
                    <td class="meta-label">Durasi Cuti</td>
                    <td class="meta-val">{leave_info['days_requested']} Hari Kerja ({leave_info['start_date']} s/d {leave_info['end_date']})</td>
                </tr>
                <tr>
                    <td class="meta-label">Personil Pengganti</td>
                    <td class="meta-val">{leave_info['substitute_name']}</td>
                </tr>
                <tr>
                    <td class="meta-label">Sisa Kuota Cuti Terbaru</td>
                    <td class="meta-val">{leave_info['leave_balance']} Hari</td>
                </tr>
                <tr>
                    <td class="meta-label">Diverifikasi Oleh</td>
                    <td class="meta-val">{manager_name}</td>
                </tr>
            </table>

            <div class="btn-row">
                <a href="{pdf_download_url}" class="btn btn-secondary" target="_blank">Lihat Dokumen PDF Resmi</a>
                <a href="{base_url}/" class="btn btn-primary">Buka Dashboard Web</a>
            </div>
        </div>
        <div class="receipt-footer">
            PT Bali Towerindo Sentra Tbk | Wisma Kodel Lantai 6, Jl. H.R. Rasuna Said Kav. B-4, Jakarta Selatan 12920
        </div>
    </div>
</body>
</html>"""

    return HTMLResponse(content=html_content, status_code=200)


@router.get("/client-onboarding-action", response_class=HTMLResponse)
async def quick_client_onboarding_action(
    onboarding_id: str,
    action: str = "APPROVE",
    manager_name: str = "Finance & Commercial Lead",
    request: Request = None
):
    """
    Direct one-click approval/rejection endpoint for New Telecom Client Onboarding & MLA Lease Contract.
    When APPROVED:
      1. Updates pending_client_onboardings status to 'APPROVED'
      2. Inserts new client into telecom_clients
      3. Inserts new contract into mla_contracts
      4. Generates initial invoice in revenue_invoices
    Returns a responsive corporate HTML confirmation landing page.
    """
    from database.db import get_db_connection
    from core.config import settings, get_base_url

    base_url = get_base_url(request)

    clean_action = action.strip().upper()
    is_approve = clean_action in ["APPROVE", "APPROVED"]
    db_status = "APPROVED" if is_approve else "REJECTED"

    conn = get_db_connection(read_only=False)
    try:
        # Ensure pending table exists
        conn.execute("""
            CREATE TABLE IF NOT EXISTS pending_client_onboardings (
                onboarding_id VARCHAR PRIMARY KEY,
                client_id VARCHAR,
                client_name VARCHAR,
                client_type VARCHAR,
                npwp VARCHAR,
                billing_email VARCHAR,
                payment_terms VARCHAR,
                contract_id VARCHAR,
                site_id VARCHAR,
                monthly_rate BIGINT,
                billing_frequency VARCHAR,
                start_date VARCHAR,
                end_date VARCHAR,
                first_invoice_amount BIGINT,
                approval_status VARCHAR DEFAULT 'PENDING_APPROVAL',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                approved_at TIMESTAMP,
                approved_by VARCHAR
            );
        """)

        row = conn.execute("""
            SELECT 
                onboarding_id, client_id, client_name, client_type, npwp, billing_email,
                payment_terms, contract_id, site_id, monthly_rate, billing_frequency,
                start_date, end_date, first_invoice_amount, approval_status
            FROM pending_client_onboardings
            WHERE onboarding_id = ?;
        """, [onboarding_id]).fetchone()

        if not row:
            return HTMLResponse(
                content=f"""<!DOCTYPE html>
<html>
<head><title>Dokumen Onboarding Tidak Ditemukan | {onboarding_id}</title></head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #F1F5F9; display: flex; align-items: center; justify-content: center; min-height: 100vh; margin: 0;">
    <div style="background: #FFFFFF; border: 1px solid #CBD5E1; border-radius: 8px; padding: 32px; max-width: 480px; text-align: center; box-shadow: 0 2px 4px rgba(0,0,0,0.06);">
        <h2 style="color: #0F172A; margin-top: 0;">Dokumen Tidak Ditemukan</h2>
        <p style="color: #475569; font-size: 14px;">Berkas onboarding nomor <strong>{onboarding_id}</strong> tidak ditemukan di basis data Finance.</p>
        <a href="{base_url}/" style="display: inline-block; margin-top: 16px; background: #0F172A; color: #FFFFFF; padding: 10px 20px; border-radius: 6px; text-decoration: none; font-size: 13px;">Buka Dashboard</a>
    </div>
</body>
</html>""",
                status_code=404
            )

        cols = [
            "onboarding_id", "client_id", "client_name", "client_type", "npwp", "billing_email",
            "payment_terms", "contract_id", "site_id", "monthly_rate", "billing_frequency",
            "start_date", "end_date", "first_invoice_amount", "current_status"
        ]
        ob_info = dict(zip(cols, row))
        prev_status = ob_info.get("current_status")

        # Update approval status in pending_client_onboardings
        conn.execute("""
            UPDATE pending_client_onboardings
            SET approval_status = ?, approved_at = CURRENT_TIMESTAMP, approved_by = ?
            WHERE onboarding_id = ?;
        """, [db_status, manager_name, onboarding_id])

        inv_id = None
        inv_number = None

        if is_approve and prev_status != "APPROVED":
            # 1. Update/Insert telecom_clients
            existing_c = conn.execute("SELECT client_id FROM telecom_clients WHERE client_id = ?", [ob_info["client_id"]]).fetchone()
            if not existing_c:
                conn.execute("""
                    INSERT INTO telecom_clients (client_id, client_name, client_type, npwp, billing_email, payment_terms)
                    VALUES (?, ?, ?, ?, ?, ?);
                """, [
                    ob_info["client_id"], ob_info["client_name"], ob_info["client_type"],
                    ob_info["npwp"], ob_info["billing_email"], ob_info["payment_terms"]
                ])

            # 2. Update/Insert mla_contracts
            existing_mla = conn.execute("SELECT contract_id FROM mla_contracts WHERE contract_id = ?", [ob_info["contract_id"]]).fetchone()
            if not existing_mla:
                conn.execute("""
                    INSERT INTO mla_contracts (contract_id, client_id, site_id, monthly_rate, billing_frequency, start_date, end_date, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 'ACTIVE');
                """, [
                    ob_info["contract_id"], ob_info["client_id"], ob_info["site_id"],
                    ob_info["monthly_rate"], ob_info["billing_frequency"], ob_info["start_date"],
                    ob_info["end_date"]
                ])
            else:
                conn.execute("UPDATE mla_contracts SET status = 'ACTIVE' WHERE contract_id = ?;", [ob_info["contract_id"]])

            # 3. Update existing invoice to PAID, or insert if not exists
            existing_inv = conn.execute("SELECT invoice_id FROM revenue_invoices WHERE contract_id = ?", [ob_info["contract_id"]]).fetchone()
            if existing_inv:
                conn.execute("""
                    UPDATE revenue_invoices 
                    SET payment_status = 'PAID', payment_date = CAST(CURRENT_DATE AS VARCHAR) 
                    WHERE contract_id = ? OR client_id = ?;
                """, [ob_info["contract_id"], ob_info["client_id"]])
            else:
                max_inv = conn.execute("SELECT MAX(invoice_id) FROM revenue_invoices;").fetchone()[0]
                last_inv_num = 8
                if max_inv and "INV-2026-" in str(max_inv):
                    try:
                        last_inv_num = int(str(max_inv).split("-")[-1])
                    except Exception:
                        last_inv_num = 8
                inv_id = f"INV-2026-{(last_inv_num + 1):03d}"
                inv_number = f"INV/BLT/2026/04/{(last_inv_num + 1):03d}"
                
                period_cov = "2026-Q2" if ob_info["billing_frequency"] == "QUARTERLY" else "2026-04"
                months_mult = 3 if ob_info["billing_frequency"] == "QUARTERLY" else 1
                subtotal = int(ob_info["monthly_rate"]) * months_mult
                ppn = int(subtotal * 0.11)
                total_bill = subtotal + ppn

                conn.execute("""
                    INSERT INTO revenue_invoices (
                        invoice_id, invoice_number, contract_id, client_id, period_covered,
                        amount_subtotal, tax_ppn, total_billed, invoice_date, due_date,
                        payment_status, payment_date
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, CAST(CURRENT_DATE AS VARCHAR), CAST(CURRENT_DATE + INTERVAL 30 DAY AS VARCHAR), 'PAID', CAST(CURRENT_DATE AS VARCHAR));
                """, [
                    inv_id, inv_number, ob_info["contract_id"], ob_info["client_id"],
                    period_cov, subtotal, ppn, total_bill
                ])
        elif not is_approve:
            conn.execute("UPDATE mla_contracts SET status = 'REJECTED' WHERE contract_id = ?;", [ob_info["contract_id"]])
            conn.execute("UPDATE revenue_invoices SET payment_status = 'CANCELLED' WHERE contract_id = ?;", [ob_info["contract_id"]])

        conn.commit()
    finally:
        conn.close()

    # Confirmation HTML
    if is_approve:
        status_badge = '<span style="background: #DCFCE7; color: #166534; border: 1px solid #86EFAC; padding: 6px 14px; border-radius: 6px; font-weight: 700; font-size: 11.5px; letter-spacing: 0.05em; text-transform: uppercase;">STATUS: DISETUJUI (APPROVED)</span>'
        heading_text = "Kontrak Sewa Menara Resmi Disetujui & Database Terintegrasi"
        desc_text = f"Pendaftaran klien operator <strong>{ob_info['client_name']}</strong> ({ob_info['client_id']}) dan kontrak MLA <strong>{ob_info['contract_id']}</strong> telah disahkan. Seluruh tabel basis data (klien, kontrak, invoice) telah otomatis terupdate."
    else:
        status_badge = '<span style="background: #FEE2E2; color: #991B1B; border: 1px solid #FCA5A5; padding: 6px 14px; border-radius: 6px; font-weight: 700; font-size: 11.5px; letter-spacing: 0.05em; text-transform: uppercase;">STATUS: DITOLAK (REJECTED)</span>'
        heading_text = "Pengajuan Kontrak Sewa Ditolak"
        desc_text = f"Pengajuan sewa menara untuk <strong>{ob_info['client_name']}</strong> ({onboarding_id}) telah ditolak. Data tidak ditambahkan ke daftar klien aktif."

    html_content = f"""<!DOCTYPE html>
<html lang="id">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Konfirmasi Persetujuan Kontrak Sewa | {onboarding_id}</title>
    <style>
        * {{ box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #F1F5F9;
            margin: 0;
            padding: 40px 16px;
            color: #0F172A;
            display: flex;
            align-items: center;
            justify-content: center;
            min-height: 100vh;
        }}
        .receipt-card {{
            background: #FFFFFF;
            border: 1px solid #CBD5E1;
            border-radius: 12px;
            max-width: 640px;
            width: 100%;
            overflow: hidden;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.08), 0 2px 4px -2px rgba(0, 0, 0, 0.05);
        }}
        .receipt-header {{
            background: #0F172A;
            color: #FFFFFF;
            padding: 24px 32px;
            border-bottom: 3px solid #2563EB;
        }}
        .receipt-body {{
            padding: 32px;
        }}
        .meta-table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 13px;
            margin-top: 18px;
        }}
        .meta-table td {{
            padding: 10px 0;
            border-bottom: 1px solid #F1F5F9;
        }}
        .meta-label {{
            color: #64748B;
            width: 42%;
            font-weight: 500;
        }}
        .meta-val {{
            color: #0F172A;
            font-weight: 600;
            text-align: right;
        }}
        .btn-row {{
            display: flex;
            gap: 12px;
            margin-top: 28px;
            flex-wrap: wrap;
        }}
        .btn {{
            flex: 1;
            min-width: 140px;
            padding: 12px 18px;
            border-radius: 6px;
            font-size: 13px;
            font-weight: 600;
            text-decoration: none;
            text-align: center;
        }}
        .btn-primary {{
            background: #0F172A;
            color: #FFFFFF !important;
        }}
        .receipt-footer {{
            background: #F8FAFC;
            border-top: 1px solid #E2E8F0;
            padding: 16px 32px;
            font-size: 11.5px;
            color: #64748B;
            text-align: center;
        }}
    </style>
</head>
<body>
    <div class="receipt-card">
        <div class="receipt-header">
            <h1 style="font-size: 15px; font-weight: 700; margin: 0; text-transform: uppercase; letter-spacing: 0.08em; color: #F8FAFC;">PT Bali Towerindo Sentra Tbk</h1>
            <p style="font-size: 12px; color: #94A3B8; margin: 4px 0 0 0;">Divisi Keuangan & Komersial (Finance Operations)</p>
        </div>
        <div class="receipt-body">
            <div style="margin-bottom: 16px;">
                {status_badge}
            </div>
            <h2 style="font-size: 18px; font-weight: 700; margin: 0 0 8px 0; color: #0F172A;">{heading_text}</h2>
            <p style="font-size: 13.5px; color: #475569; margin: 0 0 24px 0; line-height: 1.5;">{desc_text}</p>

            <table class="meta-table">
                <tr>
                    <td class="meta-label">Nomor Pengajuan (ID)</td>
                    <td class="meta-val" style="font-family: monospace; color: #1D4ED8;">{onboarding_id}</td>
                </tr>
                <tr>
                    <td class="meta-label">Nama Klien Operator</td>
                    <td class="meta-val">{ob_info['client_name']} ({ob_info['client_id']})</td>
                </tr>
                <tr>
                    <td class="meta-label">Kontrak Sewa (MLA)</td>
                    <td class="meta-val">{ob_info['contract_id']} (Site: {ob_info['site_id']})</td>
                </tr>
                <tr>
                    <td class="meta-label">Tarif Sewa Bulanan</td>
                    <td class="meta-val">Rp {int(ob_info['monthly_rate']):,} / bulan</td>
                </tr>
                <tr>
                    <td class="meta-label">Frekuensi & Durasi</td>
                    <td class="meta-val">{ob_info['billing_frequency']} ({ob_info['start_date']} s/d {ob_info['end_date']})</td>
                </tr>
                <tr>
                    <td class="meta-label">Status Tagihan Perdana</td>
                    <td class="meta-val" style="color: {'#15803D' if is_approve else '#64748B'};">
                        {f'{inv_id} ({inv_number}) — UNPAID' if inv_id else ('Diterbitkan Otomatis' if is_approve else '-')}
                    </td>
                </tr>
                <tr>
                    <td class="meta-label">Diverifikasi Oleh</td>
                    <td class="meta-val">{manager_name}</td>
                </tr>
            </table>

            <div class="btn-row">
                <a href="{base_url}/" class="btn btn-primary">Buka Dashboard Web PT Bali Tower</a>
            </div>
        </div>
        <div class="receipt-footer">
            PT Bali Towerindo Sentra Tbk | Wisma Kodel Lantai 6, Jl. H.R. Rasuna Said Kav. B-4, Jakarta Selatan 12920
        </div>
    </div>
</body>
</html>"""

    return HTMLResponse(content=html_content, status_code=200)


@router.get("/{pr_number}", response_model=PurchaseRequisitionDoc)
async def get_requisition_by_number(pr_number: str):
    """Returns a single purchase requisition by PR Number."""
    pr = PR_STORE.get(pr_number)
    if not pr:
        raise HTTPException(status_code=404, detail="Purchase Requisition not found.")
    return pr


@router.post("/action")
async def execute_approval_action(payload: ApprovalActionPayload):
    """
    Executes Human-In-The-Loop action (Approve or Reject) for a Purchase Requisition.
    Automatically regenerates the formal Typst PDF document with the updated status.
    """
    pr = _ensure_pr_in_store(payload.pr_number)
    if not pr:
        raise HTTPException(status_code=404, detail="Purchase Requisition not found.")

    action = payload.action.upper()
    pr.status = "APPROVED" if action == "APPROVE" else "REJECTED"
    _update_db_status(pr.pr_number, pr.status, pr if action == "APPROVE" else None)
    _regenerate_pdf(pr)

    message = (
        f"Dokumen {payload.pr_number} telah disetujui oleh {payload.manager_name}. Status diteruskan ke Purchasing."
        if action == "APPROVE" else
        f"Dokumen {payload.pr_number} telah ditolak oleh {payload.manager_name}."
    )

    return {
        "status": "success",
        "pr_number": pr.pr_number,
        "new_status": pr.status,
        "message": message,
        "updated_at": datetime.now().isoformat()
    }


@router.post("/dispatch-email")
async def dispatch_pr_email(payload: DispatchEmailPayload, current_user: TokenData = Depends(get_current_user)):
    """
    Dispatches formal Typst PR approval notification email to Logistics Manager or custom recipient.
    """
    pr = _ensure_pr_in_store(payload.pr_number)
    if not pr:
        raise HTTPException(status_code=404, detail=f"Draf PR {payload.pr_number} tidak ditemukan.")

    target_email = payload.recipient_email or "manager.logistik@balitower.co.id"

    from pathlib import Path
    pdf_path = None
    clean_filename = f"{pr.pr_number.replace('-', '_')}.pdf"

    if pr.pdf_path and Path(pr.pdf_path).exists():
        pdf_path = Path(pr.pdf_path)
    elif (Path("storage/documents") / clean_filename).exists():
        pdf_path = Path("storage/documents") / clean_filename
    elif (Path("storage/pending") / clean_filename).exists():
        pdf_path = Path("storage/pending") / clean_filename

    if not pdf_path or not pdf_path.exists():
        _regenerate_pdf(pr)
        if pr.pdf_path and Path(pr.pdf_path).exists():
            pdf_path = Path(pr.pdf_path)
        elif (Path("storage/documents") / clean_filename).exists():
            pdf_path = Path("storage/documents") / clean_filename

    from core.dispatcher import dispatcher
    dispatch_res = await dispatcher.dispatch_email(
        recipient_email=target_email,
        subject=f"Permintaan Persetujuan Pengadaan Material: {pr.pr_number} - PT Bali Towerindo Sentra Tbk",
        content_text=f"Dokumen pengajuan {pr.pr_number} sebesar Rp {pr.total_budget:,.2f} telah diterbitkan dan menunggu persetujuan Anda.",
        attachment_path=str(pdf_path) if pdf_path else None,
        pr_number=pr.pr_number
    )

    pr.email_sent = True

    return {
        "status": "success",
        "pr_number": pr.pr_number,
        "recipient_email": target_email,
        "message": f"Email permohonan persetujuan untuk {pr.pr_number} berhasil dikirim ke {target_email}."
    }


@router.post("/reset")
async def reset_sample_data(seed: bool = False):
    """
    Resets PR_STORE to clean state, clears DuckDB orders, purchase_orders, and purchase_requests.
    If seed=True, seeds PR-2026-0819-001 for test suites.
    """
    PR_STORE.clear()

    try:
        from database.db import execute_db_write

        def _clear_all_tables(conn):
            existing_tables = set(r[0] for r in conn.execute("SHOW TABLES;").fetchall())
            if "orders" in existing_tables:
                conn.execute("DELETE FROM orders;")
            if "purchase_orders" in existing_tables:
                conn.execute("DELETE FROM purchase_orders;")
            if "purchase_requests" in existing_tables:
                conn.execute("DELETE FROM purchase_requests;")

        execute_db_write(_clear_all_tables)
    except Exception as e:
        print(f"[RESET] Warning cleaning balitower orders/PRs: {e}")

    # Synchronize purchase_orders.csv
    try:
        from database.db import WORKSPACE_DIR
        inv_csv = WORKSPACE_DIR / "data" / "balitower" / "01_inventory" / "purchase_orders.csv"
        if inv_csv.exists():
            inv_csv.write_text("po_id,po_number,supplier_id,item_id,order_quantity,unit_price,total_amount,status,order_date,expected_delivery,actual_delivery,warehouse_id,pr_number\n", encoding="utf-8")
    except Exception as e:
        print(f"[RESET] Could not clear purchase_orders.csv: {e}")

    if seed:
        sample_pr = _create_default_pr()
        PR_STORE["PR-2026-0819-001"] = sample_pr
        _regenerate_pdf(sample_pr)
        persist_pr_to_db(sample_pr)
        return {"status": "reset", "message": "PR-2026-0819-001 reset to PENDING status with all 5 DuckDB critical items."}

    return {"status": "reset", "message": "Seluruh PR dan PO berhasil dikosongkan (Clean Reset)."}


@router.post("/clear-all")
async def clear_all_prs_and_pos(current_user: TokenData = Depends(get_current_user)):
    """
    Membersihkan seluruh draf PR, mengosongkan PR_STORE, menghapus seluruh berkas PDF PR dan PO,
    serta mengosongkan tabel purchase_orders, purchase_requests, dan orders di DuckDB,
    dan mengosongkan berkas purchase_orders.csv.
    """
    PR_STORE.clear()

    # Clear orders, purchase_orders, and purchase_requests in balitower.db
    try:
        from database.db import execute_db_write

        def _clear_all_tables(conn):
            existing_tables = set(r[0] for r in conn.execute("SHOW TABLES;").fetchall())
            if "orders" in existing_tables:
                conn.execute("DELETE FROM orders;")
            if "purchase_orders" in existing_tables:
                conn.execute("DELETE FROM purchase_orders;")
            if "purchase_requests" in existing_tables:
                conn.execute("DELETE FROM purchase_requests;")

        execute_db_write(_clear_all_tables)
    except Exception as e:
        print(f"[CLEAR-ALL] Error clearing DuckDB orders: {e}")

    # Synchronize purchase_orders.csv to 0 rows (only header)
    try:
        from database.db import WORKSPACE_DIR
        inv_csv = WORKSPACE_DIR / "data" / "balitower" / "01_inventory" / "purchase_orders.csv"
        if inv_csv.exists():
            inv_csv.write_text("po_id,po_number,supplier_id,item_id,order_quantity,unit_price,total_amount,status,order_date,expected_delivery,actual_delivery,warehouse_id,pr_number\n", encoding="utf-8")
    except Exception as e:
        print(f"[CLEAR-ALL] Could not clear purchase_orders.csv: {e}")

    # Remove generated PDFs from storage
    deleted_files = 0
    from database.db import STORAGE_DIR
    for sub in ["documents", "pending", "approved", "rejected", "purchase_orders"]:
        folder = STORAGE_DIR / sub
        if folder.exists():
            for pdf_file in folder.glob("*.pdf"):
                try:
                    pdf_file.unlink()
                    deleted_files += 1
                except Exception as e:
                    print(f"[CLEAR-ALL] Could not delete {pdf_file}: {e}")

    return {
        "status": "success",
        "message": f"Seluruh draf PR dan PO berhasil dibersihkan ({deleted_files} berkas PDF dihapus).",
        "total_prs_now": len(PR_STORE),
        "total_pos_now": 0
    }



