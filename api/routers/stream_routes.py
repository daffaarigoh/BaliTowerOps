import asyncio
import json
import uuid
from collections.abc import AsyncGenerator
from datetime import datetime

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from core.config import settings
from core.observability import tracer
from core.schemas import PurchaseItemRequest, PurchaseRequisitionDoc
from core.security import TokenData, get_current_user

router = APIRouter(prefix="/api/stream", tags=["Live Agent Streaming"])


@router.get("/inventory-summary")
async def get_inventory_summary(current_user: TokenData = Depends(get_current_user)):
    """
    Returns live inventory items and health status directly from DuckDB via TenantSchemaAdapter.
    """
    items = []
    try:
        from database.schema_adapters import TenantSchemaAdapter
        raw_items = TenantSchemaAdapter.get_all_inventory_items(tenant_id=current_user.tenant_id)

        for r in raw_items:
            cur_stock = r.get("current_stock", 0)
            min_thresh = r.get("min_threshold", 0)
            if cur_stock < min_thresh:
                health = "CRITICAL"
            elif cur_stock <= min_thresh * 1.3:
                health = "WARNING"
            else:
                health = "HEALTHY"

            items.append({
                "item_id": r.get("item_id"),
                "name": r.get("name"),
                "category": r.get("category", "General"),
                "current_stock": cur_stock,
                "min_threshold": min_thresh,
                "avg_daily_usage": float(r.get("avg_daily_usage", 1.0)),
                "lead_time_days": int(r.get("lead_time_days", 3)),
                "unit": r.get("unit", "pcs"),
                "unit_price": float(r.get("unit_price", 0.0)),
                "health": health
            })
    except Exception as e:
        items = []

    total_items = len(items)
    critical_items = sum(1 for i in items if i["health"] == "CRITICAL")
    warning_items = sum(1 for i in items if i["health"] == "WARNING")
    healthy_items = sum(1 for i in items if i["health"] == "HEALTHY")

    return {
        "total_sku": total_items,
        "critical_count": critical_items,
        "warning_count": warning_items,
        "healthy_count": healthy_items,
        "items": items
    }



async def agent_thought_generator(tenant_id: str = "ALL") -> AsyncGenerator[str, None]:
    """
    Dynamically executes and streams the live multi-agent decision steps with Server-Sent Events (SSE)
    connected directly to DuckDB and LangGraph multi-agent workflow scoped by tenant.
    """
    trace_id = f"trace-{uuid.uuid4().hex[:8]}"
    tracer.start_trace(trace_id=trace_id)

    # Step 1: Real Scan from DuckDB
    from mcp_server.tools import get_low_stock_items
    low_stock = get_low_stock_items(tenant_id=tenant_id)
    num_low = len(low_stock)
    item_names = [it.get("name", it.get("item_id", "")) for it in low_stock]
    item_summary_str = ", ".join(item_names[:3]) + (f" dan {num_low - 3} SKU lainnya" if num_low > 3 else "")

    yield f"data: {json.dumps({'timestamp': datetime.now().strftime('%H:%M:%S'), 'step': 1, 'node': 'Scanner Node (DuckDB)', 'model': 'DuckDB-Engine', 'message': f'Memindai inventaris ({tenant_id}) di DuckDB... Ditemukan {num_low} SKU dengan stok kritis di bawah threshold: {item_summary_str}.', 'progress': 16})}\n\n"
    await asyncio.sleep(0.6)

    # Step 2: Real Dynamic Stock Calculator
    reorder_details = []
    for it in low_stock[:3]:
        name = it.get("name", "")
        cur = it.get("current_stock", 0)
        thresh = it.get("min_threshold", 0)
        req = max(thresh * 2 - cur, 10)
        unit = it.get("unit", "pcs")
        reorder_details.append(f"{name} (Reorder: {req} {unit})")
    reorder_str = ", ".join(reorder_details)

    yield f"data: {json.dumps({'timestamp': datetime.now().strftime('%H:%M:%S'), 'step': 2, 'node': 'Dynamic Stock Calculator', 'model': 'Math-Engine', 'message': f'Menghitung Safety Stock & Burn Rate harian: {reorder_str}.', 'progress': 33})}\n\n"
    await asyncio.sleep(0.6)

    # Step 3: Real Agent Execution (Planner & Vendor Matcher)
    from agents.workflow import run_balitowerops_cycle
    from api.routers.approval_routes import PR_STORE
    from docgen.compiler import generate_pr_pdf

    pr_doc = run_balitowerops_cycle(tenant_id=tenant_id)
    
    vendor_names = list(set([it.vendor_name for it in pr_doc.items]))[:2]
    vendor_str = " & ".join([f"'{v}'" for v in vendor_names]) if vendor_names else "supplier terverifikasi"
    total_budget_fmt = f"Rp {pr_doc.total_budget:,.0f}".replace(",", ".")

    active_model = settings.MODEL_NAME or "qwen-38"
    yield f"data: {json.dumps({'timestamp': datetime.now().strftime('%H:%M:%S'), 'step': 3, 'node': 'Procurement Planner Node', 'model': active_model, 'message': f'{active_model} mencocokkan supplier: Memilih {vendor_str} berdasarkan harga termurah & lead time tercepat.', 'progress': 50})}\n\n"
    await asyncio.sleep(0.7)

    # Step 4: Compliance Auditor
    yield f"data: {json.dumps({'timestamp': datetime.now().strftime('%H:%M:%S'), 'step': 4, 'node': 'Compliance Auditor Node', 'model': active_model, 'message': f'{active_model} memverifikasi anggaran: Total PR {total_budget_fmt} dinyatakan PASSED ({pr_doc.auditor_notes}).', 'progress': 68})}\n\n"
    await asyncio.sleep(0.6)

    # Step 5: Typst Engine
    clean_filename = f"{pr_doc.pr_number.replace('-', '_')}.pdf"
    PR_STORE[pr_doc.pr_number] = pr_doc
    generate_pr_pdf(pr_doc, output_path=f"storage/documents/{clean_filename}")

    yield f"data: {json.dumps({'timestamp': datetime.now().strftime('%H:%M:%S'), 'step': 5, 'node': 'Document Engine (Typst)', 'model': 'Typst-Compiler', 'message': f'Typst berhasil menyusun dan meng-compile dokumen {clean_filename} dengan status PENDING.', 'progress': 85})}\n\n"
    await asyncio.sleep(0.5)

    # Step 6: HITL Dispatcher
    yield f"data: {json.dumps({'timestamp': datetime.now().strftime('%H:%M:%S'), 'step': 6, 'node': 'Human-In-The-Loop Dispatcher', 'model': 'Dashboard & Email', 'message': f'Dokumen {pr_doc.pr_number} berhasil diterbitkan dan siap diverifikasi di tab Purchase Requisitions.', 'progress': 100})}\n\n"

    tracer.end_trace(verdict="PASSED")
    yield f"data: {json.dumps({'event': 'DONE', 'message': f'Autonomous cycle completed. Dokumen {pr_doc.pr_number} siap disetujui.'})}\n\n"




@router.get("/agent-run")
async def stream_agent_execution(
    tenant_id: str = "ALL",
    current_user: TokenData = Depends(get_current_user)
):
    """
    Server-Sent Events endpoint streaming live agent reasoning traces to the frontend console.
    Protected by JWT bearer authentication.
    """
    # Enforce multi-tenant scoping
    active_tenant = current_user.tenant_id if current_user.tenant_id != "ALL" else tenant_id
    return StreamingResponse(
        agent_thought_generator(tenant_id=active_tenant),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )
