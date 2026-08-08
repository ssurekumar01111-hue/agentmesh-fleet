#!/usr/bin/env python3
"""
Milestone script: Update agent_registry/expense-approval from 'pending' to 'active'
with the real service account, corrected allowedCollections, allowedTools, and riskLevel.
"""
import os
from datetime import datetime, timezone
from google.cloud import firestore

PROJECT_ID = "agentmesh-fleet-2026"
db = firestore.Client(project=PROJECT_ID, database="(default)")

updated = {
    "status": "active",
    "version": "1.0.0",
    "serviceAccountEmail": f"agentmesh-expense-approval@{PROJECT_ID}.iam.gserviceaccount.com",
    "capabilities": ["expense-review", "policy-check", "workflow-escalation"],
    "allowedTools": [
        "firestore:sandbox_expenses",
        "firestore:memory",
        "firestore:workflows",
        "firestore:audit_log",
    ],
    # Explicitly NOT: sandbox_employees, sandbox_invoices, sandbox_vendors, sandbox_incidents
    "allowedCollections": [
        "sandbox_expenses",
        "memory",
        "workflows",
        "audit_log",
    ],
    "riskLevel": "medium",
    "updatedAt": datetime.now(timezone.utc),
}

ref = db.collection("agent_registry").document("expense-approval")
ref.update(updated)

# Read back to confirm
doc = ref.get().to_dict()
print("=== agent_registry/expense-approval after update ===")
for k, v in sorted(doc.items()):
    print(f"  {k}: {v}")
print("\n[+] Registry update confirmed.")
