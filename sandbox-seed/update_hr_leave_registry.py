#!/usr/bin/env python3
"""
Update agent_registry/leave-assistant document from 'pending' to 'active'
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
    "serviceAccountEmail": f"agentmesh-hr-leave@{PROJECT_ID}.iam.gserviceaccount.com",
    "capabilities": ["leave-review", "policy-check", "pto-balance-eval"],
    "allowedTools": [
        "firestore:sandbox_leave_requests",
        "firestore:sandbox_employees",
        "firestore:memory",
        "firestore:workflows",
        "firestore:audit_log",
    ],
    # Allowed: sandbox_leave_requests, sandbox_employees (for balance/employee info lookups), memory, workflows, audit_log.
    # Explicitly NOT: sandbox_invoices, sandbox_vendors, sandbox_expenses, sandbox_incidents
    "allowedCollections": [
        "sandbox_leave_requests",
        "sandbox_employees",
        "memory",
        "workflows",
        "audit_log",
    ],
    "riskLevel": "low",
    "updatedAt": datetime.now(timezone.utc),
}

ref = db.collection("agent_registry").document("leave-assistant")
ref.update(updated)

# Read back to confirm
doc = ref.get().to_dict()
print("=== agent_registry/leave-assistant after update ===")
for k, v in sorted(doc.items()):
    print(f"  {k}: {v}")
print("\n[+] Registry update confirmed.")
