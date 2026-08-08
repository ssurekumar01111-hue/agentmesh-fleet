#!/usr/bin/env python3
"""Verify planted expense exp-2026-006 in Firestore."""
from google.cloud import firestore
from datetime import date

db = firestore.Client(project="agentmesh-fleet-2026", database="(default)")

print("=== Verifying sandbox_expenses collection ===")
docs = list(db.collection("sandbox_expenses").stream())
print(f"Total documents: {len(docs)}")
for doc in sorted(docs, key=lambda d: d.id):
    data = doc.to_dict()
    print(f"  {doc.id}: ${data.get('amount'):,.2f} {data.get('category')} "
          f"emp={data.get('employeeId')} receipt={data.get('receiptAttached')} "
          f"expDate={data.get('expenseDate')} submitted={data.get('submittedDate')}")

print("\n=== Planted violation (exp-2026-006) full document ===")
ref = db.collection("sandbox_expenses").document("exp-2026-006").get()
data = ref.to_dict()
for k, v in sorted(data.items()):
    print(f"  {k}: {v}")

# Compute the 3 independent signals
amount = data["amount"]
hard_cap = 150  # meals
lag = (date.fromisoformat(data["submittedDate"]) - date.fromisoformat(data["expenseDate"])).days
print(f"\n=== Agent-computable signals ===")
print(f"  1. Amount overage: ${amount:,.2f} vs meals cap ${hard_cap} → {amount/hard_cap:.1f}x")
print(f"  2. Submission lag: {lag} days vs 30-day window → {lag-30} days late")
print(f"  3. Receipt attached: {data['receiptAttached']}")
