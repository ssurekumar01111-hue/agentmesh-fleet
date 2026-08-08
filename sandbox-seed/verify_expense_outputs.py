#!/usr/bin/env python3
"""Verify that Memory and Workflow documents were written by the expense-approval agent."""
from google.cloud import firestore
import json

db = firestore.Client(project="agentmesh-fleet-2026", database="(default)")

cases = ["case-exp-2026-006", "case-exp-2026-001"]
wfs = ["wf-exp-2026-006", "wf-exp-2026-001"]

print("=" * 60)
print("MEMORY DOCUMENTS (written by expense-approval agent)")
print("=" * 60)
for case_id in cases:
    doc = db.collection("memory").document(case_id).get()
    if doc.exists:
        d = doc.to_dict()
        print(f"\n  [+] memory/{case_id}")
        print(f"      workflowId:       {d.get('workflowId')}")
        print(f"      entityType:       {d.get('entityType')}")
        print(f"      riskScore:        {d.get('riskScore')}")
        print(f"      summary:          {d.get('summary')[:100]}...")
        print(f"      findings count:   {len(d.get('findings', []))}")
        print(f"      history entries:  {len(d.get('history', []))}")
    else:
        print(f"\n  [-] memory/{case_id} — NOT FOUND")

print("\n" + "=" * 60)
print("WORKFLOW DOCUMENTS (written by expense-approval agent)")
print("=" * 60)
for wf_id in wfs:
    doc = db.collection("workflows").document(wf_id).get()
    if doc.exists:
        d = doc.to_dict()
        print(f"\n  [+] workflows/{wf_id}")
        print(f"      type:             {d.get('type')}")
        print(f"      status:           {d.get('status')}")
        print(f"      currentStep:      {d.get('currentStep')}")
        print(f"      initiatingAgent:  {d.get('initiatingAgentId')}")
        ctx = d.get("context", {})
        print(f"      context.expenseId:     {ctx.get('expenseId')}")
        print(f"      context.amount:        {ctx.get('amount')}")
        print(f"      context.assessStatus:  {ctx.get('assessmentStatus')}")
        print(f"      context.riskScore:     {ctx.get('riskScore')}")
    else:
        print(f"\n  [-] workflows/{wf_id} — NOT FOUND")

print("\n" + "=" * 60)
print("agent_registry/expense-approval")
print("=" * 60)
doc = db.collection("agent_registry").document("expense-approval").get().to_dict()
print(f"  status:          {doc.get('status')}")
print(f"  version:         {doc.get('version')}")
print(f"  serviceAccount:  {doc.get('serviceAccountEmail')}")
print(f"  allowedCollections: {doc.get('allowedCollections')}")
print(f"  riskLevel:       {doc.get('riskLevel')}")
