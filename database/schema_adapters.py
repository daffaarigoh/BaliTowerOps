from typing import Any
from database.db import get_db_connection


class TenantSchemaAdapter:
    """
    Adapter Layer that dynamically abstracts and translates 3 heterogeneous database schemas
    (Manufacturing Electronics, Pharma WMS, Fleet Parts) into a Canonical Procurement Entity.
    """

    @classmethod
    def get_low_stock_items(cls, tenant_id: str = "ALL") -> list[dict[str, Any]]:
        """Retrieve items whose physical stock has fallen below threshold for a given tenant."""
        conn = get_db_connection(read_only=True)
        try:
            existing_tables = set(r[0] for r in conn.execute("SHOW TABLES;").fetchall())
            t_clean = (tenant_id or "ALL").upper()
            if t_clean in ["HR", "TENANT_B", "USERB", "FINANCE", "TENANT_C", "USERC"]:
                return []

            if "stock_balances" in existing_tables and "warehouses" in existing_tables and "inventory_items" in existing_tables:
                rows = conn.execute("""
                    SELECT 
                        sb.balance_id,
                        sb.item_id,
                        i.item_code,
                        i.item_name,
                        w.warehouse_id,
                        w.warehouse_name,
                        i.category,
                        sb.quantity_on_hand,
                        sb.reorder_point,
                        sb.reorder_point * 3 AS max_thresh,
                        i.lead_time_days,
                        i.unit,
                        COALESCE(i.unit_price, 10000.0) AS unit_price,
                        COALESCE(s.supplier_id, 'SUP-001') AS supplier_id,
                        COALESCE(s.supplier_name, 'PT Bali Vendor Utama') AS supplier_name
                    FROM stock_balances sb
                    JOIN inventory_items i ON sb.item_id = i.item_id
                    JOIN warehouses w ON sb.warehouse_id = w.warehouse_id
                    LEFT JOIN suppliers s ON i.supplier_id = s.supplier_id
                    WHERE sb.quantity_on_hand <= sb.reorder_point 
                       OR sb.stock_status IN ('CRITICAL', 'LOW_STOCK', 'OUT_OF_STOCK')
                    ORDER BY 
                        CASE WHEN sb.stock_status = 'OUT_OF_STOCK' THEN 1
                             WHEN sb.stock_status = 'CRITICAL' THEN 2
                             WHEN sb.stock_status = 'LOW_STOCK' THEN 3
                             ELSE 4 END ASC,
                        (sb.reorder_point - sb.quantity_on_hand) DESC,
                        sb.balance_id ASC;
                """).fetchall()
                results = []
                for r in rows:
                    bal_id, item_id, item_code, name, wh_id, wh_name, cat, stock, min_thresh, max_thresh, lt_days, unit, price, sup_id, sup_name = r
                    stock_val = int(stock)
                    min_val = int(min_thresh)
                    reorder_qty = max(min_val * 2 - stock_val, 1)
                    results.append({
                        "balance_id": bal_id,
                        "item_id": item_id,
                        "item_code": item_code,
                        "name": f"{name} ({wh_name})",
                        "base_name": name,
                        "warehouse_id": wh_id,
                        "warehouse_name": wh_name,
                        "category": cat,
                        "current_stock": stock_val,
                        "min_threshold": min_val,
                        "max_threshold": int(max_thresh),
                        "avg_daily_usage": 5.0,
                        "lead_time_days": int(lt_days),
                        "unit": unit,
                        "unit_price": float(price),
                        "safety_stock": min_val,
                        "reorder_qty": int(reorder_qty),
                        "vendor_id": sup_id,
                        "vendor_name": sup_name,
                        "tenant_id": "usera",
                        "raw_source_table": "stock_balances"
                    })
                return results

            if "inventory_items" in existing_tables:
                rows = conn.execute("""
                    SELECT 
                        i.item_id,
                        i.item_name,
                        i.category,
                        COALESCE(SUM(sb.quantity_on_hand), 0) AS total_stock,
                        i.lead_time_days,
                        i.unit,
                        i.unit_price,
                        COALESCE(s.supplier_id, 'SUP-001') AS supplier_id,
                        COALESCE(s.supplier_name, 'PT Bali Vendor Utama') AS supplier_name,
                        CASE WHEN COUNT(sb.warehouse_id) > 0 THEN CAST(SUM(sb.reorder_point) AS BIGINT) ELSE i.min_stock END AS min_thresh,
                        CASE WHEN COUNT(sb.warehouse_id) > 0 THEN CAST(SUM(sb.reorder_point * 3) AS BIGINT) ELSE i.min_stock * 3 END AS max_thresh
                    FROM inventory_items i
                    LEFT JOIN stock_balances sb ON i.item_id = sb.item_id AND (sb.stock_status IN ('CRITICAL', 'LOW_STOCK') OR sb.quantity_on_hand <= sb.reorder_point)
                    LEFT JOIN suppliers s ON i.supplier_id = s.supplier_id
                    GROUP BY i.item_id, i.item_name, i.category, i.min_stock, i.lead_time_days, i.unit, i.unit_price, s.supplier_id, s.supplier_name
                    HAVING COUNT(sb.warehouse_id) > 0
                    ORDER BY (SUM(sb.reorder_point) - SUM(sb.quantity_on_hand)) DESC;
                """).fetchall()
                results = []
                for r in rows:
                    item_id, name, cat, stock, lt_days, unit, price, sup_id, sup_name, min_thresh, max_thresh = r
                    stock_val = int(stock)
                    min_val = int(min_thresh)
                    reorder_qty = max(min_val * 2 - stock_val, 1)
                    results.append({
                        "item_id": item_id,
                        "name": name,
                        "category": cat,
                        "current_stock": stock_val,
                        "min_threshold": min_val,
                        "max_threshold": int(max_thresh),
                        "avg_daily_usage": 5.0,
                        "lead_time_days": int(lt_days),
                        "unit": unit,
                        "unit_price": float(price),
                        "safety_stock": min_val,
                        "reorder_qty": int(reorder_qty),
                        "vendor_id": sup_id,
                        "vendor_name": sup_name,
                        "tenant_id": "usera",
                        "raw_source_table": "inventory_items"
                    })
                return results

            results = []

            # Dynamic low-stock items from table 'items'
            low_custom_rows = conn.execute("""
                SELECT i.item_id, i.name, i.category, i.current_stock, i.min_threshold, i.max_threshold,
                       i.avg_daily_usage, i.lead_time_days, i.unit, i.tenant_id,
                       COALESCE(v.unit_price, 0.0) as unit_price
                FROM items i
                LEFT JOIN (
                    SELECT item_id, MIN(unit_price) as unit_price 
                    FROM vendors 
                    GROUP BY item_id
                ) v ON i.item_id = v.item_id
                WHERE (i.tenant_id = ? OR ? = 'ALL') 
                  AND i.current_stock <= i.min_threshold
                  AND (i.item_id NOT LIKE 'ITM-0%' OR v.unit_price > 0)
                ORDER BY (i.min_threshold - i.current_stock) DESC;
            """, [tenant_id, tenant_id]).fetchall()
            existing_low_ids = {it["item_id"] for it in results}
            for r in low_custom_rows:
                if r[0] not in existing_low_ids:
                    stock_val = int(r[3])
                    min_val = int(r[4])
                    reorder_qty = max(min_val * 2 - stock_val, 1)
                    results.append({
                        "item_id": r[0],
                        "name": r[1],
                        "category": r[2],
                        "current_stock": stock_val,
                        "min_threshold": min_val,
                        "max_threshold": int(r[5]) if r[5] else min_val * 3,
                        "avg_daily_usage": float(r[6]) if r[6] else 1.0,
                        "lead_time_days": int(r[7]) if r[7] else 3,
                        "unit": r[8] or "pcs",
                        "unit_price": float(r[10]) if r[10] else 0.0,
                        "safety_stock": min_val,
                        "reorder_qty": reorder_qty,
                        "tenant_id": r[9],
                        "raw_source_table": "items"
                    })

            return results
        finally:
            conn.close()

    @classmethod
    def get_all_inventory_items(cls, tenant_id: str = "ALL") -> list[dict[str, Any]]:
        """Retrieve all items across the active tenant's real table."""
        conn = get_db_connection(read_only=True)
        try:
            existing_tables = set(r[0] for r in conn.execute("SHOW TABLES;").fetchall())
            if "inventory_items" in existing_tables:
                t_clean = (tenant_id or "ALL").upper()
                if t_clean in ["HR", "TENANT_B", "USERB", "FINANCE", "TENANT_C", "USERC"]:
                    return []
                rows = conn.execute("""
                    SELECT 
                        i.item_id,
                        i.item_name,
                        i.category,
                        COALESCE(SUM(sb.quantity_on_hand), i.min_stock * 2) AS stock,
                        CASE WHEN COUNT(sb.warehouse_id) > 0 THEN CAST(SUM(sb.reorder_point) AS BIGINT) ELSE i.min_stock END AS min_thresh,
                        CASE WHEN COUNT(sb.warehouse_id) > 0 THEN CAST(SUM(sb.reorder_point * 3) AS BIGINT) ELSE i.min_stock * 3 END AS max_thresh,
                        i.lead_time_days,
                        i.unit,
                        i.unit_price,
                        s.supplier_name
                    FROM inventory_items i
                    LEFT JOIN stock_balances sb ON i.item_id = sb.item_id
                    LEFT JOIN suppliers s ON i.supplier_id = s.supplier_id
                    GROUP BY i.item_id, i.item_name, i.category, i.min_stock, i.lead_time_days, i.unit, i.unit_price, s.supplier_name
                    ORDER BY i.item_id ASC;
                """).fetchall()
                items = []
                for r in rows:
                    item_id, name, cat, stock, min_thresh, max_thresh, lt_days, unit, price, supp_name = r
                    items.append({
                        "item_id": item_id,
                        "name": name,
                        "category": cat,
                        "current_stock": int(stock),
                        "min_threshold": int(min_thresh),
                        "max_threshold": int(max_thresh),
                        "avg_daily_usage": 5.0,
                        "lead_time_days": int(lt_days),
                        "unit": unit,
                        "unit_price": float(price),
                        "supplier_name": supp_name or "-",
                        "tenant_id": "usera"
                    })
                return items

            items = []

            # Include dynamically registered items from table 'items'
            custom_rows = conn.execute("""
                SELECT i.item_id, i.name, i.category, i.current_stock, i.min_threshold, i.max_threshold,
                       i.avg_daily_usage, i.lead_time_days, i.unit, i.tenant_id,
                       COALESCE(v.unit_price, 0.0) as unit_price
                FROM items i
                LEFT JOIN (
                    SELECT item_id, MIN(unit_price) as unit_price 
                    FROM vendors 
                    GROUP BY item_id
                ) v ON i.item_id = v.item_id
                WHERE (i.tenant_id = ? OR ? = 'ALL')
                  AND (i.item_id NOT LIKE 'ITM-0%' OR v.unit_price > 0)
                ORDER BY i.item_id ASC;
            """, [tenant_id, tenant_id]).fetchall()
            existing_ids = {it["item_id"] for it in items}
            for r in custom_rows:
                if r[0] not in existing_ids:
                    items.append({
                        "item_id": r[0],
                        "name": r[1],
                        "category": r[2],
                        "current_stock": int(r[3]),
                        "min_threshold": int(r[4]),
                        "max_threshold": int(r[5]) if r[5] else int(r[4]) * 3,
                        "avg_daily_usage": float(r[6]) if r[6] else 1.0,
                        "lead_time_days": int(r[7]) if r[7] else 3,
                        "unit": r[8] or "pcs",
                        "unit_price": float(r[10]) if r[10] else 0.0,
                        "tenant_id": r[9]
                    })

            return items
        finally:
            conn.close()

    @classmethod
    def get_specific_item_stock(cls, item_name: str, tenant_id: str = "ALL") -> list[dict[str, Any]]:
        """Search and retrieve items matching item_name in the tenant's real table."""
        all_items = cls.get_all_inventory_items(tenant_id)
        query_lower = item_name.strip().lower()
        return [it for it in all_items if query_lower in it["name"].lower() or query_lower in it["item_id"].lower()]

    @classmethod
    def update_item_stock(cls, item_id: str, qty_to_add: int, item_name: str | None = None, tenant_id: str = "ALL") -> bool:
        """
        Increments physical inventory stock in the tenant's real heterogeneous table,
        with fallback to legacy items table.
        """
        conn = get_db_connection()
        updated = False
        try:
            name_param = (item_name or item_id).strip().lower()
            id_param = item_id.strip()

            existing_tables = set(r[0] for r in conn.execute("SHOW TABLES;").fetchall())
            if "stock_balances" in existing_tables:
                wh_row = conn.execute("SELECT warehouse_id FROM stock_balances WHERE item_id = ? ORDER BY quantity_on_hand ASC LIMIT 1;", [id_param]).fetchone()
                target_wh = wh_row[0] if wh_row else "WH-JKT-01"

                conn.execute("""
                    UPDATE stock_balances
                    SET quantity_on_hand = quantity_on_hand + ?,
                        stock_status = CASE 
                            WHEN (quantity_on_hand + ?) <= reorder_point * 0.5 THEN 'CRITICAL'
                            WHEN (quantity_on_hand + ?) <= reorder_point THEN 'LOW_STOCK'
                            ELSE 'NORMAL'
                        END,
                        last_updated = CURRENT_TIMESTAMP
                    WHERE item_id = ? AND warehouse_id = ?;
                """, [qty_to_add, qty_to_add, qty_to_add, id_param, target_wh])

                if "items" in existing_tables:
                    conn.execute("""
                        UPDATE items
                        SET current_stock = current_stock + ?
                        WHERE item_id = ? OR lower(name) LIKE ?;
                    """, [qty_to_add, id_param, f"%{name_param}%"])

                conn.commit()
                return True

            # Also update legacy/shared items table if matching item exists
            if "items" in existing_tables:
                conn.execute("""
                    UPDATE items
                    SET current_stock = GREATEST(current_stock + ?, min_threshold + 5)
                    WHERE item_id = ? OR lower(name) LIKE ?;
                """, [qty_to_add, id_param, f"%{name_param}%"])

            conn.commit()
            return updated
        finally:
            conn.close()

    @classmethod
    def update_item_threshold(cls, item_id_or_name: str, new_threshold: int, tenant_id: str = "ALL") -> bool:
        """
        Updates safety stock threshold in the tenant's real heterogeneous table and legacy items table.
        """
        conn = get_db_connection()
        updated = False
        try:
            target = item_id_or_name.strip()
            target_lower = target.lower()

            existing_tables = set(r[0] for r in conn.execute("SHOW TABLES;").fetchall())
            if "inventory_items" in existing_tables:
                wh_count_row = conn.execute("SELECT COUNT(*) FROM stock_balances WHERE item_id = ? OR lower(item_id) = ?;", [target, target_lower]).fetchone()
                wh_count = wh_count_row[0] if wh_count_row and wh_count_row[0] > 0 else 1
                per_wh_min = max(1, new_threshold // wh_count)

                conn.execute("""
                    UPDATE inventory_items
                    SET min_stock = ?
                    WHERE item_id = ? OR lower(item_name) LIKE ?;
                """, [per_wh_min, target, f"%{target_lower}%"])
                conn.execute("""
                    UPDATE stock_balances
                    SET reorder_point = ?
                    WHERE item_id = ?;
                """, [per_wh_min, target])
                return True

            # Fallback items table
            conn.execute("""
                UPDATE items
                SET min_threshold = ?
                WHERE item_id = ? OR lower(name) LIKE ?;
            """, [new_threshold, target, f"%{target_lower}%"])

            conn.commit()
            return updated
        finally:
            conn.close()

    @classmethod
    def register_new_product(cls, item_data: dict, tenant_id: str = "TENANT_A") -> dict:
        """
        Registers a new inventory item directly into the active tenant's real table and shared registry.
        """
        import uuid
        conn = get_db_connection()
        effective_tenant = tenant_id if tenant_id and tenant_id != "ALL" else "TENANT_A"
        name = item_data.get("name", "New Item")
        category = item_data.get("category", "General")
        stock = int(item_data.get("current_stock", 0))
        min_thresh = int(item_data.get("min_threshold", 10))
        lead_time = int(item_data.get("lead_time_days", 3))
        unit = item_data.get("unit", "pcs")
        unit_price = float(item_data.get("unit_price", 50000.0))
        unit_price_usd = round(unit_price / 16000.0, 2)

        try:
            existing_tables = [r[0] for r in conn.execute("SHOW TABLES").fetchall()]
            registered_id = item_data.get("item_code") or f"SKU-{uuid.uuid4().hex[:6].upper()}"

            if "inventory_items" in existing_tables:
                internal_id = f"ITEM-{uuid.uuid4().hex[:6].upper()}"
                supplier_id = item_data.get("supplier_id") or "SUP-001"
                conn.execute("""
                    INSERT INTO inventory_items (item_id, item_code, item_name, category, unit, unit_price, min_stock, safety_stock, lead_time_days, supplier_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """, [internal_id, registered_id, name, category, unit, unit_price, min_thresh, min_thresh, lead_time, supplier_id])

                if "stock_balances" in existing_tables:
                    wh_id = item_data.get("warehouse_id") or "WH-BDG-01"
                    bal_id = f"BAL-{uuid.uuid4().hex[:6].upper()}"
                    st_status = "NORMAL" if stock > min_thresh else ("LOW_STOCK" if stock > min_thresh * 0.5 else "CRITICAL")
                    from datetime import datetime
                    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    conn.execute("""
                        INSERT INTO stock_balances (balance_id, item_id, warehouse_id, quantity_on_hand, quantity_reserved, reorder_point, stock_status, last_stock_take_date, last_updated)
                        VALUES (?, ?, ?, ?, 0, ?, ?, ?, ?);
                    """, [bal_id, internal_id, wh_id, stock, min_thresh, st_status, now_str[:10], now_str])

            # Also register to legacy items & vendors if tables exist
            if "items" in existing_tables:
                conn.execute("""
                    INSERT INTO items (item_id, name, category, current_stock, min_threshold, max_threshold, avg_daily_usage, lead_time_days, unit, tenant_id)
                    VALUES (?, ?, ?, ?, ?, ?, 1.0, ?, ?, ?);
                """, [registered_id, name, category, stock, min_thresh, min_thresh * 3, lead_time, unit, effective_tenant])

            if "vendors" in existing_tables:
                conn.execute("""
                    INSERT INTO vendors (vendor_id, name, item_id, unit_price, lead_time_days, rating, tenant_id)
                    VALUES (?, 'Standard Verified Supplier', ?, ?, ?, 4.8, ?);
                """, [f"VND-{registered_id[-4:]}", registered_id, unit_price, lead_time, effective_tenant])

            conn.commit()
            return {
                "item_id": registered_id,
                "name": name,
                "tenant_id": effective_tenant
            }
        finally:
            conn.close()

