#!/usr/bin/env python3
"""
Integration test for IT/Security Agent against the live deployed Cloud Run service.

Tests:
 1. Suspicious State: Audits planted suspicious repo (Northbridge-Retail-Co. containing AWS secret key commit), verifies HIGH_RISK detection, automated GitHub issue creation via Gateway, and Firestore memory/workflow update.
 2. Clean State: Audits clean repo (agentmesh-fleet), verifies LOW_RISK assessment (riskScore < 0.50) and NO GitHub issue created.

Usage:
    python test_agent.py [--service-url URL]

Defaults to the live Cloud Run URL. Set IT_SECURITY_URL env var to override.
"""

import argparse
import json
import os
import sys

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


def audit_repository(base_url: str, repo: str) -> dict:
    url = f"{base_url.rstrip('/')}/audit"
    payload = {"repo": repo}
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


def verify_firestore_docs(repo: str):
    case_id = f"sec-case-{repo.replace('/', '-')}"
    workflow_id = f"sec-wf-{repo.replace('/', '-')}"

    mem_doc = db.collection("memory").document(case_id).get()
    wf_doc = db.collection("workflows").document(workflow_id).get()
    inc_doc = db.collection("sandbox_incidents").document("inc-2026-001").get()

    assert mem_doc.exists, f"Memory doc '{case_id}' missing in Firestore!"
    assert wf_doc.exists, f"Workflow doc '{workflow_id}' missing in Firestore!"

    return mem_doc.to_dict(), wf_doc.to_dict(), inc_doc.to_dict() if inc_doc.exists else {}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--service-url", default=DEFAULT_URL, help="Base URL of it-security service")
    args = parser.parse_args()
    base_url = args.service_url

    print("=" * 70)
    print("AgentMesh IT & Security Agent — Live Cloud Run Integration Test")
    print(f"Service URL: {base_url}")
    print("=" * 70)

    # ------------------------------------------------------------------
    # Test 1: Suspicious Repo State Detection (Northbridge-Retail-Co.)
    # ------------------------------------------------------------------
    print(f"\n\n--- TEST 1: Suspicious Repo State Detection ({SUSPICIOUS_REPO}) ---")
    result_suspicious = audit_repository(base_url, SUSPICIOUS_REPO)

    print("\nAssertions:")
    p1 = result_suspicious.get("riskScore", 0.0) >= 0.70 or result_suspicious.get("assessmentStatus") == "HIGH_RISK"
    print(f"  [{'PASS' if p1 else 'FAIL'}] riskScore >= 0.70 or HIGH_RISK: got riskScore={result_suspicious.get('riskScore')}, status={result_suspicious.get('assessmentStatus')}")
    p2 = result_suspicious.get("githubIssue") is not None
    print(f"  [{'PASS' if p2 else 'FAIL'}] GitHub issue produced: got {result_suspicious.get('githubIssue')}")

    mem_data, wf_data, inc_data = verify_firestore_docs(SUSPICIOUS_REPO)
    print("\n--- REAL FIRESTORE DOCUMENTS PRODUCED ---")
    print(f"Memory Doc ({result_suspicious.get('caseId')}): riskScore={mem_data.get('riskScore')}")
    print(f"Workflow Doc ({result_suspicious.get('workflowId')}): status={wf_data.get('status')}")
    if inc_data:
        print(f"Incident Doc (inc-2026-001): status={inc_data.get('status')}, title='{inc_data.get('title')}'")

    # ------------------------------------------------------------------
    # Test 2: Clean Repo State Test (agentmesh-fleet)
    # ------------------------------------------------------------------
    print(f"\n\n--- TEST 2: Clean Repo State Test ({CLEAN_REPO}) ---")
    result_clean = audit_repository(base_url, CLEAN_REPO)

    print("\nAssertions:")
    c1 = result_clean.get("riskScore", 1.0) < 0.50
    print(f"  [{'PASS' if c1 else 'FAIL'}] riskScore < 0.50: got {result_clean.get('riskScore')}")
    c2 = result_clean.get("githubIssue") is None
    print(f"  [{'PASS' if c2 else 'FAIL'}] NO GitHub issue created for clean state: got {result_clean.get('githubIssue')}")

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    print("\n\n" + "=" * 70)
    all_pass = all([p1, p2, c1, c2])
    print(f"OVERALL: {'ALL TESTS PASSED [PASS]' if all_pass else 'SOME TESTS FAILED [FAIL]'}")
    print("=" * 70)
    sys.exit(0 if all_pass else 1)


if __name__ == "__main__":
    main()
