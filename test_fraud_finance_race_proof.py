import os
import sys
import time
import json
import subprocess
import requests
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

os.environ["ALLOW_LOCAL_AUTH_EMULATION"] = "true"

sys.path.append(os.path.join(os.path.dirname(__file__), "agents", "fraud-finance"))
from gateway_client import GatewayClient

AGENT_URL = "https://agentmesh-fraud-finance-138003672216.asia-south1.run.app"
GATEWAY_URL = "https://agentmesh-gateway-138003672216.asia-south1.run.app"
PROJECT_ID = "agentmesh-fleet-2026"
SA_EMAIL = f"agentmesh-fraud-finance@{PROJECT_ID}.iam.gserviceaccount.com"
DASHBOARD_SA = f"agentmesh-dashboard@{PROJECT_ID}.iam.gserviceaccount.com"

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

def send_worker_request(req_id, worker_payload):
    headers = get_auth_headers()
    url = f"{AGENT_URL}/worker/investigate"
    t_start = time.time()
    print(f"[{datetime.now(timezone.utc).isoformat()}] [Thread {req_id}] Firing worker request...", flush=True)
    try:
        res = requests.post(url, json=worker_payload, headers=headers, timeout=60)
        t_elapsed = time.time() - t_start
        print(f"[{datetime.now(timezone.utc).isoformat()}] [Thread {req_id}] Received HTTP {res.status_code} in {t_elapsed:.2f}s", flush=True)
        return {
            "threadId": req_id,
            "statusCode": res.status_code,
            "response": res.json() if res.status_code == 200 else res.text,
            "elapsed": t_elapsed
        }
    except Exception as e:
        print(f"[{datetime.now(timezone.utc).isoformat()}] [Thread {req_id}] Exception: {e}", flush=True)
        return {"threadId": req_id, "error": str(e)}

def run_race_proof_test():
    print("=" * 80, flush=True)
    print("FRAUD & FINANCE ATOMIC CLAIM IDEMPOTENCY RACE PROOF TEST", flush=True)
    print("=" * 80, flush=True)

    invoice_id = "inv-2026-001"
    workflow_id = f"wf-{invoice_id}"

    # 1. Reset workflow document in Firestore to status="queued"
    print(f"\n[*] Resetting workflow document '{workflow_id}' in Firestore to status='queued'...", flush=True)
    init_payload = {
        "callerServiceAccount": DASHBOARD_SA,
        "targetResource": "firestore:workflows",
        "collectionName": "workflows",
        "action": "write",
        "payload": {
            "docId": workflow_id,
            "data": {
                "type": "invoice-review",
                "status": "queued",
                "initiatingAgentId": "fraud-finance",
                "involvedAgentIds": ["fraud-finance", "compliance"],
                "involvedServiceAccounts": [SA_EMAIL, DASHBOARD_SA],
                "currentStep": "queued",
                "context": {"invoiceId": invoice_id},
                "updatedAt": datetime.now(timezone.utc).isoformat()
            }
        }
    }
    requests.post(f"{GATEWAY_URL}/v1/execute", json=init_payload, headers={"x-emulated-sa": DASHBOARD_SA}, timeout=30)

    # 2. Build duplicate worker push payloads
    payload_a = {
        "message": {
            "attributes": {"agentType": "fraud-finance", "invoiceId": invoice_id, "workflowId": workflow_id},
            "data": "",
            "messageId": "pubsub-race-msg-A"
        }
    }
    payload_b = {
        "message": {
            "attributes": {"agentType": "fraud-finance", "invoiceId": invoice_id, "workflowId": workflow_id},
            "data": "",
            "messageId": "pubsub-race-msg-B"
        }
    }

    # 3. Fire NEAR-SIMULTANEOUS requests using ThreadPoolExecutor
    print(f"\n[*] Firing 2 near-simultaneous duplicate worker requests concurrently...", flush=True)
    with ThreadPoolExecutor(max_workers=2) as executor:
        f1 = executor.submit(send_worker_request, "A", payload_a)
        f2 = executor.submit(send_worker_request, "B", payload_b)
        res_a = f1.result()
        res_b = f2.result()

    print("\n" + "=" * 80, flush=True)
    print("CONCURRENT WORKER RESPONSES SUMMARY:", flush=True)
    print(f"Thread A Response: {json.dumps(res_a, indent=2)}", flush=True)
    print(f"Thread B Response: {json.dumps(res_b, indent=2)}", flush=True)
    print("=" * 80, flush=True)

    # 4. Verify Atomic Rejection Evidence
    responses = [res_a.get("response", {}), res_b.get("response", {})]
    skipped_count = sum(1 for r in responses if isinstance(r, dict) and r.get("status") == "skipped")
    success_count = sum(1 for r in responses if isinstance(r, dict) and (r.get("status") in ["in_progress", "completed", "waiting_approval", "success"] or "workflowStatus" in r or "riskScore" in r))

    print(f"\n[+] Analysis of Race Condition Test Results:", flush=True)
    print(f"    - Total concurrent requests: 2", flush=True)
    print(f"    - Atomic Claims Succeeded: {success_count}", flush=True)
    print(f"    - Atomic Claims Rejected (Skipped): {skipped_count}", flush=True)

    assert success_count == 1, f"Expected exactly 1 request to claim and execute, got {success_count}"
    assert skipped_count == 1, f"Expected exactly 1 request to be atomically rejected, got {skipped_count}"

    rejected_res = [r for r in responses if isinstance(r, dict) and r.get("status") == "skipped"][0]
    print(f"\n[+] Atomic Claim Rejection Evidence:")
    print(f"    - Status: {rejected_res.get('status')}")
    print(f"    - Reason: {rejected_res.get('reason')}")
    print(f"    - Current Workflow Status Observed: {rejected_res.get('currentStatus')}")

    print("\n" + "=" * 80, flush=True)
    print("CONCURRENCY RACE PROOF PASSED! RACE WINDOW IS ATOMICALLY CLOSED!")
    print("=" * 80, flush=True)

if __name__ == "__main__":
    run_race_proof_test()
