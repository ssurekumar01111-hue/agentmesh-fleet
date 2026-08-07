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
    audit_log_id = res_data.get("auditLogId")
    assert audit_log_id is not None, "Gateway did not return auditLogId"

    # Verify audit_log entry in Firestore by exact ID
    time.sleep(1)
    log_doc = db.collection("audit_log").document(audit_log_id).get()
    assert log_doc.exists, f"audit_log doc {audit_log_id} not found in Firestore!"
    log_data = log_doc.to_dict()
    print(f"[+] PASS: Allowed test succeeded! Real audit_log ID: {audit_log_id}")
    print(f"    Agent ID: {log_data.get('agentId')}")
    print(f"    Policy Decision: {log_data.get('policyDecision')}")
    print(f"    Action: {log_data.get('action')}")
    print(f"    Latency: {log_data.get('latencyMs')} ms")
    return audit_log_id, log_data

def test_denied_case():
    print("\n" + "=" * 60)
    print("TEST 2: DENIED CASE (Check 3a - allowedCollections failure)")
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
    audit_log_id = res_data.get("auditLogId")
    assert audit_log_id is not None, "Gateway did not return auditLogId"

    # Verify audit_log entry in Firestore by exact ID
    time.sleep(1)
    log_doc = db.collection("audit_log").document(audit_log_id).get()
    assert log_doc.exists, f"audit_log doc {audit_log_id} not found in Firestore!"
    log_data = log_doc.to_dict()
    print(f"[+] PASS: Check 3a Denied test succeeded! Real audit_log ID: {audit_log_id}")
    print(f"    Agent ID: {log_data.get('agentId')}")
    print(f"    Policy Decision: {log_data.get('policyDecision')}")
    print(f"    Policy Reason (Check 3a): {log_data.get('policyReason')}")
    print(f"    Latency: {log_data.get('latencyMs')} ms")
    return audit_log_id, log_data

def test_denied_check_3b_policy_query():
    print("\n" + "=" * 60)
    print("TEST 3: DENIED CASE - ISOLATING CHECK 3b (policies collection query)")
    print("=" * 60)
    
    # 1. Temporarily grant 'sandbox_employees' to fraud-finance in agent_registry
    # so Check 3a (allowedCollections) PASSES completely.
    reg_ref = db.collection("agent_registry").document("fraud-finance")
    orig_manifest = reg_ref.get().to_dict()
    orig_allowed = orig_manifest.get("allowedCollections", [])
    
    temp_allowed = list(set(orig_allowed + ["sandbox_employees"]))
    reg_ref.update({"allowedCollections": temp_allowed})
    print("[*] Temporarily added 'sandbox_employees' to allowedCollections (Check 3a will pass).")

    try:
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
        
        reason = res_data.get("policyReason", "")
        # Confirm policyReason comes specifically from Check 3b (pol-deny-finance-hr)
        assert "Least privilege policy violation" in reason or "Deny Finance Access to HR Data" in reason or "Finance department identities may not inspect HR employee records" in reason, f"Unexpected policy reason from 3b: {reason}"
        
        audit_log_id = res_data.get("auditLogId")
        assert audit_log_id is not None, "Gateway did not return auditLogId"

        # Verify audit_log entry in Firestore by exact ID
        time.sleep(1)
        log_doc = db.collection("audit_log").document(audit_log_id).get()
        assert log_doc.exists, f"audit_log doc {audit_log_id} not found in Firestore!"
        log_data = log_doc.to_dict()
        print(f"[+] PASS: Check 3b Policy Denial test succeeded! Real audit_log ID: {audit_log_id}")
        print(f"    Agent ID: {log_data.get('agentId')}")
        print(f"    Policy Decision: {log_data.get('policyDecision')}")
        print(f"    Policy Reason (Check 3b): {log_data.get('policyReason')}")
        print(f"    Latency: {log_data.get('latencyMs')} ms")
        return audit_log_id, log_data
    finally:
        # Restore original registry manifest
        reg_ref.update({"allowedCollections": orig_allowed})
        print("[*] Restored original allowedCollections for 'fraud-finance' in agent_registry.")

def main():
    print(f"[*] Starting Gateway Automated Integration Tests against {GATEWAY_URL}...")
    allowed_id, allowed_log = test_allowed_case()
    denied_3a_id, denied_3a_log = test_denied_case()
    denied_3b_id, denied_3b_log = test_denied_check_3b_policy_query()

    print("\n" + "=" * 70)
    print("EXPLICIT DOCUMENT ID & REASON COMPARISON SUMMARY")
    print("=" * 70)
    print(f"  • Check 3a Denied Audit Document ID : {denied_3a_id}")
    print(f"    Check 3a Policy Reason           : {denied_3a_log.get('policyReason')}")
    print(f"  • Check 3b Denied Audit Document ID : {denied_3b_id}")
    print(f"    Check 3b Policy Reason           : {denied_3b_log.get('policyReason')}")
    print("-" * 70)
    assert denied_3a_id != denied_3b_id, "ERROR: Document IDs for 3a and 3b must be distinct!"
    print("[+] VERIFIED: Check 3a and Check 3b produced two DISTINCT real document IDs in Firestore!")
    print("=" * 70 + "\n")

if __name__ == "__main__":
    main()

