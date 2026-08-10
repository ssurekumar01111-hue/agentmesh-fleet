#!/usr/bin/env python3
"""
Full Pause -> Approve -> Resume End-to-End Chain Verification Test
"""

import os
import sys
import time
import requests
from google.cloud import firestore

GATEWAY_URL = os.getenv("GATEWAY_URL", "https://agentmesh-gateway-138003672216.asia-south1.run.app")
AGENT_URL = os.getenv("FRAUD_FINANCE_URL", "https://agentmesh-fraud-finance-138003672216.asia-south1.run.app")
PROJECT_ID = os.getenv("GCP_PROJECT_ID", "agentmesh-fleet-2026")
DATABASE_ID = os.getenv("FIRESTORE_DATABASE", "(default)")

db = firestore.Client(project=PROJECT_ID, database=DATABASE_ID)

def get_auth_headers():
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

def test_full_approval_resume_chain():
    print("\n" + "=" * 70)
    print("FULL PAUSE -> APPROVE -> RESUME END-TO-END CHAIN VERIFICATION")
    print("=" * 70)

    wf_id = "wf-inv-2026-007"
    
    # 1. Ensure workflow is in waiting_approval state
    wf_ref = db.collection("workflows").document(wf_id)
    wf_doc = wf_ref.get()
    curr_data = wf_doc.to_dict() if wf_doc.exists else {}
    curr_data["status"] = "waiting_approval"
    curr_data["currentStep"] = "human_approval_gate"
    wf_ref.set(curr_data)
    print(f"[*] Set workflow '{wf_id}' to status='waiting_approval'.")

    # 2. Simulate Dashboard Approve Action via Gateway
    print(f"[*] Executing Dashboard Approve action via Gateway for '{wf_id}'...")
    dash_headers = {
        "Content-Type": "application/json",
        "x-emulated-sa": f"agentmesh-dashboard@{PROJECT_ID}.iam.gserviceaccount.com"
    }
    dash_payload = {
        "callerServiceAccount": f"agentmesh-dashboard@{PROJECT_ID}.iam.gserviceaccount.com",
        "targetResource": "firestore:workflows",
        "collectionName": "workflows",
        "action": "write",
        "payload": {
            "docId": wf_id,
            "data": {
                **curr_data,
                "status": "resumed",
                "updatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ")
            }
        }
    }
    res_dash = requests.post(f"{GATEWAY_URL}/v1/execute", json=dash_payload, headers=dash_headers)
    print(f"[*] Gateway Dashboard Approve HTTP Status: {res_dash.status_code}")
    print(f"[*] Response Body: {res_dash.text}")
    assert res_dash.status_code == 200, f"Dashboard approve failed with status {res_dash.status_code}"
    
    # Verify Firestore document transition
    time.sleep(1)
    updated_doc = wf_ref.get().to_dict()
    assert updated_doc.get("status") == "resumed", f"Expected Firestore status 'resumed', got '{updated_doc.get('status')}'"
    print(f"[+] PASS: Dashboard Approve write successfully transitioned workflow '{wf_id}' status to 'resumed'!")

    # 3. Trigger Agent /resume Endpoint
    print(f"[*] Invoking Agent /resume endpoint for '{wf_id}'...")
    agent_headers = get_auth_headers()
    resume_res = requests.post(f"{AGENT_URL}/resume", json={"workflowId": wf_id}, headers=agent_headers, timeout=30)
    print(f"[*] Agent /resume HTTP Status: {resume_res.status_code}")
    print(f"[*] Agent /resume Response: {resume_res.text}")
    assert resume_res.status_code == 200, f"Agent /resume failed with status {resume_res.status_code}"
    
    res_data = resume_res.json()
    assert res_data.get("status") == "resumed" or res_data.get("status") == "completed", f"Unexpected resume status: {res_data}"
    print(f"[+] PASS: Agent /resume endpoint executed successfully! Final status: {res_data.get('status')}")

def main():
    test_full_approval_resume_chain()
    print("\n" + "=" * 70)
    print("END-TO-END APPROVAL & RESUME CHAIN VERIFIED SUCCESSFULLY!")
    print("=" * 70 + "\n")

if __name__ == "__main__":
    main()
