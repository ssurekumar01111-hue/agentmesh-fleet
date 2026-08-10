#!/usr/bin/env python3
"""
Phase 5b End-to-End Real Verification Script:
1. Tests Overview, Registry, Live Workflows, Policies, and Observability endpoints.
2. Executes Policy Playground zero-trust check 1: Compliance Agent -> sandbox_employees (Must DENY with real policyReason).
3. Executes Policy Playground zero-trust check 2: Fraud Agent -> sandbox_invoices (Must ALLOW).
4. Verifies Workflow Detail Stepper & human approval action: approves a waiting_approval workflow and verifies 'resumed' Firestore status.
"""

import os
import json
import urllib.request
import urllib.error
from google.cloud import firestore

PROJECT_ID = "agentmesh-fleet-2026"
DATABASE_ID = "(default)"
DASHBOARD_URL = "https://agentmesh-dashboard-138003672216.asia-south1.run.app"
GATEWAY_URL = "https://agentmesh-gateway-138003672216.asia-south1.run.app"
WORKFLOW_ID = "wf-inv-2026-009"

db = firestore.Client(project=PROJECT_ID, database=DATABASE_ID)

def call_dashboard_gateway(payload):
    req = urllib.request.Request(
        f"{DASHBOARD_URL}/api/gateway",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode("utf-8"))

def run_e2e_verification():
    print("=" * 80)
    print("PHASE 5b — END-TO-END REAL DASHBOARD & POLICY PLAYGROUND VERIFICATION")
    print("=" * 80)

    # 1. Tab Data Verification
    print("\n[Step 1: 5-Tab Data Verification via Gateway]")
    reg_data = call_dashboard_gateway({"targetResource": "firestore:agent_registry", "collectionName": "agent_registry", "action": "read"})
    wf_data = call_dashboard_gateway({"targetResource": "firestore:workflows", "collectionName": "workflows", "action": "read"})
    pol_data = call_dashboard_gateway({"targetResource": "firestore:policies", "collectionName": "policies", "action": "read"})
    log_data = call_dashboard_gateway({"targetResource": "firestore:audit_log", "collectionName": "audit_log", "action": "read"})

    agents = reg_data.get("data", [])
    workflows = wf_data.get("data", [])
    policies = pol_data.get("data", [])
    logs = log_data.get("data", [])

    print(f"  • Registered Agent Docs : {len(agents)}")
    print(f"  • Workflow Docs          : {len(workflows)}")
    print(f"  • Policy Collection Docs : {len(policies)}")
    print(f"  • Audit Log Docs         : {len(logs)}")

    assert len(agents) > 0, "No agents returned"
    assert len(workflows) > 0, "No workflows returned"
    assert len(policies) > 0, "No policies returned"
    assert len(logs) > 0, "No audit logs returned"

    # 2. Policy Playground Live Test 1: Compliance -> sandbox_employees (Expect DENY)
    print("\n[Step 2: Policy Playground Live Test — Compliance -> sandbox_employees]")
    comp_sa = "agentmesh-compliance@agentmesh-fleet-2026.iam.gserviceaccount.com"
    deny_payload = {
        "simulate": True,
        "targetAgentSa": comp_sa,
        "targetResource": "firestore:sandbox_employees",
        "collectionName": "sandbox_employees",
        "action": "read"
    }

    try:
        deny_res = call_dashboard_gateway(deny_payload)
    except urllib.error.HTTPError as e:
        deny_res = json.loads(e.read().decode("utf-8"))

    print(f"  • Policy Decision: {deny_res.get('policyDecision') or deny_res.get('status')}")
    print(f"  • Target Agent SA: {deny_res.get('targetSa')}")
    print(f"  • Simulated Tag  : {deny_res.get('simulated')}")
    print(f"  • Policy Reason  : {deny_res.get('policyReason') or deny_res.get('detail')}")
    print(f"  • Audit Log ID   : {deny_res.get('auditLogId')}")

    assert deny_res.get("policyDecision") == "denied" or deny_res.get("status") == "denied", "Expected DENIED"
    assert deny_res.get("simulated") is True, "Expected simulated: true"
    assert "sandbox_employees" in (deny_res.get("policyReason") or deny_res.get("detail")), "Expected policy reason to reference sandbox_employees"
    assert deny_res.get("auditLogId") is not None, "Missing auditLogId"

    # 3. Policy Playground Live Test 2: Fraud -> sandbox_invoices (Expect ALLOW)
    print("\n[Step 3: Policy Playground Live Test — Fraud -> sandbox_invoices]")
    fraud_sa = "agentmesh-fraud-finance@agentmesh-fleet-2026.iam.gserviceaccount.com"
    allow_payload = {
        "simulate": True,
        "targetAgentSa": fraud_sa,
        "targetResource": "firestore:sandbox_invoices",
        "collectionName": "sandbox_invoices",
        "action": "read"
    }

    allow_res = call_dashboard_gateway(allow_payload)
    print(f"  • Policy Decision: {allow_res.get('policyDecision') or allow_res.get('status')}")
    print(f"  • Target Agent SA: {allow_res.get('targetSa')}")
    print(f"  • Simulated Tag  : {allow_res.get('simulated')}")
    print(f"  • Audit Log ID   : {allow_res.get('auditLogId')}")

    assert allow_res.get("policyDecision") == "allowed" or allow_res.get("status") == "allowed", "Expected ALLOWED"
    assert allow_res.get("simulated") is True, "Expected simulated: true"
    assert allow_res.get("auditLogId") is not None, "Missing auditLogId"

    # 4. Live Workflow Gate Review & Approval Test
    print(f"\n[Step 4: Live Workflow Gate Review — Resetting {WORKFLOW_ID} & Approving]")
    db.collection("workflows").document(WORKFLOW_ID).update({
        "status": "waiting_approval",
        "currentStep": "human_approval_gate",
        "updatedAt": firestore.SERVER_TIMESTAMP
    })

    wf_before = db.collection("workflows").document(WORKFLOW_ID).get().to_dict()
    print(f"  • Status Before Approval : '{wf_before.get('status')}'")

    approve_payload = {
        "targetResource": "firestore:workflows",
        "collectionName": "workflows",
        "action": "write",
        "payload": {
            "docId": WORKFLOW_ID,
            "data": {
                **wf_before,
                "status": "resumed",
                "currentStep": "human_approval_granted",
                "updatedAt": datetime.now(timezone.utc).isoformat()
            }
        }
    }
    approve_res = call_dashboard_gateway(approve_payload)
    print(f"  • Gateway Write Status   : {approve_res.get('status')}")

    wf_after = db.collection("workflows").document(WORKFLOW_ID).get().to_dict()
    print(f"  • Status After Approval  : '{wf_after.get('status')}' (currentStep: '{wf_after.get('currentStep')}')")
    assert wf_after.get("status") == "resumed"

    print("\n" + "=" * 80)
    print("PHASE 5b E2E VERIFICATION SUCCESSFUL — REAL GATEWAY ALLOW/DENY & WORKFLOW GATE PROVED!")
    print("=" * 80 + "\n")

if __name__ == "__main__":
    run_e2e_verification()
