#!/usr/bin/env python3
"""
Integration test for the Expense Approval Agent.
Updated for Phase 15c async 202/queued pattern.

Tests two expense reports against the live deployed Cloud Run service:
  1. exp-2026-006 — planted policy-violating expense -> 202 -> poll -> waiting_approval
  2. exp-2026-001 — normal compliant expense         -> 202 -> poll -> completed

Pattern: POST /review -> 202 + {status: "queued", workflowId}
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
    "EXPENSE_APPROVAL_URL",
    "https://agentmesh-expense-approval-138003672216.asia-south1.run.app",
)

VIOLATING_EXPENSE_ID = "exp-2026-006"
NORMAL_EXPENSE_ID = "exp-2026-001"

PROJECT_ID = os.getenv("GCP_PROJECT_ID", "agentmesh-fleet-2026")
DATABASE_ID = os.getenv("FIRESTORE_DATABASE", "(default)")

db = firestore.Client(project=PROJECT_ID, database=DATABASE_ID)


def get_auth_headers(url: str) -> dict:
    headers = {"Content-Type": "application/json"}
    token = os.getenv("TOKEN")
    if not token:
        try:
            import subprocess
            cmd = r'& "C:\Program Files (x86)\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd" auth print-identity-token'
            res = subprocess.run(["powershell", "-Command", cmd], capture_output=True, text=True, timeout=10)
            token = res.stdout.strip()
        except Exception:
            token = None
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def trigger_review(base_url: str, expense_id: str) -> requests.Response:
    """POST /review -> expect 202 + {status: queued, workflowId}."""
    url = f"{base_url.rstrip('/')}/review"
    payload = {"expenseId": expense_id}
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


def assert_field(result: dict, field: str, expected_values, label: str):
    actual = result.get(field)
    if isinstance(expected_values, (list, tuple, set)):
        ok = actual in expected_values
    else:
        ok = actual == expected_values
    status = "PASS" if ok else "FAIL"
    print(f"  [{status}] {label}: got '{actual}' (expected {expected_values})")
    return ok


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--service-url", default=DEFAULT_URL, help="Base URL of expense-approval service")
    args = parser.parse_args()
    base_url = args.service_url

    print("=" * 70)
    print("AgentMesh Expense Approval Agent — Async 202 Integration Test (Phase 15c)")
    print(f"Service URL: {base_url}")
    print("=" * 70)

    # ------------------------------------------------------------------
    # Test 1: Planted policy-violating expense (exp-2026-006)
    # Expected: 202 -> poll -> waiting_approval, riskScore >= 0.60
    # ------------------------------------------------------------------
    print(f"\n--- TEST 1: Policy-violating expense ({VIOLATING_EXPENSE_ID}) ---")
    workflow_id = f"exp-wf-{VIOLATING_EXPENSE_ID}"

    res = trigger_review(base_url, VIOLATING_EXPENSE_ID)

    print("\nAssertions (async trigger):")
    p1 = res.status_code == 202
    print(f"  [{'PASS' if p1 else 'FAIL'}] HTTP 202 Accepted: got {res.status_code}")
    res_json = res.json() if res.content else {}
    p2 = res_json.get("status") == "queued"
    print(f"  [{'PASS' if p2 else 'FAIL'}] response.status == 'queued': got '{res_json.get('status')}'")
    p3 = bool(res_json.get("workflowId") or res_json.get("messageId"))
    print(f"  [{'PASS' if p3 else 'FAIL'}] response has workflowId/messageId: wfId={res_json.get('workflowId')}")

    derived_wf_id = res_json.get("workflowId", workflow_id)

    if p1 and p2:
        final_wf = poll_workflow_until_terminal(derived_wf_id)
        ctx = final_wf.get("context", {})

        print("\nAssertions (terminal Firestore state):")
        p4 = final_wf.get("status") == "waiting_approval"
        print(f"  [{'PASS' if p4 else 'FAIL'}] terminal status == 'waiting_approval': got '{final_wf.get('status')}'")
        risk_score = ctx.get("riskScore") or final_wf.get("riskScore") or 0
        p5 = float(risk_score) >= 0.60
        print(f"  [{'PASS' if p5 else 'FAIL'}] riskScore >= 0.60: got {risk_score}")
        assessment = ctx.get("assessmentStatus") or final_wf.get("assessmentStatus") or ""
        p6 = assessment in {"FLAGGED", "ESCALATED"}
        print(f"  [{'PASS' if p6 else 'FAIL'}] assessmentStatus in {{FLAGGED, ESCALATED}}: got '{assessment}'")

        if ctx.get("findings"):
            print(f"\n  Findings for {VIOLATING_EXPENSE_ID}:")
            for i, f in enumerate(ctx["findings"], 1):
                print(f"    {i}. {f}")
    else:
        p4, p5, p6 = False, False, False
        print("  [SKIP] Skipping terminal assertions (trigger failed)")

    # ------------------------------------------------------------------
    # Test 2: Normal compliant expense (exp-2026-001)
    # Expected: 202 -> poll -> completed, riskScore < 0.40
    # ------------------------------------------------------------------
    print(f"\n\n--- TEST 2: Normal compliant expense ({NORMAL_EXPENSE_ID}) ---")
    workflow_id_n = f"exp-wf-{NORMAL_EXPENSE_ID}"

    res_n = trigger_review(base_url, NORMAL_EXPENSE_ID)

    print("\nAssertions (async trigger):")
    n1 = res_n.status_code == 202
    print(f"  [{'PASS' if n1 else 'FAIL'}] HTTP 202 Accepted: got {res_n.status_code}")
    res_n_json = res_n.json() if res_n.content else {}
    n2 = res_n_json.get("status") == "queued"
    print(f"  [{'PASS' if n2 else 'FAIL'}] response.status == 'queued': got '{res_n_json.get('status')}'")

    derived_wf_id_n = res_n_json.get("workflowId", workflow_id_n)

    if n1 and n2:
        final_wf_n = poll_workflow_until_terminal(derived_wf_id_n)
        ctx_n = final_wf_n.get("context", {})

        print("\nAssertions (terminal Firestore state):")
        n3 = final_wf_n.get("status") == "completed"
        print(f"  [{'PASS' if n3 else 'FAIL'}] terminal status == 'completed': got '{final_wf_n.get('status')}'")
        risk_score_n = ctx_n.get("riskScore") or final_wf_n.get("riskScore") or 1.0
        n4 = float(risk_score_n) < 0.40
        print(f"  [{'PASS' if n4 else 'FAIL'}] riskScore < 0.40: got {risk_score_n}")
    else:
        n3, n4 = False, False
        print("  [SKIP] Skipping terminal assertions (trigger failed)")

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    print("\n\n" + "=" * 70)
    all_pass = all([p1, p2, p3, p4, p5, p6, n1, n2, n3, n4])
    print(f"OVERALL: {'ALL TESTS PASSED [PASS]' if all_pass else 'SOME TESTS FAILED [FAIL]'}")
    print("=" * 70)
    sys.exit(0 if all_pass else 1)


if __name__ == "__main__":
    main()
