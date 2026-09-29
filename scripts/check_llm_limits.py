#!/usr/bin/env python3
"""
CLI Tool to inspect LLM spend, limits, and real-time usage (RPM, TPM, Budget).
"""
import sys
import json
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx
from core.config import settings

def main():
    api_key = settings.LLM_KEY or settings.MODEL_API_KEY
    if not api_key:
        print("[ERROR] API Key tidak ditemukan di environment/settings (.env).")
        return

    headers = {"Authorization": f"Bearer {api_key}"}
    
    print("\n" + "=" * 62)
    print("           BALITOWER OPS - LLM USAGE & LIMIT MONITOR")
    print("=" * 62)

    # 1. Fetch Key Info & Spend via LiteLLM Key Info
    # Note: 10.7.1.21 is the internal proxy host exposing /key/info
    info_hosts = ["http://10.7.1.21", "https://api.balillm.ai"]
    key_info = None

    for host in info_hosts:
        try:
            with httpx.Client(timeout=4.0) as client:
                res = client.get(f"{host}/key/info", headers=headers)
                if res.status_code == 200:
                    key_info = res.json().get("info", {})
                    break
        except Exception:
            continue

    if key_info:
        spend = key_info.get("spend", 0.0)
        max_budget = key_info.get("max_budget", 0.0)
        duration = key_info.get("budget_duration", "N/A")
        reset_at = key_info.get("budget_reset_at", "N/A")
        rpm_limit = key_info.get("rpm_limit", "N/A")
        tpm_limit = key_info.get("tpm_limit", "N/A")
        max_parallel = key_info.get("max_parallel_requests", "N/A")
        key_alias = key_info.get("key_alias", "N/A")
        metadata = key_info.get("metadata", {})
        model_rpm = metadata.get("model_rpm_limit", {})
        model_tpm = metadata.get("model_tpm_limit", {})
        allowed_models = key_info.get("models", [])

        pct_spent = (spend / max_budget * 100) if max_budget else 0.0

        print(f"\n[1] SPEND & BUDGET STATUS:")
        print(f"  • Key Alias           : {key_alias}")
        print(f"  • Total Spend Terpakai: ${spend:.6f}")
        print(f"  • Max Budget Limit    : ${max_budget:.2f} ({duration})")
        print(f"  • Sisa Budget         : ${max(0.0, max_budget - spend):.6f} (Terpakai {pct_spent:.2f}%)")
        print(f"  • Jadwal Reset Budget : {reset_at}")

        print(f"\n[2] OVERALL KEY LIMITS:")
        print(f"  • Key RPM Limit       : {rpm_limit} requests / minute")
        print(f"  • Key TPM Limit       : {tpm_limit} tokens / minute")
        print(f"  • Max Parallel Req    : {max_parallel} concurrent requests")
        print(f"  • Allowed Models      : {', '.join(allowed_models)}")

        if model_rpm or model_tpm:
            print(f"\n[3] PER-MODEL SUB-LIMITS (Spesifik per Model):")
            all_m = sorted(set(list(model_rpm.keys()) + list(model_tpm.keys())))
            for m in all_m:
                r = model_rpm.get(m, "-")
                t = model_tpm.get(m, "-")
                print(f"  • {m:<18}: RPM Limit = {str(r):<5} | TPM Limit = {str(t):<6}")
    else:
        print("\n[!] Gagal mengambil /key/info dari gateway.")

    # 2. Live Rate Limit Check via Minimal Inference Ping
    base_endpoint = (settings.MODEL_URL or "https://api.balillm.ai/v1").rstrip("/")
    if base_endpoint.endswith("/models"):
        base_endpoint = base_endpoint[:-7]
    if not base_endpoint.endswith("/v1"):
        base_endpoint = f"{base_endpoint}/v1"

    print(f"\n[4] REAL-TIME RATE LIMIT CHECK (Menit Berjalan via {base_endpoint}):")
    try:
        with httpx.Client(timeout=6.0) as client:
            resp = client.post(
                f"{base_endpoint}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={
                    "model": settings.MODEL_NAME or "qwen-38",
                    "messages": [{"role": "user", "content": "ping"}],
                    "max_tokens": 1
                }
            )
            h = resp.headers
            rpm_lim = int(h.get("x-ratelimit-api_key-limit-requests", 40))
            rpm_rem = int(h.get("x-ratelimit-api_key-remaining-requests", 40))
            rpm_used = rpm_lim - rpm_rem

            tpm_lim = int(h.get("x-ratelimit-api_key-limit-tokens", 60000))
            tpm_rem = int(h.get("x-ratelimit-api_key-remaining-tokens", 60000))
            tpm_used = tpm_lim - tpm_rem

            par_lim = int(h.get("x-ratelimit-api_key-limit-max_parallel_requests", 5))
            par_rem = int(h.get("x-ratelimit-api_key-remaining-max_parallel_requests", 5))
            par_used = par_lim - par_rem

            print(f"  • RPM Saat Ini (Menit Ini) : {rpm_used} / {rpm_lim} requests terpakai (Sisa: {rpm_rem})")
            print(f"  • TPM Saat Ini (Menit Ini) : {tpm_used} / {tpm_lim} tokens terpakai   (Sisa: {tpm_rem})")
            print(f"  • Concurrency Paralel Aktif: {par_used} / {par_lim} worker aktif    (Sisa: {par_rem})")
    except Exception as e:
        print(f"  [!] Gagal ping live inference: {e}")

    print("\n" + "=" * 62 + "\n")

if __name__ == "__main__":
    main()
