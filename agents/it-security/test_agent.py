#!/usr/bin/env python3
"""
Integration test for IT/Security Agent against the live deployed Cloud Run service.
Updated for Phase 15c async 202/queued pattern.

Tests:
 1. Suspicious State: Audits Northbridge-Retail-Co. -> HIGH_RISK detection
 2. Clean State: Audits agentmesh-fleet -> LOW_RISK

Pattern: POST /audit -> 202 + {status: "queued", workflowId}
         -> poll Firestore via SDK until terminal state
         -> assert on terminal Firestore state

Usage:
    python test_agent.py [--service-url URL]
"""

import argparse
import json
import os
import sys
import time

import requests
from google.cloud import firestore

DEFAULT_URL = os.getenv(
    "IT_SECURITY_URL",
    "https://agentmesh-it-security-138003672216.asia-south1.run.app",
)

PROJECT_ID = os.getenv("GCP_PROJECT_ID", "agentmesh-fleet-2026")
DATABASE_ID = os.getenv("FIRESTORE_DATABASE", "(default)")
SUSPICIOUS_REPO = "ssurekumar01111-hue/Northbridge-Retail-Co."
CLEAN_REPO = "ssurekumar01111-hue/agentmesh-fleet"

db = firestore.Client(project=PROJECT_ID, database=DATABASE_ID)


def get_auth_headers(url: str) -> dict:
    headers = {"Content-Type": "application/json"}
    token = os.getenv("TOKEN")
    if not token:
        try:
            import subprocess
            gcloud_path = r"C:\Program Files (x86)\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd"
            res = subprocess.run([gcloud_path, "auth", "print-identity-token"], capture_output=True, text=True, timeout=10)
            token = res.stdout.strip()
        except Exception:
            token = None
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def trigger_audit(base_url: str, repo: str) -> requests.Response:
    """POST /audit -> expect 202 + {status: queued, workflowId}."""
    url = f"{base_url.rstrip('/')}/audit"
    payload = {"repo": repo}
    headers = get_auth_headers(base_url)
    print(f"\n[*] POST {url}")
    print(f"    Payload: {json.dumps(payload)}")
    res = requests.post(url, json=payload, headers=headers, timeout=30)
    print(f"    HTTP Status: {res.status_code}")
    print(f"    Response: {res.text[:300]}")
    return res


def poll_workflow_until_terminal(workflow_id: str, max_wait: int = 180, interval: float = 2.0) -> dict:
    """Poll Firestore workflow doc until a terminal state is reached."""
    TERMINAL_STATES = {"waiting_approval", "completed", "failed"}
    seen_states = {}
    poll_start = time.time()

    print(f"\n    [Poll] Polling workflow '{workflow_id}' (max {max_wait}s)...")
    while time.time() - poll_start < max_wait:
        wf_doc = db.collection("workflows").document(workflow_id).get()
        wf = wf_doc.to_dict() if wf_doc.exists else {}
        status = wf.get("status")
        elapsed = round(time.time() - poll_start, 1)

        if status and status not in seen_states:
            seen_states[status] = elapsed
            print(f"    [Poll T+{elapsed}s] status='{status}'")

        if status in TERMINAL_STATES:
            print(f"    [Poll] Terminal state '{status}' at T+{elapsed}s")
            return wf

        time.sleep(interval)

    print(f"    [Poll] WARNING: Timeout. Seen: {list(seen_states.keys())}")
    return {}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--service-url", default=DEFAULT_URL, help="Base URL of it-security service")
    args = parser.parse_args()
    base_url = args.service_url

    print("=" * 70)
    print("AgentMesh IT & Security Agent — Async 202 Integration Test (Phase 15c)")
    print(f"Service URL: {base_url}")
    print("=" * 70)

    # ------------------------------------------------------------------
    # Test 1: Suspicious Repo (Northbridge-Retail-Co.)
    # Expected: 202 -> poll -> terminal (waiting_approval or completed), HIGH_RISK
    # ------------------------------------------------------------------
    print(f"\n--- TEST 1: Suspicious Repo ({SUSPICIOUS_REPO}) ---")
    repo_slug = SUSPICIOUS_REPO.replace("/", "-")
    workflow_id = f"sec-wf-{repo_slug}"

    res = trigger_audit(base_url, SUSPICIOUS_REPO)

    print("\nAssertions (async trigger):")
    p1 = res.status_code == 202
    print(f"  [{'PASS' if p1 else 'FAIL'}] HTTP 202 Accepted: got {res.status_code}")
    res_json = res.json() if res.content else {}
    p2 = res_json.get("status") == "queued"
    print(f"  [{'PASS' if p2 else 'FAIL'}] response.status == 'queued': got '{res_json.get('status')}'")
    p3 = bool(res_json.get("workflowId") or res_json.get("messageId"))
    print(f"  [{'PASS' if p3 else 'FAIL'}] response has workflowId/messageId")

    if p1 and p2:
        final_wf = poll_workflow_until_terminal(workflow_id)
        ctx = final_wf.get("context", {})

        print("\nAssertions (terminal Firestore state):")
        p4 = final_wf.get("status") in {"waiting_approval", "completed"}
        print(f"  [{'PASS' if p4 else 'FAIL'}] terminal status in {{waiting_approval, completed}}: got '{final_wf.get('status')}'")
        p5 = (ctx.get("riskScore") or 0) >= 0.70 or ctx.get("assessmentStatus") == "HIGH_RISK"
        print(f"  [{'PASS' if p5 else 'FAIL'}] HIGH_RISK detected (riskScore={ctx.get('riskScore')}, status={ctx.get('assessmentStatus')})")

        mem_doc = db.collection("memory").document(f"sec-case-{repo_slug}").get()
        p6 = mem_doc.exists
        print(f"  [{'PASS' if p6 else 'FAIL'}] Memory doc 'sec-case-{repo_slug}' exists in Firestore")
    else:
        p4, p5, p6 = False, False, False
        print("  [SKIP] Skipping terminal assertions (trigger failed)")

    # ------------------------------------------------------------------
    # Test 2: Clean Repo (agentmesh-fleet)
    # Expected: 202 -> poll -> completed, LOW_RISK
    # ------------------------------------------------------------------
    print(f"\n\n--- TEST 2: Clean Repo ({CLEAN_REPO}) ---")
    clean_slug = CLEAN_REPO.replace("/", "-")
    clean_wf_id = f"sec-wf-{clean_slug}"

    res_c = trigger_audit(base_url, CLEAN_REPO)

    print("\nAssertions (async trigger):")
    c1 = res_c.status_code == 202
    print(f"  [{'PASS' if c1 else 'FAIL'}] HTTP 202 Accepted: got {res_c.status_code}")
    res_c_json = res_c.json() if res_c.content else {}
    c2 = res_c_json.get("status") == "queued"
    print(f"  [{'PASS' if c2 else 'FAIL'}] response.status == 'queued': got '{res_c_json.get('status')}'")

    if c1 and c2:
        final_wf_c = poll_workflow_until_terminal(clean_wf_id)
        ctx_c = final_wf_c.get("context", {})

        print("\nAssertions (terminal Firestore state):")
        c3 = final_wf_c.get("status") == "completed"
        print(f"  [{'PASS' if c3 else 'FAIL'}] terminal status == 'completed': got '{final_wf_c.get('status')}'")
        c4 = (ctx_c.get("riskScore") or 1.0) < 0.50
        print(f"  [{'PASS' if c4 else 'FAIL'}] riskScore < 0.50: got {ctx_c.get('riskScore')}")
    else:
        c3, c4 = False, False

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    print("\n\n" + "=" * 70)
    all_pass = all([p1, p2, p3, p4, p5, p6, c1, c2, c3, c4])
    print(f"OVERALL: {'ALL TESTS PASSED [PASS]' if all_pass else 'SOME TESTS FAILED [FAIL]'}")
    print("=" * 70)
    sys.exit(0 if all_pass else 1)


if __name__ == "__main__":
    main()
