#!/usr/bin/env python3
"""
Update agent_registry/contract-review document from 'pending' to 'active'
with real service account, corrected allowedCollections, allowedTools, and riskLevel.
"""
import os
from datetime import datetime, timezone
from google.cloud import firestore

PROJECT_ID = "agentmesh-fleet-2026"
db = firestore.Client(project=PROJECT_ID, database="(default)")

updated = {
    "status": "active",
    "version": "1.0.0",
    "serviceAccountEmail": f"agentmesh-legal-contract@{PROJECT_ID}.iam.gserviceaccount.com",
    "capabilities": ["contract-parse", "clause-validation", "legal-policy-review"],
    "allowedTools": [
        "firestore:sandbox_contracts",
        "firestore:memory",
        "firestore:workflows",
        "firestore:audit_log",
    ],
    # Allowed: sandbox_contracts, memory, workflows, audit_log
    # Explicitly NOT: sandbox_invoices, sandbox_vendors, sandbox_expenses, sandbox_leave_requests, sandbox_incidents
    "allowedCollections": [
        "sandbox_contracts",
        "memory",
        "workflows",
        "audit_log",
    ],
    "riskLevel": "medium",
    "updatedAt": datetime.now(timezone.utc),
}

ref = db.collection("agent_registry").document("contract-review")
ref.update(updated)

# Read back to confirm
doc = ref.get().to_dict()
print("=== agent_registry/contract-review after update ===")
for k, v in sorted(doc.items()):
    print(f"  {k}: {v}")
print("\n[+] Registry update confirmed.")
