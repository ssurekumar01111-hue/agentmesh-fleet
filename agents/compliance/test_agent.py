#!/usr/bin/env python3
"""
Integration test for Compliance Agent against the live deployed Cloud Run service.

Tests:
 1. Responsibility 1: Reviews paused workflow 'wf-inv-2026-007', queries policies via Gateway, generates compliance assessment, and writes to memory doc 'compliance-case-inv-2026-007'.
 2. Responsibility 2: Executes unauthorized read of 'sandbox_employees' via Gateway using 'agentmesh-compliance' identity. Asserts HTTP 403 / failure and returns auditLogId.

Usage:
    python test_agent.py [--service-url URL]

Defaults to the live Cloud Run URL. Set COMPLIANCE_URL env var to override.
"""

import argparse
import json
import os
import sys

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


def review_workflow(base_url: str, workflow_id: str = "wf-inv-2026-007") -> dict:
    url = f"{base_url.rstrip('/')}/review"
    payload = {"workflowId": workflow_id}
    headers = get_auth_headers(base_url)
    print(f"\n[*] POST {url}")
    print(f"    Payload: {json.dumps(payload)}")
    res = requests.post(url, json=payload, headers=headers, timeout=60)
    print(f"    HTTP Status: {res.status_code}")
    if res.status_code != 200:
        print(f"    ERROR body: {res.text[:500]}")
        return {}
    data = res.json()
    print(f"    Response:\n{json.dumps(data, indent=2)}")
    return data


def test_denied_access(base_url: str) -> dict:
    url = f"{base_url.rstrip('/')}/test-denied"
    headers = get_auth_headers(base_url)
    print(f"\n[*] POST {url}")
    res = requests.post(url, json={}, headers=headers, timeout=60)
    print(f"    HTTP Status: {res.status_code}")
    if res.status_code != 200:
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
    print("AgentMesh Compliance Agent — Live Cloud Run Integration Test")
    print(f"Service URL: {base_url}")
    print("=" * 70)

    # ------------------------------------------------------------------
    # Test 1: Responsibility 1 — Workflow Compliance Review
    # ------------------------------------------------------------------
    print("\n--- TEST 1: Workflow Compliance Review (wf-inv-2026-007) ---")
    resp_review = review_workflow(base_url, "wf-inv-2026-007")
    data_review = resp_review.get("data", {})

    print("\nAssertions:")
    p1 = assert_field(
        data_review,
        "workflowId",
        "wf-inv-2026-007",
        "workflowId matches",
    )
    p2 = assert_field(
        data_review,
        "assessmentDecision",
        {"ESCALATE", "REJECT", "APPROVE"},
        "assessmentDecision is ESCALATE/REJECT/APPROVE",
    )
    p3 = assert_field(
        data_review,
        "complianceCaseId",
        "compliance-case-inv-2026-007",
        "complianceCaseId matches",
    )

    mem_doc = db.collection("memory").document("compliance-case-inv-2026-007").get()
    p4 = mem_doc.exists
    print(f"  [{'PASS' if p4 else 'FAIL'}] Firestore Memory document 'compliance-case-inv-2026-007' exists")
    if mem_doc.exists:
        mem_data = mem_doc.to_dict()
        print("\n--- REAL FIRESTORE MEMORY DOCUMENT PRODUCED ---")
        print(f"Memory Doc ID       : compliance-case-inv-2026-007")
        print(f"Assessment Decision : {mem_data.get('assessmentDecision')}")
        print(f"Summary             : {mem_data.get('summary')}")

    # ------------------------------------------------------------------
    # Test 2: Responsibility 2 — Live Zero-Trust Denial Test
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
            print("\n--- REAL AUDIT LOG DOCUMENT PRODUCED ---")
            print(f"Audit Log ID    : {audit_log_id}")
            print(f"Agent ID        : {ad_data.get('agentId')}")
            print(f"Policy Decision : {ad_data.get('policyDecision')}")
            print(f"Policy Reason   : {ad_data.get('policyReason')}")

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    print("\n\n" + "=" * 70)
    all_pass = all([p1, p2, p3, p4, d1, d2])
    print(f"OVERALL: {'ALL TESTS PASSED [PASS]' if all_pass else 'SOME TESTS FAILED [FAIL]'}")
    print("=" * 70)
    sys.exit(0 if all_pass else 1)


if __name__ == "__main__":
    main()
