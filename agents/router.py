import json
import re

from core.config import settings
from core.llm_client import gateway
from database.db import get_db_connection

def extract_recipient_email(prompt: str) -> str | None:
    """Helper to detect any email address or named person/role mentioned in the prompt text."""
    if not prompt:
        return None

    # 1. Direct standard RFC email regex pattern (e.g. user@balitower.co.id)
    match = re.search(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+', prompt)
    if match:
        email = match.group(0).strip().rstrip(".,;:!?")
        return email

    p_lower = prompt.lower().strip()

    # Guard: If user literally asks to send to email without specifying an email address,
    # do NOT resolve to any fallback account! Clarification MUST be requested instead.
    if re.search(r'\b(?:ke\s+email|via\s+email|kirimkan?\s+(?:ke\s+)?email)\b', p_lower):
        return None

    # 2. Dynamic employee & corporate role recipient resolution
    # Named contact aliases
    zeiniah_email = (settings.SMTP_EMAIL or "").strip() or "zeiniahalfiah@gmail.com"
    daffa_email = (getattr(settings, "DEFAULT_RECIPIENT_EMAIL", None) or "").strip() or "muhammaddaffaarigoh@gmail.com"
    if "zeiniah" in p_lower:
        return zeiniah_email
    if "daffa" in p_lower and any(w in p_lower for w in ["ke daffa", "kepada daffa", "untuk daffa", "daffa"]):
        return daffa_email

    # Default recipient for roles and internal colleague resolution
    user_email = (getattr(settings, "DEFAULT_RECIPIENT_EMAIL", None) or "").strip() or settings.SMTP_EMAIL or "muhammaddaffaarigoh@gmail.com"

    # NOTE: "pengadaan" and "procurement" are explicitly excluded from bare role match
    # because in Indonesian, "pengadaan barang" is the operational noun phrase, never an email recipient!
    role_keys = ["hr.operations", "hrd", "hr", "personalia", "manager", "manajer", "boss", "bos"]
    for role_key in role_keys:
        # Must be explicitly preceded by direction indicators like 'ke', 'kepada', 'teruskan ke'
        if re.search(r'(?:ke|kepada|teruskan\s+ke|kirim\s+ke)\s+(?:rekan\s+|tim\s+|email\s+)?\b' + re.escape(role_key) + r'\b', p_lower):
            return user_email

    conn = None
    try:
        conn = get_db_connection(read_only=True)
        tables = set(r[0] for r in conn.execute("SHOW TABLES;").fetchall())
        if "employees" in tables:
            emp_rows = conn.execute("SELECT full_name FROM employees WHERE full_name IS NOT NULL;").fetchall()
            for (full_name,) in emp_rows:
                if not full_name:
                    continue
                first_name = full_name.split()[0].lower()
                # Check for explicit recipient context: "ke <nama>" or "kepada <nama>"
                if (len(first_name) >= 3 and re.search(r'(?:ke|kepada|teruskan\s+ke|kirim\s+ke)\s+(?:rekan\s+|staf\s+)?' + re.escape(first_name) + r'\b', p_lower)) or (f"ke {full_name.lower()}" in p_lower):
                    return user_email
    except Exception:
        pass
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass

    return None


def check_clarification_needs(prompt: str, tenant_id: str = "ALL", recipient_email: str | None = None) -> dict | None:
    """
    Evaluates whether the user's natural language request lacks critical parameters.
    If so, returns structured clarification payload so agent can query the user back.
    """
    if not prompt:
        return None
    p_lower = prompt.lower().strip()
    
    # 1. Email clarification: User requested email dispatch/approval, but provided no recipient email address
    has_email_intent = (
        any(w in p_lower for w in ["kirimkan ke email", "kirim ke email", "kirim via email", "kirimkan via email", "ke email", "via email", "kirim email", "notif email", "emailkan"])
        or (("email" in p_lower or "surel" in p_lower) and any(w in p_lower for w in ["kirim", "send", "notif", "teruskan", "approve", "persetujuan", "surat"]))
    )
    extracted_email = extract_recipient_email(prompt) or recipient_email
    if has_email_intent and not extracted_email:
        clean_prompt = prompt.strip()
        default_target = (getattr(settings, "DEFAULT_RECIPIENT_EMAIL", None) or "").strip() or (settings.SMTP_EMAIL or "").strip() or "muhammaddaffaarigoh@gmail.com"
        
        # Build clean suggestion hint
        if re.search(r'ke\s+email\s*$', clean_prompt, re.IGNORECASE):
            hint_str = re.sub(r'ke\s+email\s*$', f'ke {default_target}', clean_prompt, flags=re.IGNORECASE)
        elif re.search(r'ke\s+email\b', clean_prompt, re.IGNORECASE):
            hint_str = re.sub(r'ke\s+email\b', f'ke {default_target}', clean_prompt, flags=re.IGNORECASE)
        else:
            hint_str = f"{clean_prompt} ke {default_target}"

        return {
            "needs_clarification": True,
            "field": "recipient_email",
            "title": "Alamat Email Diperlukan",
            "message": f"Anda meminta pengiriman notifikasi/persetujuan via email, namun alamat email penerima belum disebutkan. Mohon tentukan alamat email tujuan (contoh: *{default_target}* atau *manager@balitower.co.id*).",
            "hint": hint_str
        }
        
    # 2. Threshold update clarification: wants to update threshold but lacks value or item name
    wants_threshold = any(w in p_lower for w in ["ubah threshold", "ganti ambang", "update batas stok", "atur threshold", "ubah batas", "set threshold", "edit batas"])
    has_number = bool(re.search(r'\d+', prompt))
    if wants_threshold:
        if not has_number:
            return {
                "needs_clarification": True,
                "field": "threshold_parameters",
                "title": "Detail Batas Stok Diperlukan",
                "message": "Untuk memperbarui batas minimum atau maksimum stok, mohon sebutkan nama barang serta nilai batas baru yang diinginkan (contoh: *'Ubah batas minimum SFP Transceiver menjadi 25'*).",
                "hint": "Ubah batas minimum SFP Transceiver menjadi 25"
            }
        
        # Check if item name is missing (e.g. "ubah batas minimum menjadi 25" without specifying which item)
        inventory_words = ["sfp", "kabel", "patch", "drop", "otb", "adapter", "baterai", "transceiver", "core", "fo", "fiber", "router", "switch", "clamp", "odc", "odp", "closure"]
        has_item_mention = any(iw in p_lower for iw in inventory_words) or any(len(word) > 3 and word not in ["ubah", "ganti", "update", "atur", "batas", "minimum", "maksimum", "menjadi", "threshold", "stok", "stoknya", "tolong", "buat", "biar"] for word in p_lower.split())
        # If the words are strictly command words without an item subject
        command_only_words = {"ubah", "ganti", "update", "atur", "batas", "minimum", "maksimum", "menjadi", "threshold", "stok", "stoknya", "tolong", "buat", "biar", "ke", "di", "dan", "ya", "dong"}
        tokens = set(re.findall(r'[a-zA-Z]+', p_lower))
        if tokens.issubset(command_only_words):
            match_num = re.search(r'\d+', prompt)
            val_num = match_num.group(0) if match_num else "20"
            return {
                "needs_clarification": True,
                "field": "threshold_item_name",
                "title": "Nama Barang Diperlukan",
                "message": f"Mohon sebutkan nama barang material yang ingin diperbarui batas stoknya menjadi {val_num}.",
                "hint": f"Ubah batas minimum [Nama Material] menjadi {val_num}"
            }
        
    # 3. Product registration clarification: wants to register/add new product but no details provided
    wants_register = any(w in p_lower for w in ["tambah produk", "tambah barang", "daftarkan barang", "daftarkan produk", "registrasi produk", "registrasi barang", "tambah material"])
    has_spec = bool(re.search(r'(stok|batas|min|harga|satuan|\d+)', p_lower))
    if wants_register and not has_spec:
        return {
            "needs_clarification": True,
            "field": "product_details",
            "title": "Spesifikasi Produk Diperlukan",
            "message": "Untuk mendaftarkan produk baru ke database inventaris, mohon sertakan informasi nama produk dan jumlah stok awal (contoh: *'Tambah produk Baterai Lithium 48V, stok 15, batas min 5'*).",
            "hint": "Tambah produk Baterai Lithium 48V, stok 15, batas min 5"
        }

    # 4. Goods receipt clarification: wants to record received goods but no PO number
    wants_receipt = any(w in p_lower for w in ["catat penerimaan", "penerimaan barang", "barang sudah sampai", "terima po", "catat po tiba", "barang tiba"])
    has_po_mention = bool(
        re.search(r'po/blt/\d{4}/\d{1,2}/\d{1,4}', p_lower) or
        re.search(r'\bpo[-_/\s]?\w*[-_/\s]?\d+', p_lower) or
        re.search(r'\bpo[-_]?\d+', p_lower) or
        "po/" in p_lower or
        "po-" in p_lower
    )
    if wants_receipt and not has_po_mention:
        return {
            "needs_clarification": True,
            "field": "po_number_required",
            "title": "Nomor PO Diperlukan",
            "message": "Untuk mencatat penerimaan barang masuk ke gudang, mohon sebutkan nomor Purchase Order (PO) yang diterima (contoh: *'Barang untuk PO-2026-006 sudah sampai di Gudang Bandung, tolong catat penerimaannya'*).",
            "hint": "Barang untuk PO-2026-006 sudah sampai di Gudang Bandung, tolong catat penerimaannya"
        }

    # 5. PO document lookup clarification: wants to view PO document without PO number
    wants_po_doc = any(w in p_lower for w in ["lihat dokumen po", "tampilkan berkas po", "unduh po", "cetak pdf po", "lihat berkas po", "tampilkan po", "download po", "lihat po"])
    if wants_po_doc and not has_po_mention:
        return {
            "needs_clarification": True,
            "field": "po_lookup_id",
            "title": "Nomor Purchase Order Diperlukan",
            "message": "Mohon sebutkan nomor Purchase Order (PO) yang ingin dilihat atau diunduh dokumen PDF resminya (contoh: *'Tolong tampilkan dokumen PDF untuk PO-2026-006'*).",
            "hint": "Tolong tampilkan dokumen PDF untuk PO-2026-006"
        }

    # 6. Specific item stock query clarification: asks for stock but specifies no item
    wants_specific_stock = any(w in p_lower for w in ["berapa stok barang", "cek stok barang", "tampilkan stok barang", "cek saldo barang", "stok barang apa", "cek ketersediaan barang"])
    generic_only = tokens = set(re.findall(r'[a-zA-Z]+', p_lower))
    generic_stock_words = {"berapa", "cek", "tampilkan", "saldo", "stok", "barang", "barangnya", "material", "saat", "ini", "ada", "apa", "saja", "tolong", "gudang"}
    if wants_specific_stock and tokens.issubset(generic_stock_words):
        return {
            "needs_clarification": True,
            "field": "item_name_required",
            "title": "Nama Barang Diperlukan",
            "message": "Mohon sebutkan nama atau SKU barang material yang ingin Anda periksa stoknya (contoh: *'Berapa stok SFP Transceiver 10G saat ini?'*).",
            "hint": "Berapa stok SFP Transceiver 10G saat ini?"
        }

    # 7. Leave approval or processing clarification: wants to approve/reject leave but no leave ID or employee
    wants_leave_action = ("cuti" in p_lower) and any(w in p_lower for w in ["setujui", "tolak", "proses", "otorisasi", "verifikasi", "approve", "reject"])
    if wants_leave_action:
        has_leave_id = bool(re.search(r'\blv[-_]?\d+', p_lower))
        emp_match = re.search(r'(?:cuti|milik|atas\s+nama)\s+(?:sdr\s+|bapak\s+|ibu\s+|pak\s+)?([a-zA-Z]{3,})', p_lower)
        filler_leave_words = {"ini", "itu", "dong", "ya", "saja", "lah", "tersebut", "yang", "pending", "diajukan"}
        has_valid_emp = emp_match and (emp_match.group(1).lower() not in filler_leave_words)
        if not (has_leave_id or has_valid_emp):
            return {
                "needs_clarification": True,
                "field": "leave_id_required",
                "title": "ID Pengajuan Cuti Diperlukan",
                "message": "Untuk memproses persetujuan atau penolakan cuti karyawan, mohon sebutkan nomor registrasi pengajuan cuti (contoh: *'Setujui pengajuan cuti LV-20260910-001'*).",
                "hint": "Setujui pengajuan cuti LV-20260910-001"
            }

    # 8. Invoice / Billing generation clarification: wants to generate invoice without client/operator
    wants_invoice_gen = ("invoice" in p_lower or "tagihan" in p_lower) and any(w in p_lower for w in ["buat", "terbitkan", "draf", "draft", "generate", "cetak"])
    has_operator = any(op in p_lower for op in ["telkomsel", "tsel", "indosat", "isat", "xl", "smartfren", "smart", "moratel", "hutchison"])
    if wants_invoice_gen and not has_operator:
        return {
            "needs_clarification": True,
            "field": "client_operator_required",
            "title": "Nama Operator / Klien Diperlukan",
            "message": "Untuk menerbitkan dokumen tagihan/invoice sewa menara, mohon sebutkan nama operator telekomunikasi klien (contoh: *'Buat draf invoice sewa menara untuk operator Telkomsel'*).",
            "hint": "Buat draf invoice sewa menara untuk operator Telkomsel"
        }

    # 9. Employee mutation clarification: wants to mutate employee but lacks department or position or name
    wants_mutation = any(w in p_lower for w in ["mutasi", "pindahkan karyawan", "rotasi karyawan"])
    if wants_mutation:
        clean_p = re.sub(r'^(?:contoh|saran|instruksi)\s*:\s*', '', prompt.strip(), flags=re.IGNORECASE).strip(' "\'')
        clean_lower = clean_p.lower()
        has_dept = any(d in clean_lower for d in ["departemen", "divisi", "it", "field operations", "noc", "finance", "project engineering", "logistik", "hr"])
        has_pos = any(p in clean_lower for p in ["jabatan", "posisi", "sebagai", "full stack", "rigger", "splicer", "supervisor", "lead", "specialist", "billing", "accounting", "technician", "teknisi", "engineer", "admin", "junior", "senior"])
        
        emp_match = re.search(r'(?:mutasi|pindahkan)\s+(?:karyawan\s+)?([a-zA-Z\s]{3,25}?)(?:\s+(?:ke|dan|dengan|sebagai|menjadi|jadi)\b|$)', clean_p, re.IGNORECASE)
        emp_name = emp_match.group(1).strip() if emp_match else ""
        if emp_name.lower() in ["karyawan", "pegawai", "staff", "dia", "ini", "teknisi"]:
            emp_name = ""
            
        if not has_dept or not has_pos or not emp_name:
            if not emp_name:
                missing_item = "nama karyawan serta departemen dan jabatan tujuan"
                hint_str = "Tolong mutasi [Nama Karyawan] ke departemen [Departemen] dengan jabatan [Posisi]"
            elif not has_dept:
                missing_item = "nama departemen/divisi tujuan"
                hint_str = f"Tolong mutasi {emp_name} ke departemen [Departemen] dengan jabatan [Posisi]"
            else:
                missing_item = "jabatan/posisi baru"
                hint_str = f"Tolong mutasi {emp_name} ke departemen [Departemen] dengan jabatan [Posisi]"
                
            return {
                "needs_clarification": True,
                "field": "mutation_parameters_required",
                "title": "Data Mutasi Karyawan Belum Lengkap",
                "message": f"Untuk memproses mutasi{f' {emp_name}' if emp_name else ''}, kami perlu konfirmasi: {missing_item} yang dituju? Mohon sebutkan agar data mutasi dapat dicatat dengan lengkap di database.",
                "hint": hint_str
            }
    return None


class SemanticRouter:
    @classmethod
    async def route_prompt(
        cls, 
        prompt: str, 
        tenant_id: str = "ALL", 
        history: list[dict[str, str]] | None = None
    ) -> dict:
        """
        Matches user prompt strictly to a predefined workflow ID allowed for this tenant.
        Does NOT hallucinate or pick an arbitrary workflow if intent is out-of-scope.
        Returns workflow_id: None and is_unrelated: True if the prompt is out of scope.
        Supports multi-turn context history.
        """
        conn = get_db_connection(read_only=True)
        query_cols = "id, name, description, business_instruction, example_prompts, tenant_id"
        if tenant_id in ["ALL", "admin", "ADMIN", "SUPERADMIN"]:
            workflows = conn.execute(f"""
                SELECT {query_cols} 
                FROM workflows 
                ORDER BY id ASC
            """).fetchall()
        else:
            tenant_variants = [tenant_id, "ALL"]
            if tenant_id in ["INVENTORY", "TENANT_A", "usera"]:
                tenant_variants.extend(["INVENTORY", "TENANT_A", "usera"])
            elif tenant_id in ["HR", "TENANT_B", "userb"]:
                tenant_variants.extend(["HR", "TENANT_B", "userb"])
            elif tenant_id in ["FINANCE", "TENANT_C", "userc"]:
                tenant_variants.extend(["FINANCE", "TENANT_C", "userc"])
            placeholders = ", ".join(["?"] * len(tenant_variants))
            workflows = conn.execute(f"""
                SELECT {query_cols} 
                FROM workflows 
                WHERE tenant_id IN ({placeholders})
                ORDER BY id ASC
            """, tenant_variants).fetchall()
        conn.close()
        
        if not workflows:
            return {
                "workflow_id": None,
                "send_email": False,
                "threshold_updates": [],
                "target_item_name": None,
                "is_fallback": False
            }

        prompt_clean = re.sub(r'^(?:contoh|saran|instruksi)\s*:\s*', '', prompt.strip(), flags=re.IGNORECASE).strip(' "\'').lower()
        # Guard against single-word, ambiguous, or too-short inputs without clear command
        if len(prompt_clean) < 3 or prompt_clean in ["pr", "po", "stok", "cek", "halo", "hi", "tes", "test", "help", "menu", "workflow", "buat", "pesan"]:
            return {
                "workflow_id": None,
                "is_unrelated": True,
                "send_email": False,
                "threshold_updates": [],
                "target_item_name": None,
                "is_fallback": False
            }

        # Build enriched workflows context including business instructions and example prompts
        workflow_entries = []
        for row in workflows:
            wf_id, wf_name, wf_desc, wf_inst, wf_ex, wf_tenant = row
            entry = f"- ID: {wf_id}\n  Nama: {wf_name}\n  Deskripsi: {wf_desc or '-'}"
            if wf_inst:
                entry += f"\n  Instruksi Bisnis: {wf_inst}"
            if wf_ex:
                try:
                    examples = json.loads(wf_ex) if isinstance(wf_ex, str) else wf_ex
                    if isinstance(examples, list) and examples:
                        entry += f"\n  Contoh Prompt: {'; '.join(str(x) for x in examples)}"
                except Exception:
                    entry += f"\n  Contoh Prompt: {wf_ex}"
            workflow_entries.append(entry)
        workflows_str = "\n\n".join(workflow_entries)
        
        system_prompt = f"""You are a Strict Semantic Router for an Enterprise Management System (PT Bali Towerindo Sentra Tbk).
Match the user's operational command to EXACTLY ONE of the following permitted workflows:

{workflows_str}

CRITICAL RULES:
1. CONTEXTUAL SENTENCE UNDERSTANDING (DO NOT DO KEYWORD MATCHING):
   - You MUST analyze the FULL CONTEXT and grammatical meaning of the user's sentence. Never match solely on isolated words (such as "cuti", "leave", "email", "stok", "po").
   - CREATE/SUBMIT vs QUERY/RECAP/REPORT/EXPORT:
     * Workflow WF-B03 is STRICTLY for RECORDING A NEW LEAVE APPLICATION for an individual employee ("Pengajuan Cuti Teknisi dan Penerbitan Dokumen PDF HR"). It requires an intent to submit/apply for new leave (e.g. "Ajukan cuti 3 hari untuk Budi Santoso").
     * If the user's sentence context is asking to QUERY, RECAP, AUDIT, VIEW HISTORY, FILTER, or SEND/EXPORT A REPORT OF EXISTING RECORDS (e.g. 'kirim Employee Leave Request History status Pending_Approval ke email...', 'rekap permohonan cuti pending', 'lihat histori cuti teknisi'), this is a QUERY/REPORT intent, NOT a leave submission!
     * DO NOT MATCH query/report/history requests to WF-B03! If no workflow exists in the permitted list for that specific export/email report, return:
       {{"workflow_id": null, "action_type": "workflow_not_found", "is_unrelated": false, "can_request_admin": true}}
   - PROCUREMENT/RESTOCK vs QUERY EXISTING PRs:
     * Workflow WF-A01 is strictly for drafting NEW procurement PR for depleted inventory. Do not match existing PR inquiries or PR history exports to WF-A01.
   - CLIENT ONBOARDING vs QUERY CONTRACTS:
     * Workflow WF-C04 is strictly for onboarding a NEW client operator and initial MLA contract. Do not match general client list or invoice inquiries to WF-C04.
2. If the user's prompt is UNRELATED, vague, ambiguous, programming questions, chit-chat, or general greetings without clear command, return:
   {{"workflow_id": null, "is_unrelated": true}}
3. If the user's operational command is an ad-hoc analytical inquiry, conditional anomaly detection, custom filtering threshold, multi-entity emergency assignment/roster, or cross-entity query (e.g. combining active technicians and rigger candidates for emergency duty, or inspecting radius GPS distances), return:
   {{"workflow_id": null, "is_unrelated": false}}
   so the Autonomous Agent can execute precise dynamic SQL queries directly on DuckDB. Standard candidate filtering workflow (WF-B02) is only for simple rigger applicant filtering, NOT emergency duty assignment across both employees and candidates.
4. If the user wants to register, add, or create a new inventory item, extract "new_item_data": {{"name": string, "category": string, "current_stock": int, "min_threshold": int, "max_threshold": int, "avg_daily_usage": float, "lead_time_days": int, "unit": string}}.
5. If the user wants to update a threshold, extract "threshold_updates": [{{"item_name": "name of item", "new_min_threshold": 100, "new_max_threshold": 300}}].
6. If the user specifies an item name to inspect, extract "target_item_name".
7. If the user explicitly asks to send an email, report, or notify via email, extract "send_email": true. Otherwise, "send_email": false.
8. STRICT PARAMETER COMPLETENESS & CLARIFICATION VALIDATION:
   You MUST verify if all mandatory parameters required for the user's intended action are present. If ANY critical parameter is missing, DO NOT guess, DO NOT execute the workflow, and DO NOT default to preset values. You MUST return:
   {{
     "workflow_id": "clarification_needed",
     "needs_clarification": true,
     "clarification": {{
       "title": "Judul Parameter yang Kurang",
       "message": "Pesan ramah dalam Bahasa Indonesia yang menjelaskan parameter apa yang belum lengkap dan meminta konfirmasi ke pengguna.",
       "hint": "Contoh kalimat prompt lengkap yang bisa langsung digunakan pengguna"
     }}
   }}

Output strictly valid JSON with exact keys:
- "workflow_id" (string or null)
- "action_type" (optional string, e.g. "workflow_not_found" or "clarification_needed")
- "is_unrelated" (boolean)
- "can_request_admin" (optional boolean)
- "needs_clarification" (optional boolean)
- "clarification" (optional object with title, message, hint)
- "new_item_data" (optional object)
- "threshold_updates" (optional array)
- "target_item_name" (optional string)
- "send_email" (boolean)
"""
        messages = [{"role": "system", "content": system_prompt}]
        if history and isinstance(history, list):
            for turn in history[-6:]:
                if isinstance(turn, dict) and turn.get("role") and turn.get("content"):
                    messages.append({"role": turn["role"], "content": str(turn["content"])})
        messages.append({"role": "user", "content": prompt})

        prompt_lower = prompt.lower()
        extracted_email = extract_recipient_email(prompt)

        # Dynamic check: if user explicitly specified an exact registered workflow ID from DuckDB
        valid_ids = {r[0] for r in workflows}
        words = re.findall(r'[a-zA-Z0-9\-_]+', prompt)
        for w in words:
            w_upper = w.upper()
            if w_upper in valid_ids:
                return {
                    "workflow_id": w_upper,
                    "send_email": bool(extracted_email) or ("email" in prompt_lower),
                    "recipient_email": extracted_email,
                    "is_fallback": False
                }

        # ----------------------------------------------------
        # LAYER 1: DYNAMIC LLM-FIRST ROUTING (Primary Brain)
        # ----------------------------------------------------
        try:
            response_str = await gateway.chat_completion(
                settings.MODEL_NAME or "qwen-38", 
                messages, 
                temperature=0.1, 
                response_format_json=True
            )
            json_match = re.search(r'\{.*\}', response_str, re.DOTALL)
            if json_match:
                response_str = json_match.group(0)
            parsed = json.loads(response_str)

            # 1. Parameter Clarification needed
            if parsed.get("needs_clarification") or parsed.get("workflow_id") == "clarification_needed":
                return {
                    "workflow_id": "clarification_needed",
                    "action_type": "clarification_needed",
                    "needs_clarification": True,
                    "clarification": parsed.get("clarification") or {
                        "title": "Klarifikasi Diperlukan",
                        "message": parsed.get("message") or "Mohon lengkapi parameter instruksi Anda.",
                        "hint": prompt
                    },
                    "message": (parsed.get("clarification") or {}).get("message", "Mohon lengkapi parameter instruksi Anda."),
                    "is_fallback": False
                }

            # 2. Workflow proposal needed (User asking for unsupported/unregistered business workflow)
            if parsed.get("action_type") == "workflow_not_found" or parsed.get("can_request_admin"):
                return {
                    "workflow_id": None,
                    "action_type": "workflow_not_found",
                    "can_request_admin": True,
                    "is_tool_blocked": True,
                    "message": parsed.get("message") or "Alur kerja untuk instruksi ini belum terdaftar di sistem operasional BaliTower. Anda dapat mengajukan permohonan alur kerja baru ini ke Administrator.",
                    "prompt_text": prompt,
                    "is_fallback": False
                }

            # 3. Direct match with registered workflow ID from DuckDB
            wf_match = parsed.get("workflow_id")
            if wf_match and wf_match in valid_ids:
                return {
                    "workflow_id": wf_match,
                    "send_email": bool(extracted_email) or bool(parsed.get("send_email")),
                    "recipient_email": extracted_email or parsed.get("recipient_email"),
                    "threshold_updates": parsed.get("threshold_updates", []),
                    "target_item_name": parsed.get("target_item_name"),
                    "new_item_data": parsed.get("new_item_data"),
                    "is_fallback": False
                }

            # 4. Out-of-scope / Unrelated chit-chat
            if parsed.get("is_unrelated"):
                return {
                    "workflow_id": None,
                    "is_unrelated": True,
                    "send_email": False,
                    "threshold_updates": [],
                    "target_item_name": None,
                    "is_fallback": False
                }

            # 5. Ad-Hoc / Dynamic Execution (Tier 2 AutonomousAgent)
            # When prompt is valid operational intent but no registered workflow matches
            po_match = re.search(r'\b(PO-\d{4}-\d{3,4})\b', prompt, re.IGNORECASE)
            target_po_id = parsed.get("target_po_id") or (po_match.group(1).upper() if po_match else None)

            return {
                "workflow_id": None,
                "is_unrelated": False,
                "send_email": bool(extracted_email) or bool(parsed.get("send_email")),
                "recipient_email": extracted_email or parsed.get("recipient_email"),
                "threshold_updates": parsed.get("threshold_updates", []),
                "target_item_name": parsed.get("target_item_name"),
                "target_po_id": target_po_id,
                "is_fallback": False
            }

        except Exception as e:
            print(f"[SEMANTIC ROUTER] LLM offline or timed out ({e}). Activating dynamic fallback.")

            # Dynamic Fallback:
            # 1. Check clarification needs if critical parameters missing
            clarif = check_clarification_needs(prompt, tenant_id=tenant_id, recipient_email=extracted_email)
            if clarif:
                return {
                    "workflow_id": "clarification_needed",
                    "action_type": "clarification_needed",
                    "needs_clarification": True,
                    "clarification": clarif,
                    "message": clarif.get("message", "Mohon lengkapi parameter instruksi Anda."),
                    "is_fallback": True
                }

            # 2. Check if prompt matches exact example prompts registered dynamically in DuckDB
            for row in workflows:
                wf_id, wf_name, wf_desc, wf_inst, wf_ex, wf_tenant = row
                if wf_ex:
                    try:
                        ex_list = json.loads(wf_ex) if isinstance(wf_ex, str) else wf_ex
                        if isinstance(ex_list, list):
                            for ex_p in ex_list:
                                ex_clean = str(ex_p).lower().strip()
                                clean_prompt_core = re.sub(r'^(?:tolong|mohon|silakan|bantu|coba)\s+', '', prompt_lower).strip(' .!?,\'"')
                                clean_ex_core = re.sub(r'^(?:tolong|mohon|silakan|bantu|coba)\s+', '', ex_clean).strip(' .!?,\'"')
                                if ex_clean and (
                                    ex_clean == prompt_lower
                                    or prompt_lower.strip(' .!?,') == ex_clean.strip(' .!?,')
                                    or clean_prompt_core == clean_ex_core
                                ):
                                    return {
                                        "workflow_id": wf_id,
                                        "send_email": bool(extracted_email) or ("email" in prompt_lower),
                                        "recipient_email": extracted_email,
                                        "is_fallback": True
                                    }
                    except Exception:
                        pass

            # 3. Otherwise, gracefully fall through to AutonomousAgent (Tier 2) for ad-hoc processing
            po_match = re.search(r'\b(PO-\d{4}-\d{3,4})\b', prompt, re.IGNORECASE)
            return {
                "workflow_id": None,
                "is_unrelated": False,
                "send_email": bool(extracted_email) or ("email" in prompt_lower),
                "recipient_email": extracted_email,
                "threshold_updates": [],
                "target_item_name": None,
                "target_po_id": po_match.group(1).upper() if po_match else None,
                "is_fallback": True
            }

