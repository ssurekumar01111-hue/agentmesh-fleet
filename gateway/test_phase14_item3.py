#!/usr/bin/env python3
"""
Phase 14 Item 3 & Follow-up Verification Test:
Tests Workflow Ownership Enforcement on Gateway:
 1. Uninvolved agent write attempt -> Denied (HTTP 403)
 2. Dashboard Control Plane Human Operator Approve write attempt -> Allowed (HTTP 200)
 3. Involved agent write attempt -> Allowed (HTTP 200)
"""

import os
import sys
import time
import requests
from google.cloud import firestore

GATEWAY_URL = os.getenv("GATEWAY_URL", "https://agentmesh-gateway-138003672216.asia-south1.run.app")
PROJECT_ID = os.getenv("GCP_PROJECT_ID", "agentmesh-fleet-2026")
DATABASE_ID = os.getenv("FIRESTORE_DATABASE", "(default)")

db = firestore.Client(project=PROJECT_ID, database=DATABASE_ID)

def test_workflow_ownership():
    print("\n" + "=" * 70)
    print("ITEM 3: WORKFLOW OWNERSHIP CHECK TEST")
    print("=" * 70)

    target_wf_id = "wf-inv-2026-007"
    
    # 1. Uninvolved Agent Write Attempt (legal-contract attempting to overwrite fraud-finance workflow)
    print(f"\n[*] Attempting write to '{target_wf_id}' as uninvolved agent 'legal-contract'...")
    headers_uninvolved = {
        "Content-Type": "application/json",
        "x-emulated-sa": f"agentmesh-legal-contract@{PROJECT_ID}.iam.gserviceaccount.com"
    }
    payload_uninvolved = {
        "callerServiceAccount": f"agentmesh-legal-contract@{PROJECT_ID}.iam.gserviceaccount.com",
        "targetResource": "firestore:workflows",
        "collectionName": "workflows",
        "action": "write",
        "payload": {
            "docId": target_wf_id,
            "data": {
                "status": "tampered_by_legal_contract"
            }
        }
    }

    res_un = requests.post(f"{GATEWAY_URL}/v1/execute", json=payload_uninvolved, headers=headers_uninvolved)
    print(f"[*] Uninvolved Write Response Code: {res_un.status_code}")
    print(f"[*] Uninvolved Write Body: {res_un.text}")

    res_un_data = res_un.json()
    assert res_un.status_code == 403, f"Expected 403 Forbidden for uninvolved write, got {res_un.status_code}"
    assert res_un_data.get("status") == "denied"
    assert res_un_data.get("policyDecision") == "denied"
    assert "Workflow ownership check failed" in res_un_data.get("policyReason", "")
    
    audit_id = res_un_data.get("auditLogId")
    assert audit_id is not None, "Audit log ID missing from ownership denial!"
    
    time.sleep(1)
    audit_doc = db.collection("audit_log").document(audit_id).get()
    assert audit_doc.exists, f"Audit log doc {audit_id} not found!"
    print(f"[+] PASS: Uninvolved agent write correctly DENIED! Audit Log ID: {audit_id}")

    # 2. Dashboard Human Operator Write Attempt (agentmesh-dashboard approving workflow)
    print(f"\n[*] Attempting write to '{target_wf_id}' as Dashboard Human Operator 'dashboard'...")
    headers_dash = {
        "Content-Type": "application/json",
        "x-emulated-sa": f"agentmesh-dashboard@{PROJECT_ID}.iam.gserviceaccount.com"
    }
    wf_doc = db.collection("workflows").document(target_wf_id).get()
    curr_data = wf_doc.to_dict() if wf_doc.exists else {}

    payload_dash = {
        "callerServiceAccount": f"agentmesh-dashboard@{PROJECT_ID}.iam.gserviceaccount.com",
        "targetResource": "firestore:workflows",
        "collectionName": "workflows",
        "action": "write",
        "payload": {
            "docId": target_wf_id,
            "data": {
                **curr_data,
                "status": "resumed",
                "updatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ")
            }
        }
    }

    res_dash = requests.post(f"{GATEWAY_URL}/v1/execute", json=payload_dash, headers=headers_dash)
    print(f"[*] Dashboard Write Response Code: {res_dash.status_code}")
    print(f"[*] Dashboard Write Body: {res_dash.text}")

    res_dash_data = res_dash.json()
    assert res_dash.status_code == 200, f"Expected 200 OK for dashboard write, got {res_dash.status_code}"
    assert res_dash_data.get("status") == "allowed"
    print(f"[+] PASS: Dashboard Control Plane Human Operator write successfully ALLOWED!")

    # 3. Involved Agent Write Attempt (fraud-finance updating its own workflow)
    print(f"\n[*] Attempting write to '{target_wf_id}' as involved agent 'fraud-finance'...")
    headers_involved = {
        "Content-Type": "application/json",
        "x-emulated-sa": f"agentmesh-fraud-finance@{PROJECT_ID}.iam.gserviceaccount.com"
    }

    payload_involved = {
        "callerServiceAccount": f"agentmesh-fraud-finance@{PROJECT_ID}.iam.gserviceaccount.com",
        "targetResource": "firestore:workflows",
        "collectionName": "workflows",
        "action": "write",
        "payload": {
            "docId": target_wf_id,
            "data": {
                **curr_data,
                "status": "waiting_approval",
                "updatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ")
            }
        }
    }

    res_in = requests.post(f"{GATEWAY_URL}/v1/execute", json=payload_involved, headers=headers_involved)
    print(f"[*] Involved Write Response Code: {res_in.status_code}")
    print(f"[*] Involved Write Body: {res_in.text}")

    res_in_data = res_in.json()
    assert res_in.status_code == 200, f"Expected 200 OK for involved write, got {res_in.status_code}"
    assert res_in_data.get("status") == "allowed"
    assert res_in_data.get("policyDecision") == "allowed"
    print(f"[+] PASS: Involved agent write successfully ALLOWED!")

def main():
    test_workflow_ownership()
    print("\n" + "=" * 70)
    print("ITEM 3 WORKFLOW OWNERSHIP ENFORCEMENT VERIFICATION PASSED!")
    print("=" * 70 + "\n")

if __name__ == "__main__":
    main()
