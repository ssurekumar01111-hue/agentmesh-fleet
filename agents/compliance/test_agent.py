#!/usr/bin/env python3
"""
Test script for Compliance Agent.
Tests:
 1. Responsibility 1: Reviews paused workflow 'wf-inv-2026-007', queries policies via Gateway, generates compliance assessment, and writes to memory doc 'compliance-case-inv-2026-007'.
 2. Responsibility 2: Executes unauthorized read of 'sandbox_employees' via Gateway using 'agentmesh-compliance' identity. Asserts HTTP 403 / failure and returns auditLogId.
"""

import os
import sys
from agent import ComplianceAgent
from google.cloud import firestore

PROJECT_ID = os.getenv("GCP_PROJECT_ID", "agentmesh-fleet-2026")
DATABASE_ID = os.getenv("FIRESTORE_DATABASE", "(default)")

db = firestore.Client(project=PROJECT_ID, database=DATABASE_ID)

def test_responsibility_1_workflow_review():
    print("\n" + "=" * 70)
    print("TEST 4c - RESPONSIBILITY 1: WORKFLOW COMPLIANCE REVIEW TEST")
    print("=" * 70)

    agent = ComplianceAgent()
    res = agent.review_workflow_compliance("wf-inv-2026-007")

    print("\n--- COMPLIANCE AGENT REASONING OUTPUT ---")
    print(f"Workflow ID        : {res['workflowId']}")
    print(f"Compliance Case ID : {res['complianceCaseId']}")
    print(f"Assessment Decision: {res['assessmentDecision']}")
    print(f"Summary            : {res['summary']}")
    print("Findings           :")
    for f in res['findings']:
        print(f"  • {f}")

    assert res['assessmentDecision'] in ("ESCALATE", "REJECT", "APPROVE"), f"Invalid decision {res['assessmentDecision']}"
    assert res['complianceCaseId'] == "compliance-case-inv-2026-007", f"Unexpected case ID {res['complianceCaseId']}"

    # Readback from Firestore memory collection
    mem_doc = db.collection("memory").document("compliance-case-inv-2026-007").get()
    assert mem_doc.exists, "Compliance memory doc 'compliance-case-inv-2026-007' missing in Firestore!"

    mem_data = mem_doc.to_dict()
    print("\n--- REAL FIRESTORE MEMORY DOCUMENT PRODUCED ---")
    print(f"Memory Doc ID: compliance-case-inv-2026-007")
    print(f"Assessment Decision: {mem_data.get('assessmentDecision')}")
    print(f"Summary            : {mem_data.get('summary')}")
    print(f"Findings           : {mem_data.get('findings')}")
    print(f"Updated At         : {mem_data.get('updatedAt')}")

    return res

def test_responsibility_2_denied_access():
    print("\n" + "=" * 70)
    print("TEST 4c - RESPONSIBILITY 2: LIVE ZERO-TRUST DENIAL TEST")
    print("=" * 70)

    agent = ComplianceAgent()
    gateway_res = agent.test_hr_data_access()

    print("\n--- GATEWAY RESPONSE SUMMARY ---")
    print(f"Success Flag : {gateway_res.get('success')}")
    print(f"Status Code  : {gateway_res.get('status_code')}")
    print(f"Error Detail : {gateway_res.get('error')}")
    print(f"Audit Log ID : {gateway_res.get('auditLogId')}")

    # Assert genuine rejection
    assert gateway_res.get('success') is False, "EXPECTED DENIAL, but request succeeded!"
    assert gateway_res.get('status_code') in (403, 400), f"Expected HTTP 403 or 400, got {gateway_res.get('status_code')}"

    # Audit log verification if auditLogId was returned
    audit_log_id = gateway_res.get('auditLogId')
    if audit_log_id:
        audit_doc = db.collection("audit_log").document(audit_log_id).get()
        if audit_doc.exists:
            ad_data = audit_doc.to_dict()
            print("\n--- REAL AUDIT LOG DOCUMENT PRODUCED ---")
            print(f"Audit Log ID    : {audit_log_id}")
            print(f"Agent ID        : {ad_data.get('agentId')}")
            print(f"Policy Decision : {ad_data.get('policyDecision')}")
            print(f"Policy Reason   : {ad_data.get('policyReason')}")

    return gateway_res

def main():
    print("[*] Running Compliance Agent Integration Tests...")
    test_responsibility_1_workflow_review()
    test_responsibility_2_denied_access()
    print("\n" + "=" * 70)
    print("ALL COMPLIANCE AGENT TESTS PASSED PERFECTLY!")
    print("=" * 70 + "\n")

if __name__ == "__main__":
    main()
