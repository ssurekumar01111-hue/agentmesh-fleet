#!/usr/bin/env python3
"""
Integration test for Fraud & Finance Agent against the live deployed Cloud Run service.
Updated for Phase 15c async 202/queued pattern.

Tests:
 1. Anomalous Invoice inv-2026-007 ($185k vs max $30k) -> Must flag HIGH RISK,
    escalate workflow to 'waiting_approval', write memory & workflow.
 2. Normal Invoice inv-2026-001 ($18.45k within $15k-$25k) -> Must assess LOW RISK,
    set workflow status to 'completed'.

Pattern: POST /investigate -> 202 + {status: "queued", workflowId}
         -> poll Firestore via Gateway every 2s until terminal state
         -> assert on terminal Firestore state

Usage:
    python test_agent.py [--service-url URL]

Defaults to the live Cloud Run URL. Set FRAUD_FINANCE_URL env var to override.
"""

import argparse
import json
import os
import sys
import time

import requests
from google.cloud import firestore

DEFAULT_URL = os.getenv(
    "FRAUD_FINANCE_URL",
    "https://agentmesh-fraud-finance-138003672216.asia-south1.run.app",
)
GATEWAY_URL = os.getenv(
    "GATEWAY_URL",
    "https://agentmesh-gateway-138003672216.asia-south1.run.app",
)
DASHBOARD_SA = "agentmesh-dashboard@agentmesh-fleet-2026.iam.gserviceaccount.com"

PROJECT_ID = os.getenv("GCP_PROJECT_ID", "agentmesh-fleet-2026")
DATABASE_ID = os.getenv("FIRESTORE_DATABASE", "(default)")

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


def poll_workflow_until_terminal(workflow_id: str, max_wait: int = 120, interval: float = 2.0) -> dict:
    """Poll Firestore workflow doc via direct SDK until a terminal state is reached."""
    TERMINAL_STATES = {"waiting_approval", "completed", "failed"}
    seen_states = {}
    poll_start = time.time()

    print(f"\n    [Poll] Polling workflow '{workflow_id}' for terminal state (max {max_wait}s, interval {interval}s)...")
    while time.time() - poll_start < max_wait:
        wf_doc = db.collection("workflows").document(workflow_id).get()
        wf = wf_doc.to_dict() if wf_doc.exists else {}
        status = wf.get("status")
        elapsed = round(time.time() - poll_start, 1)

        if status and status not in seen_states:
            seen_states[status] = {"timestamp": wf.get("updatedAt", ""), "elapsed_seconds": elapsed}
            print(f"    [Poll T+{elapsed}s] status='{status}' (updatedAt={wf.get('updatedAt', 'n/a')})")

        if status in TERMINAL_STATES:
            print(f"    [Poll] Terminal state '{status}' reached at T+{elapsed}s")
            return wf

        time.sleep(interval)

    print(f"    [Poll] WARNING: Max wait {max_wait}s exceeded. Last seen states: {list(seen_states.keys())}")
    return {}


def trigger_investigation(base_url: str, invoice_id: str) -> dict:
    """POST /investigate -> expect 202 + {status: queued, workflowId}."""
    url = f"{base_url.rstrip('/')}/investigate"
    payload = {"invoiceId": invoice_id}
    headers = get_auth_headers(base_url)
    print(f"\n[*] POST {url}")
    print(f"    Payload: {json.dumps(payload)}")
    res = requests.post(url, json=payload, headers=headers, timeout=30)
    print(f"    HTTP Status: {res.status_code}")
    print(f"    Response: {res.text[:300]}")
    return res


def assert_field(result: dict, field: str, expected_values, label: str):
    actual = result.get(field)
    if isinstance(expected_values, (list, tuple, set)):
        ok = actual in expected_values
    else:
        ok = actual == expected_values
    status = "PASS" if ok else "FAIL"
    print(f"  [{status}] {label}: got '{actual}' (expected {expected_values})")
    return ok


def verify_firestore_memory(invoice_id: str):
    case_id = f"case-{invoice_id}"
    mem_doc = db.collection("memory").document(case_id).get()
    assert mem_doc.exists, f"Memory doc '{case_id}' was not created in Firestore!"
    return mem_doc.to_dict()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--service-url", default=DEFAULT_URL, help="Base URL of fraud-finance service")
    args = parser.parse_args()
    base_url = args.service_url

    print("=" * 70)
    print("AgentMesh Fraud & Finance Agent — Async 202 Integration Test (Phase 15c)")
    print(f"Service URL: {base_url}")
    print("=" * 70)

    # ------------------------------------------------------------------
    # Test 1: Anomalous Invoice (inv-2026-007 - $185,000.00)
    # Expected: 202 -> poll -> waiting_approval, HIGH RISK riskScore >= 0.70
    # ------------------------------------------------------------------
    print("\n--- TEST 1: Anomalous Invoice (inv-2026-007) ---")
    invoice_id = "inv-2026-007"
    workflow_id = f"wf-{invoice_id}"

    res = trigger_investigation(base_url, invoice_id)

    print("\nAssertions (Phase 15c async pattern):")
    p1 = res.status_code == 202
    print(f"  [{'PASS' if p1 else 'FAIL'}] HTTP 202 Accepted: got {res.status_code}")

    res_json = res.json() if res.content else {}
    p2 = res_json.get("status") == "queued"
    print(f"  [{'PASS' if p2 else 'FAIL'}] response.status == 'queued': got '{res_json.get('status')}'")
    p3 = bool(res_json.get("workflowId") or res_json.get("messageId"))
    print(f"  [{'PASS' if p3 else 'FAIL'}] response has workflowId/messageId: workflowId={res_json.get('workflowId')}, messageId={res_json.get('messageId')}")

    if p1 and p2:
        # Poll for terminal state
        final_wf = poll_workflow_until_terminal(workflow_id)

        print("\nAssertions (terminal Firestore state):")
        p4 = final_wf.get("status") == "waiting_approval"
        print(f"  [{'PASS' if p4 else 'FAIL'}] Workflow terminal status == 'waiting_approval': got '{final_wf.get('status')}'")

        risk_score = final_wf.get("context", {}).get("riskScore")
        p5 = risk_score is not None and risk_score >= 0.70
        print(f"  [{'PASS' if p5 else 'FAIL'}] riskScore >= 0.70: got {risk_score}")

        # Verify memory doc
        try:
            mem_data = verify_firestore_memory(invoice_id)
            p6 = True
            print(f"  [PASS] Firestore Memory doc 'case-{invoice_id}' exists: riskScore={mem_data.get('riskScore')}")
        except AssertionError as e:
            p6 = False
            print(f"  [FAIL] {e}")
    else:
        p4, p5, p6 = False, False, False
        print("  [SKIP] Skipping Firestore polling assertions (trigger failed)")

    # ------------------------------------------------------------------
    # Test 2: Normal Invoice (inv-2026-001 - $18,450.00)
    # Expected: 202 -> poll -> completed, LOW RISK riskScore < 0.50
    # ------------------------------------------------------------------
    print("\n\n--- TEST 2: Normal Invoice (inv-2026-001) ---")
    invoice_id_n = "inv-2026-001"
    workflow_id_n = f"wf-{invoice_id_n}"

    res_n = trigger_investigation(base_url, invoice_id_n)

    print("\nAssertions (Phase 15c async pattern):")
    n1 = res_n.status_code == 202
    print(f"  [{'PASS' if n1 else 'FAIL'}] HTTP 202 Accepted: got {res_n.status_code}")

    res_n_json = res_n.json() if res_n.content else {}
    n2 = res_n_json.get("status") == "queued"
    print(f"  [{'PASS' if n2 else 'FAIL'}] response.status == 'queued': got '{res_n_json.get('status')}'")

    if n1 and n2:
        final_wf_n = poll_workflow_until_terminal(workflow_id_n)

        print("\nAssertions (terminal Firestore state):")
        n3 = final_wf_n.get("status") == "completed"
        print(f"  [{'PASS' if n3 else 'FAIL'}] Workflow terminal status == 'completed': got '{final_wf_n.get('status')}'")

        risk_score_n = final_wf_n.get("context", {}).get("riskScore")
        n4 = risk_score_n is not None and risk_score_n < 0.50
        print(f"  [{'PASS' if n4 else 'FAIL'}] riskScore < 0.50: got {risk_score_n}")
    else:
        n3, n4 = False, False
        print("  [SKIP] Skipping Firestore polling assertions (trigger failed)")

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
