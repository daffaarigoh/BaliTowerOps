import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

# Fix console encoding on Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Base path resolution
WORKSPACE_DIR = Path(__file__).resolve().parent.parent
if str(WORKSPACE_DIR) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_DIR))

import asyncio
import json

import threading
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from agents.state import AgentState, PurchaseRequisition, RestockItem
from core.config import settings
from core.llm_client import gateway
from database.db import execute_db_write, get_db_connection
from docgen.compiler import generate_pr_pdf
from mcp_server.tools import get_best_vendors, get_low_stock_items

# Global in-memory checkpointer for thread persistence
memory_checkpointer = MemorySaver()


def record_orders_to_db(pr: PurchaseRequisition, status: str = "PENDING"):
    """Insert or update order records into DuckDB orders table with write serialization."""
    def _write_orders(conn):
        tenant_val = getattr(pr, "tenant_id", None) or "TENANT_A"
        existing = conn.execute("SELECT order_id FROM orders WHERE pr_number = ?", [pr.pr_number]).fetchall()
        if existing:
            conn.execute("UPDATE orders SET status = ? WHERE pr_number = ?", [status, pr.pr_number])
        else:
            insert_params = []
            for idx, item in enumerate(pr.items, start=1):
                order_id = f"ORD-{pr.pr_number}-{item.item_id}-{idx:02d}"
                insert_params.append((
                    order_id, pr.pr_number, item.item_id, item.vendor_id,
                    item.reorder_qty, item.unit_price, item.total_price, status, tenant_val
                ))
            if insert_params:
                conn.executemany("""
                    INSERT INTO orders (order_id, pr_number, item_id, vendor_id, quantity, unit_price, total_price, status, tenant_id, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP);
                """, insert_params)

    execute_db_write(_write_orders)


def update_db_orders_status(pr_number: str, status: str):
    """Update all orders under a PR number to a new status (e.g. APPROVED, REJECTED) and create official POs on APPROVE."""
    def _update_orders(conn):
        if status.upper() == "APPROVED":
            # ERP Standard: Physical stock increments upon physical Goods Receipt (DELIVERED)
            # when material arrives at the regional warehouse.
            # Here on APPROVE, we synchronize purchase_orders (status ORDERED) and generate PO PDF.
            existing_tables = set(r[0] for r in conn.execute("SHOW TABLES;").fetchall())
            if "purchase_orders" in existing_tables:
                try:
                    from api.routers.approval_routes import sync_approved_pr_to_purchase_orders
                    sync_approved_pr_to_purchase_orders(conn, pr_number)
                except Exception as sync_err:
                    print(f"[WORKFLOW] Failed to sync PO: {sync_err}")
        elif status.upper() in ["REJECTED", "CANCELLED"]:
            existing_tables = set(r[0] for r in conn.execute("SHOW TABLES;").fetchall())
            if "purchase_orders" in existing_tables:
                po_cols = [c[0] for c in conn.execute("DESCRIBE purchase_orders;").fetchall()]
                if "pr_number" in po_cols:
                    conn.execute("UPDATE purchase_orders SET status = 'REJECTED' WHERE pr_number = ?;", [pr_number])

        conn.execute("""
            UPDATE orders 
            SET status = ?
            WHERE pr_number = ?;
        """, [status, pr_number])

    execute_db_write(_update_orders)


def scan_node(state: AgentState) -> dict[str, Any]:
    """
    Node 1: Scan Node
    Scans DuckDB inventory database to detect items below safety stock threshold for the active tenant.
    """
    tenant_id = state.get("tenant_id", "ALL")
    print(f"\n[AGENT] [STEP 1: SCAN] Scanning inventory database for low stock items (Tenant: {tenant_id})...")
    low_stock_items = get_low_stock_items(tenant_id=tenant_id)
    print(f"[AGENT] Found {len(low_stock_items)} items requiring replenishment.")
    
    return {
        "low_stock_items": low_stock_items,
        "logs": state.get("logs", []) + [f"Scanned inventory ({tenant_id}): identified {len(low_stock_items)} critical items."]
    }


_worker_loop = None
_worker_thread = None
_worker_lock = threading.Lock()


def _get_worker_loop():
    """Returns a singleton background event loop for safely bridging sync nodes to async LLM calls."""
    global _worker_loop, _worker_thread
    with _worker_lock:
        if _worker_loop is None or not _worker_thread or not _worker_thread.is_alive():
            ready_event = threading.Event()

            def _start_loop():
                nonlocal ready_event
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                global _worker_loop
                _worker_loop = loop
                ready_event.set()
                loop.run_forever()

            _worker_thread = threading.Thread(target=_start_loop, daemon=True, name="WorkflowAsyncBridge")
            _worker_thread.start()
            ready_event.wait()
        return _worker_loop


def _run_sync(coro):
    """Safely executes an async coroutine from synchronous graph nodes without event loop conflicts."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        # Running inside an active event loop (e.g. FastAPI worker thread)
        worker_loop = _get_worker_loop()
        future = asyncio.run_coroutine_threadsafe(coro, worker_loop)
        return future.result(timeout=120)
    return asyncio.run(coro)


def planner_node(state: AgentState) -> dict[str, Any]:
    """
    Node 2: Planner Node (qwen-38 Planner & Vendor Matcher)
    Analyzes safety stock deficits, selects optimal vendors, and drafts line item justifications.
    """
    active_model = settings.MODEL_NAME or "qwen-38"
    print(f"[AGENT] [STEP 2: PLANNER] Running Planner Node ({active_model}) - Vendor matching & budget calculation via LLM...")
    low_stock_items = state.get("low_stock_items", [])
    tenant_id = state.get("tenant_id", "ALL")
    
    planned_items: list[RestockItem] = []
    total_budget = 0.0
    
    if not low_stock_items:
        return {"planned_items": [], "total_budget": 0.0, "logs": state.get("logs", []) + ["Planner: No items to plan."]}

    # Prepare data for LLM
    items_data = []
    for item in low_stock_items:
        vendor = get_best_vendors(item["item_id"], tenant_id=tenant_id) or {
            "vendor_id": "VND-DEFAULT", "name": "Standard Supplier",
            "unit_price": 10000.0, "lead_time_days": 7, "rating": 4.0
        }
        items_data.append({
            "id": item["item_id"],
            "name": item["name"],
            "qty": item["reorder_qty"],
            "vendor_id": vendor.get("vendor_id", "VND-DEFAULT"),
            "vendor": vendor.get("name", "Standard Supplier"),
            "price": float(vendor.get("unit_price", 10000.0)),
        })

    prompt = f"""
You are an expert Procurement Planner AI.
For each item, calculate line_total (qty * price).
Keep 'reason' short, concise and professional in Indonesian (max 10 words per item).

Data:
{json.dumps(items_data)}

Output format must be a JSON object with a key 'items' containing a list of objects:
- item_id (string)
- vendor_id (string)
- vendor_name (string)
- unit_price (float)
- line_total (float)
- reason (string, short Indonesian max 10 words)
"""

    messages = [
        {"role": "system", "content": "You are a Procurement AI. Always output valid JSON."},
        {"role": "user", "content": prompt}
    ]
    
    llm_items = {}
    is_llm_success = False
    try:
        response_str = _run_sync(
            gateway.chat_completion(settings.MODEL_NAME or "qwen-38", messages, temperature=0.1, response_format_json=True)
        )
        
        if response_str.startswith("```json"):
            response_str = response_str.strip("`").removeprefix("json").strip()
            
        llm_output = json.loads(response_str)
        llm_items = {i["item_id"]: i for i in llm_output.get("items", [])}
        is_llm_success = bool(llm_items)
    except Exception as e:
        print(f"[AGENT] LLM Planner unavailable ({e}). Utilizing deterministic heuristic fallback.")

    # Reconstruct items safely
    for item in low_stock_items:
        item_id = item["item_id"]
        llm_item = llm_items.get(item_id, {})
        
        vendor_id = llm_item.get("vendor_id", "VND-DEFAULT")
        vendor_name = llm_item.get("vendor_name", "Standard Supplier")
        unit_price = float(llm_item.get("unit_price", 10000.0))
        line_total = float(llm_item.get("line_total", unit_price * item["reorder_qty"]))
        reason = llm_item.get("reason", f"Stok kritis. Restock via {vendor_name}.")
        
        total_budget += line_total
        
        planned_items.append(RestockItem(
            item_id=item_id,
            name=item["name"],
            category=item["category"],
            current_stock=item["current_stock"],
            min_threshold=item["min_threshold"],
            reorder_qty=item["reorder_qty"],
            unit=item["unit"],
            warehouse_id=item.get("warehouse_id"),
            warehouse_name=item.get("warehouse_name"),
            vendor_id=vendor_id,
            vendor_name=vendor_name,
            unit_price=unit_price,
            total_price=line_total,
            reason=reason
        ))
        
    mode_str = "via LLM" if is_llm_success else "via Heuristic Fallback"
    print(f"[AGENT] Planned {len(planned_items)} line items {mode_str}. Subtotal budget: Rp {total_budget:,.0f}")
    
    return {
        "planned_items": planned_items,
        "total_budget": total_budget,
        "logs": state.get("logs", []) + [f"Planner ({mode_str}): Matched {len(planned_items)} items. Total={total_budget}"]
    }


def audit_node(state: AgentState) -> dict[str, Any]:
    """
    Node 3: Audit Node (qwen-38 Compliance & Policy Enforcer)
    Validates budget threshold and vendor compliance.
    """
    active_model = settings.MODEL_NAME or "qwen-38"
    print(f"[AGENT] [STEP 3: AUDIT] Running Audit Node ({active_model}) - Compliance & budget guardrail via LLM...")
    total_budget = state.get("total_budget", 0.0)
    planned_items = state.get("planned_items", [])
    
    BUDGET_CEILING = 100_000_000.0
    
    items_summary = [
        {"name": i.name, "vendor": i.vendor_name, "qty": i.reorder_qty, "total": i.total_price}
        for i in planned_items
    ]
    
    prompt = f"""
You are a Compliance & Budget Auditor AI for enterprise procurement at PT Bali Towerindo Sentra Tbk.
Evaluate this restock requisition:
- Maximum approved budget ceiling: Rp {BUDGET_CEILING:,.0f}
- Requested total budget: Rp {total_budget:,.0f}
- Line items: {len(planned_items)}

Items:
{json.dumps(items_summary[:10], indent=2)}

Rules:
- If total_budget <= {BUDGET_CEILING} and len(planned_items) > 0: status is 'PASSED'.
- If total_budget > {BUDGET_CEILING}: status is 'REVISED'.
- If items list is empty: status is 'REJECTED'.

Provide a professional 'auditor_notes' in Indonesian explaining your evaluation.

Output format must be a JSON object with:
- "auditor_status": "PASSED" | "REVISED" | "REJECTED"
- "auditor_notes": string (Indonesian)
"""

    messages = [
        {"role": "system", "content": "You are an Auditor AI. Always output valid JSON."},
        {"role": "user", "content": prompt}
    ]
    
    is_llm_audit = False
    try:
        response_str = _run_sync(
            gateway.chat_completion(settings.MODEL_NAME or "qwen-38", messages, temperature=0.1, response_format_json=True)
        )
        
        if response_str.startswith("```json"):
            response_str = response_str.strip("`").removeprefix("json").strip()
            
        llm_output = json.loads(response_str)
        auditor_status = llm_output.get("auditor_status", "REVISED")
        auditor_notes = llm_output.get("auditor_notes", "Audit failed to parse response.")
        is_llm_audit = True
    except Exception as e:
        print(f"[AGENT] LLM Audit unavailable ({e}). Utilizing deterministic heuristic fallback.")
        if total_budget <= BUDGET_CEILING and len(planned_items) > 0:
            auditor_status = "PASSED"
            auditor_notes = f"Evaluasi lolos (Heuristic Fallback). Anggaran Rp {total_budget:,.0f} dalam batas pagu."
        else:
            auditor_status = "REVISED"
            auditor_notes = "Peringatan Anggaran (Heuristic Fallback). Melebihi batas pagu Rp 100 Juta atau tidak ada item."
        
    mode_label = "LLM" if is_llm_audit else "Heuristic Fallback"
    print(f"[AGENT] Audit Result ({mode_label}): {auditor_status} - {auditor_notes}")
    
    return {
        "auditor_status": auditor_status,
        "auditor_notes": auditor_notes,
        "logs": state.get("logs", []) + [f"Auditor ({mode_label}): Status={auditor_status}."]
    }


def typst_node(state: AgentState) -> dict[str, Any]:
    """
    Node 4: Typst Node
    Compiles initial Purchase Requisition into a PDF and logs pending orders.
    """
    print("[AGENT] [STEP 4: TYPST] Running Typst Node - Generating Initial Purchase Requisition...")
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    pr_timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    pr_number = f"PR-{pr_timestamp}"
    thread_id = state.get("thread_id", f"thread-{pr_timestamp}")
    
    items = state.get("planned_items", [])
    total_budget = state.get("total_budget", 0.0)
    auditor_status = state.get("auditor_status", "PASSED")
    auditor_notes = state.get("auditor_notes", "")
    tenant_id = state.get("tenant_id", "ALL")
    
    pr_doc = PurchaseRequisition(
        pr_number=pr_number,
        created_at=now_str,
        items=items,
        total_budget=total_budget,
        auditor_status=auditor_status,
        auditor_notes=auditor_notes,
        status="PENDING",
        tenant_id=tenant_id,
        thread_id=thread_id
    )
    
    pdf_path = generate_pr_pdf(pr_doc)
    pr_doc.pdf_path = pdf_path
    
    # Save pending orders to DuckDB
    record_orders_to_db(pr_doc, status="PENDING")
    
    print(f"[AGENT] Initial Document Generated: {pdf_path}")
    print(f"[AGENT] PR #{pr_number} created with status 'PENDING'. Pausing before Wait Approval Node...")

    
    return {
        "pr_document": pr_doc,
        "pdf_path": pdf_path,
        "thread_id": thread_id,
        "logs": state.get("logs", []) + [f"Typst Node: Generated document {pr_number} at {pdf_path} (Pending Approval)."]
    }


def wait_approval_node(state: AgentState) -> dict[str, Any]:
    """
    Node 5: Wait Approval Node (Human-In-The-Loop)
    Reads manager decision (APPROVE / REJECT).
    Updates DuckDB orders table and compiles the final stamped PDF (_APPROVED.pdf or _REJECTED.pdf).
    """
    pr_doc = state.get("pr_document")
    raw_action = str(state.get("approval_action", "APPROVE")).strip().upper()
    approver = state.get("approver_name", "Operations Manager")
    notes = state.get("approval_notes", "")
    
    is_approve = raw_action in ["APPROVE", "APPROVED", "Y", "YES"]
    final_status = "APPROVED" if is_approve else "REJECTED"
    
    print(f"\n[AGENT] [STEP 5: HITL APPROVAL] Processing decision: '{final_status}' by '{approver}'...")
    
    if pr_doc:
        pr_doc.status = final_status
        if not is_approve:
            pr_doc.auditor_notes = f"[REJECTED by {approver}]: {notes or 'Pengadaan ditolak oleh manajer. Tidak ada pembelian diproses.'}"
        else:
            pr_doc.auditor_notes = f"[APPROVED by {approver}]: {notes or 'Pengadaan disetujui untuk pemesanan vendor.'}"
            
        # Update DuckDB orders table status
        update_db_orders_status(pr_doc.pr_number, final_status)
        
        # Compile final PDF with _APPROVED or _REJECTED suffix
        final_pdf_path = generate_pr_pdf(pr_doc)
        pr_doc.pdf_path = final_pdf_path
        print(f"[AGENT] Final Document Compiled: {final_pdf_path}")
    else:
        final_pdf_path = None
        
    print(f"[AGENT] Final PR Status: {final_status}. DuckDB orders updated successfully.")
    
    log_msg = f"Manager ({approver}) marked PR as {final_status}."
    return {
        "pr_document": pr_doc,
        "pdf_path": final_pdf_path,
        "is_approved": is_approve,
        "logs": state.get("logs", []) + [log_msg]
    }


def create_balitowerops_graph() -> StateGraph:
    """Build and compile the LangGraph workflow with HITL interrupt_before on wait_approval_node."""
    workflow = StateGraph(AgentState)
    
    workflow.add_node("scan_node", scan_node)
    workflow.add_node("planner_node", planner_node)
    workflow.add_node("audit_node", audit_node)
    workflow.add_node("typst_node", typst_node)
    workflow.add_node("wait_approval_node", wait_approval_node)
    
    workflow.add_edge(START, "scan_node")
    workflow.add_edge("scan_node", "planner_node")
    workflow.add_edge("planner_node", "audit_node")
    workflow.add_edge("audit_node", "typst_node")
    workflow.add_edge("typst_node", "wait_approval_node")
    workflow.add_edge("wait_approval_node", END)
    
    return workflow.compile(
        checkpointer=memory_checkpointer,
        interrupt_before=["wait_approval_node"]
    )


# Singleton compiled graph
balitowerops_app = create_balitowerops_graph()

PR_THREAD_REGISTRY: dict[str, str] = {}


def run_balitowerops_cycle(thread_id: str | None = None, tenant_id: str = "ALL") -> PurchaseRequisition:
    """
    Runs cycle up to the HITL interrupt point (Typst Node) scoped by tenant_id.
    Returns the generated PurchaseRequisition with status PENDING_APPROVAL.
    """
    if thread_id is None:
        thread_id = f"thread-{uuid.uuid4().hex[:8]}"
        
    initial_state: AgentState = {
        "thread_id": thread_id,
        "tenant_id": tenant_id,
        "low_stock_items": [],
        "planned_items": [],
        "total_budget": 0.0,
        "auditor_status": "",
        "auditor_notes": "",
        "pr_document": None,
        "pdf_path": None,
        "approval_action": None,
        "approver_name": None,
        "approval_notes": None,
        "is_approved": False,
        "logs": []
    }
    
    config = {"configurable": {"thread_id": thread_id}}
    final_state = balitowerops_app.invoke(initial_state, config=config)
    
    pr_doc = final_state.get("pr_document")
    if pr_doc:
        PR_THREAD_REGISTRY[pr_doc.pr_number] = thread_id
        
    return pr_doc


def resume_approval(
    pr_number: str,
    action: str = "APPROVE",
    approver_name: str = "Warehouse Operations Manager",
    notes: str = "",
    thread_id: str | None = None
) -> PurchaseRequisition:
    """
    Resumes the workflow from the checkpoint with either APPROVE or REJECT action.
    """
    if thread_id is None:
        thread_id = PR_THREAD_REGISTRY.get(pr_number, f"thread-{pr_number}")
        
    config = {"configurable": {"thread_id": thread_id}}
    
    normalized_action = "APPROVE" if str(action).strip().upper() in ["APPROVE", "APPROVED", "Y", "YES"] else "REJECT"
    
    balitowerops_app.update_state(
        config,
        {
            "approval_action": normalized_action,
            "approver_name": approver_name,
            "approval_notes": notes
        }
    )
    
    resumed_state = balitowerops_app.invoke(None, config=config)
    return resumed_state.get("pr_document")




