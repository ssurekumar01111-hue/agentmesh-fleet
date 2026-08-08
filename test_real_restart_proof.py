#!/usr/bin/env python3
"""
Phase 4d — Real Cloud Run Service Restart Proof Script
Executes steps 1-7 with real Cloud Run service restart via gcloud.
"""

import os
import sys
import time
import json
import urllib.request
import urllib.error
import subprocess
from google.cloud import firestore

PROJECT_ID = os.getenv("GCP_PROJECT_ID", "agentmesh-fleet-2026")
DATABASE_ID = os.getenv("FIRESTORE_DATABASE", "(default)")
GCLOUD_BIN = r"C:\Program Files (x86)\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd"
SERVICE_NAME = "agentmesh-fraud-finance"
REGION = "asia-south1"
SERVICE_URL = "https://agentmesh-fraud-finance-138003672216.asia-south1.run.app"

INVOICE_ID = "inv-2026-009"
WORKFLOW_ID = f"wf-{INVOICE_ID}"
CASE_ID = f"case-{INVOICE_ID}"
COMPLIANCE_CASE_ID = f"compliance-{CASE_ID}"

db = firestore.Client(project=PROJECT_ID, database=DATABASE_ID)

sys.path.insert(0, os.path.abspath("gateway"))
from main import execute_request, GatewayRequest
import importlib
import importlib.util

class FakeRequest:
    pass

async def call_gateway_direct(caller_sa, resource, collection, action, payload):
    req = GatewayRequest(
        callerServiceAccount=caller_sa,
        targetResource=resource,
        collectionName=collection,
        action=action,
        payload=payload
    )
    res = await execute_request(req, FakeRequest(), caller_email=caller_sa)
    if hasattr(res, "body"):
        data = json.loads(res.body.decode("utf-8"))
        if isinstance(data, dict):
            data["status_code"] = getattr(res, "status_code", 200)
        return data
    return res

def load_module(name, dir_path, filename):
    abs_dir = os.path.abspath(dir_path)
    if abs_dir in sys.path:
        sys.path.remove(abs_dir)
    sys.path.insert(0, abs_dir)
    for mod_key in ["gateway_client", "reasoning", "agent"]:
        if mod_key in sys.modules:
            del sys.modules[mod_key]
    file_path = os.path.join(abs_dir, filename)
    spec = importlib.util.spec_from_file_location(name, file_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod

def read_workflow_state(label: str):
    doc = db.collection("workflows").document(WORKFLOW_ID).get()
    data = doc.to_dict() if doc.exists else {}
    print(f"\n--- FIRESTORE WORKFLOW STATE [{label}] ---")
    print(f"Workflow ID : {WORKFLOW_ID}")
    print(f"Status      : {data.get('status')}")
    print(f"CurrentStep : {data.get('currentStep')}")
    print(f"Updated At  : {data.get('updatedAt')}")
    return data

def get_revisions():
    cmd = [GCLOUD_BIN, "run", "revisions", "list", f"--service={SERVICE_NAME}", f"--region={REGION}", f"--project={PROJECT_ID}", "--format=json"]
    out = subprocess.check_output(cmd).decode("utf-8")
    return json.loads(out)

async def main():
    print("=" * 80)
    print("PHASE 4d — PROVE REAL CLOUD RUN SERVICE RESTART FOR WORKFLOW RESUMPTION")
    print("=" * 80)

    fraud_sa = f"agentmesh-fraud-finance@{PROJECT_ID}.iam.gserviceaccount.com"
    comp_sa = f"agentmesh-compliance@{PROJECT_ID}.iam.gserviceaccount.com"

    # Step 1: Confirm/create workflow at waiting_approval
    print("\n[Step 1] Seed / Verify workflow at 'waiting_approval' for inv-2026-009...")
    inv_res = await call_gateway_direct(fraud_sa, "firestore:sandbox_invoices", "sandbox_invoices", "read", {"docId": INVOICE_ID})
    invoice = inv_res.get("data", {})
    vendor_id = invoice.get("vendorId")
    vend_res = await call_gateway_direct(fraud_sa, "firestore:sandbox_vendors", "sandbox_vendors", "read", {"docId": vendor_id})
    vendor = vend_res.get("data", {})

    fraud_reasoning = load_module("fraud_reasoning", "agents/fraud-finance", "reasoning.py")
    f_engine = fraud_reasoning.FraudReasoningEngine()
    risk_score, f_summary, f_findings, status = f_engine.analyze_invoice(invoice, vendor)

    await call_gateway_direct(fraud_sa, "firestore:memory", "memory", "write", {
        "docId": CASE_ID,
        "data": {
            "workflowId": WORKFLOW_ID,
            "entityType": "invoice",
            "entityId": CASE_ID,
            "summary": f_summary,
            "findings": f_findings,
            "riskScore": risk_score,
            "history": ["Investigation initiated.", "Vendor baseline fetched.", f"Risk score {risk_score:.2f}"],
            "updatedAt": "AUTO_TIMESTAMP"
        }
    })

    await call_gateway_direct(fraud_sa, "firestore:workflows", "workflows", "write", {
        "docId": WORKFLOW_ID,
        "data": {
            "type": "invoice-review",
            "status": "waiting_approval",
            "initiatingAgentId": "fraud-finance",
            "involvedAgentIds": ["fraud-finance", "compliance"],
            "involvedServiceAccounts": [fraud_sa],
            "currentStep": "human_approval_gate",
            "context": {"invoiceId": INVOICE_ID, "amount": invoice.get("amount"), "riskScore": risk_score},
            "updatedAt": "AUTO_TIMESTAMP"
        }
    })
    wf_s1 = read_workflow_state("STEP 1: CREATED/CONFIRMED WAITING_APPROVAL")
    assert wf_s1.get("status") == "waiting_approval"

    # Step 2: Compliance review step
    print("\n[Step 2] Compliance agent audits workflow wf-inv-2026-009...")
    wf_read = await call_gateway_direct(comp_sa, "firestore:workflows", "workflows", "read", {"docId": WORKFLOW_ID})
    mem_read = await call_gateway_direct(comp_sa, "firestore:memory", "memory", "read", {"docId": CASE_ID})
    pol_read = await call_gateway_direct(comp_sa, "firestore:policies", "policies", "query", {"query": []})

    comp_reasoning = load_module("compliance_reasoning", "agents/compliance", "reasoning.py")
    c_engine = comp_reasoning.ComplianceReasoningEngine()
    decision, c_summary, c_findings = c_engine.evaluate_workflow_compliance(
        wf_read.get("data", {}),
        mem_read.get("data", {}),
        pol_read.get("data", {}).get("documents", [])
    )
    print(f"  • Compliance Decision: {decision}")

    await call_gateway_direct(comp_sa, "firestore:memory", "memory", "write", {
        "docId": COMPLIANCE_CASE_ID,
        "data": {
            "workflowId": WORKFLOW_ID,
            "entityType": "invoice_compliance_review",
            "entityId": CASE_ID,
            "summary": c_summary,
            "findings": c_findings,
            "assessmentDecision": decision,
            "history": ["Compliance audit initiated via Gateway.", f"Decision={decision}"],
            "updatedAt": "AUTO_TIMESTAMP"
        }
    })

    # Step 3: Flip workflow to "resumed" via temporary approval stand-in script
    print("\n[Step 3] Stand-in script flips workflow wf-inv-2026-009 to 'resumed' in Firestore...")
    pause_timestamp = time.time()
    db.collection("workflows").document(WORKFLOW_ID).update({
        "status": "resumed",
        "currentStep": "human_approval_granted",
        "updatedAt": firestore.SERVER_TIMESTAMP
    })
    wf_s3 = read_workflow_state("STEP 3: WORKFLOW FLIPPED TO RESUMED")
    assert wf_s3.get("status") == "resumed"

    # Capture initial revision prior to force restart
    initial_revisions = get_revisions()
    active_old_rev = next((r for r in initial_revisions if r.get("status", {}).get("conditions", [{}])[0].get("status") == "True"), initial_revisions[0])
    old_rev_name = active_old_rev["metadata"]["name"]
    print(f"\n[Baseline] Current Active Cloud Run Revision: {old_rev_name}")

    # Step 4: Force a REAL restart of deployed Cloud Run service
    print("\n[Step 4] FORCING REAL CLOUD RUN SERVICE RESTART via gcloud run services update...")
    restart_ts = int(time.time())
    update_cmd = [
        GCLOUD_BIN, "run", "services", "update", SERVICE_NAME,
        f"--region={REGION}", f"--project={PROJECT_ID}",
        f"--update-env-vars=RESTART_MARKER={restart_ts}"
    ]
    subprocess.check_call(update_cmd)

    # Confirm new revision created
    post_revisions = get_revisions()
    new_rev = post_revisions[0]
    new_rev_name = new_rev["metadata"]["name"]
    new_rev_created = new_rev["metadata"]["creationTimestamp"]
    print(f"  • Old Revision Name/ID: {old_rev_name}")
    print(f"  • New Revision Name/ID: {new_rev_name}")
    print(f"  • New Revision Creation Time: {new_rev_created}")

    assert new_rev_name != old_rev_name, "ERROR: Cloud Run did not create a new revision!"
    elapsed = time.time() - pause_timestamp
    print(f"  • Elapsed time between workflow pause and new revision creation: {elapsed:.2f} seconds")

    # Step 5: Confirm new revision is live and serving via /health on deployed URL
    print("\n[Step 5] Polling /health on live deployed Cloud Run URL...")
    health_url = f"{SERVICE_URL}/health"
    health_ok = False
    for i in range(12):
        try:
            req = urllib.request.Request(health_url)
            with urllib.request.urlopen(req) as resp:
                if resp.status == 200:
                    health_body = json.loads(resp.read().decode("utf-8"))
                    print(f"  • /health Response: {health_body}")
                    health_ok = True
                    break
        except Exception as e:
            print(f"  Waiting for service... ({e})")
            time.sleep(3)

    assert health_ok, "Deployed Cloud Run service health check failed!"

    # Step 6 & 7: Call real deployed Cloud Run endpoint to trigger completion
    print("\n[Step 6 & 7] Calling LIVE Cloud Run POST /resume endpoint to trigger completion...")
    resume_url = f"{SERVICE_URL}/resume"
    payload_data = json.dumps({"workflowId": WORKFLOW_ID}).encode("utf-8")
    req = urllib.request.Request(resume_url, data=payload_data, headers={"Content-Type": "application/json"}, method="POST")

    with urllib.request.urlopen(req) as resp:
        http_code = resp.status
        http_response = json.loads(resp.read().decode("utf-8"))

    print(f"  • Real HTTP Endpoint Called: POST {resume_url}")
    print(f"  • Payload Sent              : {{'workflowId': '{WORKFLOW_ID}'}}")
    print(f"  • Real HTTP Status Code    : {http_code}")
    print(f"  • Real HTTP Response Body  : {json.dumps(http_response, indent=2)}")

    # Verify Firestore final workflow document
    final_wf_doc = db.collection("workflows").document(WORKFLOW_ID).get().to_dict()
    print("\n--- FINAL FIRESTORE WORKFLOW DOCUMENT ---")
    print(json.dumps(final_wf_doc, indent=2, default=str))

    assert final_wf_doc.get("status") == "completed", f"Expected completed, got {final_wf_doc.get('status')}"
    assert final_wf_doc.get("currentStep") == "review_complete", f"Expected review_complete, got {final_wf_doc.get('currentStep')}"

    print("\n" + "=" * 80)
    print("PROVED: REAL CLOUD RUN SERVICE RESTART FOR WORKFLOW RESUMPTION SUCCESSFUL!")
    print("=" * 80 + "\n")

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
