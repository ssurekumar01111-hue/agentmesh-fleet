"""
Verification script for Phase 25 Followup:
Proves daily spend accumulation across multiple transactions in the same day against live Gateway.

Sequence:
1. Manifest configured with maxTransactionAmount=$20,000, dailySpendLimit=$25,000.
2. Transaction 1: Submit $15,000 expense -> ALLOWED (Audit Log 1).
3. Transaction 2: Submit $12,000 expense immediately -> DENIED with 'Daily spend limit exceeded.' (15,000 + 12,000 = 27,000 > 25,000).
4. Verify on-the-fly calculation counts 'allowed' and 'waiting_approval', but ignores 'denied'.
5. Transaction 3: Submit $8,000 under approval threshold -> WAITING_APPROVAL (Audit Log 3).
6. Verify dailySpendUsed accumulates to $23,000 ($15,000 + $8,000).
7. Transaction 4: Submit $3,000 expense -> DENIED ('Daily spend limit exceeded.' 23,000 + 3,000 = 26,000 > 25,000).
"""

import os
import sys
import time
import subprocess
import requests
from google.cloud import firestore

PROJECT_ID = os.getenv("GCP_PROJECT_ID", "agentmesh-fleet-2026")
GATEWAY_URL = os.getenv("GATEWAY_URL", "https://agentmesh-gateway-138003672216.asia-south1.run.app")
AGENT_ID = "expense-approval"
SA_EMAIL = f"agentmesh-{AGENT_ID}@{PROJECT_ID}.iam.gserviceaccount.com"

db = firestore.Client(project=PROJECT_ID)

def get_auth_headers(sa_email: str) -> dict:
    headers = {
        "Content-Type": "application/json",
        "x-emulated-sa": sa_email
    }
    token = os.getenv("TOKEN")
    if not token:
        try:
            cmd = r'& "C:\Program Files (x86)\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd" auth print-identity-token'
            res = subprocess.run(["powershell", "-Command", cmd], capture_output=True, text=True, timeout=10)
            token = res.stdout.strip()
        except Exception as e:
            print(f"Error obtaining token: {e}")
            token = None
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers

def clean_agent_audit_logs():
    docs = db.collection("audit_log").where("agentId", "==", AGENT_ID).stream()
    count = 0
    for doc in docs:
        doc.reference.delete()
        count += 1
    print(f"[*] Cleaned {count} previous audit_log entries for {AGENT_ID}.")

def set_registry_spending_policy(max_tx: float, daily_limit: float, approval_threshold: float):
    ref = db.collection("agent_registry").document(AGENT_ID)
    ref.update({
        "maxTransactionAmount": max_tx,
        "dailySpendLimit": daily_limit,
        "approvalThreshold": approval_threshold,
        "spendingPolicy": {
            "maxTransactionAmount": max_tx,
            "dailySpendLimit": daily_limit,
            "approvalThreshold": approval_threshold,
            "currency": "USD"
        }
    })
    print(f"[*] Updated registry spending policy: maxTx=${max_tx:,.2f}, dailyLimit=${daily_limit:,.2f}, approvalThreshold=${approval_threshold:,.2f}")

def run_accumulation_verification():
    print("=" * 75)
    print("PHASE 25 FOLLOWUP: MULTI-TRANSACTION DAILY SPEND ACCUMULATION VERIFICATION")
    print("=" * 75)

    headers = get_auth_headers(SA_EMAIL)
    clean_agent_audit_logs()

    # Step 0: Set spending policy: maxTx=$20k, daily=$25k, approval=$20k (to test ALLOWED first)
    set_registry_spending_policy(max_tx=20000.0, daily_limit=25000.0, approval_threshold=20000.0)

    # -------------------------------------------------------------------------
    # STEP 1a: Submit Transaction 1 ($15,000) -> MUST BE ALLOWED
    # -------------------------------------------------------------------------
    print("\n" + "-" * 70)
    print("[1a] SUBMIT TRANSACTION 1: $15,000 Expense (Initial dailySpendUsed = $0.00)")
    print("-" * 70)

    tx1_payload = {
        "callerServiceAccount": SA_EMAIL,
        "targetResource": "firestore:sandbox_expenses",
        "collectionName": "sandbox_expenses",
        "action": "write",
        "payload": {
            "docId": "exp-accum-001",
            "data": {
                "amount": 15000.00,
                "vendorName": "Global Cloud Infrastructure",
                "category": "Software Infrastructure",
                "status": "approved",
                "notes": "Q3 Cloud Capacity Reservation ($15,000.00)"
            }
        }
    }

    r1 = requests.post(f"{GATEWAY_URL}/v1/execute", json=tx1_payload, headers=headers, timeout=30)
    print(f"[*] Gateway HTTP Status: {r1.status_code}")
    print(f"[*] Response Body: {r1.text}")

    assert r1.status_code == 200, f"Expected 200, got {r1.status_code}"
    d1 = r1.json()
    assert d1.get("policyDecision") == "allowed", f"Expected 'allowed', got {d1.get('policyDecision')}"
    audit_id_1 = d1.get("auditLogId")
    assert audit_id_1 is not None, "Missing auditLogId in response"

    print(f"[+] PASS 1a: Transaction 1 ($15,000.00) successfully ALLOWED!")
    print(f"    - Policy Decision: {d1.get('policyDecision')}")
    print(f"    - Audit Log ID:    {audit_id_1}")

    # -------------------------------------------------------------------------
    # STEP 1b & 1c: Submit Transaction 2 ($12,000) -> MUST BE DENIED (Daily limit exceeded)
    # -------------------------------------------------------------------------
    print("\n" + "-" * 70)
    print("[1b & 1c] SUBMIT TRANSACTION 2: $12,000 Expense Same Day")
    print("          Accumulation: $15,000 (prior) + $12,000 (requested) = $27,000 > $25,000 limit")
    print("-" * 70)

    tx2_payload = {
        "callerServiceAccount": SA_EMAIL,
        "targetResource": "firestore:sandbox_expenses",
        "collectionName": "sandbox_expenses",
        "action": "write",
        "payload": {
            "docId": "exp-accum-002",
            "data": {
                "amount": 12000.00,
                "vendorName": "Enterprise Data Warehouse Inc",
                "category": "Database Infrastructure",
                "status": "pending_approval",
                "notes": "Data Warehouse Storage Expansion ($12,000.00)"
            }
        }
    }

    r2 = requests.post(f"{GATEWAY_URL}/v1/execute", json=tx2_payload, headers=headers, timeout=30)
    print(f"[*] Gateway HTTP Status: {r2.status_code}")
    print(f"[*] Response Body: {r2.text}")

    assert r2.status_code == 403, f"Expected 403 Forbidden, got {r2.status_code}"
    d2 = r2.json()
    assert d2.get("policyDecision") == "denied", f"Expected 'denied', got {d2.get('policyDecision')}"
    assert d2.get("policyReason") == "Daily spend limit exceeded.", f"Expected 'Daily spend limit exceeded.', got {d2.get('policyReason')}"
    audit_id_2 = d2.get("auditLogId")

    spending_details_2 = d2.get("spendingDetails", {})
    daily_used_2 = spending_details_2.get("dailySpendUsed")
    requested_amt_2 = spending_details_2.get("requestedAmount")
    daily_limit_2 = spending_details_2.get("dailySpendLimit")

    assert daily_used_2 == 15000.0, f"Expected dailySpendUsed=15000.0, got {daily_used_2}"
    assert requested_amt_2 == 12000.0, f"Expected requestedAmount=12000.0, got {requested_amt_2}"
    assert daily_limit_2 == 25000.0, f"Expected dailySpendLimit=25000.0, got {daily_limit_2}"

    print(f"[+] PASS 1b/1c: Transaction 2 ($12,000.00) genuinely DENIED with 'Daily spend limit exceeded.'!")
    print(f"    - Policy Decision:      {d2.get('policyDecision')}")
    print(f"    - Policy Reason:        {d2.get('policyReason')}")
    print(f"    - Prior Daily Spend:    ${daily_used_2:,.2f}")
    print(f"    - Requested Amount:     ${requested_amt_2:,.2f}")
    print(f"    - Total If Allowed:     ${(daily_used_2 + requested_amt_2):,.2f} > Limit ${daily_limit_2:,.2f}")
    print(f"    - Denied Audit Log ID:  {audit_id_2}")

    # -------------------------------------------------------------------------
    # STEP 2: Verify Denied transaction did NOT increment dailySpendUsed,
    #         and verify WAITING_APPROVAL transactions DO increment dailySpendUsed.
    # -------------------------------------------------------------------------
    print("\n" + "-" * 70)
    print("[2a] VERIFY 'DENIED' DECISION DID NOT INCREMENT dailySpendUsed")
    print("-" * 70)

    # Set approvalThreshold to $5k so operations between $5k and $10k go to waiting_approval
    set_registry_spending_policy(max_tx=20000.0, daily_limit=25000.0, approval_threshold=5000.0)

    # Transaction 3: $8,000 expense (15,000 + 8,000 = 23,000 <= 25,000 -> WAITING_APPROVAL)
    print("\n" + "-" * 70)
    print("[2b] SUBMIT TRANSACTION 3: $8,000 Expense (> approvalThreshold $5,000)")
    print("     Cumulative: $15,000 (Tx 1) + $8,000 (Tx 3) = $23,000 <= $25,000 limit -> WAITING_APPROVAL")
    print("-" * 70)

    tx3_payload = {
        "callerServiceAccount": SA_EMAIL,
        "targetResource": "firestore:sandbox_expenses",
        "collectionName": "sandbox_expenses",
        "action": "write",
        "payload": {
            "docId": "exp-accum-003",
            "data": {
                "amount": 8000.00,
                "vendorName": "Enterprise Analytics Suite",
                "category": "Analytics",
                "status": "pending_approval",
                "notes": "Annual Analytics Platform License ($8,000.00)"
            }
        }
    }

    r3 = requests.post(f"{GATEWAY_URL}/v1/execute", json=tx3_payload, headers=headers, timeout=30)
    print(f"[*] Gateway HTTP Status: {r3.status_code}")
    print(f"[*] Response Body: {r3.text}")

    assert r3.status_code == 200, f"Expected 200, got {r3.status_code}"
    d3 = r3.json()
    assert d3.get("policyDecision") == "waiting_approval", f"Expected 'waiting_approval', got {d3.get('policyDecision')}"
    audit_id_3 = d3.get("auditLogId")

    print(f"[+] PASS 2b: Transaction 3 ($8,000.00) routed to 'waiting_approval'!")
    print(f"    - Policy Decision: {d3.get('policyDecision')}")
    print(f"    - Audit Log ID:    {audit_id_3}")

    # Transaction 4: $3,000 expense
    # If waiting_approval is counted: 15,000 + 8,000 + 3,000 = 26,000 > 25,000 -> DENIED
    print("\n" + "-" * 70)
    print("[2c] SUBMIT TRANSACTION 4: $3,000 Expense")
    print("     Cumulative: $15,000 (Tx 1) + $8,000 (Tx 3 waiting) + $3,000 = $26,000 > $25,000 limit -> DENIED")
    print("-" * 70)

    tx4_payload = {
        "callerServiceAccount": SA_EMAIL,
        "targetResource": "firestore:sandbox_expenses",
        "collectionName": "sandbox_expenses",
        "action": "write",
        "payload": {
            "docId": "exp-accum-004",
            "data": {
                "amount": 3000.00,
                "vendorName": "Team Collaboration Tools",
                "category": "Productivity",
                "status": "pending_approval",
                "notes": "Team workspace licenses ($3,000.00)"
            }
        }
    }

    r4 = requests.post(f"{GATEWAY_URL}/v1/execute", json=tx4_payload, headers=headers, timeout=30)
    print(f"[*] Gateway HTTP Status: {r4.status_code}")
    print(f"[*] Response Body: {r4.text}")

    assert r4.status_code == 403, f"Expected 403 Forbidden, got {r4.status_code}"
    d4 = r4.json()
    assert d4.get("policyDecision") == "denied", f"Expected 'denied', got {d4.get('policyDecision')}"
    assert d4.get("policyReason") == "Daily spend limit exceeded.", f"Expected 'Daily spend limit exceeded.', got {d4.get('policyReason')}"
    audit_id_4 = d4.get("auditLogId")

    spending_details_4 = d4.get("spendingDetails", {})
    daily_used_4 = spending_details_4.get("dailySpendUsed")
    assert daily_used_4 == 23000.0, f"Expected dailySpendUsed=23000.0 ($15k allowed + $8k waiting), got {daily_used_4}"

    print(f"[+] PASS 2c: Transaction 4 ($3,000.00) DENIED! Confirms 'waiting_approval' ($8k) is included in daily total (${daily_used_4:,.2f})!")
    print(f"    - Policy Decision:      {d4.get('policyDecision')}")
    print(f"    - Policy Reason:        {d4.get('policyReason')}")
    print(f"    - Prior Daily Spend:    ${daily_used_4:,.2f} ($15,000 allowed + $8,000 waiting_approval)")
    print(f"    - Requested Amount:     $3,000.00")
    print(f"    - Total If Allowed:     ${(daily_used_4 + 3000.0):,.2f} > Limit $25,000.00")
    print(f"    - Denied Audit Log ID:  {audit_id_4}")

    # -------------------------------------------------------------------------
    # RESTORE standard Phase 25 defaults
    # -------------------------------------------------------------------------
    print("\n" + "-" * 70)
    print("[3] RESTORING DEFAULT REGISTRY SPENDING POLICY (maxTx=$10k, daily=$25k, threshold=$5k)")
    print("-" * 70)
    set_registry_spending_policy(max_tx=10000.0, daily_limit=25000.0, approval_threshold=5000.0)

    print("\n" + "=" * 75)
    print("MULTI-TRANSACTION DAILY ACCUMULATION EVIDENCE SUMMARY")
    print("=" * 75)
    print(f"  1. Tx 1 ($15,000.00) ALLOWED            -> Audit ID: {audit_id_1}")
    print(f"  2. Tx 2 ($12,000.00) DENIED ($27k>$25k) -> Audit ID: {audit_id_2} (Reason: 'Daily spend limit exceeded.')")
    print(f"  3. Tx 3 ($8,000.00)  WAITING_APPROVAL   -> Audit ID: {audit_id_3} (Total Spend Used: $23,000.00)")
    print(f"  4. Tx 4 ($3,000.00)  DENIED ($26k>$25k) -> Audit ID: {audit_id_4} (Reason: 'Daily spend limit exceeded.')")
    print("=" * 75)

if __name__ == "__main__":
    run_accumulation_verification()
