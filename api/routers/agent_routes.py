import asyncio
import re
import json
import sys
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, status, Response, Depends
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

# Base path resolution
WORKSPACE_DIR = Path(__file__).resolve().parent.parent.parent
if str(WORKSPACE_DIR) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_DIR))

from agents.state import PurchaseRequisition, RestockItem
from agents.workflow import resume_approval, run_autorestock_cycle
from core.security import TokenData, get_current_user
from api.routers.balitower_routes import require_inventory_access
from database.db import get_db_connection
from mcp_server.tools import get_all_inventory_items

router = APIRouter(tags=["AutoRestock Agent"])

STORAGE_DIR = WORKSPACE_DIR / "storage"


class ApprovalRequest(BaseModel):
    pr_number: str = Field(..., description="Purchase Requisition number to approve or reject")
    action: str = Field("APPROVE", description="Decision action: 'APPROVE' or 'REJECT'")
    approver_name: str | None = Field("Warehouse Operations Manager", description="Name/Role of approver")
    notes: str | None = Field(None, description="Optional notes or reason for decision")


class ApprovalResponse(BaseModel):
    pr_number: str
    status: str
    approver: str
    message: str
    pr_document: PurchaseRequisition | None = None


@router.get("/api/inventory/items", response_model=list[dict[str, Any]])
def get_inventory_items(response: Response, current_user: TokenData = Depends(require_inventory_access)):
    """
    Retrieve all inventory items from DuckDB.
    """
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    try:
        items = get_all_inventory_items(tenant_id=current_user.tenant_id)
        return items
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch inventory items: {e!s}"
        )


@router.post("/api/agent/run-cycle", response_model=PurchaseRequisition)
def run_agent_cycle(current_user: TokenData = Depends(get_current_user)):
    """
    Triggers the LangGraph multi-agent workflow:
    1. Scan items below safety threshold.
    2. Planner (qwen-38) matches optimal vendors & calculates budget.
    3. Auditor (qwen-38) enforces compliance guardrails.
    4. Typst compiles the formal Purchase Requisition PDF.
    5. Graph pauses before Wait Approval Node (HITL).
    """
    try:
        tenant_id = current_user.tenant_id if current_user else "ALL"
        pr_document = run_autorestock_cycle(tenant_id=tenant_id)
        if pr_document:
            from api.routers.approval_routes import PR_STORE
            from docgen.compiler import generate_pr_pdf
            
            clean_filename = f"{pr_document.pr_number.replace('-', '_')}.pdf"
            PR_STORE[pr_document.pr_number] = pr_document
            generate_pr_pdf(pr_document, output_path=f"storage/documents/{clean_filename}")
        return pr_document
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"AutoRestock agent cycle failed: {e!s}"
        )



@router.get("/api/documents/pr/{pr_number}/download")
def download_pr_document(pr_number: str, inline: bool = False):
    """
    Downloads or previews the generated Typst Purchase Requisition PDF.
    Use ?inline=true to display in-browser (for iframe previews).
    Checks status-specific folders first to ensure the served PDF matches true PR status.
    """
    clean_pr_num = pr_number.replace("/", "_").replace("\\", "_")
    clean_filename = f"{pr_number.replace('-', '_')}.pdf"
    
    # Check DB/PR_STORE status first
    from api.routers.approval_routes import _ensure_pr_in_store, _regenerate_pdf
    pr_doc = _ensure_pr_in_store(pr_number)
    current_status = (pr_doc.status if pr_doc else "PENDING").upper()
    
    candidate_paths = []
    if "APPROV" in current_status:
        candidate_paths = [
            STORAGE_DIR / "approved" / f"{clean_pr_num}.pdf",
            STORAGE_DIR / "approved" / clean_filename,
            STORAGE_DIR / "documents" / clean_filename,
            STORAGE_DIR / "documents" / f"{clean_pr_num}.pdf",
        ]
    elif "REJECT" in current_status:
        candidate_paths = [
            STORAGE_DIR / "rejected" / f"{clean_pr_num}.pdf",
            STORAGE_DIR / "rejected" / clean_filename,
            STORAGE_DIR / "documents" / clean_filename,
            STORAGE_DIR / "documents" / f"{clean_pr_num}.pdf",
        ]
    else:
        candidate_paths = [
            STORAGE_DIR / "pending" / f"{clean_pr_num}.pdf",
            STORAGE_DIR / "pending" / clean_filename,
            STORAGE_DIR / "documents" / clean_filename,
            STORAGE_DIR / "documents" / f"{clean_pr_num}.pdf",
            STORAGE_DIR / f"{clean_pr_num}.pdf"
        ]
    
    found_path = None
    for path in candidate_paths:
        if path.exists():
            found_path = path
            break
            
    # If not found or if the document needs regeneration for its current status
    if found_path is None and pr_doc:
        try:
            _regenerate_pdf(pr_doc)
            for path in candidate_paths:
                if path.exists():
                    found_path = path
                    break
        except Exception as e:
            print(f"[download_pr_document] Regeneration on-the-fly failed: {e}")

    # Recursive wildcard search fallback
    if found_path is None:
        matches = list(STORAGE_DIR.rglob(f"*{clean_pr_num}*.pdf"))
        if matches:
            found_path = matches[0]

    if found_path is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Purchase Requisition PDF '{pr_number}' not found in storage."
        )
            
    return FileResponse(
        path=str(found_path),
        media_type="application/pdf",
        filename=f"{clean_pr_num}.pdf",
        content_disposition_type="inline" if inline else "attachment"
    )


@router.get("/api/documents/po/{po_id}/download")
def download_po_document(po_id: str, inline: bool = False):
    """
    Downloads or previews the official Typst Purchase Order (PO) PDF.
    Use ?inline=true to display in-browser (for iframe modal previews).
    Generates the PDF dynamically on-the-fly via Typst if not already compiled.
    """
    clean_po_id = po_id.replace("/", "_").replace("\\", "_")
    po_storage_dir = STORAGE_DIR / "purchase_orders"
    po_storage_dir.mkdir(parents=True, exist_ok=True)
    target_pdf = po_storage_dir / f"{clean_po_id}.pdf"

    from docgen.compiler import generate_po_pdf
    try:
        pdf_path = generate_po_pdf(po_id, output_path=target_pdf)
    except Exception as err:
        if target_pdf.exists():
            pdf_path = str(target_pdf)
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Gagal menerbitkan dokumen Purchase Order '{po_id}': {err}"
            )

    return FileResponse(
        path=str(pdf_path),
        media_type="application/pdf",
        filename=f"{clean_po_id}.pdf",
        content_disposition_type="inline" if inline else "attachment"
    )


@router.get("/api/documents/leave/{leave_id}/download")
def download_leave_document(leave_id: str, inline: bool = False):
    """
    Downloads or previews the official Typst Leave Request PDF.
    Use ?inline=true to display in-browser (for iframe modal previews).
    Generates the PDF dynamically on-the-fly via Typst if not already compiled.
    """
    clean_leave_id = leave_id.replace("/", "_").replace("\\", "_")
    leave_storage_dir = STORAGE_DIR / "leave_requests"
    leave_storage_dir.mkdir(parents=True, exist_ok=True)
    target_pdf = leave_storage_dir / f"{clean_leave_id}.pdf"

    from docgen.compiler import generate_leave_pdf
    try:
        pdf_path = generate_leave_pdf(leave_id, output_path=target_pdf)
    except Exception as err:
        if target_pdf.exists():
            pdf_path = str(target_pdf)
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Gagal menerbitkan dokumen Surat Pengajuan Cuti '{leave_id}': {err}"
            )

    return FileResponse(
        path=str(pdf_path),
        media_type="application/pdf",
        filename=f"{clean_leave_id}.pdf",
        content_disposition_type="inline" if inline else "attachment"
    )


@router.get("/api/documents/invoice/{invoice_id}/download")
def download_invoice_document(invoice_id: str, inline: bool = False):
    """
    Downloads or previews the official Typst Tower Lease Invoice / MLA Contract PDF.
    Use ?inline=true to display in-browser (for iframe modal previews).
    Generates the PDF dynamically on-the-fly via Typst if not already compiled.
    Supports both invoice IDs (e.g. INV-2026-001) and onboarding IDs (e.g. ONB-2026-001).
    """
    clean_id = invoice_id.replace("/", "_").replace("\\", "_")
    invoice_storage_dir = STORAGE_DIR / "invoices"
    invoice_storage_dir.mkdir(parents=True, exist_ok=True)
    target_pdf = invoice_storage_dir / f"{clean_id}.pdf"

    from docgen.compiler import generate_invoice_pdf
    try:
        pdf_path = generate_invoice_pdf(invoice_id, output_path=target_pdf)
    except Exception as err:
        if target_pdf.exists():
            pdf_path = str(target_pdf)
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Gagal menerbitkan dokumen Invoice/Kontrak Sewa '{invoice_id}': {err}"
            )

    return FileResponse(
        path=str(pdf_path),
        media_type="application/pdf",
        filename=f"{clean_id}.pdf",
        content_disposition_type="inline" if inline else "attachment"
    )


@router.get("/api/documents/reports/{report_name}/download")
def download_dynamic_report_document(report_name: str, inline: bool = False):
    """
    Downloads or previews an official Typst Dynamic Report PDF.
    Use ?inline=true to display in-browser / iframe modal previews.
    """
    clean_name = report_name.replace("/", "_").replace("\\", "_")
    if not clean_name.endswith(".pdf"):
        clean_name = f"{clean_name}.pdf"

    reports_dir = STORAGE_DIR / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    target_pdf = reports_dir / clean_name

    if not target_pdf.exists():
        matches = list(reports_dir.glob(f"*{report_name}*"))
        if matches:
            target_pdf = matches[0]
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Laporan PDF '{report_name}' tidak ditemukan di penyimpanan."
            )

    return FileResponse(
        path=str(target_pdf),
        media_type="application/pdf",
        filename=target_pdf.name,
        content_disposition_type="inline" if inline else "attachment"
    )


@router.post("/api/agent/approve", response_model=ApprovalResponse)
def approve_pr_requisition(request: ApprovalRequest):
    """
    Handles Human-In-The-Loop (HITL) approval for a Purchase Requisition:
    - If APPROVE: Updates DuckDB orders table status to 'APPROVED' and resumes the paused LangGraph workflow.
    - If REJECT: Updates DuckDB orders table status to 'REJECTED'.
    """
    try:
        action = request.action.upper()
        if action not in ["APPROVE", "REJECT"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Action must be either 'APPROVE' or 'REJECT'."
            )
            
        updated_pr = resume_approval(
            pr_number=request.pr_number,
            action=action,
            approver_name=request.approver_name or "Manager",
            notes=request.notes or ""
        )
        
        final_status = "APPROVED" if action == "APPROVE" else "REJECTED"
        msg = f"Purchase Requisition {request.pr_number} successfully {final_status} by {request.approver_name}."
        
        return ApprovalResponse(
            pr_number=request.pr_number,
            status=final_status,
            approver=request.approver_name or "Manager",
            message=msg,
            pr_document=updated_pr
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process PR approval: {e!s}"
        )


class UpdateItemThresholdRequest(BaseModel):
    min_threshold: int | None = Field(None, description="New minimum safety threshold")
    max_threshold: int | None = Field(None, description="New maximum safety threshold")
    current_stock: int | None = Field(None, description="Optional update to current physical stock")
    avg_daily_usage: float | None = Field(None, description="Optional update to daily usage burn rate")
    lead_time_days: int | None = Field(None, description="Optional update to vendor lead time")


@router.patch("/api/inventory/items/{item_id}")
def update_item_threshold(item_id: str, payload: UpdateItemThresholdRequest, current_user: TokenData = Depends(get_current_user)):
    """
    Updates threshold and inventory parameters for a specific item in DuckDB.
    Supports real heterogeneous tenant tables and legacy items.
    """
    from database.schema_adapters import TenantSchemaAdapter
    tenant_id = current_user.tenant_id if current_user else "ALL"
    
    # 1. Look up existing item in real tenant tables or legacy items
    matching_items = TenantSchemaAdapter.get_specific_item_stock(item_id, tenant_id=tenant_id)
    if matching_items:
        existing_name = matching_items[0]["name"]
        cur_stock = matching_items[0].get("current_stock", 0)
        old_min = matching_items[0].get("min_threshold", 0)
    else:
        conn = get_db_connection(read_only=True)
        legacy = conn.execute("SELECT item_id, name, min_threshold, max_threshold, current_stock FROM items WHERE item_id = ? OR lower(name) LIKE ?", [item_id, f"%{item_id.lower()}%"]).fetchone()
        conn.close()
        if not legacy:
            raise HTTPException(status_code=404, detail=f"Item with ID '{item_id}' not found in inventory.")
        existing_name = legacy[1]
        cur_stock = legacy[4]
        old_min = legacy[2]

    # 2. Apply threshold update if provided
    new_min = payload.min_threshold if payload.min_threshold is not None else old_min
    if payload.min_threshold is not None:
        TenantSchemaAdapter.update_item_threshold(item_id, payload.min_threshold, tenant_id=tenant_id)

    # 3. Update legacy items table if extra fields provided
    conn = get_db_connection()
    try:
        updates = []
        params = []
        if payload.min_threshold is not None:
            updates.append("min_threshold = ?")
            params.append(payload.min_threshold)
        if payload.max_threshold is not None:
            updates.append("max_threshold = ?")
            params.append(payload.max_threshold)
        if payload.current_stock is not None:
            updates.append("current_stock = ?")
            params.append(payload.current_stock)
        if payload.avg_daily_usage is not None:
            updates.append("avg_daily_usage = ?")
            params.append(payload.avg_daily_usage)
        if payload.lead_time_days is not None:
            updates.append("lead_time_days = ?")
            params.append(payload.lead_time_days)

        if updates:
            params.extend([item_id, f"%{item_id.lower()}%"])
            conn.execute(f"UPDATE items SET {', '.join(updates)} WHERE item_id = ? OR lower(name) LIKE ?;", params)
            conn.commit()
    finally:
        conn.close()

    return {
        "status": "success",
        "message": f"Berhasil memperbarui {existing_name} ({item_id}).",
        "item": {
            "item_id": item_id,
            "name": existing_name,
            "min_threshold": new_min,
            "current_stock": payload.current_stock if payload.current_stock is not None else cur_stock
        }
    }



from services.goods_receipt_service import process_goods_receipt


class CustomPromptRequest(BaseModel):
    prompt: str = Field(..., description="Natural language prompt from user describing restock intent or workflow")
    destinations: list[str] | None = Field(None, description="Explicit destinations: ['database', 'email', 'pdf']")
    recipient_email: str | None = Field(None, description="Optional custom recipient email")
    history: list[dict[str, Any]] | None = Field(None, description="Optional multi-turn conversation history: [{'role': 'user', 'content': '...'}, ...]")


def classify_workflow_proposal_eligibility(prompt: str, agent_result: dict, user_role: str = "USER") -> bool:
    """
    Determines whether a user prompt should show the 'Ajukan Alur Kerja ke Administrator' proposal card.
    
    Enterprise Policy:
    1. Admin user -> False (Admin can create workflows directly in admin portal).
    2. Pure Greetings / Pleasantries / Out-of-Domain Refusal -> False.
    3. Direct Single-Tool Execution (Safe Read Queries, Check Stock, View PO):
       -> False (Task was successfully executed by the LLM single-tool capability; no workflow card needed).
    4. Guarded Tool Blocked or Unregistered Multi-Step Workflow Required:
       -> True (Action is blocked by enterprise governance, so system actively recommends proposing an admin workflow).
    """
    if str(user_role).upper() == "ADMIN":
        return False

    action_type = agent_result.get("action_type", "")
    message = agent_result.get("message", "")

    # Out of scope or domain refusal -> Never propose workflow
    if action_type in ["out_of_scope", "security_refusal"]:
        return False
    if "hanya berwenang melayani pertanyaan dan instruksi seputar operasional Dashboard BaliTower" in message:
        return False

    # Pure Greetings / Pleasantries -> Never propose workflow
    p_clean = re.sub(r'[^\w\s]', '', prompt.lower()).strip()
    pleasantries = ['halo', 'hai', 'hi', 'selamat pagi', 'selamat siang', 'selamat sore', 'selamat malam', 'terima kasih', 'terimakasih', 'makasih', 'thanks', 'thank you']
    if p_clean in pleasantries:
        return False

    # 1. If action was blocked due to guarded tool policy, unregistered workflow, or explicit flag
    if action_type == "workflow_not_found" or agent_result.get("is_tool_blocked") or agent_result.get("guarded_tool") or agent_result.get("can_request_admin"):
        return True

    # 2. Check message content where LLM explains the action cannot be processed directly
    lower_msg = message.lower()
    lower_prompt = prompt.lower()
    cannot_process_directly = (
        (
            ("tidak dapat" in lower_msg or "tidak bisa" in lower_msg or "tidak menyediakan" in lower_msg)
            and any(k in lower_msg for k in [
                "proses langsung", "diproses langsung", "memproses langsung",
                "dilakukan langsung", "diubah langsung", "dieksekusi langsung",
                "secara langsung"
            ])
        )
        or (
            ("alur kerja" in lower_msg or "workflow" in lower_msg)
            and any(w in lower_msg for w in [
                "tidak menyediakan", "belum memiliki", "belum ada", "tidak ada",
                "tidak didukung", "belum didukung", "belum terdaftar", "tidak terdaftar",
                "wajib", "perlu", "harus", "membutuhkan", "memerlukan", "secara langsung"
            ])
        )
        or (
            ("secara langsung" in lower_msg or "proses langsung" in lower_msg or "diproses langsung" in lower_msg)
            and any(w in lower_msg for w in ["tidak", "belum", "hanya dapat"])
        )
        or "tindakan terproteksi" in lower_msg
        or "tidak berwenang melakukan perubahan langsung" in lower_msg
        or "hanya dapat dilakukan melalui alur kerja" in lower_msg
        or (
            any(v in lower_prompt for v in ["ubah", "ganti", "update", "set", "jadikan", "pindahkan", "hapus", "naikkan", "turunkan"])
            and any(n in lower_prompt for n in ["status", "karyawan", "pegawai", "work status", "jabatan", "divisi", "permanent", "kontrak", "threshold", "stok", "produk"])
            and not agent_result.get("is_tool_success")
        )
    )
    if cannot_process_directly:
        return True

    # 3. If the user explicitly asks to create/register a workflow
    lower_prompt = prompt.lower()
    is_create_workflow_request = (
        bool(re.search(r'\b(buat|bikin|create|tambah|daftarkan|ajukan)\s+(alur\s+kerja|workflow)\b', lower_prompt))
        or bool(re.search(r'\b(workflow|alur kerja)\s+(baru|belum ada)\b', lower_prompt))
        or bool(re.search(r'\b(saya\s+butuh|perlu)\s+(alur\s+kerja|workflow)\b', lower_prompt))
    )
    if is_create_workflow_request:
        return True

    # Safe direct queries and resolved actions should NOT propose workflow
    return False


def evaluate_contextual_tenant_boundary(prompt: str, current_user: TokenData) -> dict | None:
    """
    Evaluates whether the user's prompt is an explicit operational action directed at
    another division's restricted domain, while understanding the whole context of the sentence
    rather than isolated word substrings.

    Context-Aware Rules:
    1. Super Admin / ALL: Unrestricted access across all enterprise schemas.
    2. Universal Topics (Profile, System Health, Emergency SOP, Greetings): Allowed for all users.
    3. User's Own Division Context:
       - HR (User B):
         - Employee Mutations: Target department (e.g. 'Finance & Accounting', 'Logistics', 'IT')
           and target position (e.g. 'Junior Billing', 'Warehouse Lead') are attributes of the employee,
           NOT access to Finance invoices or Logistics inventory. Always allowed.
         - Employee Directory: Inquiries about employees across any company department are HR's legitimate role.
         - Leave management, recruitment, candidate screening, K3 licenses are fully within HR scope.
       - Inventory (User A):
         - Checking inventory items, power/electrical materials (trafo, genset batteries, cables),
           or telecom site equipment is strictly Inventory scope.
         - Procurement PR/PO restock, goods receipt, safety stock thresholds are fully within Inventory scope.
       - Finance (User C):
         - Invoices, operator billing, cash flow, MLA contracts are strictly Finance scope.
         - Site land leases and utility bills (PLN electricity, genset fuel) for ANY facility
           (including warehouse land or logistics hubs) are legitimate Finance OPEX audit scope.
    4. Out-of-Scope Detection (Only blocks when PRIMARY INTENT is an unauthorized action in another domain):
       - If HR user attempts: Material restock PR/PO creation, or Telecom MLA billing/invoice generation.
       - If Inventory user attempts: Approving employee leave, candidate recruitment screening, or Telecom invoice generation.
       - If Finance user attempts: Material restock PR/PO creation, or Approving employee leave/candidate screening.
    """
    if not prompt or not current_user:
        return None

    u_role = str(getattr(current_user, 'role', 'USER')).upper()
    u_tenant_raw = str(getattr(current_user, 'tenant_id', 'ALL')).upper()

    if u_role == "ADMIN" or u_tenant_raw in ["ALL", "ADMIN", "SUPERADMIN"]:
        return None

    norm_tenant = u_tenant_raw
    if norm_tenant in ["INVENTORY", "USERA", "TENANT_A"]:
        norm_tenant = "INVENTORY"
    elif norm_tenant in ["HR", "USERB", "TENANT_B"]:
        norm_tenant = "HR"
    elif norm_tenant in ["FINANCE", "USERC", "TENANT_C"]:
        norm_tenant = "FINANCE"

    lower_p = prompt.strip().lower()

    # Universal actions allowed for any authenticated user
    universal_keywords = [
        "profil", "siapa saya", "info akun", "hak akses", "role saya", "wewenang saya",
        "status sistem", "status server", "health check", "kesehatan sistem",
        "panduan darurat", "kontak darurat", "sop operasional", "helpdesk",
        "halo", "hai", "hi", "selamat", "terima kasih", "thanks"
    ]
    if any(uk in lower_p for uk in universal_keywords):
        return None

    # Primary Action & Subject Detectors (Whole Context)
    
    # 1. HR Domain Detectors
    is_hr_mutation = (
        any(w in lower_p for w in ["mutasi", "mutasikan", "pindahkan", "rotasi"]) and
        any(w in lower_p for w in ["karyawan", "pegawai", "staf", "teknisi", "departemen", "divisi", "jabatan", "posisi", "sebagai", "ke", "budi", "dewi", "ahmad", "dedi"])
    )
    is_hr_employee_query = (
        any(w in lower_p for w in ["karyawan", "pegawai", "staf", "teknisi", "personalia", "sdm"]) and
        any(w in lower_p for w in ["daftar", "siapa", "berapa", "jumlah", "profil", "status", "data", "cari", "tampilkan", "lihat", "cek"]) and
        not any(w in lower_p for w in ["buatkan pr", "bikin pr", "restock", "draf pr", "draft pr", "po-", "purchase order"])
    )
    is_hr_leave_action = (
        ("cuti" in lower_p or "izin kerja" in lower_p) and
        any(w in lower_p for w in ["ajukan", "buat", "submit", "setujui", "approve", "tolak", "reject", "saldo", "kuota", "permohonan", "status", "otorisasi"])
    )
    is_hr_recruitment_action = (
        any(w in lower_p for w in ["kandidat", "pelamar", "rigger", "tkpk", "screening", "lowongan", "job_postings", "rekrutmen"])
    )
    is_primary_hr = is_hr_mutation or is_hr_employee_query or is_hr_leave_action or is_hr_recruitment_action

    # 2. Inventory Domain Detectors
    is_inv_procurement_action = (
        any(w in lower_p for w in ["buatkan pr", "bikin pr", "draf pr", "draft pr", "restock", "pesan material", "pengadaan barang", "pengadaan material", "terbitkan pr"])
    )
    is_inv_stock_query = (
        any(w in lower_p for w in ["stok", "persediaan", "saldo barang", "ketersediaan", "material"]) and
        any(w in lower_p for w in ["cek", "berapa", "tampilkan", "lihat", "sisa", "kritis", "menipis", "daftar"]) and
        not any(w in lower_p for w in ["cuti", "karyawan", "pegawai", "invoice", "tagihan sewa"])
    )
    is_inv_receipt_action = (
        any(w in lower_p for w in ["penerimaan barang", "catat penerimaan", "barang tiba", "barang sudah sampai", "barang sampai", "terima po", "konfirmasi penerimaan"])
    )
    is_inv_threshold_action = (
        any(w in lower_p for w in ["threshold", "ambang batas", "batas minimum", "batas stok", "safety stock"]) and
        any(w in lower_p for w in ["ubah", "ganti", "update", "atur", "set", "edit"])
    )
    is_primary_inv = is_inv_procurement_action or is_inv_stock_query or is_inv_receipt_action or is_inv_threshold_action

    # 3. Finance Domain Detectors
    is_fin_invoice_action = (
        any(w in lower_p for w in ["invoice", "tagihan sewa", "tagihan operator", "faktur", "billing"]) and
        any(w in lower_p for w in ["buat", "terbitkan", "draf", "draft", "generate", "cetak", "laporan", "rekap", "cek", "status"]) and
        not any(w in lower_p for w in ["mutasi", "karyawan", "pegawai"])
    )
    is_fin_revenue_action = (
        any(w in lower_p for w in [
            "laporan pendapatan", "pendapatan sewa", "sewa menara", "rekapitulasi pendapatan",
            "arus kas", "cash flow", "kontrak mla", "mla_contracts"
        ])
    )
    is_fin_opex_action = (
        any(w in lower_p for w in [
            "sewa lahan", "biaya sewa lahan", "beban listrik", "listrik pln",
            "audit beban listrik", "beban pengeluaran", "biaya operasional site", "genset fuel"
        ])
    )
    is_fin_onboarding_action = (
        any(w in lower_p for w in ["onboarding klien", "onboarding operator", "daftarkan operator baru", "kontrak sewa baru", "daftarkan klien"])
    )
    is_primary_fin = is_fin_invoice_action or is_fin_revenue_action or is_fin_opex_action or is_fin_onboarding_action

    # Multi-Tenant Resolution
    # A. User is HR
    if norm_tenant == "HR":
        if is_primary_hr:
            return None
        if is_inv_procurement_action or is_inv_receipt_action or is_inv_threshold_action:
            return {
                "parsed_intent": {"workflow_id": "tenant_boundary_restricted"},
                "action_type": "out_of_scope",
                "message": f"Akses Ditolak: Permintaan ini di luar ranah kewenangan Anda. Akun Anda ({current_user.username}) terdaftar khusus untuk Divisi {current_user.tenant_id}. Anda tidak memiliki akses ke alur kerja Schema A (Divisi Logistik / Material Gudang) perusahaan.",
                "generated_prs": [],
                "affected_items": []
            }
        if is_fin_invoice_action or is_fin_revenue_action or is_fin_opex_action or is_fin_onboarding_action:
            return {
                "parsed_intent": {"workflow_id": "tenant_boundary_restricted"},
                "action_type": "out_of_scope",
                "message": f"Akses Ditolak: Akun Anda ({current_user.username} - Divisi {u_tenant_raw}) tidak memiliki izin mengakses data Schema C (Divisi Keuangan). Akses ini dilindungi dan hanya dapat dibuka oleh staf Divisi Keuangan atau Super Administrator.",
                "generated_prs": [],
                "affected_items": []
            }

    # B. User is INVENTORY
    elif norm_tenant == "INVENTORY":
        if is_primary_inv:
            return None
        if is_hr_leave_action or is_hr_recruitment_action or is_hr_mutation:
            return {
                "parsed_intent": {"workflow_id": "tenant_boundary_restricted"},
                "action_type": "out_of_scope",
                "message": f"Akses Ditolak: Permintaan ini di luar ranah kewenangan Anda. Akun Anda ({current_user.username}) terdaftar khusus untuk Divisi {current_user.tenant_id}. Anda tidak memiliki akses ke alur kerja Schema B (Divisi HR) perusahaan.",
                "generated_prs": [],
                "affected_items": []
            }
        if is_fin_invoice_action or is_fin_revenue_action or is_fin_opex_action or is_fin_onboarding_action:
            return {
                "parsed_intent": {"workflow_id": "tenant_boundary_restricted"},
                "action_type": "out_of_scope",
                "message": f"Akses Ditolak: Akun Anda ({current_user.username} - Divisi {u_tenant_raw}) tidak memiliki izin mengakses data Schema C (Divisi Keuangan). Akses ini dilindungi dan hanya dapat dibuka oleh staf Divisi Keuangan atau Super Administrator.",
                "generated_prs": [],
                "affected_items": []
            }

    # C. User is FINANCE
    elif norm_tenant == "FINANCE":
        if is_primary_fin:
            return None
        if is_inv_procurement_action or is_inv_receipt_action or is_inv_threshold_action:
            return {
                "parsed_intent": {"workflow_id": "tenant_boundary_restricted"},
                "action_type": "out_of_scope",
                "message": f"Akses Ditolak: Permintaan ini di luar ranah kewenangan Anda. Akun Anda ({current_user.username}) terdaftar khusus untuk Divisi {current_user.tenant_id}. Anda tidak memiliki akses ke alur kerja Schema A (Divisi Logistik / Material Gudang) perusahaan.",
                "generated_prs": [],
                "affected_items": []
            }
        if is_hr_leave_action or is_hr_recruitment_action or is_hr_mutation:
            return {
                "parsed_intent": {"workflow_id": "tenant_boundary_restricted"},
                "action_type": "out_of_scope",
                "message": f"Akses Ditolak: Permintaan ini di luar ranah kewenangan Anda. Akun Anda ({current_user.username}) terdaftar khusus untuk Divisi {current_user.tenant_id}. Anda tidak memiliki akses ke alur kerja Schema B (Divisi HR) perusahaan.",
                "generated_prs": [],
                "affected_items": []
            }

    return None


async def execute_prompt_logic(
    request: CustomPromptRequest,
    current_user: TokenData,
    stage_callback = None
) -> dict:
    if not request.prompt.strip():
        raise HTTPException(status_code=400, detail="Prompt tidak boleh kosong.")

    from agents.router import extract_recipient_email, check_clarification_needs

    # 0. Context Merge: If user is responding directly to a previous clarification question
    if request.history and len(request.history) >= 1:
        last_turn = request.history[-1]
        last_content = str(last_turn.get("content", "")).lower()
        # Case A: Email clarification response
        if any(kw in last_content for kw in ["alamat email", "penerima belum disebutkan", "email tujuan"]):
            new_email = extract_recipient_email(request.prompt)
            if new_email:
                prev_user_prompt = None
                for turn in reversed(request.history[:-1]):
                    if turn.get("role") == "user":
                        prev_user_prompt = str(turn.get("content", "")).strip()
                        break
                if prev_user_prompt:
                    merged = re.sub(r'\bke\s+email\b', f'ke {new_email}', prev_user_prompt, flags=re.IGNORECASE)
                    if new_email not in merged:
                        merged = f"{merged.rstrip('. ')} ke {new_email}"
                    request.prompt = merged
        # Case B: Threshold item or value clarification response
        elif "batas minimum" in last_content or "ambang batas" in last_content:
            prev_user_prompt = None
            for turn in reversed(request.history[:-1]):
                if turn.get("role") == "user":
                    prev_user_prompt = str(turn.get("content", "")).strip()
                    break
            if prev_user_prompt and len(request.prompt.split()) <= 4:
                request.prompt = f"{prev_user_prompt.rstrip('. ')} {request.prompt.strip()}"

    lower_prompt = request.prompt.strip().lower()

    if stage_callback:
        await stage_callback("analyze", "Menganalisis instruksi & hak akses wewenang...")

    # 0. Security Guardrail: Pre-Execution Prompt Injection & Destructive Command Check
    from agents.autonomous_agent import AutonomousAgent
    is_safe, refusal_msg = AutonomousAgent.check_prompt_injection_guardrail(request.prompt)
    if not is_safe:
        return {
            "parsed_intent": {"workflow_id": "security_guardrail_refusal"},
            "action_type": "security_refusal",
            "message": refusal_msg,
            "generated_prs": [],
            "affected_items": []
        }

    # 0.5 Domain Scope Guardrail: Pre-Execution Out-of-Domain Filter
    is_out_of_domain, domain_refusal_msg = AutonomousAgent.check_domain_boundary(request.prompt)
    if is_out_of_domain:
        return {
            "parsed_intent": {"workflow_id": "out_of_domain_refusal"},
            "action_type": "out_of_scope",
            "message": domain_refusal_msg,
            "generated_prs": [],
            "affected_items": [],
            "can_request_admin": False,
            "prompt_text": request.prompt
        }

    u_tenant = str(getattr(current_user, 'tenant_id', 'ALL')).upper()
    u_role = str(getattr(current_user, 'role', 'USER')).upper()

    # 0.7 Check if user directly requests to open/render the interactive workflow proposal form in chat
    is_interactive_form_request = (
        bool(re.search(r'\b(mau\s+ajukan|ingin\s+ajukan|ajukan|request|buka\s+form|form\s+pengajuan|formulir)\s+(alur\s+kerja|workflow)\b', lower_prompt))
        and not any(task_kw in lower_prompt for task_kw in ["untuk", "rekap", "audit", "restock", "laporan", "otomatisasi", "vendor"])
    ) or lower_prompt.strip() in [
        "mau ajukan workflow", "ajukan workflow", "request workflow", "form workflow",
        "form pengajuan workflow", "formulir workflow", "mau ajukan alur kerja",
        "ajukan alur kerja", "request alur kerja", "buka form workflow", "workflow request",
        "buka form pengajuan workflow", "tampilkan form workflow"
    ]

    if is_interactive_form_request:
        return {
            "parsed_intent": {"workflow_id": "render_workflow_request_form"},
            "action_type": "render_workflow_request_form",
            "message": "Silakan lengkapi formulir pengajuan alur kerja baru di bawah ini. Usulan Anda akan langsung diteruskan ke antrean Administrator untuk ditinjau dan dikompilasi.",
            "prompt_text": request.prompt,
            "can_request_admin": True,
            "user_tenant": u_tenant,
            "user_role": u_role,
            "generated_prs": [],
            "affected_items": []
        }

    # 0.8 Check if user is asking to create/register a new workflow but lacks admin authority
    is_create_workflow_request = (
        bool(re.search(r'\b(buat|bikin|create|tambah|daftarkan|ajukan)\s+(alur\s+kerja|workflow)\b', lower_prompt))
        or bool(re.search(r'\b(workflow|alur kerja)\s+(baru|belum ada)\b', lower_prompt))
        or bool(re.search(r'\b(saya\s+butuh|perlu)\s+(alur\s+kerja|workflow)\b', lower_prompt))
    )
    if is_create_workflow_request and u_role != "ADMIN":
        return {
            "parsed_intent": {"workflow_id": "workflow_not_found"},
            "action_type": "workflow_not_found",
            "message": "Pembuatan alur kerja baru merupakan wewenang khusus Administrator. Anda dapat mengajukan permohonan alur kerja ini langsung ke Administrator agar dapat ditinjau dan dikompilasi.",
            "prompt_text": request.prompt,
            "can_request_admin": True,
            "generated_prs": [],
            "affected_items": []
        }

    # 1. Proactive Clarification Check
    clarif = check_clarification_needs(
        request.prompt,
        tenant_id=current_user.tenant_id if current_user else "ALL",
        recipient_email=request.recipient_email
    )
    if clarif:
        return {
            "parsed_intent": {"workflow_id": "clarification_needed"},
            "action_type": "clarification_needed",
            "needs_clarification": True,
            "message": clarif["message"],
            "clarification": clarif,
            "generated_prs": [],
            "affected_items": []
        }

    # 2. Specialized Goods Receipt Process (PO arrival at warehouse)
    gr_result = process_goods_receipt(request.prompt, current_user)
    if gr_result:
        return gr_result

    # 3. Multi-Tenant Context-Aware Boundary Guard
    tenant_boundary_violation = evaluate_contextual_tenant_boundary(request.prompt, current_user)
    if tenant_boundary_violation:
        return tenant_boundary_violation

    # 4. Primary: Match User Prompt to Admin-Created / Predefined Workflows
    from agents.router import SemanticRouter
    from agents.json_executor import JSONExecutionEngine
    from database.db import get_db_connection

    routing_res = await SemanticRouter.route_prompt(
        prompt=request.prompt,
        tenant_id=u_tenant,
        history=request.history
    )

    wf_id = routing_res.get("workflow_id") if isinstance(routing_res, dict) else None

    # Handle unregistered mutation / workflow proposal requirement
    if isinstance(routing_res, dict) and routing_res.get("action_type") == "workflow_not_found":
        msg = routing_res.get("message") or "Alur kerja untuk instruksi ini belum terdaftar di sistem operasional BaliTower."
        return {
            "parsed_intent": {"workflow_id": None},
            "action_type": "workflow_not_found",
            "message": msg,
            "can_request_admin": True,
            "prompt_text": request.prompt,
            "is_tool_blocked": True,
            "generated_prs": [],
            "prs": [],
            "affected_items": []
        }

    # Handle LLM-determined clarification requirement
    if isinstance(routing_res, dict) and (routing_res.get("needs_clarification") or wf_id == "clarification_needed"):
        clarif = routing_res.get("clarification") or {
            "title": "Klarifikasi Diperlukan",
            "message": routing_res.get("message", "Mohon lengkapi parameter instruksi Anda."),
            "hint": request.prompt
        }
        return {
            "parsed_intent": {"workflow_id": "clarification_needed"},
            "action_type": "clarification_needed",
            "message": clarif.get("message", "Mohon lengkapi parameter instruksi Anda."),
            "clarification": clarif,
            "generated_prs": [],
            "affected_items": []
        }

    if wf_id:
        conn = get_db_connection(read_only=True)
        row = None
        try:
            row = conn.execute("SELECT id, name, description, business_instruction, compiled_json, tenant_id FROM workflows WHERE id = ?", [wf_id]).fetchone()
        finally:
            conn.close()

        if row:
            wf_id_db, wf_name, wf_desc, wf_inst, wf_compiled_raw, wf_tenant = row
            try:
                compiled_json = json.loads(wf_compiled_raw) if isinstance(wf_compiled_raw, str) else wf_compiled_raw
            except Exception:
                compiled_json = {}

            if stage_callback:
                await stage_callback("plan", f"Memilih workflow: '{wf_name}' ({wf_id})...")

            custom_context = {
                "prompt": request.prompt,
                "username": current_user.username if current_user else "user",
                "role": current_user.role if current_user else "USER",
                "tenant_id": u_tenant,
                "recipient_email": request.recipient_email or routing_res.get("recipient_email"),
                "send_email": routing_res.get("send_email", False),
                "new_item_data": routing_res.get("new_item_data"),
                "threshold_updates": routing_res.get("threshold_updates", []),
                "target_item_name": routing_res.get("target_item_name"),
                "workflow_id": wf_id,
                "workflow_name": wf_name,
                "user_info": {
                    "username": current_user.username if current_user else "user",
                    "role": current_user.role if current_user else "USER",
                    "tenant_id": u_tenant
                }
            }

            if stage_callback:
                await stage_callback("execute", f"Mengeksekusi tahapan alur kerja '{wf_name}'...")

            exec_result = await JSONExecutionEngine.execute(
                compiled_json=compiled_json,
                tenant_id=u_tenant,
                custom_context=custom_context
            )

            target_po_id = exec_result.get("target_po_id") or custom_context.get("target_po_id")
            target_po_num = exec_result.get("target_po_number") or custom_context.get("target_po_number")
            
            is_hr_tenant = u_tenant in ["HR", "TENANT_B", "userb"]
            is_fin_tenant = u_tenant in ["FINANCE", "TENANT_C", "userc"]

            str_compiled = str(compiled_json).lower()
            if is_hr_tenant:
                if (
                    exec_result.get("action_type") == "hr_mutation"
                    or exec_result.get("mutated_employee")
                    or any(k in str_compiled for k in ["mutasi", "mutate", "employment_status", "status kerja", "status kepegawaian"])
                ):
                    action_type = "hr_mutation"
                elif exec_result.get("leave_id") or "leave" in str_compiled or "cuti" in str_compiled:
                    action_type = "hr_leave"
                else:
                    action_type = "hr_query"
                target_po_id = None
                target_po_num = None
            elif is_fin_tenant:
                if exec_result.get("onboarding_id") or "onboard" in str_compiled:
                    action_type = "finance_onboarding"
                else:
                    action_type = "finance_query"
                target_po_id = None
                target_po_num = None
            elif (
                exec_result.get("action_type") == "hr_mutation" 
                or exec_result.get("mutated_employee") 
                or any(k in str_compiled for k in ["mutasi", "mutate", "employment_status", "status kerja", "status kepegawaian"])
            ):
                action_type = "hr_mutation"
            elif "view_po" in str_compiled or target_po_id:
                action_type = "view_po_document"
            elif exec_result.get("onboarding_id") or "onboard" in str_compiled:
                action_type = "finance_onboarding"
            elif wf_id in ["WF-C01", "WF-C02", "WF-C04", "WF-004", "WF-005"] or "finance.revenue_report" in str_compiled or "finance.opex_audit" in str_compiled or "finance.cashflow_summary" in str_compiled:
                action_type = "finance_query"
            elif wf_id in ["WF-B02", "WF-B03", "WF-B04", "WF-003"] or "hr.filter_candidates" in str_compiled or "hr.audit_attendance" in str_compiled or "pending_leaves" in custom_context:
                action_type = "hr_query"
            elif wf_id in ["WF-ALL-01", "WF-ALL-02", "WF-ALL-03"] or "system.check_profile" in str_compiled or "system.get_system_info" in str_compiled or "system.get_company_guidelines" in str_compiled:
                action_type = "general"
            elif exec_result.get("registered_item") or "register_product" in str_compiled:
                action_type = "register_product"
            elif "update_threshold" in str_compiled:
                action_type = "update_threshold"
            elif exec_result.get("pr_number") or ("restock" in str_compiled and not exec_result.get("registered_item")):
                action_type = "review_prs"
            else:
                action_type = "workflow_execution"

            prs_list = []
            if not is_hr_tenant and not is_fin_tenant:
                pr_num = exec_result.get("pr_number")
                if pr_num:
                    from api.routers.approval_routes import PR_STORE, _ensure_pr_in_store
                    pr_doc = _ensure_pr_in_store(pr_num)
                    if pr_doc:
                        prs_list = [{
                            "pr_number": pr_doc.pr_number,
                            "supplier_name": "Multiple Vendors" if len(set(it.vendor_name for it in pr_doc.items)) > 1 else (pr_doc.items[0].vendor_name if pr_doc.items else "Vendor"),
                            "grand_total": pr_doc.total_budget,
                            "total_budget": pr_doc.total_budget,
                            "status": pr_doc.status.lower(),
                            "email_sent": exec_result.get("email_sent", False),
                            "items": [{"item_name": it.name, "quantity": it.reorder_qty, "unit": it.unit} for it in pr_doc.items]
                        }]
                    else:
                        ctx = exec_result.get("context", {})
                        items = ctx.get("planned_orders") or ctx.get("pr_items") or []
                        formatted_items = []
                        for it in items:
                            if hasattr(it, "item_name"):
                                formatted_items.append({"item_name": it.item_name, "quantity": getattr(it, "quantity", 1), "unit": getattr(it, "unit", "pcs")})
                            elif isinstance(it, dict):
                                formatted_items.append({"item_name": it.get("item_name") or it.get("name"), "quantity": it.get("quantity") or it.get("reorder_qty", 1), "unit": it.get("unit", "pcs")})
                        prs_list = [{
                            "pr_number": pr_num,
                            "supplier_name": "Vendor Terdaftar",
                            "grand_total": exec_result.get("total_budget", 0),
                            "total_budget": exec_result.get("total_budget", 0),
                            "status": "pending",
                            "email_sent": exec_result.get("email_sent", False),
                            "items": formatted_items
                        }]

            return {
                "parsed_intent": {"workflow_id": wf_id, "workflow_name": wf_name},
                "action_type": action_type,
                "message": exec_result.get("summary", ""),
                "email_sent": exec_result.get("email_sent", False),
                "generated_prs": prs_list,
                "prs": prs_list,
                "affected_items": exec_result.get("affected_items", []),
                "total_items_analyzed": exec_result.get("total_items_analyzed", len(exec_result.get("affected_items", []))),
                "target_destinations": exec_result.get("target_destinations", ["database"]),
                "pdf_download_url": exec_result.get("pdf_download_url") if not is_hr_tenant else (exec_result.get("pdf_download_url") if "leave" in str(exec_result.get("pdf_download_url", "")) else None),
                "po_id": target_po_id,
                "po_number": target_po_num,
                "onboarding_id": exec_result.get("onboarding_id"),
                "client_name": exec_result.get("client_name"),
                "site_id": exec_result.get("site_id"),
                "total_billed": exec_result.get("total_billed", 0),
                "leave_id": exec_result.get("leave_id"),
                "applicant_name": exec_result.get("applicant_name"),
                "leave_type": exec_result.get("leave_type"),
                "days_requested": exec_result.get("days_requested"),
                "mutated_employee": exec_result.get("mutated_employee"),
                "execution_steps": exec_result.get("execution_steps", []),
                "total_budget_formatted": exec_result.get("total_budget_formatted", "Rp 0")
            }

    # 6. Fallback: Core Autonomous Agent Reasoning & Execution (for ad-hoc queries / free-form)
    from agents.autonomous_agent import AutonomousAgent
    agent_result = await AutonomousAgent.run(
        prompt=request.prompt,
        current_user=current_user,
        stage_callback=stage_callback,
        history=request.history
    )

    can_propose = classify_workflow_proposal_eligibility(
        prompt=request.prompt,
        agent_result=agent_result,
        user_role=getattr(current_user, "role", "USER")
    )

    final_action_type = agent_result.get("action_type", "general")
    if can_propose and final_action_type not in ["render_workflow_request_form", "workflow_not_found"]:
        final_action_type = "workflow_not_found"

    dashboard_response = {
        "parsed_intent": agent_result.get("parsed_intent", {"workflow_id": "autonomous_agent"}),
        "action_type": final_action_type,
        "message": agent_result.get("message", ""),
        "email_sent": agent_result.get("email_sent", False),
        "generated_prs": agent_result.get("generated_prs", []),
        "prs": agent_result.get("prs", []),
        "affected_items": agent_result.get("affected_items", []),
        "total_items_analyzed": agent_result.get("total_items_analyzed", len(agent_result.get("affected_items", []))),
        "target_destinations": agent_result.get("target_destinations", ["database"]),
        "pdf_download_url": agent_result.get("pdf_download_url"),
        "po_id": agent_result.get("po_id"),
        "po_number": agent_result.get("po_number"),
        "onboarding_id": agent_result.get("onboarding_id"),
        "client_name": agent_result.get("client_name"),
        "site_id": agent_result.get("site_id"),
        "total_billed": agent_result.get("total_billed", 0),
        "leave_id": agent_result.get("leave_id"),
        "applicant_name": agent_result.get("applicant_name"),
        "leave_type": agent_result.get("leave_type"),
        "days_requested": agent_result.get("days_requested"),
        "execution_steps": agent_result.get("execution_steps", []),
        "total_budget_formatted": agent_result.get("total_budget_formatted", "Rp 0"),
        "can_request_admin": can_propose,
        "is_tool_blocked": True if can_propose else agent_result.get("is_tool_blocked", False),
        "prompt_text": request.prompt
    }

    if agent_result.get("generated_prs") and not dashboard_response["prs"]:
        dashboard_response["prs"] = agent_result["generated_prs"]

    return dashboard_response




@router.post("/api/agent/custom-prompt")
async def execute_custom_prompt_workflow(request: CustomPromptRequest, current_user: TokenData = Depends(get_current_user)):
    """
    Accepts free-form natural language instructions from non-technical users,
    synthesizes a custom multi-agent workflow, executes actions, and dispatches outputs.
    """
    return await execute_prompt_logic(request, current_user)


@router.post("/api/agent/stream-prompt")
async def execute_custom_prompt_workflow_stream(request: CustomPromptRequest, current_user: TokenData = Depends(get_current_user)):
    """
    Real-Time SSE Streaming Endpoint for interactive Chat Dashboard (TTPS Optimization).
    Streams live stage status badges, clarification questions, token-by-token content,
    and final rich interactive dashboard response card.
    """
    async def event_generator():
        stages_queue = asyncio.Queue()

        async def stage_cb(stage: str, message: str):
            await stages_queue.put({"type": "status", "stage": stage, "message": message})

        # 1. Instant Initial Stage Badge (TTPS < 20ms)
        yield f"data: {json.dumps({'type': 'status', 'stage': 'analyze', 'message': 'Menganalisis instruksi & hak akses wewenang...'})}\n\n"

        # 2. Asynchronous execution with real-time stage forwarding
        task = asyncio.create_task(execute_prompt_logic(request, current_user, stage_callback=stage_cb))

        while not task.done():
            try:
                stage_msg = await asyncio.wait_for(stages_queue.get(), timeout=0.08)
                yield f"data: {json.dumps(stage_msg)}\n\n"
            except asyncio.TimeoutError:
                pass

        # Drain any remaining stage events
        while not stages_queue.empty():
            stage_msg = stages_queue.get_nowait()
            yield f"data: {json.dumps(stage_msg)}\n\n"

        try:
            result = await task
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
            return

        # 3. Clarification event if parameters missing
        if result.get("action_type") == "clarification_needed":
            yield f"data: {json.dumps({'type': 'clarification', 'clarification': result.get('clarification'), 'message': result.get('message')})}\n\n"

        # 4. Token-by-token streaming for ultra-fluid typing effect
        msg = result.get("message", "")
        if msg:
            words = msg.split(" ")
            for i, w in enumerate(words):
                token = w + (" " if i < len(words) - 1 else "")
                yield f"data: {json.dumps({'type': 'token', 'content': token})}\n\n"
                await asyncio.sleep(0.01)

        # 5. Final complete event with rich interactive payload
        yield f"data: {json.dumps({'type': 'complete', 'payload': result})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.get("/api/agent/prompt-templates")
def get_prompt_templates():
    """
    Returns curated 1-click prompt templates for non-technical users tailored to Bali Tower.
    """
    return [
        {
            "id": 1,
            "title": "Cek Stok Kritis & Buat Draf PR",
            "prompt": "Periksa stok material menara yang menipis dan buatkan draf Purchase Requisition (PR)."
        },
        {
            "id": 2,
            "title": "Catat Penerimaan Barang PO Tiba",
            "prompt": "Barang untuk PO-2026-006 sudah sampai di Gudang Bandung, tolong catat penerimaannya."
        },
        {
            "id": 3,
            "title": "Lihat & Unduh Dokumen PO Resmi",
            "prompt": "Tolong tampilkan dokumen PDF untuk PO-2026-006."
        },
        {
            "id": 4,
            "title": "Filter Pelamar Rigger K3 TKPK",
            "prompt": "Saring kandidat pelamar posisi Rigger / Tower Climber yang memiliki sertifikasi K3 TKPK aktif dan berstatus layak naik menara (Fit for Height)."
        },
        {
            "id": 5,
            "title": "Pengajuan Cuti Teknisi Menara",
            "prompt": "Ajukan cuti tahunan 3 hari untuk teknisi Budi Santoso mulai besok."
        },
        {
            "id": 6,
            "title": "Laporan Pemasukan Sewa Menara",
            "prompt": "Tampilkan ringkasan pendapatan sewa menara dari operator Telkomsel, XL, dan Indosat beserta piutang invoice yang belum dibayar."
        },
        {
            "id": 7,
            "title": "Biaya Listrik PLN & Sewa Lahan",
            "prompt": "Tampilkan rincian pengeluaran beban operasional untuk tagihan listrik PLN shelter dan sewa lahan lokasi menara per site."
        },
        {
            "id": 8,
            "title": "Ringkasan Arus Kas Operasional",
            "prompt": "Berapa total kas masuk (inflow) versus kas keluar (outflow) dan surplus kas bersih operasional saat ini?"
        }
    ]



@router.get("/api/agent/tools", tags=["Agent Configuration"])
def get_agent_tools():
    '''
    Returns the comprehensive list of tools (APIs) available to the AI model
    for executing autonomous workflows.
    '''
    return {
        "status": "success",
        "available_tools": [
            # 1. INVENTORY OPERATIONS
            {
                "tool_name": "inventory.check_specific_stock",
                "description": "Memeriksa saldo fisik barang spesifik pada gudang regional (Jakarta, Bandung, Surabaya, dll).",
                "access_tier": "DIRECT_ACCESS",
                "category": "Inventory Operations"
            },
            {
                "tool_name": "inventory.get_low_stock_products",
                "description": "Mengidentifikasi material yang berada di bawah ambang batas aman (safety stock).",
                "access_tier": "DIRECT_ACCESS",
                "category": "Inventory Operations"
            },
            {
                "tool_name": "inventory.get_all_products",
                "description": "Mengambil seluruh data katalog master inventaris menara dan fiber optic untuk audit.",
                "access_tier": "DIRECT_ACCESS",
                "category": "Inventory Operations"
            },
            {
                "tool_name": "po.query_orders",
                "description": "Melacak status daftar Purchase Order aktif, nomor PO, vendor, dan progres pengiriman.",
                "access_tier": "DIRECT_ACCESS",
                "category": "Inventory Operations"
            },
            {
                "tool_name": "inventory.update_threshold",
                "description": "Menyesuaikan batas minimum (safety stock) dan batas maksimum kuantitas barang gudang.",
                "access_tier": "GUARDED_WORKFLOW",
                "category": "Inventory Operations"
            },
            {
                "tool_name": "inventory.register_product",
                "description": "Mendaftarkan item SKU material baru ke dalam master katalog inventaris perusahaan.",
                "access_tier": "GUARDED_WORKFLOW",
                "category": "Inventory Operations"
            },
            {
                "tool_name": "purchase_order.create_draft",
                "description": "Menyusun draf dokumen Purchase Requisition (PR) berdasarkan data kebutuhan stok kritis.",
                "access_tier": "GUARDED_WORKFLOW",
                "category": "Inventory Operations"
            },
            {
                "tool_name": "po.approve",
                "description": "Otorisasi pengesahan dokumen Purchase Order (PO) menjadi status APPROVED untuk vendor.",
                "access_tier": "GUARDED_WORKFLOW",
                "category": "Inventory Operations"
            },
            {
                "tool_name": "inventory.crud_record",
                "description": "Operasi CRUD basis data Inventaris & Logistik (Create, Read, Update, Delete untuk master item, stok gudang, supplier, dan PO).",
                "access_tier": "GUARDED_WORKFLOW",
                "category": "Inventory Operations"
            },

            # 2. HR & WORKFORCE OPERATIONS
            {
                "tool_name": "hr.filter_candidates",
                "description": "Penyaringan kandidat Rigger Menara berkualifikasi sertifikat K3 TKPK tingkat 1 atau tingkat 2.",
                "access_tier": "DIRECT_ACCESS",
                "category": "HR & Workforce"
            },
            {
                "tool_name": "hr.query_pending_leaves",
                "description": "Memeriksa dan merekap seluruh pengajuan cuti karyawan yang berstatus PENDING_APPROVAL.",
                "access_tier": "DIRECT_ACCESS",
                "category": "HR & Workforce"
            },
            {
                "tool_name": "hr.audit_attendance",
                "description": "Audit absensi GPS geofencing teknisi site tower dan perhitungan jam kerja lembur.",
                "access_tier": "DIRECT_ACCESS",
                "category": "HR & Workforce"
            },
            {
                "tool_name": "hr.mutate_employee",
                "description": "Melakukan mutasi posisi/jabatan dan departemen karyawan pada basis data master kepegawaian.",
                "access_tier": "GUARDED_WORKFLOW",
                "category": "HR & Workforce"
            },
            {
                "tool_name": "hr.approve_leave",
                "description": "Otorisasi permohonan cuti karyawan (APPROVED) dan pemotongan otomatis kuota saldo cuti tahunan.",
                "access_tier": "GUARDED_WORKFLOW",
                "category": "HR & Workforce"
            },
            {
                "tool_name": "hr.submit_leave_request",
                "description": "Merekam pengajuan cuti teknisi/karyawan baru ke dalam basis data DuckDB.",
                "access_tier": "GUARDED_WORKFLOW",
                "category": "HR & Workforce"
            },
            {
                "tool_name": "hr.crud_record",
                "description": "Operasi CRUD basis data SDM & Ketenagakerjaan (Create, Read, Update, Delete untuk kandidat K3, direktori karyawan, cuti, dan lowongan kerja).",
                "access_tier": "GUARDED_WORKFLOW",
                "category": "HR & Workforce"
            },

            # 3. FINANCE & COMMERCIAL OPERATIONS
            {
                "tool_name": "finance.revenue_report",
                "description": "Menampilkan rekapitulasi pendapatan sewa menara per operator, total tagihan terbit, pembayaran lunas, dan piutang (AR).",
                "access_tier": "DIRECT_ACCESS",
                "category": "Finance & Commercial"
            },
            {
                "tool_name": "finance.opex_audit",
                "description": "Audit transaksi beban operasional site (OPEX) termasuk listrik PLN, sewa lahan, dan bahan bakar genset.",
                "access_tier": "DIRECT_ACCESS",
                "category": "Finance & Commercial"
            },
            {
                "tool_name": "finance.cashflow_summary",
                "description": "Menghitung ringkasan arus kas operasional (Inflow vs Outflow) dan surplus kas bersih perusahaan.",
                "access_tier": "DIRECT_ACCESS",
                "category": "Finance & Commercial"
            },
            {
                "tool_name": "finance.audit_client_onboardings",
                "description": "Memeriksa daftar pengajuan sewa menara dan pendaftaran operator baru yang masih menunggu otorisasi persetujuan.",
                "access_tier": "DIRECT_ACCESS",
                "category": "Finance & Commercial"
            },
            {
                "tool_name": "finance.draft_client_onboarding",
                "description": "Menyusun draft pendaftaran klien operator baru & kontrak sewa menara (MLA) serta estimasi tagihan perdana untuk otorisasi.",
                "access_tier": "GUARDED_WORKFLOW",
                "category": "Finance & Commercial"
            },
            {
                "tool_name": "finance.approve_client_onboarding",
                "description": "Mengesahkan otorisasi onboarding operator: mengaktifkan klien, kontrak MLA aktif, dan faktur perdana.",
                "access_tier": "GUARDED_WORKFLOW",
                "category": "Finance & Commercial"
            },
            {
                "tool_name": "finance.generate_invoice",
                "description": "Menerbitkan draf faktur invoice penagihan sewa menara BTS resmi kepada operator telekomunikasi.",
                "access_tier": "GUARDED_WORKFLOW",
                "category": "Finance & Commercial"
            },
            {
                "tool_name": "finance.crud_record",
                "description": "Operasi CRUD basis data Keuangan & Komersial (Create, Read, Update, Delete untuk invoice, klien, kontrak MLA, sewa lahan, utilitas).",
                "access_tier": "GUARDED_WORKFLOW",
                "category": "Finance & Commercial"
            },

            # 4. DOCUMENT GENERATION
            {
                "tool_name": "docgen.compile",
                "description": "Mengompilasi berkas PDF Purchase Requisition (PR) resmi beresolusi tinggi menggunakan mesin Typst.",
                "access_tier": "GUARDED_WORKFLOW",
                "category": "Document Generation"
            },
            {
                "tool_name": "docgen.compile_po",
                "description": "Mengompilasi berkas resmi Purchase Order (PO) format PDF bertanda tangan dan berkop surat PT Bali Towerindo Sentra Tbk.",
                "access_tier": "GUARDED_WORKFLOW",
                "category": "Document Generation"
            },
            {
                "tool_name": "docgen.compile_leave_pdf",
                "description": "Mengompilasi dokumen resmi Surat Pengajuan Cuti karyawan ke format PDF Typst dengan kop surat resmi.",
                "access_tier": "GUARDED_WORKFLOW",
                "category": "Document Generation"
            },

            # 5. NOTIFICATION & DISPATCH
            {
                "tool_name": "notification.dispatch",
                "description": "Mendistribusikan notifikasi alert multi-channel dengan tautan verifikasi persetujuan.",
                "access_tier": "GUARDED_WORKFLOW",
                "category": "Notification & Dispatch"
            },
            {
                "tool_name": "notification.send_email",
                "description": "Mengirimkan email HTML resmi via SMTP kepada manajer operasional atau vendor eksternal.",
                "access_tier": "GUARDED_WORKFLOW",
                "category": "Notification & Dispatch"
            },

            # 6. REASONING & VALIDATION
            {
                "tool_name": "calculate_reorder_quantity",
                "description": "Kalkulasi matematis kuantitas restock optimal, burn rate, dan buffer persediaan pengadaan.",
                "access_tier": "DIRECT_ACCESS",
                "category": "Reasoning & Validation"
            },
            {
                "tool_name": "agent.reason_and_validate",
                "description": "Inferensi AI untuk memvalidasi kelayakan aturan bisnis dan kelengkapan parameter sebelum commit database.",
                "access_tier": "GUARDED_WORKFLOW",
                "category": "Reasoning & Validation"
            },

            # 7. SYSTEM & UNIVERSAL UTILITIES (SCHEMA ALL)
            {
                "tool_name": "system.check_profile",
                "description": "Pemeriksaan kredensial akun login, role pengguna, dan batasan partisi tenant aktif.",
                "access_tier": "DIRECT_ACCESS",
                "category": "System & Universal Utilities"
            },
            {
                "tool_name": "system.get_system_info",
                "description": "Audit status kesehatan layanan sistem, konektivitas DuckDB backend, dan gateway LLM.",
                "access_tier": "DIRECT_ACCESS",
                "category": "System & Universal Utilities"
            },
            {
                "tool_name": "system.get_company_guidelines",
                "description": "Menampilkan panduan SOP operasional dan kontak darurat NOC/Helpdesk PT Bali Towerindo Sentra Tbk.",
                "access_tier": "DIRECT_ACCESS",
                "category": "System & Universal Utilities"
            }
        ]
    }

