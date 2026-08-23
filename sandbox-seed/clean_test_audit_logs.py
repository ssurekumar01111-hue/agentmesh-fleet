#!/usr/bin/env python3
"""
Clean test audit logs for expense-approval generated during test dry-runs.
"""
from google.cloud import firestore

db = firestore.Client(project="agentmesh-fleet-2026")

docs = db.collection("audit_log").where("agentId", "==", "expense-approval").stream()
count = 0
for d in docs:
    d.reference.delete()
    count += 1

print(f"Cleaned {count} dry-run audit_log entries for expense-approval.")
