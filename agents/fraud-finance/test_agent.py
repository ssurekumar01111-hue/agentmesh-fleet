#!/usr/bin/env python3
"""
Integration test for Fraud & Finance Agent against the live deployed Cloud Run service.

Tests:
 1. Anomalous Invoice inv-2026-007 ($185k vs max $30k) -> Must flag HIGH RISK, escalate workflow to 'waiting_approval', write memory & workflow.
 2. Normal Invoice inv-2026-001 ($18.45k within $15k-$25k) -> Must assess LOW RISK, set workflow status to 'completed'.

Usage:
    python test_agent.py [--service-url URL]

Defaults to the live Cloud Run URL. Set FRAUD_FINANCE_URL env var to override.
"""

import argparse
import json
import os
import sys

import requests
from google.cloud import firestore

DEFAULT_URL = os.getenv(
    "FRAUD_FINANCE_URL",
    "https://agentmesh-fraud-finance-138003672216.asia-south1.run.app",
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


def investigate_invoice(base_url: str, invoice_id: str) -> dict:
    url = f"{base_url.rstrip('/')}/investigate"
    payload = {"invoiceId": invoice_id}
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


def verify_firestore_docs(invoice_id: str):
    case_id = f"case-{invoice_id}"
    workflow_id = f"wf-{invoice_id}"

    mem_doc = db.collection("memory").document(case_id).get()
    wf_doc = db.collection("workflows").document(workflow_id).get()

    assert mem_doc.exists, f"Memory doc '{case_id}' was not created in Firestore!"
    assert wf_doc.exists, f"Workflow doc '{workflow_id}' was not created in Firestore!"

    return mem_doc.to_dict(), wf_doc.to_dict()


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
    parser.add_argument("--service-url", default=DEFAULT_URL, help="Base URL of fraud-finance service")
    args = parser.parse_args()
    base_url = args.service_url

    print("=" * 70)
    print("AgentMesh Fraud & Finance Agent — Live Cloud Run Integration Test")
    print(f"Service URL: {base_url}")
    print("=" * 70)

    # ------------------------------------------------------------------
    # Test 1: Anomalous Invoice (inv-2026-007 - $185,000.00)
    # Expected: High Risk score >= 0.70, workflowStatus = waiting_approval
    # ------------------------------------------------------------------
    print("\n--- TEST 1: Anomalous Invoice (inv-2026-007) ---")
    result_anomalous = investigate_invoice(base_url, "inv-2026-007")

    print("\nAssertions:")
    p1 = result_anomalous.get("riskScore", 0.0) >= 0.70
    print(f"  [{'PASS' if p1 else 'FAIL'}] riskScore >= 0.70: got {result_anomalous.get('riskScore')}")
    p2 = assert_field(
        result_anomalous,
        "assessmentStatus",
        {"HIGH_RISK", "FLAGGED", "ESCALATED"},
        "assessmentStatus is HIGH_RISK/FLAGGED/ESCALATED",
    )
    p3 = assert_field(
        result_anomalous,
        "workflowStatus",
        "waiting_approval",
        "workflowStatus is waiting_approval",
    )

    mem_data, wf_data = verify_firestore_docs("inv-2026-007")
    print("\n--- REAL FIRESTORE DOCUMENTS PRODUCED ---")
    print(f"Memory Doc (case-inv-2026-007): riskScore={mem_data.get('riskScore')}, findings={mem_data.get('findings')}")
    print(f"Workflow Doc (wf-inv-2026-007): status={wf_data.get('status')}, currentStep={wf_data.get('currentStep')}")

    # ------------------------------------------------------------------
    # Test 2: Normal Invoice (inv-2026-001 - $18,450.00)
    # Expected: Low Risk score < 0.50, workflowStatus = completed
    # ------------------------------------------------------------------
    print("\n\n--- TEST 2: Normal Invoice (inv-2026-001) ---")
    result_normal = investigate_invoice(base_url, "inv-2026-001")

    print("\nAssertions:")
    n1 = result_normal.get("riskScore", 1.0) < 0.50
    print(f"  [{'PASS' if n1 else 'FAIL'}] riskScore < 0.50: got {result_normal.get('riskScore')}")
    n2 = assert_field(
        result_normal,
        "assessmentStatus",
        {"LOW_RISK", "APPROVED", "PASSED"},
        "assessmentStatus is LOW_RISK/APPROVED/PASSED",
    )
    n3 = assert_field(
        result_normal,
        "workflowStatus",
        "completed",
        "workflowStatus is completed",
    )

    mem_data_n, wf_data_n = verify_firestore_docs("inv-2026-001")
    print("\n--- REAL FIRESTORE DOCUMENTS PRODUCED ---")
    print(f"Memory Doc (case-inv-2026-001): riskScore={mem_data_n.get('riskScore')}, findings={mem_data_n.get('findings')}")
    print(f"Workflow Doc (wf-inv-2026-001): status={wf_data_n.get('status')}, currentStep={wf_data_n.get('currentStep')}")

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    print("\n\n" + "=" * 70)
    all_pass = all([p1, p2, p3, n1, n2, n3])
    print(f"OVERALL: {'ALL TESTS PASSED [PASS]' if all_pass else 'SOME TESTS FAILED [FAIL]'}")
    print("=" * 70)
    sys.exit(0 if all_pass else 1)


if __name__ == "__main__":
    main()
