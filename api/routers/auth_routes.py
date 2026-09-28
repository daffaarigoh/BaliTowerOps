import asyncio
import json
import uuid
from datetime import timedelta
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field

from core.security import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    TokenData,
    create_access_token,
    get_current_admin,
    get_current_user,
    get_password_hash,
    verify_password,
)
from database.db import execute_db_write, get_db_connection

router = APIRouter(prefix="/api/auth", tags=["Authentication"])

WORKFLOWS_JSON_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "balitower" / "workflows.json"

class LoginRequest(BaseModel):
    username: str
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str
    role: str
    tenant_id: str


@router.post("/login", response_model=Token)
async def login(req: LoginRequest):
    conn = get_db_connection(read_only=True)
    row = conn.execute(
        "SELECT username, password_hash, role, tenant_id FROM users WHERE username = ?",
        [req.username]
    ).fetchone()
    conn.close()

    if not row:
        raise HTTPException(status_code=401, detail="Incorrect username or password")

    username, password_hash, role, tenant_id = row
    is_valid = await asyncio.to_thread(verify_password, req.password, password_hash)
    if not is_valid:
        raise HTTPException(status_code=401, detail="Incorrect username or password")

    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": username, "role": role, "tenant_id": tenant_id},
        expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer", "role": role, "tenant_id": tenant_id}


@router.get("/me")
async def get_me(current_user: TokenData = Depends(get_current_user)):
    return {"username": current_user.username, "role": current_user.role, "tenant_id": current_user.tenant_id}



def _sync_workflows_to_json(conn):
    """Export current workflows table to data/balitower/workflows.json so it is tracked in Git."""
    try:
        rows = conn.execute("SELECT id, name, description, business_instruction, compiled_json, tenant_id, example_prompts FROM workflows ORDER BY id ASC").fetchall()
        columns = [desc[0] for desc in conn.description]
        workflows = []
        for r in rows:
            wf = dict(zip(columns, r))
            try:
                wf["compiled_json"] = json.loads(wf["compiled_json"])
            except:
                pass
            if isinstance(wf.get("example_prompts"), str):
                try:
                    wf["example_prompts"] = json.loads(wf["example_prompts"])
                except:
                    wf["example_prompts"] = []
            elif not wf.get("example_prompts"):
                wf["example_prompts"] = []
            workflows.append(wf)
        WORKFLOWS_JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(WORKFLOWS_JSON_PATH, "w", encoding="utf-8") as f:
            json.dump(workflows, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[AUTH] Failed to sync workflows to JSON: {e}")


def _sync_workflows_from_json_if_empty(conn):
    """Populate workflows from data/balitower/workflows.json if table is empty or missing specific workflows."""
    try:
        if WORKFLOWS_JSON_PATH.exists():
            with open(WORKFLOWS_JSON_PATH, "r", encoding="utf-8") as f:
                workflows = json.load(f)
            existing_ids = set(r[0] for r in conn.execute("SELECT id FROM workflows;").fetchall())
            existing_names = set(r[0].strip().lower() for r in conn.execute("SELECT name FROM workflows;").fetchall() if r[0])
            for wf in workflows:
                wf_name = (wf.get("name") or "").strip().lower()
                if wf["id"] not in existing_ids and wf_name not in existing_names:
                    compiled_str = json.dumps(wf["compiled_json"]) if isinstance(wf.get("compiled_json"), dict) else str(wf.get("compiled_json", "{}"))
                    ex_prompts_str = json.dumps(wf.get("example_prompts", []), ensure_ascii=False)
                    conn.execute(
                        "INSERT INTO workflows (id, name, description, business_instruction, compiled_json, tenant_id, example_prompts) VALUES (?, ?, ?, ?, ?, ?, ?)",
                        [wf["id"], wf["name"], wf.get("description", ""), wf.get("business_instruction", ""), compiled_str, wf.get("tenant_id", "ALL"), ex_prompts_str]
                    )
                    existing_names.add(wf_name)
                    existing_ids.add(wf["id"])
    except Exception as e:
        pass


def _ensure_workflow_tenant_column(conn):
    """Ensure the workflows table has the tenant_id and example_prompts columns, and seeds from workflows.json."""
    try:
        cols = [r[0] for r in conn.execute("DESCRIBE workflows;").fetchall()]
        if "tenant_id" not in cols:
            conn.execute("ALTER TABLE workflows ADD COLUMN tenant_id VARCHAR DEFAULT 'ALL';")
        if "example_prompts" not in cols:
            conn.execute("ALTER TABLE workflows ADD COLUMN example_prompts TEXT DEFAULT '[]';")
            
        _sync_workflows_from_json_if_empty(conn)

        # Migrate and populate example_prompts from workflows.json if rows have empty example_prompts
        if WORKFLOWS_JSON_PATH.exists():
            with open(WORKFLOWS_JSON_PATH, "r", encoding="utf-8") as f:
                seed_wfs = json.load(f)
            for wf in seed_wfs:
                ex_list = wf.get("example_prompts", [])
                if ex_list:
                    ex_str = json.dumps(ex_list, ensure_ascii=False)
                    conn.execute("""
                        UPDATE workflows 
                        SET example_prompts = ? 
                        WHERE id = ? AND (example_prompts IS NULL OR example_prompts = '[]' OR example_prompts = '')
                    """, [ex_str, wf["id"]])
    except Exception as e:
        pass


def _ensure_workflow_requests_table(conn):
    """Ensure the workflow_requests table exists for user-to-admin workflow notifications."""
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS workflow_requests (
                id VARCHAR PRIMARY KEY,
                username VARCHAR NOT NULL,
                tenant_id VARCHAR NOT NULL,
                prompt TEXT NOT NULL,
                notes TEXT,
                status VARCHAR DEFAULT 'PENDING',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                reviewed_by VARCHAR,
                resolved_workflow_id VARCHAR,
                title VARCHAR
            );
        """)
        try:
            conn.execute("ALTER TABLE workflow_requests ADD COLUMN title VARCHAR;")
        except Exception:
            pass
    except Exception as e:
        print(f"[AUTH] Failed to ensure workflow_requests table: {e}")


def _normalize_tenant_id(val: str) -> str:
    v = (val or "").strip().upper()
    mapping = {
        "ALL": "ALL",
        "SCHEMA_ALL": "ALL",
        "SCHEMA ALL": "ALL",
        "USERA": "INVENTORY",
        "TENANT_A": "INVENTORY",
        "SCHEMA_A": "INVENTORY",
        "SCHEMA A": "INVENTORY",
        "INVENTORY": "INVENTORY",
        "USERB": "HR",
        "TENANT_B": "HR",
        "SCHEMA_B": "HR",
        "SCHEMA B": "HR",
        "HR": "HR",
        "USERC": "FINANCE",
        "TENANT_C": "FINANCE",
        "SCHEMA_C": "FINANCE",
        "SCHEMA C": "FINANCE",
        "FINANCE": "FINANCE"
    }
    return mapping.get(v, "ALL")


class CreateWorkflowRequest(BaseModel):
    name: str
    description: str
    business_instruction: str
    tenant_id: str = "ALL"  # ALL, INVENTORY, HR, FINANCE
    example_prompts: list[str] | None = None
    resolving_request_id: str | None = None

@router.post("/admin/workflows/preview")
async def preview_workflow(req: CreateWorkflowRequest, admin: TokenData = Depends(get_current_admin)):
    from agents.workflow_compiler import WorkflowCompiler
    tenant_val = _normalize_tenant_id(req.tenant_id)
    preview_result = await WorkflowCompiler.preview_and_lint_instruction(req.name, req.business_instruction, tenant_id=tenant_val)
    return {
        "status": "success" if preview_result["success"] else "error",
        "name": req.name,
        "tenant_id": tenant_val,
        "compiled_json": preview_result["workflow"],
        "warnings": preview_result["warnings"],
        "errors": preview_result["errors"],
        "suggestions": preview_result["suggestions"]
    }

@router.post("/admin/workflows")
async def create_workflow(req: CreateWorkflowRequest, admin: TokenData = Depends(get_current_admin)):
    check_conn = get_db_connection(read_only=True)
    _ensure_workflow_tenant_column(check_conn)
    existing = check_conn.execute(
        "SELECT id, name FROM workflows WHERE LOWER(TRIM(name)) = LOWER(TRIM(?))",
        [req.name]
    ).fetchone()
    check_conn.close()
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Workflow dengan nama '{req.name}' sudah terdaftar (ID: {existing[0]}). Gunakan nama yang berbeda atau perbarui alur kerja yang ada."
        )

    from agents.workflow_compiler import WorkflowCompiler
    import uuid
    
    tenant_val = _normalize_tenant_id(req.tenant_id)
    lint_res = await WorkflowCompiler.preview_and_lint_instruction(req.name, req.business_instruction, tenant_id=tenant_val)
    if not lint_res["success"]:
        raise HTTPException(
            status_code=400,
            detail="Validasi alur kerja gagal: " + "; ".join(lint_res["errors"])
        )
    compiled_json = lint_res["workflow"]
    ex_prompts = req.example_prompts or compiled_json.get("example_prompts") or WorkflowCompiler.generate_heuristic_examples(req.name, req.business_instruction)
    ex_prompts_json = json.dumps(ex_prompts, ensure_ascii=False)
    
    wf_id = f"WF-{uuid.uuid4().hex[:6].upper()}"
    
    conn = get_db_connection(read_only=False)
    _ensure_workflow_tenant_column(conn)
    _ensure_workflow_requests_table(conn)
    conn.execute(
        "INSERT INTO workflows (id, name, description, business_instruction, compiled_json, tenant_id, example_prompts) VALUES (?, ?, ?, ?, ?, ?, ?)", 
        [wf_id, req.name, req.description, req.business_instruction, json.dumps(compiled_json), tenant_val, ex_prompts_json]
    )
    if req.resolving_request_id:
        conn.execute(
            "UPDATE workflow_requests SET status = 'COMPLETED', reviewed_by = ?, resolved_workflow_id = ? WHERE id = ?",
            [admin.username, wf_id, req.resolving_request_id]
        )
    _sync_workflows_to_json(conn)
    conn.close()
    
    return {
        "status": "success", 
        "workflow_id": wf_id, 
        "compiled_json": compiled_json, 
        "tenant_id": tenant_val,
        "example_prompts": ex_prompts,
        "warnings": lint_res.get("warnings", []),
        "suggestions": lint_res.get("suggestions", [])
    }

@router.get("/admin/workflows")
async def get_workflows(response: Response, admin: TokenData = Depends(get_current_admin)):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    conn = get_db_connection(read_only=True)
    try:
        rows = conn.execute("SELECT id, name, description, business_instruction, compiled_json, tenant_id, example_prompts FROM workflows ORDER BY id ASC").fetchall()
        columns = [desc[0] for desc in conn.description]
    except Exception:
        conn.close()
        write_conn = get_db_connection(read_only=False)
        _ensure_workflow_tenant_column(write_conn)
        write_conn.close()
        conn = get_db_connection(read_only=True)
        rows = conn.execute("SELECT id, name, description, business_instruction, compiled_json, tenant_id, example_prompts FROM workflows ORDER BY id ASC").fetchall()
        columns = [desc[0] for desc in conn.description]
    finally:
        conn.close()
    
    workflows = []
    for r in rows:
        wf = dict(zip(columns, r))
        if not wf.get("tenant_id"):
            wf["tenant_id"] = "ALL"
        try:
            wf["compiled_json"] = json.loads(wf["compiled_json"])
        except:
            pass
        if isinstance(wf.get("example_prompts"), str):
            try:
                wf["example_prompts"] = json.loads(wf["example_prompts"])
            except:
                wf["example_prompts"] = []
        elif not wf.get("example_prompts"):
            wf["example_prompts"] = []
        if not wf["example_prompts"]:
            from agents.workflow_compiler import WorkflowCompiler
            wf["example_prompts"] = WorkflowCompiler.generate_heuristic_examples(wf.get("name", ""), wf.get("business_instruction", "") or wf.get("description", ""))
        workflows.append(wf)
        
    return workflows

@router.delete("/admin/workflows/{wf_id}")
async def delete_workflow(wf_id: str, admin: TokenData = Depends(get_current_admin)):
    conn = get_db_connection(read_only=False)
    conn.execute("DELETE FROM workflows WHERE id = ?", [wf_id])
    _sync_workflows_to_json(conn)
    conn.close()
    return {"status": "success"}

@router.put("/admin/workflows/{wf_id}")
async def edit_workflow(wf_id: str, req: CreateWorkflowRequest, admin: TokenData = Depends(get_current_admin)):
    from agents.workflow_compiler import WorkflowCompiler
    
    tenant_val = _normalize_tenant_id(req.tenant_id)
    lint_res = await WorkflowCompiler.preview_and_lint_instruction(req.name, req.business_instruction, tenant_id=tenant_val)
    if not lint_res["success"]:
        raise HTTPException(
            status_code=400,
            detail="Validasi alur kerja gagal: " + "; ".join(lint_res["errors"])
        )
    compiled_json = lint_res["workflow"]
    ex_prompts = req.example_prompts or compiled_json.get("example_prompts") or WorkflowCompiler.generate_heuristic_examples(req.name, req.business_instruction)
    ex_prompts_json = json.dumps(ex_prompts, ensure_ascii=False)
    
    conn = get_db_connection(read_only=False)
    _ensure_workflow_tenant_column(conn)
    conn.execute(
        "UPDATE workflows SET name = ?, description = ?, business_instruction = ?, compiled_json = ?, tenant_id = ?, example_prompts = ? WHERE id = ?", 
        [req.name, req.description, req.business_instruction, json.dumps(compiled_json), tenant_val, ex_prompts_json, wf_id]
    )
    _sync_workflows_to_json(conn)
    conn.close()
    
    return {
        "status": "success", 
        "workflow_id": wf_id, 
        "compiled_json": compiled_json, 
        "tenant_id": tenant_val,
        "example_prompts": ex_prompts,
        "warnings": lint_res.get("warnings", []),
        "suggestions": lint_res.get("suggestions", [])
    }

@router.get("/workflows/help-catalog")
async def get_help_catalog(tenant: str | None = None):
    """Endpoint to fetch active workflows with generated example prompts."""
    conn = get_db_connection(read_only=False)
    _ensure_workflow_tenant_column(conn)
    rows = conn.execute("SELECT id, name, description, business_instruction, compiled_json, tenant_id, example_prompts FROM workflows ORDER BY id ASC").fetchall()
    columns = [desc[0] for desc in conn.description]
    conn.close()
    
    workflows = []
    for r in rows:
        wf = dict(zip(columns, r))
        t = wf.get("tenant_id") or "ALL"
        wf["tenant_id"] = t
        if isinstance(wf.get("example_prompts"), str):
            try:
                wf["example_prompts"] = json.loads(wf["example_prompts"])
            except:
                wf["example_prompts"] = []
        elif not wf.get("example_prompts"):
            wf["example_prompts"] = []
        if not wf["example_prompts"]:
            from agents.workflow_compiler import WorkflowCompiler
            wf["example_prompts"] = WorkflowCompiler.generate_heuristic_examples(wf.get("name", ""), wf.get("business_instruction", "") or wf.get("description", ""))
        
        # Enforce exactly one example prompt per workflow
        if wf.get("example_prompts"):
            wf["example_prompts"] = wf["example_prompts"][:1]
        
        if tenant:
            norm_t = _normalize_tenant_id(tenant)
            if norm_t != "ALL" and wf["tenant_id"] not in [norm_t, "ALL"]:
                continue
        workflows.append(wf)
        
    if tenant:
        norm_t = _normalize_tenant_id(tenant)
        if norm_t != "ALL":
            # Prioritize tenant-specific workflows first, followed by global ALL workflows
            workflows.sort(key=lambda w: (0 if w.get("tenant_id") == norm_t else 1, w["id"]))
        
    return {"status": "success", "workflows": workflows}


class WorkflowRequestPayload(BaseModel):
    prompt: str
    title: str | None = None
    notes: str | None = None
    tenant_id: str | None = None

class WorkflowRequestStatusPayload(BaseModel):
    status: str
    resolved_workflow_id: str | None = None


@router.post("/workflows/request")
async def submit_workflow_request(req: WorkflowRequestPayload, current_user: TokenData = Depends(get_current_user)):
    """User submits a new workflow request to the Administrator."""
    if not req.prompt or not req.prompt.strip():
        raise HTTPException(status_code=400, detail="Prompt instruksi tidak boleh kosong")
    
    clean_prompt = req.prompt.strip()
    clean_title = (req.title or "").strip() or None
    clean_notes = (req.notes or "").strip()
    req_id = f"REQ-{uuid.uuid4().hex[:6].upper()}"
    u_name = current_user.username or "user"
    u_tenant = _normalize_tenant_id(req.tenant_id or current_user.tenant_id)
    
    conn = get_db_connection(read_only=False)
    try:
        _ensure_workflow_requests_table(conn)
        conn.execute(
            "INSERT INTO workflow_requests (id, username, tenant_id, prompt, notes, status, title) VALUES (?, ?, ?, ?, ?, 'PENDING', ?)",
            [req_id, u_name, u_tenant, clean_prompt, clean_notes, clean_title]
        )
    finally:
        conn.close()
        
    return {
        "status": "success",
        "request_id": req_id,
        "title": clean_title,
        "message": "Permintaan alur kerja berhasil dikirimkan ke Administrator."
    }


@router.get("/admin/workflow-requests")
async def get_workflow_requests(response: Response, admin: TokenData = Depends(get_current_admin)):
    """Admin endpoint to fetch user workflow requests and pending count."""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"

    conn = get_db_connection(read_only=True)
    try:
        rows = conn.execute("""
            SELECT id, username, tenant_id, prompt, notes, status, 
                   strftime(created_at, '%d %b %Y, %H:%M') as created_at_str,
                   reviewed_by, resolved_workflow_id, title
            FROM workflow_requests 
            ORDER BY 
                CASE WHEN status = 'PENDING' THEN 0 ELSE 1 END,
                created_at DESC
            LIMIT 100
        """).fetchall()
    except Exception:
        conn.close()
        write_conn = get_db_connection(read_only=False)
        _ensure_workflow_requests_table(write_conn)
        write_conn.close()
        conn = get_db_connection(read_only=True)
        rows = conn.execute("""
            SELECT id, username, tenant_id, prompt, notes, status, 
                   strftime(created_at, '%d %b %Y, %H:%M') as created_at_str,
                   reviewed_by, resolved_workflow_id, title
            FROM workflow_requests 
            ORDER BY 
                CASE WHEN status = 'PENDING' THEN 0 ELSE 1 END,
                created_at DESC
            LIMIT 100
        """).fetchall()
    finally:
        conn.close()

    columns = ["id", "username", "tenant_id", "prompt", "notes", "status", "created_at", "reviewed_by", "resolved_workflow_id", "title"]
    requests = [dict(zip(columns, r)) for r in rows]
    pending_count = sum(1 for r in requests if r["status"] == "PENDING")
    return {
        "status": "success",
        "requests": requests,
        "pending_count": pending_count
    }


@router.post("/admin/workflow-requests/{req_id}/status")
async def update_workflow_request_status(
    req_id: str, 
    payload: WorkflowRequestStatusPayload, 
    admin: TokenData = Depends(get_current_admin)
):
    """Admin endpoint to update workflow request status (COMPLETED, REJECTED, PENDING)."""
    valid_statuses = ["PENDING", "COMPLETED", "REJECTED"]
    st = payload.status.strip().upper()
    if st not in valid_statuses:
        raise HTTPException(status_code=400, detail="Status tidak valid. Gunakan PENDING, COMPLETED, atau REJECTED.")
        
    conn = get_db_connection(read_only=False)
    _ensure_workflow_requests_table(conn)
    try:
        conn.execute("""
            UPDATE workflow_requests 
            SET status = ?, reviewed_by = ?, resolved_workflow_id = ?
            WHERE id = ?
        """, [st, admin.username, payload.resolved_workflow_id, req_id])
    finally:
        conn.close()
        
    return {"status": "success", "request_id": req_id, "updated_status": st}


@router.delete("/admin/workflow-requests/{req_id}")
async def delete_workflow_request(
    req_id: str, 
    admin: TokenData = Depends(get_current_admin)
):
    """Admin endpoint to delete a specific workflow request."""
    conn = get_db_connection(read_only=False)
    _ensure_workflow_requests_table(conn)
    try:
        conn.execute("DELETE FROM workflow_requests WHERE id = ?", [req_id])
    finally:
        conn.close()
    return {"status": "success", "request_id": req_id, "message": f"Permintaan {req_id} berhasil dihapus."}


@router.delete("/admin/workflow-requests")
async def clear_workflow_requests(
    status: str | None = None,
    admin: TokenData = Depends(get_current_admin)
):
    """Admin endpoint to clear all or filtered workflow requests."""
    conn = get_db_connection(read_only=False)
    _ensure_workflow_requests_table(conn)
    try:
        if not status or status.strip().upper() in ["ALL", ""]:
            count_res = conn.execute("SELECT COUNT(*) FROM workflow_requests").fetchone()
            count = count_res[0] if count_res else 0
            conn.execute("DELETE FROM workflow_requests")
        else:
            st = status.strip().upper()
            count_res = conn.execute("SELECT COUNT(*) FROM workflow_requests WHERE status = ?", [st]).fetchone()
            count = count_res[0] if count_res else 0
            conn.execute("DELETE FROM workflow_requests WHERE status = ?", [st])
    finally:
        conn.close()
    return {
        "status": "success",
        "deleted_count": count,
        "message": f"Berhasil menghapus {count} usulan alur kerja."
    }


@router.post("/admin/workflows/reset-defaults")
async def reset_workflows_to_defaults(admin: TokenData = Depends(get_current_admin)):
    """Admin endpoint to restore any missing base seed workflows from workflows.json.
    
    SAFE: This does NOT delete any existing custom workflows. It only re-adds 
    workflows from data/balitower/workflows.json that are currently missing from the DB.
    """
    conn = get_db_connection(read_only=False)
    _ensure_workflow_tenant_column(conn)
    try:
        restored = 0
        if WORKFLOWS_JSON_PATH.exists():
            with open(WORKFLOWS_JSON_PATH, "r", encoding="utf-8") as f:
                seed_wfs = json.load(f)
            existing_ids = set(r[0] for r in conn.execute("SELECT id FROM workflows").fetchall())
            for wf in seed_wfs:
                wid = wf.get("id")
                if not wid:
                    continue
                compiled_str = json.dumps(wf["compiled_json"]) if isinstance(wf.get("compiled_json"), dict) else str(wf.get("compiled_json", "{}"))
                ex_prompts_str = json.dumps(wf.get("example_prompts", []), ensure_ascii=False)
                if wid not in existing_ids:
                    conn.execute(
                        "INSERT INTO workflows (id, name, description, business_instruction, compiled_json, tenant_id, example_prompts) VALUES (?,?,?,?,?,?,?)",
                        [wid, wf["name"], wf.get("description", ""), wf.get("business_instruction", ""), compiled_str, wf.get("tenant_id", "ALL"), ex_prompts_str]
                    )
                    restored += 1
        _sync_workflows_to_json(conn)
    finally:
        conn.close()
    return {"status": "success", "message": f"Selesai. {restored} alur kerja berhasil dipulihkan dari berkas JSON referensi. Workflow yang sudah ada tidak diubah."}



@router.get("/admin/users")
async def get_all_users(response: Response, admin: TokenData = Depends(get_current_admin)):
    """Fetch all registered users and their multi-tenant inventory database stats."""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    
    conn = get_db_connection(read_only=True)
    users_rows = conn.execute("SELECT user_id, username, role, tenant_id FROM users ORDER BY user_id ASC").fetchall()

    # Scope 1: Inventory Items (for usera)
    inv_rows = conn.execute("""
        SELECT 
            i.item_id,
            i.item_code,
            i.item_name,
            i.category,
            COALESCE(SUM(sb.quantity_on_hand), 0) AS current_stock,
            CASE 
                WHEN COUNT(sb.warehouse_id) > 0 THEN CAST(SUM(sb.reorder_point) AS BIGINT) 
                ELSE i.min_stock 
            END AS min_threshold,
            CASE 
                WHEN COUNT(sb.warehouse_id) > 0 THEN CAST(SUM(sb.reorder_point * 3) AS BIGINT) 
                ELSE i.min_stock * 3 
            END AS max_threshold,
            i.unit,
            i.unit_price,
            s.supplier_name
        FROM inventory_items i
        LEFT JOIN stock_balances sb ON i.item_id = sb.item_id
        LEFT JOIN suppliers s ON i.supplier_id = s.supplier_id
        GROUP BY i.item_id, i.item_code, i.item_name, i.category, i.min_stock, i.unit, i.unit_price, s.supplier_name
        ORDER BY i.item_id ASC;
    """).fetchall()

    # Scope 2: HR Employees (for userb)
    emp_rows = conn.execute("""
        SELECT employee_id, full_name, department, job_title, employment_status, k3_certification, leave_balance
        FROM employees
        ORDER BY employee_id ASC;
    """).fetchall()

    # Scope 3: Finance Invoices (for userc)
    invc_rows = conn.execute("""
        SELECT r.invoice_number, COALESCE(c.client_name, r.client_id) AS client_name, r.period_covered, r.due_date, r.total_billed, r.payment_status
        FROM revenue_invoices r
        LEFT JOIN telecom_clients c ON r.client_id = c.client_id
        ORDER BY r.invoice_number ASC;
    """).fetchall()
    conn.close()

    # Build items_list for multi-tenant table view
    items_list = []
    
    # 1. usera - Material Inventory (14 items)
    usera_total_stock = 0
    usera_low_stock = 0
    for r in inv_rows:
        item_id, item_code, name, cat, stock, min_thresh, max_thresh, unit, price, supp_name = r
        stock_val = int(stock)
        min_val = int(min_thresh)
        usera_total_stock += stock_val
        if stock_val <= min_val:
            usera_low_stock += 1
        
        if stock_val == 0:
            calc_status = "Habis"
        elif stock_val <= min_val * 0.5:
            calc_status = "Kritis"
        elif stock_val <= min_val:
            calc_status = "Menipis"
        else:
            calc_status = "Normal"

        items_list.append({
            "domain": "INVENTORY",
            "tenant_id": "usera",
            "sku": item_code or item_id,
            "item_id": item_id,
            "name": name,
            "category": cat,
            "supplier_name": supp_name or "-",
            "current_stock": stock_val,
            "unit": unit or "pcs",
            "min_threshold": min_val,
            "max_threshold": int(max_thresh),
            "unit_price": float(price or 0.0),
            "status": calc_status
        })

    # 2. userb - HR Workforce (12 employees)
    userb_riggers = 0
    for r in emp_rows:
        emp_id, full_name, dept, job, emp_status, k3_cert, leave_bal = r
        if "rigger" in (job or "").lower() or "teknisi" in (job or "").lower():
            userb_riggers += 1
        items_list.append({
            "domain": "HR",
            "tenant_id": "userb",
            "item_id": emp_id,
            "employee_id": emp_id,
            "name": full_name,
            "full_name": full_name,
            "department": dept,
            "category": dept,
            "job_title": job,
            "employment_status": emp_status or "PERMANENT",
            "k3_certification": k3_cert or "NON_CERTIFIED",
            "leave_balance": int(leave_bal or 0),
            "status": emp_status or "PERMANENT",
            "unit": "orang",
            "current_stock": 1,
            "unit_price": 0.0
        })

    # 3. userc - Finance Invoices (8 invoices)
    userc_unpaid = 0
    userc_revenue = 0.0
    for r in invc_rows:
        inv_no, client, period, due_date, amount, pay_status = r
        amt = float(amount or 0.0)
        userc_revenue += amt
        if (pay_status or "").upper() in ["UNPAID", "OVERDUE"]:
            userc_unpaid += 1
        items_list.append({
            "domain": "FINANCE",
            "tenant_id": "userc",
            "item_id": inv_no,
            "invoice_number": inv_no,
            "name": f"{client} ({period})",
            "client_name": client,
            "category": "Tagihan Operator",
            "period_covered": period,
            "due_date": due_date or "-",
            "total_billed": amt,
            "unit_price": amt,
            "payment_status": pay_status or "PAID",
            "status": pay_status or "PAID",
            "unit": "invoice",
            "current_stock": 1
        })

    # Map stats for each registered user
    tenant_stats = {
        "INVENTORY": {"total_items": len(inv_rows), "total_stock": usera_total_stock, "low_stock_count": usera_low_stock},
        "TENANT_A": {"total_items": len(inv_rows), "total_stock": usera_total_stock, "low_stock_count": usera_low_stock},
        "usera": {"total_items": len(inv_rows), "total_stock": usera_total_stock, "low_stock_count": usera_low_stock},
        "HR": {"total_items": len(emp_rows), "total_stock": userb_riggers, "low_stock_count": 0},
        "TENANT_B": {"total_items": len(emp_rows), "total_stock": userb_riggers, "low_stock_count": 0},
        "userb": {"total_items": len(emp_rows), "total_stock": userb_riggers, "low_stock_count": 0},
        "FINANCE": {"total_items": len(invc_rows), "total_stock": int(userc_revenue // 1_000_000_000), "low_stock_count": userc_unpaid},
        "TENANT_C": {"total_items": len(invc_rows), "total_stock": int(userc_revenue // 1_000_000_000), "low_stock_count": userc_unpaid},
        "userc": {"total_items": len(invc_rows), "total_stock": int(userc_revenue // 1_000_000_000), "low_stock_count": userc_unpaid},
        "ALL": {"total_items": len(items_list), "total_stock": usera_total_stock, "low_stock_count": usera_low_stock}
    }

    users_list = []
    for u in users_rows:
        u_id, username, role, t_id = u
        st = tenant_stats.get(t_id, tenant_stats.get(username, {"total_items": 0, "total_stock": 0, "low_stock_count": 0}))
        users_list.append({
            "user_id": u_id,
            "username": username,
            "role": role,
            "tenant_id": t_id,
            "stats": st
        })
        
    return {
        "total_users": len(users_list),
        "users": users_list,
        "items": items_list
    }


# =========================================================================
# ADMIN DATABASE CRUD ENGINE (Unrestricted Table & Domain Management)
# =========================================================================

class AdminCreateUserRequest(BaseModel):
    username: str
    password: str = Field(..., description="Min. 8 characters with letters and numbers")
    role: str = "USER"
    tenant_id: str = "INVENTORY"

class AdminUpdateUserRequest(BaseModel):
    role: str | None = None
    tenant_id: str | None = None
    password: str | None = Field(default=None, description="Min. 8 characters with letters and numbers")

class AdminDbInsertRequest(BaseModel):
    data: dict

class AdminDbUpdateRequest(BaseModel):
    pk_col: str
    pk_val: Any
    data: dict

class AdminDbDeleteRequest(BaseModel):
    pk_col: str
    pk_val: Any


def validate_password_strength(password: str) -> None:
    """Validate password meets minimum length (8 chars) and contains letters and numbers."""
    if not password or len(password.strip()) < 8:
        raise HTTPException(
            status_code=400,
            detail="Password must be at least 8 characters long."
        )
    p = password.strip()
    has_letter = any(c.isalpha() for c in p)
    has_digit = any(c.isdigit() for c in p)
    if not (has_letter and has_digit):
        raise HTTPException(
            status_code=400,
            detail="Password must contain both letters and numbers."
        )


@router.post("/admin/users")
async def create_user(req: AdminCreateUserRequest, admin: TokenData = Depends(get_current_admin)):
    """Create a new user account with hashed credentials in the users table."""
    validate_password_strength(req.password)

    conn = get_db_connection(read_only=True)
    existing = conn.execute("SELECT username FROM users WHERE username = ?", [req.username]).fetchone()
    conn.close()
    if existing:
        raise HTTPException(status_code=400, detail=f"Username '{req.username}' sudah terdaftar.")

    user_id = f"USR-{uuid.uuid4().hex[:6].upper()}"
    p_hash = await asyncio.to_thread(get_password_hash, req.password.strip())
    tenant_val = _normalize_tenant_id(req.tenant_id)
    role_val = req.role.strip().upper() if req.role else "USER"
    if role_val not in ["ADMIN", "USER"]:
        role_val = "USER"

    execute_db_write(
        "INSERT INTO users (user_id, username, password_hash, role, tenant_id) VALUES (?, ?, ?, ?, ?)",
        [user_id, req.username, p_hash, role_val, tenant_val]
    )
    return {"status": "success", "message": f"Pengguna '{req.username}' berhasil ditambahkan.", "user_id": user_id}


@router.put("/admin/users/{user_id}")
async def update_user(user_id: str, req: AdminUpdateUserRequest, admin: TokenData = Depends(get_current_admin)):
    """Update role, tenant_id, or password for a user account."""
    conn = get_db_connection(read_only=True)
    row = conn.execute("SELECT user_id, username FROM users WHERE user_id = ?", [user_id]).fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail=f"Pengguna dengan ID '{user_id}' tidak ditemukan.")

    updates = []
    vals = []
    if req.role:
        r_val = req.role.strip().upper()
        if r_val in ["ADMIN", "USER"]:
            updates.append("role = ?")
            vals.append(r_val)
    if req.tenant_id:
        updates.append("tenant_id = ?")
        vals.append(_normalize_tenant_id(req.tenant_id))
    if req.password is not None:
        validate_password_strength(req.password)
        new_hash = await asyncio.to_thread(get_password_hash, req.password.strip())
        updates.append("password_hash = ?")
        vals.append(new_hash)

    if updates:
        vals.append(user_id)
        execute_db_write(f"UPDATE users SET {', '.join(updates)} WHERE user_id = ?", vals)
    return {"status": "success", "message": f"Data pengguna '{row[1]}' berhasil diperbarui."}


@router.delete("/admin/users/{user_id}")
async def delete_user(user_id: str, admin: TokenData = Depends(get_current_admin)):
    """Delete a user account from database."""
    conn = get_db_connection(read_only=False)
    row = conn.execute("SELECT username FROM users WHERE user_id = ?", [user_id]).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail=f"Pengguna '{user_id}' tidak ditemukan.")
    if row[0] == admin.username:
        conn.close()
        raise HTTPException(status_code=400, detail="Tidak dapat menghapus akun admin yang sedang Anda gunakan.")

    conn.execute("DELETE FROM users WHERE user_id = ?", [user_id])
    conn.commit()
    conn.close()
    return {"status": "success", "message": f"Akun pengguna '{row[0]}' berhasil dihapus."}


# -------------------------------------------------------------------------
# Generic DuckDB Table Explorer & CRUD Endpoints
# -------------------------------------------------------------------------

def _get_allowed_tables(conn) -> list[str]:
    """Retrieve all table names from database."""
    return [t[0] for t in conn.execute("SHOW TABLES;").fetchall()]


@router.get("/admin/db/tables")
async def list_database_tables(admin: TokenData = Depends(get_current_admin)):
    """List all tables in storage/balitower.db with row counts and column schemas."""
    conn = get_db_connection(read_only=True)
    tables = _get_allowed_tables(conn)
    result = []
    for t in tables:
        try:
            cnt = conn.execute(f'SELECT COUNT(*) FROM "{t}";').fetchone()[0]
            desc_rows = conn.execute(f'DESCRIBE "{t}";').fetchall()
            cols = [{"name": r[0], "type": r[1]} for r in desc_rows]
            result.append({
                "table_name": t,
                "row_count": cnt,
                "columns": cols
            })
        except Exception:
            pass
    conn.close()
    return {"tables": result, "table_names": tables}


@router.get("/admin/db/table/{table_name}")
async def get_table_data(
    table_name: str,
    limit: int = 50,
    offset: int = 0,
    search: str = "",
    admin: TokenData = Depends(get_current_admin)
):
    """Fetch paginated rows from any DuckDB table with search filtering."""
    conn = get_db_connection(read_only=True)
    allowed = _get_allowed_tables(conn)
    if table_name not in allowed:
        conn.close()
        raise HTTPException(status_code=404, detail=f"Tabel '{table_name}' tidak ditemukan di database.")

    desc_rows = conn.execute(f'DESCRIBE "{table_name}";').fetchall()
    columns = [r[0] for r in desc_rows]
    col_defs = [{"name": r[0], "type": r[1]} for r in desc_rows]

    where_clause = ""
    params = []
    if search and search.strip():
        search_terms = []
        for c in columns:
            search_terms.append(f'CAST("{c}" AS VARCHAR) ILIKE ?')
            params.append(f"%{search.strip()}%")
        where_clause = "WHERE " + " OR ".join(search_terms)

    total_cnt = conn.execute(f'SELECT COUNT(*) FROM "{table_name}" {where_clause};', params).fetchone()[0]
    
    query = f'SELECT * FROM "{table_name}" {where_clause} LIMIT ? OFFSET ?;'
    rows = conn.execute(query, params + [limit, offset]).fetchall()
    conn.close()

    data_rows = [dict(zip(columns, r)) for r in rows]
    pk_col = next((r[0] for r in desc_rows if len(r) > 3 and r[3] == "PRI"), None)
    if not pk_col:
        # Fallback to id column if exists, otherwise first column
        pk_col = next((c for c in columns if c.lower() in ["id", f"{table_name}_id", f"{table_name[:-1]}_id"] or c.lower().endswith("_id")), (columns[0] if columns else None))

    return {
        "table_name": table_name,
        "total_count": total_cnt,
        "limit": limit,
        "offset": offset,
        "columns": col_defs,
        "column_names": columns,
        "primary_key": pk_col,
        "rows": data_rows
    }


@router.post("/admin/db/table/{table_name}/insert")
async def insert_table_row(
    table_name: str,
    req: AdminDbInsertRequest,
    admin: TokenData = Depends(get_current_admin)
):
    """Insert a new row into any DuckDB table."""
    conn = get_db_connection(read_only=False)
    allowed = _get_allowed_tables(conn)
    if table_name not in allowed:
        conn.close()
        raise HTTPException(status_code=404, detail=f"Tabel '{table_name}' tidak ditemukan.")

    desc_rows = conn.execute(f'DESCRIBE "{table_name}";').fetchall()
    valid_cols = {r[0]: r[1] for r in desc_rows}

    clean_data = {}
    for k, v in req.data.items():
        if k in valid_cols:
            clean_data[k] = v

    if not clean_data:
        conn.close()
        raise HTTPException(status_code=400, detail="Tidak ada kolom data yang valid untuk disimpan.")

    cols = list(clean_data.keys())
    placeholders = ", ".join(["?"] * len(cols))
    col_names = ", ".join([f'"{c}"' for c in cols])
    values = [clean_data[c] for c in cols]

    try:
        conn.execute(f'INSERT INTO "{table_name}" ({col_names}) VALUES ({placeholders});', values)
        conn.commit()
    except Exception as e:
        conn.close()
        raise HTTPException(status_code=400, detail=f"Gagal menambahkan data ke {table_name}: {str(e)}")

    conn.close()
    return {"status": "success", "message": f"Baris baru berhasil ditambahkan ke tabel '{table_name}'.", "data": clean_data}


@router.put("/admin/db/table/{table_name}/update")
async def update_table_row(
    table_name: str,
    req: AdminDbUpdateRequest,
    admin: TokenData = Depends(get_current_admin)
):
    """Update a row in any DuckDB table by primary/key column."""
    conn = get_db_connection(read_only=False)
    allowed = _get_allowed_tables(conn)
    if table_name not in allowed:
        conn.close()
        raise HTTPException(status_code=404, detail=f"Tabel '{table_name}' tidak ditemukan.")

    desc_rows = conn.execute(f'DESCRIBE "{table_name}";').fetchall()
    valid_cols = {r[0]: r[1] for r in desc_rows}

    if req.pk_col not in valid_cols:
        conn.close()
        raise HTTPException(status_code=400, detail=f"Kolom identifikasi '{req.pk_col}' tidak valid di tabel {table_name}.")

    set_clauses = []
    vals = []
    for k, v in req.data.items():
        if k in valid_cols and k != req.pk_col:
            set_clauses.append(f'"{k}" = ?')
            vals.append(v)

    if not set_clauses:
        conn.close()
        raise HTTPException(status_code=400, detail="Tidak ada perubahan data yang diajukan.")

    vals.append(req.pk_val)
    try:
        conn.execute(f'UPDATE "{table_name}" SET {", ".join(set_clauses)} WHERE "{req.pk_col}" = ?;', vals)
        conn.commit()
    except Exception as e:
        conn.close()
        raise HTTPException(status_code=400, detail=f"Gagal memperbarui data di {table_name}: {str(e)}")

    conn.close()
    return {"status": "success", "message": f"Data di tabel '{table_name}' ({req.pk_col}={req.pk_val}) berhasil diperbarui."}


@router.delete("/admin/db/table/{table_name}/delete")
async def delete_table_row(
    table_name: str,
    req: AdminDbDeleteRequest,
    admin: TokenData = Depends(get_current_admin)
):
    """Delete a row from any DuckDB table by key column."""
    conn = get_db_connection(read_only=False)
    allowed = _get_allowed_tables(conn)
    if table_name not in allowed:
        conn.close()
        raise HTTPException(status_code=404, detail=f"Tabel '{table_name}' tidak ditemukan.")

    desc_rows = conn.execute(f'DESCRIBE "{table_name}";').fetchall()
    valid_cols = [r[0] for r in desc_rows]
    if req.pk_col not in valid_cols:
        conn.close()
        raise HTTPException(status_code=400, detail=f"Kolom '{req.pk_col}' tidak ditemukan di tabel {table_name}.")

    try:
        conn.execute(f'DELETE FROM "{table_name}" WHERE "{req.pk_col}" = ?;', [req.pk_val])
        conn.commit()
    except Exception as e:
        conn.close()
        raise HTTPException(status_code=400, detail=f"Gagal menghapus data dari {table_name}: {str(e)}")

    conn.close()
    return {"status": "success", "message": f"Data ({req.pk_col}={req.pk_val}) berhasil dihapus dari tabel '{table_name}'."}


# -------------------------------------------------------------------------
# High-Level Domain Convenience CRUD Endpoints (Inventory, HR, Finance)
# -------------------------------------------------------------------------

class AdminMaterialRequest(BaseModel):
    item_id: str | None = None
    item_code: str | None = None
    item_name: str | None = None
    name: str | None = None
    category: str | None = "Material Menara"
    unit: str = "pcs"
    unit_price: int | float = 0
    min_stock: int | None = None
    min_threshold: int | None = None
    safety_stock: int | None = None
    lead_time_days: int = 7
    supplier_id: str = "SUP-001"
    initial_stock: int = 50
    warehouse_id: str = "WH-JKT-01"

@router.post("/admin/inventory/items")
async def create_inventory_material(req: AdminMaterialRequest, admin: TokenData = Depends(get_current_admin)):
    conn = get_db_connection(read_only=False)
    item_id = req.item_id or f"BLT-INV-{(conn.execute('SELECT COUNT(*) FROM inventory_items;').fetchone()[0] + 1):03d}"
    item_code = req.item_code or item_id
    item_name = req.item_name or req.name or "Material Baru"
    category = req.category or "Material Menara"
    min_stock = req.min_stock if req.min_stock is not None else (req.min_threshold if req.min_threshold is not None else 10)
    safety_stock = req.safety_stock if req.safety_stock is not None else int(min_stock * 0.5)
    unit_price = int(req.unit_price)

    try:
        conn.execute("""
            INSERT INTO inventory_items (item_id, item_code, item_name, category, unit, unit_price, min_stock, safety_stock, lead_time_days, supplier_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """, [item_id, item_code, item_name, category, req.unit, unit_price, min_stock, safety_stock, req.lead_time_days, req.supplier_id])

        # Create corresponding stock balance row
        bal_id = f"BAL-{uuid.uuid4().hex[:6].upper()}"
        status_val = "NORMAL" if req.initial_stock > min_stock else ("CRITICAL" if req.initial_stock <= min_stock * 0.5 else "LOW")
        conn.execute("""
            INSERT INTO stock_balances (balance_id, item_id, warehouse_id, quantity_on_hand, quantity_reserved, reorder_point, stock_status, last_stock_take_date, last_updated)
            VALUES (?, ?, ?, ?, 0, ?, ?, CAST(CURRENT_DATE AS VARCHAR), CAST(CURRENT_DATE AS VARCHAR));
        """, [bal_id, item_id, req.warehouse_id, req.initial_stock, min_stock, status_val])
        conn.commit()
    except Exception as e:
        conn.close()
        raise HTTPException(status_code=400, detail=f"Gagal menambahkan material: {str(e)}")

    conn.close()
    return {"status": "success", "message": f"Material '{item_name}' ({item_id}) berhasil didaftarkan.", "item_id": item_id}


@router.put("/admin/inventory/items")
@router.put("/admin/inventory/items/{item_id}")
async def update_inventory_material(req: AdminMaterialRequest, item_id: str | None = None, admin: TokenData = Depends(get_current_admin)):
    target_id = item_id or req.item_id
    if not target_id:
        raise HTTPException(status_code=400, detail="item_id harus disertakan.")
    conn = get_db_connection(read_only=False)
    item_name = req.item_name or req.name or "Material"
    category = req.category or "Material Menara"
    min_stock = req.min_stock if req.min_stock is not None else (req.min_threshold if req.min_threshold is not None else 10)
    safety_stock = req.safety_stock if req.safety_stock is not None else int(min_stock * 0.5)
    unit_price = int(req.unit_price)

    try:
        conn.execute("""
            UPDATE inventory_items 
            SET item_name = ?, category = ?, unit = ?, unit_price = ?, min_stock = ?, safety_stock = ?, supplier_id = ?
            WHERE item_id = ?;
        """, [item_name, category, req.unit, unit_price, min_stock, safety_stock, req.supplier_id, target_id])
        conn.commit()
    except Exception as e:
        conn.close()
        raise HTTPException(status_code=400, detail=f"Gagal memperbarui material: {str(e)}")
    conn.close()
    return {"status": "success", "message": f"Material '{item_name}' ({target_id}) berhasil diperbarui."}


@router.delete("/admin/inventory/items")
@router.delete("/admin/inventory/items/{item_id}")
async def delete_inventory_material(item_id: str | None = None, admin: TokenData = Depends(get_current_admin)):
    if not item_id:
        raise HTTPException(status_code=400, detail="item_id harus disertakan.")
    conn = get_db_connection(read_only=False)
    try:
        conn.execute("DELETE FROM stock_balances WHERE item_id = ?;", [item_id])
        conn.execute("DELETE FROM inventory_items WHERE item_id = ?;", [item_id])
        conn.commit()
    except Exception as e:
        conn.close()
        raise HTTPException(status_code=400, detail=f"Gagal menghapus material: {str(e)}")
    conn.close()
    return {"status": "success", "message": f"Material '{item_id}' beserta alokasi stok berhasil dihapus."}


class AdminEmployeeRequest(BaseModel):
    employee_id: str | None = None
    full_name: str | None = None
    name: str | None = None
    department: str = "Tower Operations"
    job_title: str = "Field Technician"
    employment_status: str = "PERMANENT"
    k3_certification: str = "NON_CERTIFIED"
    k3_cert_expiry: str | None = None
    leave_balance: int = 12
    hourly_overtime_rate: int = 45000

@router.post("/admin/hr/employees")
async def create_hr_employee(req: AdminEmployeeRequest, admin: TokenData = Depends(get_current_admin)):
    conn = get_db_connection(read_only=False)
    emp_id = req.employee_id or f"EMP-{(conn.execute('SELECT COUNT(*) FROM employees;').fetchone()[0] + 1):03d}"
    full_name = req.full_name or req.name or "Karyawan Baru"
    try:
        conn.execute("""
            INSERT INTO employees (employee_id, full_name, department, job_title, employment_status, k3_certification, k3_cert_expiry, leave_balance, hourly_overtime_rate)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
        """, [emp_id, full_name, req.department, req.job_title, req.employment_status, req.k3_certification, req.k3_cert_expiry or "2027-12-31", req.leave_balance, req.hourly_overtime_rate])
        conn.commit()
    except Exception as e:
        conn.close()
        raise HTTPException(status_code=400, detail=f"Gagal menambahkan karyawan: {str(e)}")
    conn.close()
    return {"status": "success", "message": f"Karyawan '{full_name}' ({emp_id}) berhasil ditambahkan.", "employee_id": emp_id}


@router.put("/admin/hr/employees")
@router.put("/admin/hr/employees/{employee_id}")
async def update_hr_employee(req: AdminEmployeeRequest, employee_id: str | None = None, admin: TokenData = Depends(get_current_admin)):
    target_id = employee_id or req.employee_id
    if not target_id:
        raise HTTPException(status_code=400, detail="employee_id harus disertakan.")
    conn = get_db_connection(read_only=False)
    full_name = req.full_name or req.name or "Karyawan"
    try:
        conn.execute("""
            UPDATE employees
            SET full_name = ?, department = ?, job_title = ?, employment_status = ?, k3_certification = ?, leave_balance = ?, hourly_overtime_rate = ?
            WHERE employee_id = ?;
        """, [full_name, req.department, req.job_title, req.employment_status, req.k3_certification, req.leave_balance, req.hourly_overtime_rate, target_id])
        conn.commit()
    except Exception as e:
        conn.close()
        raise HTTPException(status_code=400, detail=f"Gagal memperbarui data karyawan: {str(e)}")
    conn.close()
    return {"status": "success", "message": f"Data karyawan '{full_name}' ({target_id}) berhasil diperbarui."}


@router.delete("/admin/hr/employees")
@router.delete("/admin/hr/employees/{employee_id}")
async def delete_hr_employee(employee_id: str | None = None, admin: TokenData = Depends(get_current_admin)):
    if not employee_id:
        raise HTTPException(status_code=400, detail="employee_id harus disertakan.")
    conn = get_db_connection(read_only=False)
    try:
        conn.execute("DELETE FROM leave_requests WHERE employee_id = ?;", [employee_id])
        conn.execute("DELETE FROM employees WHERE employee_id = ?;", [employee_id])
        conn.commit()
    except Exception as e:
        conn.close()
        raise HTTPException(status_code=400, detail=f"Gagal menghapus karyawan: {str(e)}")
    conn.close()
    return {"status": "success", "message": f"Karyawan '{employee_id}' berhasil dihapus."}


class AdminInvoiceRequest(BaseModel):
    invoice_id: str | None = None
    invoice_number: str | None = None
    contract_id: str = "MLA-2026-001"
    client_id: str = "CLI-001"
    period_covered: str = "2026-Q2"
    amount_subtotal: int | float | None = None
    tax_ppn: int | float | None = None
    total_billed: int | float = 73260000
    due_date: str = "2026-05-15"
    payment_status: str = "PENDING"

@router.post("/admin/finance/invoices")
async def create_finance_invoice(req: AdminInvoiceRequest, admin: TokenData = Depends(get_current_admin)):
    conn = get_db_connection(read_only=False)
    last_num = conn.execute("SELECT COUNT(*) FROM revenue_invoices;").fetchone()[0] + 1
    inv_id = req.invoice_id or f"INV-2026-{last_num:03d}"
    inv_num = req.invoice_number or f"INV/BLT/2026/04/{last_num:03d}"
    total_billed = int(req.total_billed)
    subtotal = int(req.amount_subtotal) if req.amount_subtotal is not None else int(total_billed / 1.11)
    ppn = int(req.tax_ppn) if req.tax_ppn is not None else (total_billed - subtotal)
    
    try:
        conn.execute("""
            INSERT INTO revenue_invoices (invoice_id, invoice_number, contract_id, client_id, period_covered, amount_subtotal, tax_ppn, total_billed, invoice_date, due_date, payment_status, payment_date)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, CAST(CURRENT_DATE AS VARCHAR), ?, ?, NULL);
        """, [inv_id, inv_num, req.contract_id, req.client_id, req.period_covered, subtotal, ppn, total_billed, req.due_date, req.payment_status])
        conn.commit()
    except Exception as e:
        conn.close()
        raise HTTPException(status_code=400, detail=f"Gagal menambahkan invoice: {str(e)}")
    conn.close()
    return {"status": "success", "message": f"Invoice '{inv_num}' ({inv_id}) berhasil diterbitkan.", "invoice_id": inv_id}


@router.put("/admin/finance/invoices")
@router.put("/admin/finance/invoices/{invoice_id}")
async def update_finance_invoice(req: AdminInvoiceRequest, invoice_id: str | None = None, admin: TokenData = Depends(get_current_admin)):
    target_id = invoice_id or req.invoice_id
    if not target_id:
        raise HTTPException(status_code=400, detail="invoice_id harus disertakan.")
    conn = get_db_connection(read_only=False)
    total_billed = int(req.total_billed)
    subtotal = int(req.amount_subtotal) if req.amount_subtotal is not None else int(total_billed / 1.11)
    ppn = int(req.tax_ppn) if req.tax_ppn is not None else (total_billed - subtotal)
    
    try:
        p_date = "CAST(CURRENT_DATE AS VARCHAR)" if req.payment_status == "PAID" else "NULL"
        conn.execute(f"""
            UPDATE revenue_invoices
            SET period_covered = ?, amount_subtotal = ?, tax_ppn = ?, total_billed = ?, due_date = ?, payment_status = ?, payment_date = {p_date}
            WHERE invoice_id = ?;
        """, [req.period_covered, subtotal, ppn, total_billed, req.due_date, req.payment_status, target_id])
        conn.commit()
    except Exception as e:
        conn.close()
        raise HTTPException(status_code=400, detail=f"Gagal memperbarui invoice: {str(e)}")
    conn.close()
    return {"status": "success", "message": f"Invoice '{target_id}' berhasil diperbarui."}


@router.delete("/admin/finance/invoices")
@router.delete("/admin/finance/invoices/{invoice_id}")
async def delete_finance_invoice(invoice_id: str | None = None, admin: TokenData = Depends(get_current_admin)):
    if not invoice_id:
        raise HTTPException(status_code=400, detail="invoice_id harus disertakan.")
    conn = get_db_connection(read_only=False)
    try:
        conn.execute("DELETE FROM revenue_invoices WHERE invoice_id = ?;", [invoice_id])
        conn.commit()
    except Exception as e:
        conn.close()
        raise HTTPException(status_code=400, detail=f"Gagal menghapus invoice: {str(e)}")
    conn.close()
    return {"status": "success", "message": f"Invoice '{invoice_id}' berhasil dihapus."}


