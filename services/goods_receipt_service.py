import re
from datetime import datetime
from pathlib import Path
from typing import Any

from core.security import TokenData
from database.db import get_db_connection


def process_goods_receipt(prompt: str, current_user: TokenData) -> dict | None:
    """
    Menangani pencatatan penerimaan fisik barang pesanan (Purchase Order) saat tiba di gudang regional.
    - Mengidentifikasi nomor PO atau mencari pesanan aktif (ORDERED).
    - Memperbarui status PO menjadi DELIVERED dan actual_delivery = hari ini.
    - Menambahkan kuantitas fisik ke stock_balances di gudang terkait.
    - Mengalkulasi ulang stock_status (CRITICAL / LOW_STOCK -> NORMAL).
    - Menjaga persistensi data ke DuckDB dan CSV.
    """
    lower_prompt = prompt.strip().lower()
    
    # Guard: Do not intercept if prompt is HR personnel / employee or Finance context
    is_hr_context = any(w in lower_prompt for w in [
        "karyawan", "pegawai", "staf", "teknisi", "mutasi", "cuti", "pelamar",
        "kandidat", "absensi", "lembur", "gaji", "rigger", "tkpk"
    ])
    is_fin_context = any(w in lower_prompt for w in [
        "sewa lahan", "biaya sewa", "invoice", "tagihan", "faktur", "beban listrik",
        "kontrak mla", "pendapatan sewa", "billing"
    ])
    if is_hr_context or is_fin_context:
        return None

    # 1. Deteksi kata kunci kedatangan / penerimaan barang fisik di gudang
    receipt_action_keywords = [
        "sudah sampai", "sudah tiba", "telah sampai", "telah tiba", "sudah mendarat",
        "terima barang", "penerimaan barang", "catat penerimaan", "konfirmasi penerimaan",
        "konfirmasi kedatangan", "barang tiba", "barang sampai", "barang masuk",
        "barang datang", "catat barang", "terima po", "po sampai", "po tiba",
        "pesanan sampai", "pesanan tiba"
    ]
    has_explicit_receipt_intent = any(k in lower_prompt for k in receipt_action_keywords)
    
    if not has_explicit_receipt_intent:
        has_arrival_word = any(w in lower_prompt for w in ["sampai", "tiba", "terima", "diterima", "masuk", "mendarat"])
        has_po_or_wh = any(w in lower_prompt for w in ["po-", "po ", "po/", "purchase order", "wh-"])
        has_goods_word = any(w in lower_prompt for w in ["barang", "material", "pesanan", "order", "muatan", "kargo", "kiriman", "item"])
        if has_arrival_word and (has_po_or_wh or (has_goods_word and "gudang" in lower_prompt)):
            has_explicit_receipt_intent = True

    if not has_explicit_receipt_intent:
        return None

    # 2. Strict RBAC / Tenant Authorization Check (Khusus Divisi Inventory atau Super Admin)
    u_tenant = str(getattr(current_user, 'tenant_id', 'ALL')).upper()
    u_role = str(getattr(current_user, 'role', 'USER')).upper()
    username = str(getattr(current_user, 'username', '')).lower()
    is_inv_authorized = (
        u_role in ["ADMIN", "MANAGER"] or 
        u_tenant in ["ALL", "INVENTORY", "TENANT_A"] or 
        username in ["admin", "usera", "user_inventory"]
    )
    if not is_inv_authorized:
        return {
            "parsed_intent": {"workflow_id": "tenant_boundary_restricted"},
            "action_type": "out_of_scope",
            "message": f"Akses Ditolak: Akun Anda ({current_user.username} - Divisi {u_tenant}) tidak memiliki wewenang untuk mencatat penerimaan barang fisik di Gudang Logistik. Akses ini dikhususkan untuk Staf Gudang / Divisi Inventory.",
            "generated_prs": [],
            "affected_items": []
        }

    # 3. Ekstraksi Identifier Purchase Order dari Prompt
    m_po_num = (
        re.search(r'PO/BLT/\d{4}/\d{1,2}/\d{1,4}', prompt, re.IGNORECASE) or
        re.search(r'PO/\w+/\d{4}/\d{1,2}/\d{1,4}', prompt, re.IGNORECASE) or
        re.search(r'\bPO/\S+', prompt, re.IGNORECASE)
    )
    m_po_id = re.search(r'\bPO[-_\s]?(\d{4}[-_\s]?\d{1,4}|\d{1,4})\b', prompt, re.IGNORECASE)

    conn = get_db_connection(read_only=True)
    try:
        po_rows = []
        
        # A. Pencarian berbasis nomor PO resmi (PO/BLT/...)
        if m_po_num:
            po_num_str = m_po_num.group(0).upper().strip().rstrip(".,;:!?")
            po_rows = conn.execute("""
                SELECT po.po_id, po.po_number, po.supplier_id, s.supplier_name, po.item_id, 
                       i.item_name, i.item_code, i.category, i.unit, po.order_quantity, 
                       po.total_amount, po.status, po.actual_delivery, po.warehouse_id, 
                       w.warehouse_name, w.region, w.supervisor, i.min_stock, po.order_date, po.expected_delivery
                FROM purchase_orders po
                JOIN suppliers s ON po.supplier_id = s.supplier_id
                JOIN inventory_items i ON po.item_id = i.item_id
                JOIN warehouses w ON po.warehouse_id = w.warehouse_id
                WHERE UPPER(po.po_number) = ? OR UPPER(po.po_id) = ?;
            """, [po_num_str, po_num_str]).fetchall()
            
            if not po_rows:
                digits = re.findall(r'\d+', po_num_str)
                if digits:
                    padded_digits = digits[-1].zfill(3)
                    canonical_po_id = f"PO-2026-{padded_digits}"
                    po_rows = conn.execute("""
                        SELECT po.po_id, po.po_number, po.supplier_id, s.supplier_name, po.item_id, 
                               i.item_name, i.item_code, i.category, i.unit, po.order_quantity, 
                               po.total_amount, po.status, po.actual_delivery, po.warehouse_id, 
                               w.warehouse_name, w.region, w.supervisor, i.min_stock, po.order_date, po.expected_delivery
                        FROM purchase_orders po
                        JOIN suppliers s ON po.supplier_id = s.supplier_id
                        JOIN inventory_items i ON po.item_id = i.item_id
                        JOIN warehouses w ON po.warehouse_id = w.warehouse_id
                        WHERE UPPER(po.po_id) = ? OR UPPER(po.po_number) LIKE ?;
                    """, [canonical_po_id, f"%{padded_digits}"]).fetchall()
            
        # B. Pencarian berbasis ID PO (PO-2026-006, PO-006, PO-6)
        if not po_rows and m_po_id:
            raw_po_str = m_po_id.group(0).upper().replace(" ", "-").replace("_", "-")
            digits = re.findall(r'\d+', raw_po_str)
            digits_str = digits[-1] if digits else ""
            padded_digits = digits_str.zfill(3)

            canonical_po_id = f"PO-2026-{padded_digits}"
            po_rows = conn.execute("""
                SELECT po.po_id, po.po_number, po.supplier_id, s.supplier_name, po.item_id, 
                       i.item_name, i.item_code, i.category, i.unit, po.order_quantity, 
                       po.total_amount, po.status, po.actual_delivery, po.warehouse_id, 
                       w.warehouse_name, w.region, w.supervisor, i.min_stock, po.order_date, po.expected_delivery
                FROM purchase_orders po
                JOIN suppliers s ON po.supplier_id = s.supplier_id
                JOIN inventory_items i ON po.item_id = i.item_id
                JOIN warehouses w ON po.warehouse_id = w.warehouse_id
                WHERE UPPER(po.po_id) = ? OR UPPER(po.po_id) = ?;
            """, [raw_po_str, canonical_po_id]).fetchall()

            if not po_rows:
                po_rows = conn.execute("""
                    SELECT po.po_id, po.po_number, po.supplier_id, s.supplier_name, po.item_id, 
                           i.item_name, i.item_code, i.category, i.unit, po.order_quantity, 
                           po.total_amount, po.status, po.actual_delivery, po.warehouse_id, 
                           w.warehouse_name, w.region, w.supervisor, i.min_stock, po.order_date, po.expected_delivery
                    FROM purchase_orders po
                    JOIN suppliers s ON po.supplier_id = s.supplier_id
                    JOIN inventory_items i ON po.item_id = i.item_id
                    JOIN warehouses w ON po.warehouse_id = w.warehouse_id
                    WHERE UPPER(po.po_number) LIKE ?;
                """, [f"%{padded_digits}"]).fetchall()

        # C. Jika tidak ada kode PO eksplisit, cari PO yang berstatus ORDERED berdasarkan material / gudang
        if not po_rows:
            in_transit_rows = conn.execute("""
                SELECT po.po_id, po.po_number, po.supplier_id, s.supplier_name, po.item_id, 
                       i.item_name, i.item_code, i.category, i.unit, po.order_quantity, 
                       po.total_amount, po.status, po.actual_delivery, po.warehouse_id, 
                       w.warehouse_name, w.region, w.supervisor, i.min_stock, po.order_date, po.expected_delivery
                FROM purchase_orders po
                JOIN suppliers s ON po.supplier_id = s.supplier_id
                JOIN inventory_items i ON po.item_id = i.item_id
                JOIN warehouses w ON po.warehouse_id = w.warehouse_id
                WHERE po.status = 'ORDERED';
            """, [po_num_str, po_num_str]).fetchall() if m_po_num else conn.execute("""
                SELECT po.po_id, po.po_number, po.supplier_id, s.supplier_name, po.item_id, 
                       i.item_name, i.item_code, i.category, i.unit, po.order_quantity, 
                       po.total_amount, po.status, po.actual_delivery, po.warehouse_id, 
                       w.warehouse_name, w.region, w.supervisor, i.min_stock, po.order_date, po.expected_delivery
                FROM purchase_orders po
                JOIN suppliers s ON po.supplier_id = s.supplier_id
                JOIN inventory_items i ON po.item_id = i.item_id
                JOIN warehouses w ON po.warehouse_id = w.warehouse_id
                WHERE po.status = 'ORDERED';
            """).fetchall()
            
            matched_pos = []
            for r in in_transit_rows:
                r_region = str(r[15]).lower()
                r_wh = str(r[14]).lower()
                r_item = str(r[5]).lower()
                r_sku = str(r[6]).lower()
                if (r_region in lower_prompt or r_wh in lower_prompt) and (any(part in lower_prompt for part in r_item.split()[:2]) or r_sku in lower_prompt):
                    matched_pos.append(r)
                elif r_item in lower_prompt or (len(r_item.split()) > 1 and " ".join(r_item.split()[:2]) in lower_prompt):
                    matched_pos.append(r)

            if len(matched_pos) > 0:
                target_p_id = matched_pos[0][0]
                if all(m[0] == target_p_id for m in matched_pos):
                    po_rows = [r for r in in_transit_rows if r[0] == target_p_id]
                else:
                    candidates = matched_pos
                    msg = "**Sistem Mendeteksi Purchase Order Aktif (`ORDERED`)**\n\n"
                    msg += "Mohon sebutkan nomor PO spesifik yang telah sampai di gudang fisik:\n\n"
                    msg += "| No. PO | Kode Referensi | Material | Volume | Gudang Tujuan | Estimasi Tiba |\n"
                    msg += "| :--- | :--- | :--- | :---: | :--- | :---: |\n"
                    for c in candidates[:6]:
                        msg += f"| **{c[0]}** | `{c[1]}` | {c[5]} | {c[9]:,} {c[8]} | {c[14]} ({c[15]}) | {c[19] or '-'} |\n"
                    msg += "\n*Contoh instruksi:* `Barang untuk PO-2026-038 sudah sampai di gudang, tolong catat penerimaannya.`"
                    return {
                        "parsed_intent": {"workflow_id": "goods_receipt_clarification"},
                        "action_type": "goods_receipt",
                        "message": msg,
                        "generated_prs": [],
                        "affected_items": []
                    }
            elif len(in_transit_rows) > 0:
                candidates = in_transit_rows
                msg = "**Sistem Mendeteksi Purchase Order Aktif (`ORDERED`)**\n\n"
                msg += "Mohon sebutkan nomor PO spesifik yang telah sampai di gudang fisik:\n\n"
                msg += "| No. PO | Kode Referensi | Material | Volume | Gudang Tujuan | Estimasi Tiba |\n"
                msg += "| :--- | :--- | :--- | :---: | :--- | :---: |\n"
                for c in candidates[:6]:
                    msg += f"| **{c[0]}** | `{c[1]}` | {c[5]} | {c[9]:,} {c[8]} | {c[14]} ({c[15]}) | {c[19] or '-'} |\n"
                msg += "\n*Contoh instruksi:* `Barang untuk PO-2026-038 sudah sampai di gudang, tolong catat penerimaannya.`"
                return {
                    "parsed_intent": {"workflow_id": "goods_receipt_clarification"},
                    "action_type": "goods_receipt",
                    "message": msg,
                    "generated_prs": [],
                    "affected_items": []
                }
    finally:
        conn.close()

    if not po_rows:
        return {
            "parsed_intent": {"workflow_id": "goods_receipt_not_found"},
            "action_type": "goods_receipt",
            "message": "Nomor Purchase Order (PO) yang Anda sebutkan tidak ditemukan dalam basis data logistik. Pastikan nomor PO benar (contoh: `PO-2026-006` atau `PO-2026-038`).",
            "generated_prs": [],
            "affected_items": []
        }

    canonical_po_id = po_rows[0][0]
    canonical_po_number = po_rows[0][1]
    supplier_name = po_rows[0][3]
    display_po = canonical_po_number or canonical_po_id
    ref_text = f" (Ref: `{canonical_po_id}`)" if canonical_po_number and canonical_po_number != canonical_po_id else ""

    # 4. Validasi jika seluruh item dalam PO sudah pernah berstatus DELIVERED
    all_delivered = all(r[11] == 'DELIVERED' for r in po_rows)
    if all_delivered:
        msg = f"**Informasi Penerimaan: Barang Sudah Pernah Diterima**\n\n"
        msg += f"Seluruh pesanan dalam **{display_po}**{ref_text} telah tercatat **DELIVERED** sebelumnya pada tanggal **{po_rows[0][12] or '2026-01-22'}**.\n\n"
        msg += f"- **Status Fisik**: Seluruh kuantitas barang telah masuk ke saldo gudang dan tidak dilakukan penambahan ganda demi integritas data persediaan."
        return {
            "parsed_intent": {"workflow_id": "goods_receipt_already_delivered", "po_id": canonical_po_id, "po_number": canonical_po_number},
            "action_type": "goods_receipt",
            "message": msg,
            "po_id": canonical_po_id,
            "po_number": canonical_po_number,
            "generated_prs": [],
            "affected_items": []
        }

    # 5. Analisis Multi-Warehouse & Deteksi Gudang Spesifik dari Prompt Pengguna
    warehouses_map = {}
    for r in po_rows:
        wh_id = r[13]
        if wh_id not in warehouses_map:
            warehouses_map[wh_id] = {
                "warehouse_id": wh_id,
                "warehouse_name": r[14],
                "region": r[15],
                "supervisor": r[16],
                "items": [],
                "delivered_items": [],
                "ordered_items": []
            }
        warehouses_map[wh_id]["items"].append(r)
        if r[11] == 'DELIVERED':
            warehouses_map[wh_id]["delivered_items"].append(r)
        else:
            warehouses_map[wh_id]["ordered_items"].append(r)

    is_multi_warehouse = len(warehouses_map) > 1

    all_keywords = ["semua gudang", "seluruh gudang", "semua barang", "seluruhnya", "semua item", "terima semua", "semua"]
    wants_all = any(k in lower_prompt for k in all_keywords)

    matched_wh_ids = []
    for wh_id, wh_info in warehouses_map.items():
        w_id_lower = wh_id.lower()
        w_name_lower = wh_info["warehouse_name"].lower()
        w_region_lower = wh_info["region"].lower()

        aliases = [w_id_lower, w_id_lower.replace("-", "")]
        parts = w_id_lower.split("-")
        if len(parts) >= 2:
            aliases.append(parts[1])
            aliases.append(f"wh-{parts[1]}")

        for token in w_name_lower.split():
            if token not in ["gudang", "regional", "hub", "utama", "pusat"]:
                aliases.append(token)
        if "jakarta barat" in w_name_lower:
            aliases.extend(["jakarta barat", "jakbar"])
        elif "jakarta" in w_name_lower:
            aliases.append("jakarta")

        for r_tok in w_region_lower.split():
            if len(r_tok) > 4 and r_tok not in ["jawa", "barat", "timur", "tengah", "utara", "selatan"]:
                aliases.append(r_tok)

        for al in aliases:
            if re.search(r'\b' + re.escape(al) + r'\b', lower_prompt):
                matched_wh_ids.append(wh_id)
                break

    # =========================================================================
    # KASUS A: PO Multi-Gudang & User Belum Menyebutkan Gudang Tertentu & Tidak 'Semua'
    # =========================================================================
    if is_multi_warehouse and not matched_wh_ids and not wants_all:
        msg = f"**Informasi Purchase Order Multi-Gudang Terdeteksi**\n\n"
        msg += f"Purchase Order **{display_po}**{ref_text} mencakup alokasi pengiriman barang ke **{len(warehouses_map)} gudang regional yang berbeda**.\n\n"
        msg += "### Sebaran Alokasi Gudang Tujuan:\n\n"
        msg += "| No | Gudang Tujuan | Kode Gudang | Jumlah Item | Contoh Material | PIC Gudang |\n"
        msg += "| :-: | :--- | :---: | :---: | :--- | :--- |\n"
        
        wh_summary_list = []
        for idx, (wh_id, wh_data) in enumerate(warehouses_map.items(), 1):
            wh_items = wh_data["items"]
            item_count = len(wh_items)
            sample_materials = ", ".join(list(dict.fromkeys(r[5] for r in wh_items))[:2])
            wh_name = wh_data["warehouse_name"]
            pic = wh_data["supervisor"] or "PIC Gudang"
            
            pending_count = len(wh_data["ordered_items"])
            deliv_count = len(wh_data["delivered_items"])
            status_badge = ""
            if deliv_count > 0 and pending_count == 0:
                status_badge = " *(Sudah Diterima)*"
            elif deliv_count > 0:
                status_badge = f" *({pending_count} pending)*"
            
            msg += f"| {idx} | **{wh_name}**{status_badge} | `{wh_id}` | {item_count} item | {sample_materials} | {pic} |\n"
            wh_summary_list.append({
                "warehouse_id": wh_id,
                "warehouse_name": wh_name,
                "region": wh_data["region"],
                "supervisor": pic,
                "item_count": item_count,
                "pending_count": pending_count,
                "delivered_count": deliv_count,
                "sample_materials": sample_materials
            })

        sample_wh_name = list(warehouses_map.values())[0]["warehouse_name"]
        city_hint = (
            sample_wh_name
            .replace("Regional Logistics Hub ", "")
            .replace("Gudang Regional ", "")
            .replace("Gudang Hub ", "")
            .replace("Gudang Utama ", "")
            .strip()
        )

        msg += "\n---\n"
        msg += "### Opsi Instruksi Pencatatan Penerimaan:\n"
        msg += "Silakan tentukan apakah penerimaan barang dilakukan secara **parsial per gudang** atau **seluruhnya sekaligus**:\n\n"
        msg += f"1. **Penerimaan per Gudang (Parsial)**:\n"
        msg += f"   Sebutkan nama gudang tujuan fisik yang telah menerima barang.\n"
        msg += f"   - *Contoh:* `Catat penerimaan {display_po} untuk Gudang {city_hint}`\n"
        msg += f"2. **Penerimaan Seluruhnya (All Warehouses)**:\n"
        msg += f"   Catat kedatangan seluruh material di semua lokasi gudang sekaligus.\n"
        msg += f"   - *Contoh:* `Catat penerimaan {display_po} untuk semua gudang`\n"

        return {
            "parsed_intent": {
                "workflow_id": "goods_receipt_multi_warehouse_clarification",
                "po_id": canonical_po_id,
                "po_number": canonical_po_number,
                "is_multi_warehouse": True,
                "warehouses": wh_summary_list
            },
            "action_type": "goods_receipt",
            "workflow_id": "goods_receipt_multi_warehouse_clarification",
            "message": msg,
            "po_id": canonical_po_id,
            "po_number": canonical_po_number,
            "is_multi_warehouse": True,
            "warehouses": wh_summary_list,
            "generated_prs": [],
            "affected_items": []
        }

    # =========================================================================
    # Tentukan Item yang Akan Diproses (KASUS B: Parsial vs KASUS C: Seluruhnya)
    # =========================================================================
    is_partial_mode = is_multi_warehouse and bool(matched_wh_ids) and not wants_all and (len(matched_wh_ids) < len(warehouses_map))
    
    if is_partial_mode:
        items_to_process = [r for r in po_rows if r[13] in matched_wh_ids and r[11] != 'DELIVERED']
        target_wh_names = [warehouses_map[wid]["warehouse_name"] for wid in matched_wh_ids if wid in warehouses_map]
        target_wh_str = ", ".join(target_wh_names) if target_wh_names else "Gudang Pilihan"

        # Jika seluruh item pada gudang tersebut sudah pernah diterima sebelumnya
        if not items_to_process:
            remaining_pending = [r for r in po_rows if r[11] != 'DELIVERED']
            msg = f"**Informasi Penerimaan: Barang di {target_wh_str} Sudah Diterima Sebelumnya**\n\n"
            msg += f"Seluruh material pesanan **{display_po}**{ref_text} untuk **{target_wh_str}** telah tercatat berstatus **DELIVERED** sebelumnya.\n\n"
            if remaining_pending:
                msg += "### Sisa Item Menunggu Kedatangan di Gudang Lain:\n\n"
                msg += "| No | Gudang Tujuan | Kode Gudang | Material | Volume | Estimasi Kedatangan |\n"
                msg += "| :-: | :--- | :---: | :--- | :---: | :---: |\n"
                for s_idx, r_rem in enumerate(remaining_pending, 1):
                    msg += f"| {s_idx} | {r_rem[14]} | `{r_rem[13]}` | **{r_rem[5]}** | {r_rem[9]:,} {r_rem[8]} | {r_rem[19] or '-'} |\n"
            return {
                "parsed_intent": {"workflow_id": "goods_receipt_already_delivered", "po_id": canonical_po_id, "po_number": canonical_po_number},
                "action_type": "goods_receipt",
                "message": msg,
                "po_id": canonical_po_id,
                "po_number": canonical_po_number,
                "generated_prs": [],
                "affected_items": []
            }
    else:
        # KASUS C: Single Warehouse atau User Memilih Terima Semua Gudang
        items_to_process = [r for r in po_rows if r[11] != 'DELIVERED']
        target_wh_str = "Seluruh Gudang Regional" if is_multi_warehouse else (po_rows[0][14] if po_rows else "Gudang Regional")

    # 6. Eksekusi Pembaruan Basis Data (Koneksi Tulis DuckDB)
    today_str = datetime.now().strftime("%Y-%m-%d")
    now_ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    w_conn = get_db_connection(read_only=False)
    processed_items = []
    affected_items = []

    try:
        # A. Update status DELIVERED untuk item yang diproses
        for r in items_to_process:
            itm_wh_id = r[13]
            itm_id = r[4]
            w_conn.execute("""
                UPDATE purchase_orders 
                SET status = 'DELIVERED', actual_delivery = ?
                WHERE (po_id = ? OR po_number = ?) AND warehouse_id = ? AND item_id = ?;
            """, [today_str, canonical_po_id, canonical_po_number, itm_wh_id, itm_id])

        # B. Update kuantitas fisik di stock_balances untuk setiap item yang diproses
        for r in items_to_process:
            (row_po_id, row_po_num, sup_id, sup_n, itm_id, 
             itm_name, itm_code, itm_cat, itm_unit, itm_qty, 
             itm_amount, itm_status, itm_actual_deliv, itm_wh_id, 
             itm_wh_name, itm_region, itm_supervisor, itm_min_stock, itm_order_date, itm_exp_deliv) = r

            sb_row = w_conn.execute("""
                SELECT balance_id, quantity_on_hand, quantity_reserved, reorder_point, stock_status
                FROM stock_balances
                WHERE warehouse_id = ? AND item_id = ?;
            """, [itm_wh_id, itm_id]).fetchone()

            if sb_row:
                bal_id, old_qty, res_qty, rop, old_status = sb_row
                new_qty = old_qty + itm_qty
                if new_qty <= rop * 0.5:
                    new_status = 'CRITICAL'
                elif new_qty <= rop:
                    new_status = 'LOW_STOCK'
                else:
                    new_status = 'NORMAL'

                w_conn.execute("""
                    UPDATE stock_balances
                    SET quantity_on_hand = ?, stock_status = ?, last_updated = ?
                    WHERE balance_id = ?;
                """, [new_qty, new_status, now_ts, bal_id])
            else:
                bal_id = f"STK-{itm_wh_id}-{itm_id}"
                old_qty = 0
                old_status = "TIDAK ADA"
                new_qty = itm_qty
                rop = itm_min_stock or 50
                new_status = 'NORMAL' if new_qty > rop else ('LOW_STOCK' if new_qty > rop * 0.5 else 'CRITICAL')
                w_conn.execute("""
                    INSERT INTO stock_balances VALUES (?, ?, ?, ?, 0, ?, ?, ?);
                """, [bal_id, itm_id, itm_wh_id, new_qty, rop, new_status, now_ts])

            # C. Sinkronisasi tabel kompatibilitas 'items'
            w_conn.execute("""
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
            """, [itm_id])

            processed_items.append({
                "name": itm_name,
                "code": itm_code,
                "category": itm_cat,
                "quantity": itm_qty,
                "unit": itm_unit,
                "warehouse_name": itm_wh_name,
                "warehouse_id": itm_wh_id,
                "region": itm_region,
                "old_qty": old_qty,
                "new_qty": new_qty,
                "old_status": old_status,
                "new_status": new_status,
                "min_stock": rop
            })
            affected_items.append({
                "name": itm_name,
                "current_stock": new_qty,
                "min_stock": rop,
                "unit": itm_unit
            })

        # D. Ekspor balik ke berkas CSV agar tersimpan permanen
        try:
            inv_csv_dir = Path(__file__).resolve().parent.parent / "data" / "balitower" / "01_inventory"
            if inv_csv_dir.exists():
                df_pos = w_conn.execute("SELECT * FROM purchase_orders").df()
                df_pos.to_csv(inv_csv_dir / "purchase_orders.csv", index=False)
                df_stk = w_conn.execute("SELECT * FROM stock_balances").df()
                df_stk.to_csv(inv_csv_dir / "stock_balances.csv", index=False)
        except Exception:
            pass

        w_conn.commit()
    finally:
        w_conn.close()

    # 7. Identifikasi Sisa Item di Gudang Lain (Untuk Pelaporan Parsial)
    processed_keys = {(p["warehouse_id"], p["code"]) for p in processed_items}
    remaining_items = [
        r for r in po_rows 
        if (r[13], r[6]) not in processed_keys and r[11] != 'DELIVERED'
    ]

    # 8. Format Respon Konfirmasi Korporat Bali Tower
    if is_partial_mode:
        msg = f"**Konfirmasi Penerimaan Parsial Berhasil Dibukukan**\n\n"
        msg += f"Penerimaan material pesanan **{display_po}**{ref_text} khusus untuk **{target_wh_str}** telah diverifikasi tiba dan berhasil dicatatkan ke dalam basis data persediaan PT Bali Towerindo Sentra Tbk.\n\n"
        msg += f"- **No. Purchase Order**: `{display_po}`{ref_text}\n"
        msg += f"- **Supplier / Rekanan**: {supplier_name}\n"
        msg += f"- **Gudang Diterima**: {target_wh_str}\n"
        msg += f"- **Tanggal Penerimaan**: {today_str} (Tercatat Hari Ini)\n"
        msg += f"- **Total Material Diterima di {target_wh_str}**: **{len(processed_items)} jenis barang**\n\n"
        
        msg += "| No | Nama Material & Kode | Volume Diterima | Gudang Tujuan | Saldo Fisik Gudang | Status Kesehatan |\n"
        msg += "| :-: | :--- | :---: | :--- | :---: | :---: |\n"
        for idx, p in enumerate(processed_items, 1):
            msg += f"| {idx} | **{p['name']}**<br>`{p['code']}` | **{p['quantity']:,} {p['unit']}** | {p['warehouse_name']} ({p['region']}) | {p['old_qty']:,} ➔ **{p['new_qty']:,} {p['unit']}** | `{p['old_status']}` ➔ **`{p['new_status']}`** |\n"
        
        if remaining_items:
            msg += f"\n### Sisa Material Menunggu Kedatangan di Gudang Lain:\n"
            msg += f"Berikut adalah daftar pesanan dalam PO ini yang dialokasikan ke gudang regional lainnya dan masih menunggu pengiriman fisik:\n\n"
            msg += "| No | Gudang Tujuan | Kode Gudang | Nama Material & Kode | Volume Pesanan | Status |\n"
            msg += "| :-: | :--- | :---: | :--- | :---: | :---: |\n"
            for r_idx, rem in enumerate(remaining_items, 1):
                msg += f"| {r_idx} | {rem[14]} ({rem[15]}) | `{rem[13]}` | **{rem[5]}** (`{rem[6]}`) | {rem[9]:,} {rem[8]} | `{rem[11]}` |\n"
            msg += f"\n*Untuk mencatat penerimaan gudang berikutnya, sebutkan nama gudang terkait atau ketik: `Catat penerimaan {display_po} untuk semua gudang`.*"
        else:
            msg += f"\n*Seluruh item dalam PO ini pada semua gudang telah selesai diterima (`DELIVERED`).*"
    else:
        msg = f"**Konfirmasi Penerimaan Barang Fisik Berhasil Dibukukan**\n\n"
        msg += f"Penerimaan material pesanan **{display_po}**{ref_text} telah diverifikasi tiba di gudang fisik dan berhasil dicatatkan ke dalam basis data inventaris PT Bali Towerindo Sentra Tbk.\n\n"
        msg += f"- **No. Purchase Order**: `{display_po}`{ref_text}\n"
        msg += f"- **Supplier / Rekanan**: {supplier_name}\n"
        msg += f"- **Tanggal Penerimaan**: {today_str} (Tercatat Hari Ini)\n"
        msg += f"- **Status Pesanan**: Diperbarui menjadi **`DELIVERED`**\n"
        msg += f"- **Total Material Diterima**: **{len(processed_items)} jenis barang**\n\n"
        msg += "| No | Nama Material & Kode | Volume Diterima | Gudang Tujuan | Saldo Fisik Gudang | Status Kesehatan |\n"
        msg += "| :-: | :--- | :---: | :--- | :---: | :---: |\n"
        for idx, p in enumerate(processed_items, 1):
            msg += f"| {idx} | **{p['name']}**<br>`{p['code']}` | **{p['quantity']:,} {p['unit']}** | {p['warehouse_name']} ({p['region']}) | {p['old_qty']:,} ➔ **{p['new_qty']:,} {p['unit']}** | `{p['old_status']}` ➔ **`{p['new_status']}`** |\n"
        msg += f"\n*Saldo fisik di seluruh gudang regional terkait telah bertambah dan status kesehatan persediaan telah dipulihkan secara otomatis di DuckDB Enterprise.*"

    # Pre-generate official Typst PO PDF document for immediate preview / download
    try:
        from docgen.compiler import generate_po_pdf
        generate_po_pdf(canonical_po_id)
    except Exception as err:
        print(f"[Goods Receipt] PO PDF pre-generation note: {err}")

    first_item = processed_items[0] if processed_items else {}
    return {
        "parsed_intent": {
            "workflow_id": "goods_receipt",
            "po_id": canonical_po_id,
            "po_number": canonical_po_number,
            "is_partial": is_partial_mode,
            "warehouse_id": matched_wh_ids[0] if (is_partial_mode and len(matched_wh_ids) == 1) else None,
            "warehouse_name": target_wh_str,
            "total_items": len(processed_items),
            "remaining_items_count": len(remaining_items)
        },
        "action_type": "goods_receipt",
        "message": msg,
        "po_id": canonical_po_id,
        "po_number": canonical_po_number,
        "po_status": "PARTIAL_DELIVERED" if (is_partial_mode and remaining_items) else "DELIVERED",
        "status": "DELIVERED",
        "is_partial": is_partial_mode,
        "quantity_received": first_item.get("quantity", 0),
        "stock_before": first_item.get("old_qty", 0),
        "stock_after": first_item.get("new_qty", 0),
        "total_items_received": len(processed_items),
        "pdf_download_url": f"/api/documents/po/{canonical_po_id}/download",
        "generated_prs": [],
        "affected_items": affected_items,
        "email_sent": False,
        "total_items_analyzed": len(processed_items),
        "target_destinations": ["database", "pdf"]
    }
