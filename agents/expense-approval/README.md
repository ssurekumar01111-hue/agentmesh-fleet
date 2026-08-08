# Expense Approval Agent (`agents/expense-approval`)

## Overview

The **Expense Approval Agent** is an autonomous Finance department reasoning agent built with Google Agent Development Kit (ADK) and Google GenAI Gemini (`gemini-3.5-flash`) via Vertex AI.

It evaluates employee expense reports from Northbridge Retail Co. against the company's internal expense policy, independently computing whether each report should be **APPROVED**, **FLAGGED** for review, or **ESCALATED** for VP-level approval.

---

## Security Architecture & Zero Bypass

This agent **NEVER** accesses Firestore directly. All reads, writes, memory logging, and workflow updates are routed strictly through the **AgentMesh Gateway** (`https://agentmesh-gateway-138003672216.asia-south1.run.app`) using the dedicated Cloud Run service identity:

```
agentmesh-expense-approval@agentmesh-fleet-2026.iam.gserviceaccount.com
```

Two-layer least-privilege enforcement:

1. **Firestore Security Rules** — `shared/firestore.rules` explicitly allows only `agentmesh-expense-approval` and `agentmesh-gateway` to read/write `sandbox_expenses`. All other agents (including `fraud-finance` and HR agents) are denied at the infra layer.
2. **Gateway policy check** — reads `agent_registry.expense-approval.allowedCollections` and rejects any call to a collection outside that list.

---

## Expense Policy Assessment Logic

The agent reasons against **Northbridge Retail Co. expense policy** using three independent, computable signals from raw Firestore fields:

| Signal | Field(s) Used | Policy Rule |
|--------|--------------|-------------|
| Amount vs. category cap | `amount`, `category` | Must not exceed the category hard cap; hard caps: travel $3k, meals **$150**, equipment $2k, accommodation $500/night, software $1k |
| Submission lag | `expenseDate`, `submittedDate` | Must submit within **30 days** of the expense date |
| Receipt presence | `receiptAttached` | Must be `true` |

**Assessment thresholds:**
- `APPROVED` — No policy violations found (riskScore < 0.40)
- `FLAGGED` — 1–2 policy violations detected (riskScore 0.40–0.79)
- `ESCALATED` — Hard cap exceeded OR 3+ violations (riskScore ≥ 0.80) → workflow escalated to `waiting_approval`

**CRITICAL:** The reasoning engine **never reads** pre-set `policyViolation`, `anomalyReason`, or `isAnomalous` fields from Firestore. All assessment is computed from raw numeric and date values by Gemini.

---

## Planted Policy-Violating Expense: `exp-2026-006`

| Field | Value | Policy | Violation |
|-------|-------|--------|-----------|
| `amount` | **$1,240.00** | Meals hard cap: **$150** | 8× overage (+$1,090) |
| `submittedDate` – `expenseDate` | **84 days** (May 15 → Aug 7) | ≤ 30 days | 54 days late |
| `receiptAttached` | **false** | Must be true | Missing receipt |

Three independent signals the agent must compute from raw fields — same documentation pattern as `inv-2026-007` in the fraud-finance agent.

---

## Directory Structure

| File | Purpose |
|------|---------|
| `agent.py` | Core ADK agent: fetches expense, calls reasoning engine, writes Memory, escalates workflow |
| `reasoning.py` | Vertex AI Gemini `gemini-3.5-flash` reasoning engine with deterministic fallback |
| `gateway_client.py` | Gateway client: all Firestore ops routed via AgentMesh Gateway |
| `main.py` | FastAPI HTTP endpoints: `POST /review`, `GET /health` |
| `telemetry.py` | OpenTelemetry → Cloud Trace initialiser (same pattern as fraud-finance) |
| `test_agent.py` | Integration test: violating expense (ESCALATED) + normal expense (APPROVED) |
| `Dockerfile` | Cloud Run deployment container |
| `requirements.txt` | Python dependencies |

---

## API Endpoints

### `POST /review`

Review an expense report and compute policy assessment.

```json
// Request
{ "expenseId": "exp-2026-006" }

// Response
{
  "expenseId": "exp-2026-006",
  "caseId": "case-exp-2026-006",
  "workflowId": "wf-exp-2026-006",
  "riskScore": 0.97,
  "assessmentStatus": "ESCALATED",
  "workflowStatus": "waiting_approval",
  "summary": "...",
  "findings": ["...", "...", "..."]
}
```

### `GET /health`

```json
{ "status": "ok", "service": "agentmesh-expense-approval" }
```

---

## Deployment Details

| Property | Value |
|----------|-------|
| Cloud Run Service | `agentmesh-expense-approval` |
| Region | `asia-south1` |
| Service Account | `agentmesh-expense-approval@agentmesh-fleet-2026.iam.gserviceaccount.com` |
| Live URL | `https://agentmesh-expense-approval-138003672216.asia-south1.run.app` |

---

## Running the Test

```bash
# Against the live Cloud Run service
python test_agent.py

# Against a local instance
EXPENSE_APPROVAL_URL=http://localhost:8080 python test_agent.py
```
