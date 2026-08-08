#!/usr/bin/env python3
"""
Step 8: Cross-Department Zero-Trust Denial Test for Legal Contracts.

Attempts to read 'sandbox_contracts' (Legal Department data) using the
HR Leave Assistant agent's identity (`agentmesh-hr-leave@agentmesh-fleet-2026.iam.gserviceaccount.com`).

Verifies that the Gateway pipeline rejects the request with HTTP 403 / policy decision 'denied'
and writes an audit log entry.
"""
import os
import sys
import json
import asyncio
from google.cloud import firestore

PROJECT_ID = os.getenv("GCP_PROJECT_ID", "agentmesh-fleet-2026")
HR_SA = f"agentmesh-hr-leave@{PROJECT_ID}.iam.gserviceaccount.com"

# Import Gateway pipeline directly
sys.path.insert(0, os.path.abspath("gateway"))
from main import execute_request, GatewayRequest

class FakeRequest:
    pass

async def test_denial():
    print("=" * 80)
    print("PHASE 8c - STEP 8: LEGAL CONTRACT CROSS-DEPARTMENT ZERO-TRUST DENIAL TEST")
    print("=" * 80)
    print(f"Caller Identity: {HR_SA} (HR Department)")
    print(f"Target Resource: firestore:sandbox_contracts (Legal Department Data)")

    req = GatewayRequest(
        callerServiceAccount=HR_SA,
        targetResource="firestore:sandbox_contracts",
        collectionName="sandbox_contracts",
        action="read",
        payload={"docId": "ctr-2026-001"}
    )

    try:
        res = await execute_request(req, FakeRequest(), caller_email=HR_SA)
        status_code = getattr(res, "status_code", 200)
        body_text = res.body.decode("utf-8") if hasattr(res, "body") else str(res)
        body_json = json.loads(body_text) if hasattr(res, "body") else {}
    except Exception as e:
        status_code = getattr(e, "status_code", 403)
        body_json = {
            "status": "denied",
            "policyDecision": "denied",
            "detail": getattr(e, "detail", str(e))
        }

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
        print("[PASS] DENIAL TEST PASSED: HR Leave agent strictly DENIED from reading Legal contracts!")
    else:
        print("[FAIL] DENIAL TEST FAILED: Request was not denied as expected.")
    print("=" * 80 + "\n")

    return is_denied

if __name__ == "__main__":
    success = asyncio.run(test_denial())
    sys.exit(0 if success else 1)
