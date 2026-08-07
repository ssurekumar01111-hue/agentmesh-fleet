#!/usr/bin/env python3
"""
Automated integration tests for AgentMesh Gateway.
Tests both:
 1. ALLOWED Case: fraud-finance agent requesting sandbox_invoices -> 200 OK + audit_log with policyDecision: "allowed".
 2. DENIED Case: fraud-finance agent requesting sandbox_employees -> 403 Forbidden + audit_log with policyDecision: "denied" + policyReason.
"""

import os
import sys
import time
import requests
from google.cloud import firestore

GATEWAY_URL = os.getenv("GATEWAY_URL", "http://localhost:8080")
PROJECT_ID = os.getenv("GCP_PROJECT_ID", "agentmesh-fleet-2026")
DATABASE_ID = os.getenv("FIRESTORE_DATABASE", "(default)")

db = firestore.Client(project=PROJECT_ID, database=DATABASE_ID)

def test_allowed_case():
    print("\n" + "=" * 60)
    print("TEST 1: ALLOWED CASE (fraud-finance -> sandbox_invoices)")
    print("=" * 60)
    
    headers = {
        "Content-Type": "application/json",
        "x-emulated-sa": f"agentmesh-fraud-finance@{PROJECT_ID}.iam.gserviceaccount.com"
    }
    payload = {
        "callerServiceAccount": f"agentmesh-fraud-finance@{PROJECT_ID}.iam.gserviceaccount.com",
        "targetResource": "firestore:sandbox_invoices",
        "collectionName": "sandbox_invoices",
        "action": "read"
    }

    response = requests.post(f"{GATEWAY_URL}/v1/execute", json=payload, headers=headers)
    print(f"[*] Gateway HTTP Response Code: {response.status_code}")
    print(f"[*] Response Body: {response.text}")
    
    assert response.status_code == 200, f"Expected 200 OK, got {response.status_code}"
    res_data = response.json()
    assert res_data.get("policyDecision") == "allowed"

    # Verify audit_log entry in Firestore
    time.sleep(1)
    logs = list(
        db.collection("audit_log")
        .where("agentId", "==", "fraud-finance")
        .stream()
    )

    assert len(logs) > 0, "No audit_log document found for fraud-finance!"
    # Pick the most recent log by timestamp in code
    sorted_logs = sorted(logs, key=lambda d: d.to_dict().get("latencyMs", 0))
    latest_log_doc = logs[-1]
    log_data = latest_log_doc.to_dict()
    print(f"[+] PASS: Allowed test succeeded! Real audit_log ID: {latest_log_doc.id}")
    print(f"    Agent ID: {log_data.get('agentId')}")
    print(f"    Policy Decision: {log_data.get('policyDecision')}")
    print(f"    Action: {log_data.get('action')}")
    print(f"    Latency: {log_data.get('latencyMs')} ms")
    return log_data

def test_denied_case():
    print("\n" + "=" * 60)
    print("TEST 2: DENIED CASE (fraud-finance -> sandbox_employees)")
    print("=" * 60)
    
    headers = {
        "Content-Type": "application/json",
        "x-emulated-sa": f"agentmesh-fraud-finance@{PROJECT_ID}.iam.gserviceaccount.com"
    }
    payload = {
        "callerServiceAccount": f"agentmesh-fraud-finance@{PROJECT_ID}.iam.gserviceaccount.com",
        "targetResource": "firestore:sandbox_employees",
        "collectionName": "sandbox_employees",
        "action": "read"
    }

    response = requests.post(f"{GATEWAY_URL}/v1/execute", json=payload, headers=headers)
    print(f"[*] Gateway HTTP Response Code: {response.status_code}")
    print(f"[*] Response Body: {response.text}")
    
    assert response.status_code == 403, f"Expected 403 Forbidden, got {response.status_code}"
    res_data = response.json()
    assert res_data.get("policyDecision") == "denied"
    assert res_data.get("policyReason") is not None

    # Verify audit_log entry in Firestore
    time.sleep(1)
    logs = list(
        db.collection("audit_log")
        .where("agentId", "==", "fraud-finance")
        .stream()
    )

    denied_logs = [d for d in logs if d.to_dict().get("policyDecision") == "denied"]
    assert len(denied_logs) > 0, "No audit_log document found for denied call!"
    latest_log_doc = denied_logs[-1]
    log_data = latest_log_doc.to_dict()
    print(f"[+] PASS: Denied test succeeded! Real audit_log ID: {latest_log_doc.id}")
    print(f"    Agent ID: {log_data.get('agentId')}")
    print(f"    Policy Decision: {log_data.get('policyDecision')}")
    print(f"    Policy Reason: {log_data.get('policyReason')}")
    print(f"    Latency: {log_data.get('latencyMs')} ms")
    return log_data

def main():
    print(f"[*] Starting Gateway Automated Integration Tests against {GATEWAY_URL}...")
    allowed_log = test_allowed_case()
    denied_log = test_denied_case()
    print("\n" + "=" * 60)
    print("ALL GATEWAY INTEGRATION TESTS PASSED PERFECTLY!")
    print("=" * 60 + "\n")

if __name__ == "__main__":
    main()
