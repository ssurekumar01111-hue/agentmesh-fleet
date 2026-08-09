#!/usr/bin/env python3
"""
Integration test for the Expense Approval Agent.

Tests two expense reports against the live deployed Cloud Run service:
  1. exp-2026-006 — the planted policy-violating expense (should be FLAGGED or ESCALATED)
  2. exp-2026-001 — a normal, compliant expense (should be APPROVED)

Usage:
    python test_agent.py [--service-url URL]

Defaults to the live Cloud Run URL. Set EXPENSE_APPROVAL_URL env var to override.
"""

import argparse
import json
import os
import sys

import requests

DEFAULT_URL = os.getenv(
    "EXPENSE_APPROVAL_URL",
    "https://agentmesh-expense-approval-138003672216.asia-south1.run.app",
)

VIOLATING_EXPENSE_ID = "exp-2026-006"
NORMAL_EXPENSE_ID = "exp-2026-001"


def get_auth_headers(url: str) -> dict:
    headers = {"Content-Type": "application/json"}
    token = os.getenv("TOKEN")
    if not token:
        try:
            import subprocess
            cmd = r'& "C:\Program Files (x86)\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd" auth print-identity-token'
            res = subprocess.run(["powershell", "-Command", cmd], capture_output=True, text=True, timeout=10)
            token = res.stdout.strip()
        except Exception:
            token = None
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def review_expense(base_url: str, expense_id: str) -> dict:
    url = f"{base_url.rstrip('/')}/review"
    payload = {"expenseId": expense_id}
    headers = get_auth_headers(base_url)
    print(f"\n[*] POST {url}")
    print(f"    Payload: {json.dumps(payload)}")
    res = requests.post(url, json=payload, headers=headers, timeout=60)
    print(f"    HTTP Status: {res.status_code}")
    if res.status_code != 200:
        print(f"    ERROR body: {res.text[:500]}")
        return {}
    data = res.json()
    print(f"    Response:\n{json.dumps(data, indent=2)}")
    return data



def assert_field(result: dict, field: str, expected_values, label: str):
    actual = result.get(field)
    if isinstance(expected_values, (list, tuple, set)):
        ok = actual in expected_values
    else:
        ok = actual == expected_values
    status = "PASS" if ok else "FAIL"
    print(f"  [{status}] {label}: got '{actual}' (expected {expected_values})")
    return ok


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--service-url", default=DEFAULT_URL, help="Base URL of expense-approval service")
    args = parser.parse_args()
    base_url = args.service_url

    print("=" * 70)
    print("AgentMesh Expense Approval Agent — Integration Test")
    print(f"Service URL: {base_url}")
    print("=" * 70)

    # ------------------------------------------------------------------
    # Test 1: Planted policy-violating expense (exp-2026-006)
    # Expected: FLAGGED or ESCALATED, workflowStatus = waiting_approval
    # ------------------------------------------------------------------
    print("\n\n--- TEST 1: Planted policy-violating expense (exp-2026-006) ---")
    result_violating = review_expense(base_url, VIOLATING_EXPENSE_ID)

    print("\nAssertions:")
    p1 = assert_field(result_violating, "expenseId", VIOLATING_EXPENSE_ID, "expenseId")
    p2 = assert_field(
        result_violating,
        "assessmentStatus",
        {"FLAGGED", "ESCALATED"},
        "assessmentStatus is FLAGGED or ESCALATED",
    )
    p3 = assert_field(
        result_violating,
        "workflowStatus",
        "waiting_approval",
        "workflowStatus is waiting_approval",
    )
    p4 = assert_field(result_violating, "riskScore", None, "riskScore exists")
    p4 = result_violating.get("riskScore", 0) >= 0.60
    print(f"  [{'PASS' if p4 else 'FAIL'}] riskScore >= 0.60: got {result_violating.get('riskScore')}")

    if result_violating.get("findings"):
        print(f"\n  Gemini findings for {VIOLATING_EXPENSE_ID}:")
        for i, f in enumerate(result_violating["findings"], 1):
            print(f"    {i}. {f}")

    # ------------------------------------------------------------------
    # Test 2: Normal compliant expense (exp-2026-001)
    # Expected: APPROVED, workflowStatus = completed
    # ------------------------------------------------------------------
    print("\n\n--- TEST 2: Normal compliant expense (exp-2026-001) ---")
    result_normal = review_expense(base_url, NORMAL_EXPENSE_ID)

    print("\nAssertions:")
    n1 = assert_field(result_normal, "expenseId", NORMAL_EXPENSE_ID, "expenseId")
    n2 = assert_field(
        result_normal,
        "assessmentStatus",
        "APPROVED",
        "assessmentStatus is APPROVED",
    )
    n3 = assert_field(
        result_normal,
        "workflowStatus",
        "completed",
        "workflowStatus is completed",
    )
    n4 = result_normal.get("riskScore", 1.0) < 0.40
    print(f"  [{'PASS' if n4 else 'FAIL'}] riskScore < 0.40: got {result_normal.get('riskScore')}")

    if result_normal.get("findings"):
        print(f"\n  Gemini findings for {NORMAL_EXPENSE_ID}:")
        for i, f in enumerate(result_normal["findings"], 1):
            print(f"    {i}. {f}")

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    print("\n\n" + "=" * 70)
    all_pass = all([p1, p2, p3, p4, n1, n2, n3, n4])
    print(f"OVERALL: {'ALL TESTS PASSED [PASS]' if all_pass else 'SOME TESTS FAILED [FAIL]'}")
    print("=" * 70)
    sys.exit(0 if all_pass else 1)


if __name__ == "__main__":
    main()
