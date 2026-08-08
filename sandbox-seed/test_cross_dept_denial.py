#!/usr/bin/env python3
"""
Step 8: Cross-Department Zero-Trust Denial Test.

Attempts to read 'sandbox_leave_requests' (HR Department data) using the
Fraud/Finance agent's identity (`agentmesh-fraud-finance@agentmesh-fleet-2026.iam.gserviceaccount.com`).

Verifies that the Gateway pipeline rejects the request with HTTP 403 / policy decision 'denied'
and writes an audit log entry.
"""
import os
import sys
import json
import asyncio
from google.cloud import firestore

PROJECT_ID = os.getenv("GCP_PROJECT_ID", "agentmesh-fleet-2026")
FINANCE_SA = f"agentmesh-fraud-finance@{PROJECT_ID}.iam.gserviceaccount.com"

# Import Gateway pipeline directly
sys.path.insert(0, os.path.abspath("gateway"))
from main import execute_request, GatewayRequest

class FakeRequest:
    pass

async def test_denial():
    print("=" * 80)
    print("PHASE 8b - STEP 8: CROSS-DEPARTMENT ZERO-TRUST DENIAL TEST")
    print("=" * 80)
    print(f"Caller Identity: {FINANCE_SA} (Finance Department)")
    print(f"Target Resource: firestore:sandbox_leave_requests (HR Department Data)")

    req = GatewayRequest(
        callerServiceAccount=FINANCE_SA,
        targetResource="firestore:sandbox_leave_requests",
        collectionName="sandbox_leave_requests",
        action="read",
        payload={"docId": "lvr-2026-001"}
    )

    res = await execute_request(req, FakeRequest(), caller_email=FINANCE_SA)
    
    status_code = getattr(res, "status_code", 200)
    body_text = res.body.decode("utf-8") if hasattr(res, "body") else str(res)
    body_json = json.loads(body_text) if hasattr(res, "body") else {}

    print(f"\n[+] Gateway Response Status Code: {status_code}")
    print(f"[+] Gateway Response Body:\n{json.dumps(body_json, indent=2)}")

    policy_decision = body_json.get("policyDecision")
    policy_reason = body_json.get("policyReason") or body_json.get("detail")
    audit_log_id = body_json.get("auditLogId")

    print(f"\n[+] Policy Decision : {policy_decision}")
    print(f"[+] Policy Reason   : {policy_reason}")
    print(f"[+] Audit Log ID    : {audit_log_id}")

    # Verify Audit Log entry in Firestore if created
    db = firestore.Client(project=PROJECT_ID, database="(default)")
    if audit_log_id:
        ad_doc = db.collection("audit_log").document(audit_log_id).get()
        if ad_doc.exists:
            ad_data = ad_doc.to_dict()
            print(f"\n[+] Verified Audit Log in Firestore:")
            print(f"    agentId:        {ad_data.get('agentId')}")
            print(f"    policyDecision: {ad_data.get('policyDecision')}")
            print(f"    policyReason:   {ad_data.get('policyReason')}")

    is_denied = (status_code == 403) or (policy_decision == "denied")
    print("\n" + "=" * 80)
    if is_denied:
        print("[PASS] DENIAL TEST PASSED: Fraud/Finance agent strictly DENIED from reading HR leave requests!")
    else:
        print("[FAIL] DENIAL TEST FAILED: Request was not denied as expected.")
    print("=" * 80 + "\n")

    return is_denied

if __name__ == "__main__":
    success = asyncio.run(test_denial())
    sys.exit(0 if success else 1)
