#!/usr/bin/env python3
"""
Milestone script: Update agent_registry/expense-approval with Phase 25 Gateway-enforced Spending Policy:
- maxTransactionAmount: 10000 (per-transaction cap)
- dailySpendLimit: 25000 (daily spend cap)
- approvalThreshold: 5000 (threshold requiring human approval)
- dailySpendUsed: 0 (computed on-the-fly from today's audit_log entries)
"""
import os
from datetime import datetime, timezone
from google.cloud import firestore

PROJECT_ID = os.getenv("GCP_PROJECT_ID", "agentmesh-fleet-2026")
db = firestore.Client(project=PROJECT_ID, database="(default)")

spending_policy = {
    "maxTransactionAmount": 10000.0,
    "dailySpendLimit": 25000.0,
    "approvalThreshold": 5000.0,
    "dailySpendUsed": 0.0,
    "resetMechanism": "computed_on_the_fly_from_audit_log",
    "currency": "USD"
}

updated = {
    "status": "active",
    "version": "1.0.0",
    "serviceAccountEmail": f"agentmesh-expense-approval@{PROJECT_ID}.iam.gserviceaccount.com",
    "capabilities": ["expense-review", "policy-check", "lag-audit", "spending-policy-evaluation"],
    "allowedTools": [
        "firestore:sandbox_expenses",
        "firestore:workflows",
        "firestore:memory",
        "firestore:audit_log",
    ],
    "allowedCollections": [
        "sandbox_expenses",
        "workflows",
        "memory",
        "audit_log",
    ],
    "riskLevel": "low",
    "maxTransactionAmount": 10000.0,
    "dailySpendLimit": 25000.0,
    "approvalThreshold": 5000.0,
    "dailySpendUsed": 0.0,
    "spendingPolicy": spending_policy,
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
