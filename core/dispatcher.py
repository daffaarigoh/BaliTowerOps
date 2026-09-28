import asyncio
import logging
import smtplib
from datetime import datetime
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any

import httpx

from core.config import settings

logger = logging.getLogger(__name__)


def _format_markdown_to_html(text: str) -> str:
    """Converts markdown (headings, bold, tables, code) into clean inline-styled HTML for email clients."""
    if not text:
        return ""
    import re
    lines = text.strip().split("\n")
    html_out = []
    in_table = False
    table_rows = []

    def flush_table(t_rows):
        if not t_rows:
            return ""
        tbl_html = ['<div style="overflow-x: auto; margin: 16px 0;"><table style="width: 100%; border-collapse: collapse; font-size: 12.5px; font-family: inherit; border: 1px solid #E2E8F0; background: #FFFFFF;">']
        for idx, row in enumerate(t_rows):
            cols = [c.strip() for c in row.split("|")[1:-1]]
            if not cols or all(re.match(r'^:?-+:?$', c) for c in cols):
                continue
            if idx == 0:
                tbl_html.append('<tr style="background: #F8FAFC; color: #334155; font-weight: 700; border-bottom: 2px solid #CBD5E1;">')
                for c in cols:
                    tbl_html.append(f'<th style="padding: 10px 12px; border: 1px solid #E2E8F0; text-align: left;">{_format_inline(c)}</th>')
                tbl_html.append('</tr>')
            else:
                bg = "#F8FAFC" if idx % 2 == 1 else "#FFFFFF"
                tbl_html.append(f'<tr style="background: {bg}; border-bottom: 1px solid #E2E8F0;">')
                for c in cols:
                    tbl_html.append(f'<td style="padding: 8px 12px; border: 1px solid #E2E8F0;">{_format_inline(c)}</td>')
                tbl_html.append('</tr>')
        tbl_html.append('</table></div>')
        return "".join(tbl_html)

    def _format_inline(s: str) -> str:
        s = re.sub(r'`([^`]+)`', r'<code style="background: #F1F5F9; color: #2563EB; padding: 2px 6px; border-radius: 4px; font-family: monospace; font-size: 11.5px;">\1</code>', s)
        s = re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', s)
        s = re.sub(r'(?<!\*)\*([^*]+)\*(?!\*)', r'<em>\1</em>', s)
        return s

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("|") and stripped.endswith("|"):
            in_table = True
            table_rows.append(stripped)
        else:
            if in_table:
                html_out.append(flush_table(table_rows))
                table_rows = []
                in_table = False

            if stripped.startswith("### "):
                html_out.append(f'<h3 style="color: #0F172A; font-size: 15px; font-weight: 700; margin: 18px 0 8px 0;">{_format_inline(stripped[4:])}</h3>')
            elif stripped.startswith("## "):
                html_out.append(f'<h2 style="color: #0F172A; font-size: 17px; font-weight: 700; margin: 20px 0 10px 0;">{_format_inline(stripped[3:])}</h2>')
            elif stripped.startswith("# "):
                html_out.append(f'<h1 style="color: #0F172A; font-size: 19px; font-weight: 800; margin: 22px 0 12px 0;">{_format_inline(stripped[2:])}</h1>')
            elif stripped.startswith("*") and stripped.endswith("*") and len(stripped) > 2:
                html_out.append(f'<p style="color: #64748B; font-size: 12.5px; font-style: italic; margin: 6px 0;">{_format_inline(stripped[1:-1])}</p>')
            elif stripped:
                html_out.append(f'<p style="color: #334155; font-size: 13px; line-height: 1.6; margin: 8px 0;">{_format_inline(stripped)}</p>')
            else:
                html_out.append('<div style="height: 6px;"></div>')

    if in_table:
        html_out.append(flush_table(table_rows))

    return "".join(html_out)


class MultiChannelDispatcher:
    """
    Unified multi-channel integration dispatcher:
    1. DuckDB Database (Saves structured historical data and tracks workflow progress)
    2. Email Dispatcher (Sends SMTP mail with optional PDF attachment / zero-config simulation)
    """

    @classmethod
    async def dispatch_email(
        cls,
        recipient_email: str | None = None,
        subject: str = "Notifikasi Pengadaan Inventaris",
        content_text: str = "",
        attachment_path: str | None = None,
        html_content: str | None = None,
        pr_number: str | None = None,
        leave_id: str | None = None,
        leave_data: dict[str, Any] | None = None,
        base_url: str | None = None,
        table_headers: list[str] | None = None,
        table_rows: list[list[Any] | tuple[Any, ...]] | None = None,
        action_button_label: str | None = None,
        action_button_url: str | None = None
    ) -> dict[str, Any]:
        """
        Sends a rich HTML email notification with optional PDF attachment and interactive Approve/Reject action buttons.
        Falls back to smart simulation if SMTP credentials are not configured.
        """
        import re
        from core.config import get_base_url
        if not base_url:
            base_url = get_base_url()
        recipient = recipient_email or settings.DEFAULT_RECIPIENT_EMAIL or settings.SMTP_EMAIL or "manager@balitower.co.id"
        is_smtp_configured = bool(settings.SMTP_EMAIL and settings.SMTP_PASSWORD)

        # Build dynamic Markdown table if structured table data is provided
        if table_headers and table_rows:
            tbl_lines = ["| " + " | ".join(str(h) for h in table_headers) + " |"]
            aligns = []
            for h in table_headers:
                h_l = str(h).lower()
                if any(k in h_l for k in ["no", "id", "sku", "status", "qty", "stok"]):
                    aligns.append(":---:")
                elif any(k in h_l for k in ["harga", "total", "biaya", "price"]):
                    aligns.append("---:")
                else:
                    aligns.append(":---")
            tbl_lines.append("| " + " | ".join(aligns) + " |")
            for r in table_rows:
                tbl_lines.append("| " + " | ".join(str(c) if c is not None else "-" for c in r) + " |")
            tbl_str = "\n".join(tbl_lines)
            if content_text:
                content_text = f"{content_text}\n\n{tbl_str}"
            else:
                content_text = tbl_str

        # Auto-detect PR number from subject, attachment_path, or content_text if not explicitly given
        if not pr_number:
            candidates = [attachment_path or "", subject or "", content_text or ""]
            for cand in candidates:
                m = re.search(r'\b(PR[-_]\d{8}[-_]\d{6}|PR[-_]\d{4}[-_]\d{3})\b', cand)
                if m:
                    pr_number = m.group(1).replace('_', '-')
                    break

        # Build default rich HTML for Leave Request if not provided
        if not html_content and leave_id:
            approve_link = f"{base_url}/api/approval/leave-quick-action?leave_id={leave_id}&action=APPROVE"
            reject_link = f"{base_url}/api/approval/leave-quick-action?leave_id={leave_id}&action=REJECT"
            pdf_link = f"{base_url}/api/documents/leave/{leave_id}/download"
            
            ldata = leave_data or {}
            applicant_name = ldata.get("applicant_name") or ldata.get("employee_name") or "Karyawan Pemohon"
            job_title = ldata.get("job_title") or "Staff Operasional"
            dept = ldata.get("department") or "Human Resources & Field Operations"
            start_date = ldata.get("start_date") or "-"
            end_date = ldata.get("end_date") or "-"
            days_req = ldata.get("days_requested") or 1
            reason = ldata.get("reason") or "Keperluan Pribadi / Mendesak"
            substitute = ldata.get("substitute_name") or ldata.get("substitute_employee_id") or "-"
            
            type_map = {
                "ANNUAL_LEAVE": "Cuti Tahunan",
                "SICK_LEAVE": "Cuti Sakit",
                "SPECIAL_LEAVE": "Cuti Khusus / Alasan Penting",
                "EMERGENCY_LEAVE": "Cuti Alasan Mendesak",
                "MATERNITY_LEAVE": "Cuti Melahirkan"
            }
            raw_type = str(ldata.get("leave_type") or "ANNUAL_LEAVE").upper()
            type_label = type_map.get(raw_type, raw_type)
            
            html_content = f"""<!DOCTYPE html>
<html lang="id">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Pengajuan Cuti Karyawan | {leave_id}</title>
    <style>
        body {{
            margin: 0;
            padding: 24px 12px;
            background-color: #F1F5F9;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
            color: #0F172A;
            line-height: 1.5;
            -webkit-font-smoothing: antialiased;
        }}
        .email-wrapper {{
            max-width: 620px;
            margin: 0 auto;
            background: #FFFFFF;
            border: 1px solid #CBD5E1;
            border-radius: 8px;
            overflow: hidden;
            box-shadow: 0 1px 3px rgba(0, 0, 0, 0.08);
        }}
        .corp-header {{
            background: #0F172A;
            color: #FFFFFF;
            padding: 22px 28px;
            border-bottom: 3px solid #2563EB;
        }}
        .corp-title {{
            font-size: 15px;
            font-weight: 700;
            letter-spacing: 0.08em;
            text-transform: uppercase;
            margin: 0;
            color: #F8FAFC;
        }}
        .corp-subtitle {{
            font-size: 12px;
            color: #94A3B8;
            margin: 4px 0 0 0;
            letter-spacing: 0.02em;
        }}
        .email-body {{
            padding: 28px;
        }}
        .doc-badge-row {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 20px;
            padding-bottom: 14px;
            border-bottom: 1px solid #E2E8F0;
        }}
        .doc-id {{
            font-family: 'Consolas', 'Courier New', monospace;
            font-size: 13px;
            font-weight: 700;
            color: #1D4ED8;
        }}
        .status-pill {{
            display: inline-block;
            padding: 4px 10px;
            font-size: 11px;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            background: #FEF3C7;
            color: #92400E;
            border-radius: 4px;
            border: 1px solid #FCD34D;
        }}
        .table-details {{
            width: 100%;
            border-collapse: collapse;
            margin: 18px 0;
            font-size: 13px;
        }}
        .table-details td {{
            padding: 9px 12px;
            border-bottom: 1px solid #E2E8F0;
        }}
        .table-details td.label {{
            color: #64748B;
            width: 38%;
            font-weight: 500;
        }}
        .table-details td.value {{
            color: #0F172A;
            font-weight: 600;
        }}
        .instruction-box {{
            background: #EFF6FF;
            border-left: 3px solid #2563EB;
            padding: 12px 16px;
            margin: 18px 0 24px 0;
            font-size: 12.5px;
            color: #1E40AF;
            line-height: 1.6;
        }}
        .btn-container {{
            margin: 28px 0 16px 0;
            text-align: center;
        }}
        .btn {{
            display: inline-block;
            padding: 11px 22px;
            font-size: 13px;
            font-weight: 600;
            text-decoration: none;
            border-radius: 6px;
            margin: 4px 6px;
            letter-spacing: 0.02em;
        }}
        .btn-approve {{
            background: #15803D;
            color: #FFFFFF !important;
            border: 1px solid #166534;
        }}
        .btn-reject {{
            background: #FFFFFF;
            color: #B91C1C !important;
            border: 1px solid #F87171;
        }}
        .btn-doc {{
            background: #F8FAFC;
            color: #334155 !important;
            border: 1px solid #CBD5E1;
            font-size: 12px;
            padding: 8px 16px;
        }}
        .corp-footer {{
            background: #F8FAFC;
            border-top: 1px solid #E2E8F0;
            padding: 18px 28px;
            font-size: 11.5px;
            color: #64748B;
            line-height: 1.6;
        }}
    </style>
</head>
<body>
    <div class="email-wrapper">
        <div class="corp-header">
            <h1 class="corp-title">PT Bali Towerindo Sentra Tbk</h1>
            <p class="corp-subtitle">Divisi Human Resources & Field Operations</p>
        </div>
        <div class="email-body">
            <div class="doc-badge-row">
                <div>
                    <span style="font-size: 11px; color: #64748B; text-transform: uppercase; font-weight: 600;">Nomor Dokumen Cuti:</span><br>
                    <span class="doc-id">{leave_id}</span>
                </div>
                <div style="text-align: right;">
                    <span class="status-pill">Menunggu Persetujuan HR</span>
                </div>
            </div>

            <p style="margin-top: 0; font-size: 14px; font-weight: 600; color: #0F172A;">Kepada Yth. Tim Human Resources / Manajer Operasional,</p>
            <p style="font-size: 13.5px; color: #334155; margin-bottom: 12px;">
                Permohonan pengajuan cuti kerja baru telah diajukan melalui sistem operasional mandiri karyawan dan memerlukan peninjauan serta otorisasi resmi Anda:
            </p>

            <table class="table-details">
                <tr>
                    <td class="label">Karyawan Pemohon</td>
                    <td class="value">{applicant_name}</td>
                </tr>
                <tr>
                    <td class="label">Posisi / Jabatan</td>
                    <td class="value">{job_title}</td>
                </tr>
                <tr>
                    <td class="label">Departemen / Divisi</td>
                    <td class="value">{dept}</td>
                </tr>
                <tr>
                    <td class="label">Kategori Cuti</td>
                    <td class="value">{type_label}</td>
                </tr>
                <tr>
                    <td class="label">Periode Tanggal</td>
                    <td class="value">{start_date} s/d {end_date} ({days_req} Hari Kerja)</td>
                </tr>
                <tr>
                    <td class="label">Alasan Cuti</td>
                    <td class="value">{reason}</td>
                </tr>
                <tr>
                    <td class="label">Pendelegasian Tugas</td>
                    <td class="value">{substitute}</td>
                </tr>
            </table>

            <div class="instruction-box">
                <strong>Otorisasi Digital HR:</strong> Silakan klik salah satu tombol tindakan di bawah. Sistem terintegrasi akan langsung memperbarui status kehadiran di database dan mencatatkan kuota cuti karyawan secara realtime.
            </div>

            <div class="btn-container">
                <a href="{approve_link}" class="btn btn-approve" target="_blank">&#10003; Setujui Permohonan (Approve)</a>
                <a href="{reject_link}" class="btn btn-reject" target="_blank">&#10007; Tolak Permohonan (Reject)</a>
                <a href="{pdf_link}" class="btn btn-doc" target="_blank">&#128196; Unduh Berkas Pengajuan Cuti (PDF)</a>
            </div>
        </div>
        <div class="corp-footer">
            <strong>PT Bali Towerindo Sentra Tbk</strong><br>
            Wisma Kodel Lantai 6, Jl. H.R. Rasuna Said Kav. B-4, Jakarta Selatan 12920<br>
            <em>Pemberitahuan otomatis dari Enterprise Operations Portal. Menekan tombol persetujuan langsung memperbarui status di database utama.</em>
        </div>
    </div>
</body>
</html>"""

        # Build default rich HTML for Purchase Requisition if not provided
        elif not html_content and pr_number:
            approve_link = f"{base_url}/api/approval/quick-action?pr_number={pr_number}&action=APPROVE"
            reject_link = f"{base_url}/api/approval/quick-action?pr_number={pr_number}&action=REJECT"
            pdf_link = f"{base_url}/api/documents/pr/{pr_number}/download"
            from datetime import datetime
            today_str = datetime.now().strftime("%d %B %Y, %H:%M WIB")
            formatted_body = _format_markdown_to_html(content_text)
            
            html_content = f"""<!DOCTYPE html>
<html lang="id">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Pemberitahuan Pengadaan Barang | {pr_number}</title>
    <style>
        body {{
            margin: 0;
            padding: 24px 12px;
            background-color: #F1F5F9;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
            color: #0F172A;
            line-height: 1.5;
            -webkit-font-smoothing: antialiased;
        }}
        .email-wrapper {{
            max-width: 620px;
            margin: 0 auto;
            background: #FFFFFF;
            border: 1px solid #CBD5E1;
            border-radius: 8px;
            overflow: hidden;
            box-shadow: 0 1px 3px rgba(0, 0, 0, 0.08);
        }}
        .corp-header {{
            background: #0F172A;
            color: #FFFFFF;
            padding: 22px 28px;
            border-bottom: 3px solid #2563EB;
        }}
        .corp-title {{
            font-size: 15px;
            font-weight: 700;
            letter-spacing: 0.08em;
            text-transform: uppercase;
            margin: 0;
            color: #F8FAFC;
        }}
        .corp-subtitle {{
            font-size: 12px;
            color: #94A3B8;
            margin: 4px 0 0 0;
            letter-spacing: 0.02em;
        }}
        .email-body {{
            padding: 28px;
        }}
        .doc-badge-row {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 20px;
            padding-bottom: 14px;
            border-bottom: 1px solid #E2E8F0;
        }}
        .doc-id {{
            font-family: 'Consolas', 'Courier New', monospace;
            font-size: 13px;
            font-weight: 700;
            color: #1D4ED8;
        }}
        .status-pill {{
            display: inline-block;
            padding: 4px 10px;
            font-size: 11px;
            font-weight: 700;
            background: #FEF3C7;
            color: #92400E;
            border: 1px solid #FCD34D;
            border-radius: 4px;
        }}
        .instruction-box {{
            background: #EFF6FF;
            border-left: 3px solid #2563EB;
            padding: 12px 16px;
            margin: 18px 0 24px 0;
            font-size: 12.5px;
            color: #1E40AF;
        }}
        .corp-footer {{
            background: #F8FAFC;
            border-top: 1px solid #E2E8F0;
            padding: 18px 28px;
            font-size: 11.5px;
            color: #64748B;
            line-height: 1.6;
        }}
    </style>
</head>
<body>
    <div class="email-wrapper">
        <div class="corp-header">
            <h1 class="corp-title">PT Bali Towerindo Sentra Tbk</h1>
            <p class="corp-subtitle">Divisi Supply Chain Management & Pengadaan Logistik</p>
        </div>
        <div class="email-body">
            <div class="doc-badge-row">
                <div>
                    <span style="font-size: 11px; color: #64748B; text-transform: uppercase; font-weight: 600;">Nomor Dokumen:</span><br>
                    <span class="doc-id">{pr_number}</span>
                </div>
                <div style="text-align: right;">
                    <span class="status-pill">Menunggu Otorisasi</span>
                </div>
            </div>

            <p style="margin-top: 0; font-size: 14px; font-weight: 600; color: #0F172A;">Kepada Yth. Leader / Manajer Operasional Pengadaan,</p>
            <p style="font-size: 13.5px; color: #334155; margin-bottom: 12px;">
                Sistem monitoring logistik mendeteksi ketersediaan material infrastruktur telah menyentuh batas minimum stok kerja (Reorder Point). Dokumen pengajuan pembelian (Purchase Requisition) resmi telah disusun untuk permohonan persetujuan Anda:
            </p>

            <div style="margin: 16px 0;">{formatted_body}</div>

            <div class="instruction-box">
                <strong>Ketentuan Otorisasi:</strong><br>
                1. <strong>Setujui (APPROVE)</strong>: Sistem akan segera menerbitkan Purchase Order (PO) resmi ke rekanan vendor terdaftar.<br>
                2. <strong>Tolak (REJECT)</strong>: Proses pengadaan dihentikan dan pengalokasian anggaran dibatalkan.
            </div>

            <div style="margin: 28px 0 16px 0; text-align: center;">
                <a href="{approve_link}" style="display: inline-block; padding: 12px 24px; font-size: 13px; font-weight: 700; color: #FFFFFF !important; background-color: #15803D; border: 1px solid #166534; border-radius: 6px; text-decoration: none; margin: 4px 6px; letter-spacing: 0.02em;" target="_blank">SETUJUI PENGAJUAN (APPROVE)</a>
                <a href="{reject_link}" style="display: inline-block; padding: 12px 24px; font-size: 13px; font-weight: 700; color: #B91C1C !important; background-color: #FFFFFF; border: 1px solid #F87171; border-radius: 6px; text-decoration: none; margin: 4px 6px; letter-spacing: 0.02em;" target="_blank">TOLAK PENGAJUAN (REJECT)</a>
            </div>
            <div style="text-align: center; margin-top: 8px;">
                <a href="{pdf_link}" style="display: inline-block; padding: 10px 20px; font-size: 12px; font-weight: 600; color: #2563EB !important; background-color: #EFF6FF; border: 1px solid #BFDBFE; border-radius: 6px; text-decoration: none; margin: 4px 6px;" target="_blank">Unduh Dokumen Draf Resmi (PDF)</a>
            </div>
        </div>
        <div class="corp-footer">
            <strong>PT Bali Towerindo Sentra Tbk</strong><br>
            Wisma Kodel Lantai 7, Jl. H.R. Rasuna Said Kav. B-4, Jakarta Selatan 12920<br>
            <em>Pemberitahuan otomatis dari Enterprise Operations Command Center. Tidak memerlukan balasan email.</em>
        </div>
    </div>
</body>
</html>"""

        elif not html_content:
            formatted_body = _format_markdown_to_html(content_text)
            btn_url = action_button_url or f"{base_url}/"
            btn_label = action_button_label or "Buka Portal Manajemen Logistik"

            pdf_btn_html = ""
            if attachment_path and Path(attachment_path).exists():
                p_name = Path(attachment_path).name
                if p_name.lower().endswith(".pdf"):
                    pdf_doc_link = f"{base_url}/api/documents/reports/{p_name}/download?inline=true"
                    pdf_btn_html = f"""
            <div style="text-align: center; margin-top: 8px;">
                <a href="{pdf_doc_link}" style="display: inline-block; padding: 10px 20px; font-size: 12px; font-weight: 600; color: #2563EB !important; background-color: #EFF6FF; border: 1px solid #BFDBFE; border-radius: 6px; text-decoration: none; margin: 4px 6px;" target="_blank">&#128196; Unduh / Buka Dokumen Laporan (PDF)</a>
            </div>"""

            html_content = f"""<!DOCTYPE html>
<html lang="id">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{subject}</title>
    <style>
        body {{
            margin: 0;
            padding: 24px 12px;
            background-color: #F1F5F9;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            color: #0F172A;
            line-height: 1.5;
        }}
        .email-wrapper {{
            max-width: 650px;
            margin: 0 auto;
            background: #FFFFFF;
            border: 1px solid #CBD5E1;
            border-radius: 8px;
            overflow: hidden;
            box-shadow: 0 1px 3px rgba(0, 0, 0, 0.08);
        }}
        .corp-header {{
            background: #0F172A;
            color: #FFFFFF;
            padding: 20px 24px;
            border-bottom: 3px solid #2563EB;
        }}
        .corp-title {{
            font-size: 15px;
            font-weight: 700;
            letter-spacing: 0.06em;
            text-transform: uppercase;
            margin: 0;
            color: #F8FAFC;
        }}
        .corp-subtitle {{
            font-size: 12px;
            color: #94A3B8;
            margin: 4px 0 0 0;
        }}
        .email-body {{
            padding: 24px;
        }}
        .corp-footer {{
            background: #F8FAFC;
            border-top: 1px solid #E2E8F0;
            padding: 16px 24px;
            font-size: 11.5px;
            color: #64748B;
            line-height: 1.6;
        }}
    </style>
</head>
<body>
    <div class="email-wrapper">
        <div class="corp-header">
            <h1 class="corp-title">PT Bali Towerindo Sentra Tbk</h1>
            <p class="corp-subtitle">Enterprise Operations Command Center & Logistics</p>
        </div>
        <div class="email-body">
            {formatted_body}
            <div style="text-align: center; margin: 24px 0 8px 0;">
                <a href="{btn_url}" style="display: inline-block; padding: 11px 22px; font-size: 12.5px; font-weight: 600; color: #FFFFFF !important; background-color: #2563EB; border-radius: 6px; text-decoration: none;" target="_blank">{btn_label}</a>
            </div>
            {pdf_btn_html}
        </div>
        <div class="corp-footer">
            <strong>PT Bali Towerindo Sentra Tbk</strong><br>
            Wisma Kodel Lantai 7, Jl. H.R. Rasuna Said Kav. B-4, Jakarta Selatan 12920<br>
            <em>Pemberitahuan otomatis dari Enterprise Operations Command Center.</em>
        </div>
    </div>
</body>
</html>"""

        if not is_smtp_configured:
            attach_info = f" (dengan lampiran: {Path(attachment_path).name})" if attachment_path and Path(attachment_path).exists() else ""
            msg = f"[EMAIL SIMULASI] Email berhasil disimulasikan ke '{recipient}' | Subjek: '{subject}'{attach_info}."
            logger.info(msg)
            return {
                "status": "simulated",
                "recipient": recipient,
                "subject": subject,
                "message": msg,
                "content_preview": content_text[:150] + "..." if len(content_text) > 150 else content_text,
                "interactive_actions": {
                    "approve_url": f"{base_url}/api/approval/leave-quick-action?leave_id={leave_id}&action=APPROVE" if leave_id else (f"{base_url}/api/approval/quick-action?pr_number={pr_number}&action=APPROVE" if pr_number else ""),
                    "reject_url": f"{base_url}/api/approval/leave-quick-action?leave_id={leave_id}&action=REJECT" if leave_id else (f"{base_url}/api/approval/quick-action?pr_number={pr_number}&action=REJECT" if pr_number else ""),
                    "pdf_url": f"{base_url}/api/documents/leave/{leave_id}/download" if leave_id else (f"{base_url}/api/documents/pr/{pr_number}/download" if pr_number else "")
                }
            }

        try:
            # RFC 2046 Standard: multipart/mixed at top level allows both multipart/alternative (text/html) and binary attachments
            outer = MIMEMultipart("mixed")
            outer["From"] = settings.SMTP_EMAIL
            outer["To"] = recipient
            outer["Subject"] = subject

            # Child alternative container for plain text and HTML representation
            body_alt = MIMEMultipart("alternative")
            part1 = MIMEText(content_text or "", "plain", "utf-8")
            body_alt.attach(part1)
            if html_content:
                part2 = MIMEText(html_content, "html", "utf-8")
                body_alt.attach(part2)
            outer.attach(body_alt)

            # Physical attachment (Typst PDF / document)
            if attachment_path and Path(attachment_path).exists():
                file_p = Path(attachment_path)
                with open(file_p, "rb") as f:
                    file_bytes = f.read()
                subtype = "pdf" if file_p.suffix.lower() == ".pdf" else "octet-stream"
                part_attach = MIMEApplication(file_bytes, _subtype=subtype)
                part_attach.add_header("Content-Disposition", "attachment", filename=file_p.name)
                outer.attach(part_attach)
                logger.info(f"Attached document '{file_p.name}' (application/{subtype}) to email for {recipient}")

            def _send_smtp_sync():
                with smtplib.SMTP(settings.SMTP_SERVER, settings.SMTP_PORT, timeout=15) as server:
                    server.starttls()
                    server.login(settings.SMTP_EMAIL, settings.SMTP_PASSWORD)
                    server.send_message(outer)

            await asyncio.to_thread(_send_smtp_sync)

            return {
                "channel": "email",
                "status": "success",
                "recipient": recipient,
                "subject": subject,
                "message": f"Email interaktif berhasil dikirim ke {recipient}."
            }
        except Exception as e:
            logger.error(f"Failed to send email: {e}")
            return {
                "channel": "email",
                "status": "error",
                "recipient": recipient,
                "message": f"Gagal mengirim email via SMTP: {e!s}"
            }

    @classmethod
    async def dispatch_dynamic_report(
        cls,
        title: str,
        headers: list[str],
        rows: list[list[Any] | tuple[Any, ...]],
        recipient_email: str | None = None,
        summary_text: str | None = None,
        subtitle: str = "Laporan Operasional Sistem",
        status: str = "COMPLETED",
        attach_pdf: bool = True,
        action_button_label: str | None = None,
        action_button_url: str | None = None,
        base_url: str | None = None
    ) -> dict[str, Any]:
        """
        Dispatches a dynamic, schema-agnostic report via email:
        1. Compiles an official Typst PDF report dynamically via docgen.compiler.
        2. Renders a beautiful corporate HTML email with interactive table.
        3. Attaches the generated Typst PDF to the email.
        """
        from docgen.compiler import generate_dynamic_report_pdf
        pdf_path = None
        if attach_pdf:
            try:
                pdf_path = generate_dynamic_report_pdf(
                    title=title,
                    headers=headers,
                    rows=rows,
                    subtitle=subtitle,
                    status=status,
                    summary_text=summary_text
                )
            except Exception as e:
                logger.warning(f"Failed to generate dynamic report PDF: {e}")

        subject = f"{title} | PT Bali Towerindo Sentra Tbk"
        content_lines = []
        if summary_text:
            content_lines.append(f"**Ringkasan Eksekutif:** {summary_text}")
        content_lines.append(f"\nBerikut adalah rincian data resmi per {datetime.now().strftime('%d %B %Y, %H:%M WIB')}:")
        content_text = "\n".join(content_lines)

        return await cls.dispatch_email(
            recipient_email=recipient_email,
            subject=subject,
            content_text=content_text,
            table_headers=headers,
            table_rows=rows,
            attachment_path=pdf_path,
            action_button_label=action_button_label or "Buka Portal Manajemen Logistik",
            action_button_url=action_button_url,
            base_url=base_url
        )


dispatcher = MultiChannelDispatcher()

