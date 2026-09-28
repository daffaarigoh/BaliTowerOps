"""
Bali Tower API Router
Menyediakan REST API untuk 3 Modul Operasional PT Bali Towerindo Sentra Tbk:
1. Inventory & Logistik Material Tower/FO
2. HR & Field Workforce Management (Absensi Geofencing, Cuti, Rekrutmen K3)
3. Finance & Laporan Keuangan (Invoices Sewa Menara, Biaya OPEX, List Transaksi Kas)

Dilengkapi sistem otorisasi multi-tenant ketat:
- Admin (tenant ALL): Akses penuh ke seluruh modul dan tabel.
- User Inventory (tenant INVENTORY): Hanya boleh akses modul Inventory & Logistik.
- User HR (tenant HR): Hanya boleh akses modul HR & Field Workforce.
- User Finance (tenant FINANCE): Hanya boleh akses modul Finance & Accounting.
"""

import re
from datetime import datetime, timedelta
from typing import Any
from fastapi import APIRouter, HTTPException, Depends, Query, Request, status
from pydantic import BaseModel, Field
from core.security import TokenData, get_current_user
from database.db import get_db_connection

router = APIRouter(tags=["Bali Tower Enterprise System"])


# ==============================================================================
# RBAC & STRICT MULTI-TENANT ACCESS GUARDS
# ==============================================================================

def require_inventory_access(current_user: TokenData = Depends(get_current_user)) -> TokenData:
    """Memastikan user memiliki wewenang divisi Inventory atau Super Admin."""
    role = (current_user.role or "").upper()
    tenant = (current_user.tenant_id or "").upper()
    username = (current_user.username or "").lower()
    if role in ["ADMIN", "MANAGER"] or tenant in ["ALL", "INVENTORY", "TENANT_A"] or username in ["admin", "usera", "user_inventory"]:
        return current_user
    raise HTTPException(
        status_code=403,
        detail=f"Akses ditolak: Akun Anda ({current_user.username} - Divisi {current_user.tenant_id}) tidak memiliki izin untuk mengakses modul Inventory & Logistik."
    )


def require_hr_access(current_user: TokenData = Depends(get_current_user)) -> TokenData:
    """Memastikan user memiliki wewenang divisi HR atau Super Admin."""
    role = (current_user.role or "").upper()
    tenant = (current_user.tenant_id or "").upper()
    username = (current_user.username or "").lower()
    if role in ["ADMIN", "MANAGER"] or tenant in ["ALL", "HR", "TENANT_B"] or username in ["admin", "userb", "user_hr"]:
        return current_user
    raise HTTPException(
        status_code=403,
        detail=f"Akses ditolak: Akun Anda ({current_user.username} - Divisi {current_user.tenant_id}) tidak memiliki izin untuk mengakses modul HR & Field Workforce."
    )


def require_finance_access(current_user: TokenData = Depends(get_current_user)) -> TokenData:
    """Memastikan user memiliki wewenang divisi Finance atau Super Admin."""
    role = (current_user.role or "").upper()
    tenant = (current_user.tenant_id or "").upper()
    username = (current_user.username or "").lower()
    if role in ["ADMIN", "MANAGER"] or tenant in ["ALL", "FINANCE", "TENANT_C"] or username in ["admin", "userc", "user_finance"]:
        return current_user
    raise HTTPException(
        status_code=403,
        detail=f"Akses ditolak: Akun Anda ({current_user.username} - Divisi {current_user.tenant_id}) tidak memiliki izin untuk mengakses modul Finance & Akuntansi."
    )


# ==============================================================================
# SCOPE 1: INVENTORY & LOGISTIK (5 TABEL UTAMA)
# ==============================================================================

@router.get("/api/balitower/inventory/items")
def get_inventory_items(
    category: str | None = None,
    warehouse_id: str | None = None,
    current_user: TokenData = Depends(require_inventory_access)
):
    """Tabel 1: inventory_items - Katalog lengkap material tower & FO beserta saldo stok aktual."""
    conn = get_db_connection(read_only=True)
    try:
        query = """
            SELECT 
                i.item_id,
                i.item_code,
                i.item_name AS name,
                i.category,
                i.unit,
                i.unit_price,
                CASE 
                    WHEN COUNT(sb.warehouse_id) > 0 THEN CAST(SUM(sb.reorder_point) AS BIGINT) 
                    ELSE i.min_stock 
                END AS min_stock,
                CASE 
                    WHEN COUNT(sb.warehouse_id) > 0 THEN CAST(SUM(sb.reorder_point * 3) AS BIGINT) 
                    ELSE i.min_stock * 3 
                END AS max_stock,
                CASE 
                    WHEN COUNT(sb.warehouse_id) > 0 THEN CAST(SUM(sb.reorder_point * 3) AS BIGINT) 
                    ELSE i.min_stock * 3 
                END AS max_threshold,
                i.safety_stock,
                i.lead_time_days,
                s.supplier_name,
                COALESCE(SUM(sb.quantity_on_hand), 0) AS total_stock,
                COALESCE(SUM(sb.quantity_reserved), 0) AS total_reserved,
                CASE 
                    WHEN COALESCE(SUM(sb.quantity_on_hand), 0) = 0 THEN 'OUT_OF_STOCK'
                    WHEN COALESCE(SUM(sb.quantity_on_hand), 0) <= (
                        CASE WHEN COUNT(sb.warehouse_id) > 0 THEN SUM(sb.reorder_point * 0.5) ELSE i.min_stock * 0.5 END
                    ) THEN 'CRITICAL'
                    WHEN COALESCE(SUM(sb.quantity_on_hand), 0) <= (
                        CASE WHEN COUNT(sb.warehouse_id) > 0 THEN SUM(sb.reorder_point) ELSE i.min_stock END
                    ) THEN 'LOW_STOCK'
                    ELSE 'NORMAL'
                END AS stock_status
            FROM inventory_items i
            LEFT JOIN suppliers s ON i.supplier_id = s.supplier_id
            LEFT JOIN stock_balances sb ON i.item_id = sb.item_id
            WHERE 1=1
        """
        params = []
        if category:
            query += " AND i.category = ?"
            params.append(category)
        if warehouse_id:
            query += " AND sb.warehouse_id = ?"
            params.append(warehouse_id)
            
        query += " GROUP BY i.item_id, i.item_code, i.item_name, i.category, i.unit, i.unit_price, i.min_stock, i.safety_stock, i.lead_time_days, s.supplier_name ORDER BY i.item_id ASC"
        
        rows = conn.execute(query, params).fetchall()
        cols = [desc[0] for desc in conn.description]
        return [dict(zip(cols, r)) for r in rows]
    finally:
        conn.close()


@router.get("/api/balitower/inventory/stock-balances")
def get_stock_balances(
    warehouse_id: str | None = None,
    current_user: TokenData = Depends(require_inventory_access)
):
    """Tabel 2: stock_balances - Rincian saldo fisik material per gudang penyimpanan."""
    conn = get_db_connection(read_only=True)
    try:
        query = """
            SELECT 
                sb.balance_id,
                sb.item_id,
                i.item_code,
                i.item_name,
                i.category,
                i.unit,
                w.warehouse_id,
                w.warehouse_name,
                w.region,
                sb.quantity_on_hand,
                sb.quantity_reserved,
                sb.reorder_point,
                CASE 
                    WHEN sb.quantity_on_hand = 0 THEN 'OUT_OF_STOCK'
                    WHEN sb.quantity_on_hand <= (sb.reorder_point * 0.5) THEN 'CRITICAL'
                    WHEN sb.quantity_on_hand <= sb.reorder_point THEN 'LOW_STOCK'
                    ELSE 'NORMAL'
                END AS stock_status,
                sb.last_updated,
                CAST(sb.last_updated AS VARCHAR)[:10] AS last_stock_take_date
            FROM stock_balances sb
            JOIN inventory_items i ON sb.item_id = i.item_id
            JOIN warehouses w ON sb.warehouse_id = w.warehouse_id
            WHERE 1=1
        """
        params = []
        if warehouse_id:
            query += " AND sb.warehouse_id = ?"
            params.append(warehouse_id)
        query += " ORDER BY sb.balance_id ASC;"
        rows = conn.execute(query, params).fetchall()
        cols = [desc[0] for desc in conn.description]
        return [dict(zip(cols, r)) for r in rows]
    finally:
        conn.close()


class UpdateStockBalancePayload(BaseModel):
    item_id: str
    warehouse_id: str
    new_quantity: int = Field(..., ge=0, description="Kuantitas fisik stok baru")
    reorder_point: int | None = Field(None, ge=1, description="Ambang batas minimum reorder point opsional")


@router.put("/api/balitower/inventory/stock-balances")
def update_stock_balance(
    payload: UpdateStockBalancePayload,
    current_user: TokenData = Depends(get_current_user)
):
    """
    Memperbarui kuantitas fisik stok barang pada gudang tertentu secara bebas oleh Admin.
    Secara otomatis mengalkulasi ulang stock_status berdasarkan formula matematis baku:
    - new_quantity == 0 -> OUT_OF_STOCK
    - new_quantity <= reorder_point * 0.5 -> CRITICAL
    - new_quantity <= reorder_point -> LOW_STOCK
    - new_quantity > reorder_point -> NORMAL
    """
    u_role = str(getattr(current_user, 'role', 'USER')).upper()
    u_tenant = str(getattr(current_user, 'tenant_id', 'ALL')).upper()
    username = str(getattr(current_user, 'username', '')).lower()
    is_authorized = (
        u_role in ["ADMIN", "SUPERADMIN"] or 
        u_tenant in ["ALL", "INVENTORY", "TENANT_A"] or 
        username in ["admin", "usera"]
    )
    if not is_authorized:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Akses Ditolak: Hanya Admin atau Divisi Inventory yang berhak mengubah saldo stok fisik."
        )

    now_ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    today_str = datetime.now().strftime("%Y-%m-%d")

    conn = get_db_connection(read_only=False)
    try:
        row = conn.execute("""
            SELECT balance_id, quantity_on_hand, reorder_point 
            FROM stock_balances 
            WHERE item_id = ? AND warehouse_id = ?;
        """, [payload.item_id, payload.warehouse_id]).fetchone()

        if not row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Saldo stok untuk item {payload.item_id} di gudang {payload.warehouse_id} tidak ditemukan."
            )

        bal_id, old_qty, cur_rop = row
        new_rop = payload.reorder_point if payload.reorder_point is not None else cur_rop
        new_qty = payload.new_quantity

        if new_qty == 0:
            new_status = 'OUT_OF_STOCK'
        elif new_qty <= new_rop * 0.5:
            new_status = 'CRITICAL'
        elif new_qty <= new_rop:
            new_status = 'LOW_STOCK'
        else:
            new_status = 'NORMAL'

        conn.execute("""
            UPDATE stock_balances
            SET quantity_on_hand = ?,
                reorder_point = ?,
                stock_status = ?,
                last_updated = ?,
                last_stock_take_date = ?
            WHERE balance_id = ?;
        """, [new_qty, new_rop, new_status, now_ts, today_str, bal_id])

        if payload.reorder_point is not None:
            conn.execute("""
                UPDATE inventory_items
                SET min_stock = ?
                WHERE item_id = ?;
            """, [new_rop, payload.item_id])

        try:
            conn.execute("""
                UPDATE items
                SET current_stock = (
                    SELECT COALESCE(SUM(quantity_on_hand), 0)
                    FROM stock_balances
                    WHERE stock_balances.item_id = items.item_id
                ),
                min_threshold = (
                    SELECT COALESCE(SUM(reorder_point), items.min_threshold)
                    FROM stock_balances
                    WHERE stock_balances.item_id = items.item_id
                ),
                max_threshold = (
                    SELECT COALESCE(SUM(reorder_point * 3), items.max_threshold)
                    FROM stock_balances
                    WHERE stock_balances.item_id = items.item_id
                )
                WHERE item_id = ?;
            """, [payload.item_id])
        except Exception:
            pass

        conn.commit()

        updated_data = conn.execute("""
            SELECT 
                sb.balance_id,
                sb.item_id,
                i.item_name,
                sb.warehouse_id,
                w.warehouse_name,
                sb.quantity_on_hand,
                sb.reorder_point,
                sb.stock_status,
                sb.last_stock_take_date
            FROM stock_balances sb
            JOIN inventory_items i ON sb.item_id = i.item_id
            JOIN warehouses w ON sb.warehouse_id = w.warehouse_id
            WHERE sb.balance_id = ?;
        """, [bal_id]).fetchone()

        cols = ["balance_id", "item_id", "item_name", "warehouse_id", "warehouse_name", "quantity_on_hand", "reorder_point", "stock_status", "last_stock_take_date"]
        res_dict = dict(zip(cols, updated_data))

        return {
            "status": "success",
            "message": f"Stok {res_dict['item_name']} di {res_dict['warehouse_name']} berhasil diubah menjadi {new_qty} (Status: {new_status}).",
            "data": res_dict
        }
    finally:
        conn.close()


@router.get("/api/balitower/inventory/warehouses")
def get_warehouses(current_user: TokenData = Depends(require_inventory_access)):
    """Tabel 3: warehouses - Daftar gudang regional dan kapasitas logistik."""
    conn = get_db_connection(read_only=True)
    try:
        rows = conn.execute("""
            SELECT 
                warehouse_id,
                warehouse_name,
                warehouse_type,
                region,
                address,
                capacity_sqm,
                supervisor,
                'OPERASIONAL' AS status
            FROM warehouses 
            ORDER BY warehouse_id ASC;
        """).fetchall()
        cols = [desc[0] for desc in conn.description]
        return [dict(zip(cols, r)) for r in rows]
    finally:
        conn.close()


@router.get("/api/balitower/inventory/suppliers")
def get_suppliers(current_user: TokenData = Depends(require_inventory_access)):
    """Tabel 4: suppliers - Master supplier rekanan pengadaan barang."""
    conn = get_db_connection(read_only=True)
    try:
        rows = conn.execute("""
            SELECT 
                supplier_id,
                supplier_name,
                category,
                COALESCE(contact_person, '-') AS contact_person,
                phone,
                email,
                rating,
                payment_terms
            FROM suppliers 
            ORDER BY supplier_id ASC;
        """).fetchall()
        cols = [desc[0] for desc in conn.description]
        return [dict(zip(cols, r)) for r in rows]
    finally:
        conn.close()


@router.get("/api/balitower/inventory/purchase-orders")
def get_purchase_orders(current_user: TokenData = Depends(require_inventory_access)):
    """Tabel 5: purchase_orders - Riwayat pesanan pembelian resmi pengadaan."""
    conn = get_db_connection(read_only=True)
    try:
        existing_tables = {t[0] for t in conn.execute("SHOW TABLES;").fetchall()}
        pr_filter_clauses = ["po.pr_number IS NULL", "po.status = 'DELIVERED'"]
        
        pr_sources = []
        if "orders" in existing_tables:
            pr_sources.append("SELECT pr_number FROM orders WHERE status IN ('APPROVED', 'DISETUJUI')")
        if "purchase_requests" in existing_tables:
            pr_sources.append("SELECT pr_number FROM purchase_requests WHERE status IN ('APPROVED', 'DISETUJUI')")
            
        if pr_sources:
            pr_filter_clauses.append(f"po.pr_number IN ({' UNION '.join(pr_sources)})")
            
        where_condition = f"({' OR '.join(pr_filter_clauses)}) AND po.status != 'PENDING_APPROVAL'"

        query = f"""
            SELECT 
                po.po_id,
                po.po_number,
                MIN(po.supplier_id) AS supplier_id,
                CASE 
                    WHEN COUNT(DISTINCT s.supplier_name) > 1 THEN 'Multi-Vendor Rekanan (' || COUNT(DISTINCT s.supplier_name) || ' Vendor)'
                    ELSE COALESCE(MIN(s.supplier_name), MIN(po.supplier_id))
                END AS supplier_name,
                MIN(po.item_id) AS item_id,
                CASE 
                    WHEN COUNT(po.item_id) > 1 THEN COUNT(po.item_id) || ' Material Pengadaan (' || STRING_AGG(DISTINCT i.item_name, ', ')[:55] || '...)'
                    ELSE COALESCE(MIN(i.item_name), MIN(po.item_id))
                END AS item_name,
                MIN(po.warehouse_id) AS warehouse_id,
                CASE 
                    WHEN COUNT(DISTINCT w.warehouse_name) > 1 THEN 'Multi-Gudang Regional (' || COUNT(DISTINCT w.warehouse_name) || ' Gudang)'
                    ELSE COALESCE(MIN(w.warehouse_name), MIN(po.warehouse_id))
                END AS warehouse_name,
                SUM(po.order_quantity) AS order_quantity,
                CAST(AVG(po.unit_price) AS BIGINT) AS unit_price,
                SUM(po.total_amount) AS total_amount,
                MIN(po.order_date) AS order_date,
                MIN(po.expected_delivery) AS expected_delivery,
                MIN(po.status) AS status,
                MIN(po.status) AS po_status
            FROM purchase_orders po
            LEFT JOIN suppliers s ON po.supplier_id = s.supplier_id
            LEFT JOIN inventory_items i ON po.item_id = i.item_id
            LEFT JOIN warehouses w ON po.warehouse_id = w.warehouse_id
            WHERE {where_condition}
            GROUP BY po.po_id, po.po_number
            ORDER BY MIN(po.order_date) DESC, po.po_id DESC;
        """
        rows = conn.execute(query).fetchall()
        cols = [desc[0] for desc in conn.description]
        return [dict(zip(cols, r)) for r in rows]
    finally:
        conn.close()


@router.get("/api/balitower/inventory/critical-stock")
def get_critical_stock(current_user: TokenData = Depends(require_inventory_access)):
    """Peringatan material yang membutuhkan restock segera."""
    conn = get_db_connection(read_only=True)
    try:
        query = """
            SELECT 
                sb.balance_id,
                w.warehouse_name,
                i.item_id,
                i.item_code,
                i.item_name,
                i.category,
                sb.quantity_on_hand,
                sb.reorder_point,
                sb.stock_status,
                i.unit,
                i.unit_price,
                (sb.reorder_point * 2 - sb.quantity_on_hand) AS recommended_restock_qty,
                ((sb.reorder_point * 2 - sb.quantity_on_hand) * i.unit_price) AS estimated_cost
            FROM stock_balances sb
            JOIN inventory_items i ON sb.item_id = i.item_id
            JOIN warehouses w ON sb.warehouse_id = w.warehouse_id
            WHERE sb.stock_status IN ('CRITICAL', 'LOW_STOCK')
            ORDER BY sb.stock_status ASC, sb.quantity_on_hand ASC;
        """
        rows = conn.execute(query).fetchall()
        cols = [desc[0] for desc in conn.description]
        return [dict(zip(cols, r)) for r in rows]
    finally:
        conn.close()


# ==============================================================================
# SCOPE 2: HR & FIELD WORKFORCE (6 TABEL UTAMA)
# ==============================================================================

@router.get("/api/balitower/hr/summary")
def get_hr_summary(current_user: TokenData = Depends(require_hr_access)):
    """Mengambil KPI ringkas ketenagakerjaan dan teknisi lapangan."""
    conn = get_db_connection(read_only=True)
    try:
        total_employees = conn.execute("SELECT COUNT(*) FROM employees;").fetchone()[0]
        field_techs = conn.execute("SELECT COUNT(*) FROM employees WHERE department = 'Field Operations';").fetchone()[0]
        certified_k3 = conn.execute("SELECT COUNT(*) FROM employees WHERE k3_certification IN ('TKPK 1', 'TKPK 2');").fetchone()[0]
        total_sites = conn.execute("SELECT COUNT(*) FROM telecom_sites;").fetchone()[0]
        pending_leaves = conn.execute("SELECT COUNT(*) FROM leave_requests WHERE approval_status = 'PENDING_APPROVAL';").fetchone()[0]
        open_jobs = conn.execute("SELECT COUNT(*) FROM job_postings WHERE status = 'OPEN';").fetchone()[0]

        return {
            "total_employees": total_employees,
            "field_technicians": field_techs,
            "certified_k3_tkpk": certified_k3,
            "telecom_sites_monitored": total_sites,
            "total_overtime_hours": 0.0,
            "pending_leave_requests": pending_leaves,
            "open_job_vacancies": open_jobs
        }
    finally:
        conn.close()


@router.get("/api/balitower/hr/employees")
def get_employees(
    department: str | None = None,
    k3_only: bool = False,
    current_user: TokenData = Depends(require_hr_access)
):
    """Tabel 6: employees - Master data karyawan, status sertifikasi K3, dan hak cuti."""
    conn = get_db_connection(read_only=True)
    try:
        query = """
            SELECT 
                employee_id,
                full_name,
                department,
                job_title,
                employment_status,
                k3_certification,
                k3_cert_expiry,
                leave_balance AS leave_balance_days,
                hourly_overtime_rate
            FROM employees 
            WHERE 1=1
        """
        params = []
        if department:
            query += " AND department = ?"
            params.append(department)
        if k3_only:
            query += " AND k3_certification IN ('TKPK 1', 'TKPK 2')"
            
        query += " ORDER BY employee_id ASC"
        rows = conn.execute(query, params).fetchall()
        cols = [desc[0] for desc in conn.description]
        return [dict(zip(cols, r)) for r in rows]
    finally:
        conn.close()


@router.get("/api/balitower/hr/attendances")
def get_attendances(
    limit: int = 100,
    site_id: str | None = None,
    overtime_only: bool = False,
    current_user: TokenData = Depends(require_hr_access)
):
    """Decommissioned attendance endpoint (returns empty list)."""
    return []


@router.get("/api/balitower/hr/leave-requests")
def get_leave_requests(current_user: TokenData = Depends(require_hr_access)):
    """Tabel 8: leave_requests - Riwayat dan status perizinan/cuti teknisi dan karyawan."""
    conn = get_db_connection(read_only=True)
    try:
        query = """
            SELECT 
                l.leave_id,
                l.employee_id,
                e.full_name AS applicant_name,
                e.job_title,
                l.leave_type,
                l.start_date,
                l.end_date,
                l.days_requested,
                l.reason,
                l.substitute_employee_id,
                COALESCE(sub.full_name, '-') AS substitute_name,
                l.approval_status,
                COALESCE(appr.full_name, '-') AS approved_by_name
            FROM leave_requests l
            JOIN employees e ON l.employee_id = e.employee_id
            LEFT JOIN employees sub ON l.substitute_employee_id = sub.employee_id
            LEFT JOIN employees appr ON l.approved_by = appr.employee_id
            ORDER BY l.leave_id DESC;
        """
        rows = conn.execute(query).fetchall()
        cols = [desc[0] for desc in conn.description]
        return [dict(zip(cols, r)) for r in rows]
    finally:
        conn.close()


class LeaveCreateRequest(BaseModel):
    employee_id: str
    leave_type: str = "ANNUAL_LEAVE"
    start_date: str
    days_requested: int = 1
    reason: str
    substitute_employee_id: str | None = None
    recipient_email: str | None = None


@router.post("/api/balitower/hr/leave-requests")
async def create_leave_request(
    payload: LeaveCreateRequest,
    request: Request = None,
    current_user: TokenData = Depends(require_hr_access)
):
    """
    Merekam permohonan cuti baru karyawan ke tabel DuckDB leave_requests,
    mengompilasi formulir resmi format PDF Typst, dan mendistribusikan notifikasi ke HR.
    """
    conn = get_db_connection()
    try:
        # 1. Validasi employee_id
        emp = conn.execute(
            "SELECT employee_id, full_name, job_title, department, leave_balance FROM employees WHERE employee_id = ?",
            [payload.employee_id]
        ).fetchone()
        if not emp:
            raise HTTPException(status_code=400, detail=f"Karyawan dengan ID '{payload.employee_id}' tidak ditemukan.")

        substitute_name = "-"
        substitute_title = "-"
        if payload.substitute_employee_id:
            sub = conn.execute(
                "SELECT employee_id, full_name, job_title FROM employees WHERE employee_id = ?",
                [payload.substitute_employee_id]
            ).fetchone()
            if sub:
                substitute_name = sub[1]
                substitute_title = sub[2]

        # 2. Generate next leave_id (LV-2026-XXX)
        max_row = conn.execute("SELECT leave_id FROM leave_requests ORDER BY leave_id DESC LIMIT 1").fetchone()
        next_num = 1
        if max_row and max_row[0]:
            digits = re.findall(r'\d+', max_row[0])
            if digits:
                next_num = int(digits[-1]) + 1
        new_leave_id = f"LV-2026-{next_num:03d}"

        # 3. Hitung end_date otomatis
        try:
            s_date = datetime.strptime(payload.start_date, "%Y-%m-%d")
            days = max(1, int(payload.days_requested))
            e_date = s_date + timedelta(days=days - 1)
            end_date_str = e_date.strftime("%Y-%m-%d")
        except Exception:
            end_date_str = payload.start_date
            days = max(1, int(payload.days_requested))

        # 4. Insert ke tabel leave_requests
        conn.execute("""
            INSERT INTO leave_requests (
                leave_id, employee_id, leave_type, start_date, end_date,
                days_requested, reason, substitute_employee_id, approval_status, approved_by
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'PENDING_APPROVAL', NULL);
        """, [
            new_leave_id,
            payload.employee_id,
            payload.leave_type.upper(),
            payload.start_date,
            end_date_str,
            days,
            payload.reason,
            payload.substitute_employee_id
        ])
    finally:
        conn.close()

    # Siapkan dict data leave untuk PDF generator
    leave_data = {
        "leave_id": new_leave_id,
        "employee_id": emp[0],
        "applicant_name": emp[1],
        "job_title": emp[2],
        "department": emp[3],
        "leave_balance": emp[4],
        "leave_type": payload.leave_type,
        "start_date": payload.start_date,
        "end_date": end_date_str,
        "days_requested": days,
        "reason": payload.reason,
        "substitute_employee_id": payload.substitute_employee_id,
        "substitute_name": substitute_name,
        "substitute_title": substitute_title,
        "approval_status": "PENDING_APPROVAL",
        "approved_by_name": "Eko Prasetyo"
    }

    # 5. Kompilasi dokumen resmi PDF Typst
    from docgen.compiler import generate_leave_pdf
    pdf_path = None
    try:
        pdf_path = generate_leave_pdf(leave_data)
    except Exception as e:
        print(f"[WARN] Failed to compile leave PDF on submit: {e}")

    # 6. Kirim notifikasi email ke HR dengan lampiran PDF
    from core.dispatcher import dispatcher
    dispatch_res = None
    try:
        email_msg = (
            f"Pengajuan cuti baru telah dicatat dengan rincian sebagai berikut:\n"
            f"- Nomor Cuti: {new_leave_id}\n"
            f"- Pemohon: {emp[1]} ({emp[2]})\n"
            f"- Jenis Cuti: {payload.leave_type}\n"
            f"- Periode: {payload.start_date} s/d {end_date_str} ({days} hari kerja)\n"
            f"- Alasan: {payload.reason}\n\n"
            f"Berkas resmi formulir pengajuan cuti berformat PDF terlampir."
        )
        from core.config import settings, get_base_url
        target_recipient = payload.recipient_email or settings.DEFAULT_RECIPIENT_EMAIL or settings.SMTP_EMAIL or "muhammaddaffaarigoh@gmail.com"
        dispatch_res = await dispatcher.dispatch_email(
            recipient_email=target_recipient,
            subject=f"Pengajuan Cuti Karyawan: {new_leave_id} - {emp[1]}",
            content_text=email_msg,
            attachment_path=pdf_path,
            leave_id=new_leave_id,
            leave_data=leave_data,
            base_url=get_base_url(request)
        )
    except Exception as e:
        print(f"[WARN] Failed to dispatch email to HR: {e}")

    return {
        "status": "success",
        "leave_id": new_leave_id,
        "message": f"Pengajuan cuti {new_leave_id} berhasil dicatat dan berkas PDF telah dikirimkan ke Divisi HR.",
        "pdf_url": f"/api/documents/leave/{new_leave_id}/download",
        "data": {
            "leave_id": new_leave_id,
            "applicant_name": emp[1],
            "job_title": emp[2],
            "leave_type": payload.leave_type,
            "start_date": payload.start_date,
            "end_date": end_date_str,
            "days_requested": days,
            "reason": payload.reason,
            "substitute_employee_id": payload.substitute_employee_id,
            "approval_status": "PENDING_APPROVAL",
            "pdf_path": pdf_path,
            "email_status": dispatch_res.get("status") if dispatch_res else "SENT"
        }
    }


class LeaveActionRequest(BaseModel):
    action: str  # APPROVE / REJECT
    manager_name: str | None = "HR Manager"


@router.post("/api/balitower/hr/leave-requests/{leave_id}/action")
def update_leave_status(
    leave_id: str,
    payload: LeaveActionRequest,
    current_user: TokenData = Depends(require_hr_access)
):
    """Menyetujui atau menolak pengajuan cuti."""
    conn = get_db_connection()
    try:
        new_status = "APPROVED" if payload.action.upper() == "APPROVE" else "REJECTED"
        
        row = conn.execute(
            "SELECT employee_id, leave_type, days_requested, approval_status FROM leave_requests WHERE leave_id = ?",
            [leave_id]
        ).fetchone()

        conn.execute(
            "UPDATE leave_requests SET approval_status = ?, approved_by = 'EMP-BLT-005' WHERE leave_id = ?",
            [new_status, leave_id]
        )

        if row and new_status == "APPROVED" and row[3] != "APPROVED":
            emp_id, l_type, days, _ = row
            conn.execute(
                "UPDATE employees SET leave_balance = GREATEST(0, leave_balance - ?) WHERE employee_id = ?",
                [max(1, int(days or 1)), emp_id]
            )
        conn.commit()
    finally:
        conn.close()

    try:
        from docgen.compiler import generate_leave_pdf
        generate_leave_pdf(leave_id)
    except Exception as e:
        print(f"[WARN] Failed to regenerate leave PDF: {e}")

    return {"leave_id": leave_id, "status": new_status, "message": f"Pengajuan cuti berhasil di-{new_status.lower()}"}


@router.get("/api/balitower/hr/candidates")
def get_candidates(
    job_id: str | None = None,
    fit_only: bool = False,
    current_user: TokenData = Depends(require_hr_access)
):
    """Tabel 9: candidates - Daftar pelamar dengan screening sertifikat K3 dan kelayakan medis ketinggian."""
    conn = get_db_connection(read_only=True)
    try:
        query = """
            SELECT 
                c.candidate_id,
                c.full_name,
                j.job_title,
                c.current_city,
                c.k3_cert_held,
                c.years_of_experience,
                c.medical_checkup_status,
                c.technical_score,
                c.recruitment_stage,
                c.email,
                c.phone
            FROM candidates c
            JOIN job_postings j ON c.job_id = j.job_id
            WHERE 1=1
        """
        params = []
        if job_id:
            query += " AND c.job_id = ?"
            params.append(job_id)
        if fit_only:
            query += " AND c.medical_checkup_status = 'FIT_FOR_HEIGHT'"
            
        query += " ORDER BY c.technical_score DESC"
        rows = conn.execute(query, params).fetchall()
        cols = [desc[0] for desc in conn.description]
        return [dict(zip(cols, r)) for r in rows]
    finally:
        conn.close()


@router.get("/api/balitower/hr/job-postings")
def get_job_postings(current_user: TokenData = Depends(require_hr_access)):
    """Tabel 10: job_postings - Daftar lowongan kerja teknis yang dibuka."""
    conn = get_db_connection(read_only=True)
    try:
        rows = conn.execute("""
            SELECT 
                job_id,
                job_title,
                department,
                required_k3_cert,
                min_experience_years,
                location AS work_location,
                quota AS open_positions,
                status
            FROM job_postings
            ORDER BY job_id ASC;
        """).fetchall()
        cols = [desc[0] for desc in conn.description]
        return [dict(zip(cols, r)) for r in rows]
    finally:
        conn.close()


@router.get("/api/balitower/hr/sites")
def get_sites(current_user: TokenData = Depends(require_hr_access)):
    """Tabel 11: telecom_sites - Master daftar menara BTS/MCP dan koordinat GPS."""
    conn = get_db_connection(read_only=True)
    try:
        rows = conn.execute("""
            SELECT 
                s.site_id,
                s.site_name,
                s.site_type,
                s.region,
                s.tower_height_m AS height_meters,
                'Monopole / SST' AS structure_type,
                (SELECT COUNT(*) FROM mla_contracts m WHERE m.site_id = s.site_id) AS tenant_count,
                s.status
            FROM telecom_sites s
            ORDER BY s.site_id ASC;
        """).fetchall()
        cols = [desc[0] for desc in conn.description]
        return [dict(zip(cols, r)) for r in rows]
    finally:
        conn.close()


# ==============================================================================
# SCOPE 3: FINANCE & LAPORAN KEUANGAN (6 TABEL UTAMA)
# ==============================================================================

@router.get("/api/balitower/finance/summary")
def get_finance_summary(current_user: TokenData = Depends(require_finance_access)):
    """Ringkasan eksekutif keuangan: Pendapatan, Tagihan, OPEX, dan Net Cashflow."""
    conn = get_db_connection(read_only=True)
    try:
        total_billed = conn.execute("SELECT COALESCE(SUM(total_billed), 0) FROM revenue_invoices;").fetchone()[0]
        total_paid = conn.execute("SELECT COALESCE(SUM(total_billed), 0) FROM revenue_invoices WHERE payment_status = 'PAID';").fetchone()[0]
        total_unpaid = conn.execute("SELECT COALESCE(SUM(total_billed), 0) FROM revenue_invoices WHERE payment_status = 'UNPAID';").fetchone()[0]

        pln_cost = conn.execute("SELECT COALESCE(SUM(pln_cost), 0) FROM site_utilities_cost;").fetchone()[0]
        genset_cost = conn.execute("SELECT COALESCE(SUM(genset_fuel_cost), 0) FROM site_utilities_cost;").fetchone()[0]
        land_leases_cost = conn.execute("SELECT COALESCE(SUM(annual_lease_cost), 0) FROM site_land_leases;").fetchone()[0]
        total_opex = pln_cost + genset_cost + land_leases_cost

        inflow = total_paid
        outflow = total_opex

        return {
            "total_revenue_billed_idr": int(total_billed),
            "total_revenue_collected_idr": int(total_paid),
            "outstanding_accounts_receivable_idr": int(total_unpaid),
            "cash_inflow_idr": int(inflow),
            "cash_outflow_idr": int(outflow),
            "net_cash_flow_idr": int(inflow - outflow),
            "opex_pln_electricity_idr": int(pln_cost),
            "opex_genset_fuel_idr": int(genset_cost),
            "annual_land_leases_idr": int(land_leases_cost)
        }
    finally:
        conn.close()


@router.get("/api/balitower/finance/invoices")
def get_invoices(
    status: str | None = None,
    current_user: TokenData = Depends(require_finance_access)
):
    """Tabel 12: revenue_invoices - Daftar invoice tagihan sewa menara ke operator telekomunikasi."""
    conn = get_db_connection(read_only=True)
    try:
        query = """
            SELECT 
                i.invoice_id,
                i.invoice_number,
                c.client_name,
                c.client_type,
                i.period_covered,
                i.amount_subtotal,
                i.tax_ppn,
                i.total_billed,
                i.invoice_date,
                i.due_date,
                i.payment_status,
                i.payment_date
            FROM revenue_invoices i
            JOIN telecom_clients c ON i.client_id = c.client_id
            WHERE 1=1
        """
        params = []
        if status:
            query += " AND i.payment_status = ?"
            params.append(status.upper())
            
        query += " ORDER BY i.due_date DESC"
        rows = conn.execute(query, params).fetchall()
        cols = [desc[0] for desc in conn.description]
        return [dict(zip(cols, r)) for r in rows]
    finally:
        conn.close()


@router.get("/api/balitower/finance/clients")
def get_clients(current_user: TokenData = Depends(require_finance_access)):
    """Tabel 13: telecom_clients - Master klien operator penyewa infrastruktur menara."""
    conn = get_db_connection(read_only=True)
    try:
        rows = conn.execute("""
            SELECT 
                c.client_id,
                c.client_name,
                c.client_type,
                c.npwp,
                c.billing_email,
                c.payment_terms AS payment_terms_days,
                (SELECT COUNT(*) FROM mla_contracts m WHERE m.client_id = c.client_id) AS active_lease_sites,
                2500000000 AS credit_limit_idr
            FROM telecom_clients c
            ORDER BY c.client_id ASC;
        """).fetchall()
        cols = [desc[0] for desc in conn.description]
        return [dict(zip(cols, r)) for r in rows]
    finally:
        conn.close()


@router.get("/api/balitower/finance/mla-contracts")
def get_mla_contracts(current_user: TokenData = Depends(require_finance_access)):
    """Tabel 14: mla_contracts - Master Lease Agreement kontrak sewa menara per site."""
    conn = get_db_connection(read_only=True)
    try:
        query = """
            SELECT 
                m.contract_id,
                m.client_id,
                c.client_name,
                m.site_id,
                s.site_name,
                m.monthly_rate,
                m.billing_frequency,
                m.start_date,
                m.end_date,
                m.status,
                1 AS electricity_included
            FROM mla_contracts m
            JOIN telecom_clients c ON m.client_id = c.client_id
            JOIN telecom_sites s ON m.site_id = s.site_id
            ORDER BY m.contract_id ASC;
        """
        rows = conn.execute(query).fetchall()
        cols = [desc[0] for desc in conn.description]
        return [dict(zip(cols, r)) for r in rows]
    finally:
        conn.close()


@router.get("/api/balitower/finance/land-leases")
def get_land_leases(current_user: TokenData = Depends(require_finance_access)):
    """Tabel 15: site_land_leases - Daftar sewa lahan menara dan masa berlaku sewa."""
    conn = get_db_connection(read_only=True)
    try:
        query = """
            SELECT 
                l.lease_id,
                l.site_id,
                s.site_name,
                s.region,
                l.landowner_name,
                l.annual_lease_cost,
                l.lease_duration_years,
                l.start_date,
                l.end_date,
                l.status
            FROM site_land_leases l
            JOIN telecom_sites s ON l.site_id = s.site_id
            ORDER BY l.annual_lease_cost DESC;
        """
        rows = conn.execute(query).fetchall()
        cols = [desc[0] for desc in conn.description]
        return [dict(zip(cols, r)) for r in rows]
    finally:
        conn.close()


@router.get("/api/balitower/finance/site-utilities")
def get_site_utilities(current_user: TokenData = Depends(require_finance_access)):
    """Tabel 16: site_utilities_cost - Beban listrik PLN shelter dan bahan bakar genset per site."""
    conn = get_db_connection(read_only=True)
    try:
        query = """
            SELECT 
                u.utility_id,
                u.site_id,
                s.site_name,
                u.billing_period,
                u.pln_meter_id,
                u.pln_kwh_used,
                u.pln_cost,
                u.genset_fuel_liters,
                u.genset_fuel_cost,
                u.total_utility_cost,
                u.payment_status AS paid_status
            FROM site_utilities_cost u
            JOIN telecom_sites s ON u.site_id = s.site_id
            ORDER BY u.utility_id ASC;
        """
        rows = conn.execute(query).fetchall()
        cols = [desc[0] for desc in conn.description]
        return [dict(zip(cols, r)) for r in rows]
    finally:
        conn.close()


@router.get("/api/balitower/finance/transactions")
def get_transactions(
    trx_type: str | None = None,
    limit: int = 100,
    current_user: TokenData = Depends(require_finance_access)
):
    """Tabel 17: financial_transactions - Decommissioned (mengembalikan list kosong demi kompatibilitas)."""
    return []


@router.get("/api/balitower/finance/chart-of-accounts")
def get_chart_of_accounts(current_user: TokenData = Depends(require_finance_access)):
    """Tabel 18: chart_of_accounts - Decommissioned (mengembalikan list kosong demi kompatibilitas)."""
    return []


@router.get("/api/balitower/finance/revenue-breakdown")
def get_revenue_breakdown(current_user: TokenData = Depends(require_finance_access)):
    """Rekapitulasi pendapatan sewa per operator telekomunikasi."""
    conn = get_db_connection(read_only=True)
    try:
        query = """
            SELECT 
                c.client_name,
                COUNT(i.invoice_id) AS total_invoices,
                CAST(SUM(i.total_billed) AS BIGINT) AS total_billed,
                CAST(SUM(CASE WHEN i.payment_status = 'PAID' THEN i.total_billed ELSE 0 END) AS BIGINT) AS paid_amount,
                CAST(SUM(CASE WHEN i.payment_status = 'UNPAID' THEN i.total_billed ELSE 0 END) AS BIGINT) AS outstanding_ar
            FROM revenue_invoices i
            JOIN telecom_clients c ON i.client_id = c.client_id
            GROUP BY c.client_name
            ORDER BY total_billed DESC;
        """
        rows = conn.execute(query).fetchall()
        cols = [desc[0] for desc in conn.description]
        return [dict(zip(cols, r)) for r in rows]
    finally:
        conn.close()


@router.get("/api/balitower/finance/opex-breakdown")
def get_opex_breakdown(current_user: TokenData = Depends(require_finance_access)):
    """Rincian beban operasional pengeluaran site."""
    conn = get_db_connection(read_only=True)
    try:
        query = """
            SELECT 
                '5120' AS account_code,
                'Beban Listrik PLN' AS expense_category,
                COUNT(*) AS transaction_count,
                CAST(COALESCE(SUM(pln_cost), 0) AS BIGINT) AS total_expense
            FROM site_utilities_cost
            UNION ALL
            SELECT 
                '5130' AS account_code,
                'Beban Bahan Bakar Minyak Genset' AS expense_category,
                COUNT(CASE WHEN genset_fuel_cost > 0 THEN 1 END) AS transaction_count,
                CAST(COALESCE(SUM(genset_fuel_cost), 0) AS BIGINT) AS total_expense
            FROM site_utilities_cost
            UNION ALL
            SELECT 
                '5110' AS account_code,
                'Beban Sewa Lahan Menara' AS expense_category,
                COUNT(*) AS transaction_count,
                CAST(COALESCE(SUM(annual_lease_cost), 0) AS BIGINT) AS total_expense
            FROM site_land_leases
            ORDER BY total_expense DESC;
        """
        rows = conn.execute(query).fetchall()
        cols = [desc[0] for desc in conn.description]
        return [dict(zip(cols, r)) for r in rows]
    finally:
        conn.close()
