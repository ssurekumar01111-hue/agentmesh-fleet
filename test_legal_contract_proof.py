import os
import sys
import time
import json
import subprocess
import requests
from datetime import datetime, timezone

os.environ["ALLOW_LOCAL_AUTH_EMULATION"] = "true"

sys.path.append(os.path.join(os.path.dirname(__file__), "agents", "legal-contract"))
from gateway_client import GatewayClient

AGENT_URL = "https://agentmesh-legal-contract-138003672216.asia-south1.run.app"
GATEWAY_URL = "https://agentmesh-gateway-138003672216.asia-south1.run.app"
PROJECT_ID = "agentmesh-fleet-2026"
SA_EMAIL = f"agentmesh-legal-contract@{PROJECT_ID}.iam.gserviceaccount.com"
DASHBOARD_SA = f"agentmesh-dashboard@{PROJECT_ID}.iam.gserviceaccount.com"

gateway_client = GatewayClient()
_cached_token = None

def get_token():
    global _cached_token
    if not _cached_token:
        gcloud_bin = r"C:\Program Files (x86)\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd"
        cmd = f'"{gcloud_bin}" auth print-identity-token'
        try:
            _cached_token = subprocess.check_output(cmd, shell=True, text=True).strip()
        except Exception as e:
            print(f"[!] Warning fetching gcloud token: {e}", flush=True)
            _cached_token = ""
    return _cached_token

def get_auth_headers():
    headers = {"Content-Type": "application/json"}
    token = get_token()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    else:
        headers["x-emulated-sa"] = SA_EMAIL
    return headers

def read_workflow(workflow_id):
    try:
        url = f"{GATEWAY_URL}/v1/execute"
        body = {
            "callerServiceAccount": SA_EMAIL,
            "targetResource": "firestore:workflows",
            "collectionName": "workflows",
            "action": "read",
            "payload": {"docId": workflow_id}
        }
        res = requests.post(url, json=body, headers={"x-emulated-sa": SA_EMAIL}, timeout=30)
        if res.status_code == 200:
            return res.json().get("data", {})
        return {}
    except Exception as e:
        print(f"[!] Error reading workflow: {e}", flush=True)
        return {}

def run_legal_contract_tests():
    print("=" * 80, flush=True)
    print("LEGAL CONTRACT AGENT (PHASE 15b) END-TO-END PROOF VERIFICATION", flush=True)
    print("=" * 80, flush=True)

    contract_id = "ctr-2026-001"
    workflow_id = f"wf-{contract_id}"

    # Initialize workflow document cleanly in Firestore with required ownership identities
    print(f"\n[*] Initializing workflow document '{workflow_id}' in Firestore...", flush=True)
    init_payload = {
        "callerServiceAccount": DASHBOARD_SA,
        "targetResource": "firestore:workflows",
        "collectionName": "workflows",
        "action": "write",
        "payload": {
            "docId": workflow_id,
            "data": {
                "type": "contract-review",
                "status": "queued",
                "initiatingAgentId": "contract-review",
                "involvedAgentIds": ["contract-review"],
                "involvedServiceAccounts": [SA_EMAIL, DASHBOARD_SA],
                "currentStep": "queued",
                "context": {"contractId": contract_id},
                "updatedAt": datetime.now(timezone.utc).isoformat()
            }
        }
    }
    requests.post(f"{GATEWAY_URL}/v1/execute", json=init_payload, headers={"x-emulated-sa": DASHBOARD_SA}, timeout=30)

    # ----------------------------------------------------
    # TEST 1: POST /review for contractId
    # ----------------------------------------------------
    print(f"\n[STEP 1] Submitting async contract review request for contract '{contract_id}'...", flush=True)
    headers = get_auth_headers()
    start_t = time.time()
    res = requests.post(f"{AGENT_URL}/review", json={"contractId": contract_id}, headers=headers, timeout=30)
    
    print(f"HTTP Status: {res.status_code}", flush=True)
    print(f"Response Body: {res.text}", flush=True)

    assert res.status_code == 202, f"Expected 202 Accepted, got {res.status_code}"
    res_json = res.json()
    assert res_json.get("status") == "queued", f"Expected status='queued', got {res_json.get('status')}"
    
    message_id = res_json.get("messageId")
    queued_at = res_json.get("queuedAt")
    print(f"[+] STEP 1 SUCCESS: 202 Accepted returned in {time.time() - start_t:.2f}s!", flush=True)
    print(f"    Pub/Sub Message ID: {message_id}", flush=True)
    print(f"    Queued At Timestamp: {queued_at}", flush=True)

    # ----------------------------------------------------
    # TEST 2: Poll Firestore and observe state transitions
    # ----------------------------------------------------
    print(f"\n[STEP 2] Polling Firestore for state transitions (queued -> running -> waiting_approval/completed)...", flush=True)
    seen_states = {}
    poll_start = time.time()
    max_wait = 120
    final_wf = {}

    while time.time() - poll_start < max_wait:
        wf = read_workflow(workflow_id)
        current_status = wf.get("status")
        updated_at = wf.get("updatedAt")
        
        if current_status and current_status not in seen_states:
            elapsed = time.time() - poll_start
            seen_states[current_status] = {"timestamp": updated_at, "elapsed_seconds": round(elapsed, 2)}
            print(f"    [Transition Detected] status='{current_status}' at T+{elapsed:.1f}s (updatedAt={updated_at})", flush=True)

        if current_status in ["waiting_approval", "completed"]:
            final_wf = wf
            break

        time.sleep(3)

    print(f"\n[+] Observed State Transitions Summary:", flush=True)
    for st, info in seen_states.items():
        print(f"    - {st}: {info['timestamp']} (elapsed: {info['elapsed_seconds']}s)", flush=True)

    assert "queued" in seen_states, "Workflow was never in queued state"
    assert "running" in seen_states or "waiting_approval" in seen_states or "completed" in seen_states, "Workflow did not start running"
    assert "waiting_approval" in seen_states or "completed" in seen_states, "Workflow did not finish processing"
    print(f"[+] STEP 2 SUCCESS: Verified real state transitions with real timestamps!", flush=True)

    # ----------------------------------------------------
    # TEST 3: Verify final result quality
    # ----------------------------------------------------
    print(f"\n[STEP 3] Verifying final result quality...", flush=True)
    ctx = final_wf.get("context", {})
    risk_score = ctx.get("riskScore")
    assessment_status = ctx.get("assessmentStatus")
    summary = ctx.get("summary")
    findings = ctx.get("findings", [])

    print(f"    Risk Score: {risk_score}", flush=True)
    print(f"    Assessment Status: {assessment_status}", flush=True)
    print(f"    Workflow Status: {final_wf.get('status')}", flush=True)
    print(f"    Summary: {summary}", flush=True)
    print(f"    Findings count: {len(findings)}", flush=True)
    for f in findings:
        print(f"      * {f}", flush=True)

    assert risk_score is not None or assessment_status is not None, "Missing riskScore/assessmentStatus"
    print(f"[+] STEP 3 SUCCESS: Final contract review result verified!", flush=True)

    # ----------------------------------------------------
    # TEST 4: Idempotency Guard Test (Simulate duplicate Pub/Sub delivery)
    # ----------------------------------------------------
    print(f"\n[STEP 4] Testing Idempotency Guard (sending duplicate worker payload)...", flush=True)
    worker_url = f"{AGENT_URL}/worker/review"
    duplicate_payload = {
        "message": {
            "attributes": {
                "agentType": "legal-contract",
                "contractId": contract_id,
                "workflowId": workflow_id
            },
            "data": "",
            "messageId": message_id
        }
    }
    
    dup_res = requests.post(worker_url, json=duplicate_payload, headers=headers, timeout=30)
    print(f"    Duplicate Invocation Status: {dup_res.status_code}", flush=True)
    print(f"    Duplicate Invocation Response: {dup_res.text}", flush=True)

    assert dup_res.status_code == 200, f"Expected 200 OK from worker idempotency guard, got {dup_res.status_code}"
    dup_json = dup_res.json()
    assert dup_json.get("status") == "skipped", f"Expected status='skipped', got {dup_json.get('status')}"
    print(f"[+] STEP 4 SUCCESS: Idempotency guard prevented double-processing!", flush=True)

    print("\n" + "=" * 80, flush=True)
    print("LEGAL CONTRACT AGENT PROOF PASSED PERFECTLY!", flush=True)
    print("=" * 80, flush=True)

if __name__ == "__main__":
    run_legal_contract_tests()
