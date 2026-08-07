#!/usr/bin/env python3
"""
Test script for Fraud & Finance Agent.
Tests:
 1. Anomalous Invoice inv-2026-007 ($185k vs max $30k) -> Must flag HIGH RISK, escalate workflow to 'waiting_approval', write memory & workflow.
 2. Normal Invoice inv-2026-001 ($18.45k within $15k-$25k) -> Must assess LOW RISK, set workflow status to 'completed'.
"""

import os
import sys
from agent import FraudFinanceAgent
from google.cloud import firestore

PROJECT_ID = os.getenv("GCP_PROJECT_ID", "agentmesh-fleet-2026")
DATABASE_ID = os.getenv("FIRESTORE_DATABASE", "(default)")

db = firestore.Client(project=PROJECT_ID, database=DATABASE_ID)

def verify_firestore_docs(invoice_id: str):
    case_id = f"case-{invoice_id}"
    workflow_id = f"wf-{invoice_id}"

    mem_doc = db.collection("memory").document(case_id).get()
    wf_doc = db.collection("workflows").document(workflow_id).get()

    assert mem_doc.exists, f"Memory doc '{case_id}' was not created in Firestore!"
    assert wf_doc.exists, f"Workflow doc '{workflow_id}' was not created in Firestore!"

    return mem_doc.to_dict(), wf_doc.to_dict()

def test_anomalous_invoice():
    print("\n" + "=" * 70)
    print("TEST 3a: ANOMALOUS INVOICE TEST (inv-2026-007 - $185,000.00)")
    print("=" * 70)

    agent = FraudFinanceAgent()
    res = agent.process_invoice("inv-2026-007")

    print("\n--- AGENT REASONING OUTPUT ---")
    print(f"Risk Score       : {res['riskScore']}")
    print(f"Assessment Status: {res['assessmentStatus']}")
    print(f"Workflow Status  : {res['workflowStatus']}")
    print(f"Summary          : {res['summary']}")
    print("Findings         :")
    for f in res['findings']:
        print(f"  • {f}")

    assert res['riskScore'] >= 0.70, f"Expected high risk score >= 0.70, got {res['riskScore']}"
    assert res['workflowStatus'] == "waiting_approval", f"Expected waiting_approval, got {res['workflowStatus']}"

    # Readback from Firestore
    mem_data, wf_data = verify_firestore_docs("inv-2026-007")
    print("\n--- REAL FIRESTORE DOCUMENTS PRODUCED ---")
    print(f"Memory Doc (case-inv-2026-007): riskScore={mem_data.get('riskScore')}, findings={mem_data.get('findings')}")
    print(f"Workflow Doc (wf-inv-2026-007): status={wf_data.get('status')}, currentStep={wf_data.get('currentStep')}")

    return res

def test_normal_invoice():
    print("\n" + "=" * 70)
    print("TEST 3b: NORMAL INVOICE TEST (inv-2026-001 - $18,450.00)")
    print("=" * 70)

    agent = FraudFinanceAgent()
    res = agent.process_invoice("inv-2026-001")

    print("\n--- AGENT REASONING OUTPUT ---")
    print(f"Risk Score       : {res['riskScore']}")
    print(f"Assessment Status: {res['assessmentStatus']}")
    print(f"Workflow Status  : {res['workflowStatus']}")
    print(f"Summary          : {res['summary']}")
    print("Findings         :")
    for f in res['findings']:
        print(f"  • {f}")

    assert res['riskScore'] < 0.50, f"Expected low risk score < 0.50, got {res['riskScore']}"
    assert res['workflowStatus'] == "completed", f"Expected completed status, got {res['workflowStatus']}"

    # Readback from Firestore
    mem_data, wf_data = verify_firestore_docs("inv-2026-001")
    print("\n--- REAL FIRESTORE DOCUMENTS PRODUCED ---")
    print(f"Memory Doc (case-inv-2026-001): riskScore={mem_data.get('riskScore')}, findings={mem_data.get('findings')}")
    print(f"Workflow Doc (wf-inv-2026-001): status={wf_data.get('status')}, currentStep={wf_data.get('currentStep')}")

    return res

def main():
    print("[*] Running Fraud/Finance Agent Automated Integration Tests...")
    test_anomalous_invoice()
    test_normal_invoice()
    print("\n" + "=" * 70)
    print("ALL FRAUD/FINANCE AGENT TESTS PASSED PERFECTLY!")
    print("=" * 70 + "\n")

if __name__ == "__main__":
    main()
