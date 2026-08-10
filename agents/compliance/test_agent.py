#!/usr/bin/env python3
"""
Integration test for Compliance Agent against the live deployed Cloud Run service.
Updated for Phase 15c async 202/queued pattern.

Tests:
 1. Reviews paused workflow 'wf-inv-2026-007' -> 202 -> poll Firestore -> terminal state
 2. Executes unauthorized read of 'sandbox_employees' -> Gateway 403 denial

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
    "COMPLIANCE_URL",
    "https://agentmesh-compliance-138003672216.asia-south1.run.app",
)

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


def trigger_review(base_url: str, workflow_id: str) -> requests.Response:
    """POST /review -> expect 202 + {status: queued}."""
    url = f"{base_url.rstrip('/')}/review"
    payload = {"workflowId": workflow_id}
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


def poll_memory_until_exists(doc_id: str, max_wait: int = 180, interval: float = 2.0) -> dict:
    """Poll Firestore memory doc until it exists."""
    poll_start = time.time()
    print(f"\n    [Poll] Waiting for memory doc '{doc_id}'...")
    while time.time() - poll_start < max_wait:
        doc = db.collection("memory").document(doc_id).get()
        if doc.exists:
            elapsed = round(time.time() - poll_start, 1)
            print(f"    [Poll] Memory doc '{doc_id}' appeared at T+{elapsed}s")
            return doc.to_dict()
        time.sleep(interval)
    print(f"    [Poll] WARNING: Memory doc '{doc_id}' never appeared")
    return {}


def test_denied_access(base_url: str) -> dict:
    url = f"{base_url.rstrip('/')}/test-denied"
    headers = get_auth_headers(base_url)
    print(f"\n[*] POST {url}")
    res = requests.post(url, json={}, headers=headers, timeout=60)
    print(f"    HTTP Status: {res.status_code}")
    if res.status_code not in (200, 202):
        print(f"    ERROR body: {res.text[:500]}")
        return {}
    data = res.json()
    print(f"    Response:\n{json.dumps(data, indent=2)}")
    return data


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
    parser.add_argument("--service-url", default=DEFAULT_URL, help="Base URL of compliance service")
    args = parser.parse_args()
    base_url = args.service_url

    print("=" * 70)
    print("AgentMesh Compliance Agent — Async 202 Integration Test (Phase 15c)")
    print(f"Service URL: {base_url}")
    print("=" * 70)

    # ------------------------------------------------------------------
    # Test 1: Responsibility 1 — Workflow Compliance Review
    # Pattern: 202 -> poll workflow & memory -> terminal
    # ------------------------------------------------------------------
    print("\n--- TEST 1: Workflow Compliance Review (wf-inv-2026-007) ---")
    review_wf_id = "wf-inv-2026-007"

    res = trigger_review(base_url, review_wf_id)

    print("\nAssertions (async trigger):")
    p1 = res.status_code == 202
    print(f"  [{'PASS' if p1 else 'FAIL'}] HTTP 202 Accepted: got {res.status_code}")
    res_json = res.json() if res.content else {}
    p2 = res_json.get("status") == "queued"
    print(f"  [{'PASS' if p2 else 'FAIL'}] response.status == 'queued': got '{res_json.get('status')}'")

    if p1 and p2:
        # The compliance worker creates/updates its own workflow doc and writes memory
        # The compliance workflow ID is the workflowId returned or derived
        comp_workflow_id = res_json.get("workflowId", f"compliance-wf-{review_wf_id}")
        mem_doc_id = "compliance-case-inv-2026-007"

        # Poll the compliance memory doc for terminal result
        mem_data = poll_memory_until_exists(mem_doc_id, max_wait=180)

        print("\nAssertions (terminal Firestore memory state):")
        p3 = bool(mem_data)
        print(f"  [{'PASS' if p3 else 'FAIL'}] Memory doc '{mem_doc_id}' exists in Firestore")
        p4 = mem_data.get("assessmentDecision") in {"ESCALATE", "REJECT", "APPROVE"} if mem_data else False
        print(f"  [{'PASS' if p4 else 'FAIL'}] assessmentDecision in {{ESCALATE, REJECT, APPROVE}}: got '{mem_data.get('assessmentDecision')}'")
        p5 = mem_data.get("workflowId") == review_wf_id if mem_data else False
        print(f"  [{'PASS' if p5 else 'FAIL'}] workflowId == '{review_wf_id}': got '{mem_data.get('workflowId')}'")

        if mem_data:
            print(f"\n--- REAL FIRESTORE MEMORY DOCUMENT ---")
            print(f"  assessmentDecision : {mem_data.get('assessmentDecision')}")
            print(f"  summary            : {mem_data.get('summary', '')[:120]}")
    else:
        p3, p4, p5 = False, False, False
        print("  [SKIP] Skipping terminal assertions (trigger failed)")

    # ------------------------------------------------------------------
    # Test 2: Live Zero-Trust Denial Test (synchronous, no async change needed)
    # ------------------------------------------------------------------
    print("\n\n--- TEST 2: Live Zero-Trust Denial Test ---")
    resp_denied = test_denied_access(base_url)
    gw_res = resp_denied.get("gatewayResponse", {})

    print("\nAssertions:")
    d1 = gw_res.get("success") is False
    print(f"  [{'PASS' if d1 else 'FAIL'}] Gateway returned success=False (denied): got {gw_res.get('success')}")
    d2 = gw_res.get("status_code") in (403, 400)
    print(f"  [{'PASS' if d2 else 'FAIL'}] Gateway status code is 403 or 400: got {gw_res.get('status_code')}")

    audit_log_id = gw_res.get("auditLogId")
    if audit_log_id:
        audit_doc = db.collection("audit_log").document(audit_log_id).get()
        if audit_doc.exists:
            ad_data = audit_doc.to_dict()
            print(f"\n--- REAL AUDIT LOG DOCUMENT ---")
            print(f"  Audit Log ID    : {audit_log_id}")
            print(f"  Policy Decision : {ad_data.get('policyDecision')}")

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    print("\n\n" + "=" * 70)
    all_pass = all([p1, p2, p3, p4, p5, d1, d2])
    print(f"OVERALL: {'ALL TESTS PASSED [PASS]' if all_pass else 'SOME TESTS FAILED [FAIL]'}")
    print("=" * 70)
    sys.exit(0 if all_pass else 1)


if __name__ == "__main__":
    main()
