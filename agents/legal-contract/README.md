# Legal Contract & NDA Reviewer Agent (`agents/legal-contract`)

## Overview

The **Legal Contract & NDA Reviewer Agent** is an autonomous Legal department reasoning agent built with Google Agent Development Kit (ADK) and Google GenAI Gemini (`gemini-3.5-flash`) via Vertex AI.

It evaluates vendor agreements, NDAs, MSAs, and SLAs from Northbridge Retail Co. against company legal contracting policies, independently computing whether each contract should be **APPROVED**, **FLAGGED** for legal review, or **ESCALATED** for executive legal sign-off.

---

## Security Architecture & Zero Bypass

This agent **NEVER** accesses Firestore directly. All reads, writes, memory logging, and workflow updates route strictly through the **AgentMesh Gateway** (`https://agentmesh-gateway-138003672216.asia-south1.run.app`) using its dedicated Cloud Run service identity:

```
agentmesh-legal-contract@agentmesh-fleet-2026.iam.gserviceaccount.com
```

Two-layer least-privilege enforcement:

1. **Firestore Security Rules** — `shared/firestore.rules` explicitly allows only `agentmesh-legal-contract` and `agentmesh-gateway` to read/write `sandbox_contracts`. All other agents (including `fraud-finance`, `expense-approval`, `hr-leave`, `it-security`, and `compliance`) are denied at the infra layer.
2. **Gateway policy check** — reads `agent_registry.contract-review.allowedCollections` and rejects any call to a collection outside `["sandbox_contracts", "memory", "workflows", "audit_log"]`.

---

## Legal Policy Assessment Logic

The agent reasons against **Northbridge Retail Co. Legal Contracting Guidelines** using computable signals derived from raw contract prose text and fields:

| Signal | Field(s) Used | Policy Rule |
|--------|--------------|-------------|
| Governing Jurisdiction | `governingLaw` | Governing jurisdiction MUST be **Delaware**, **New York**, or **California**. Foreign or unusual jurisdictions (e.g. Cayman Islands) are non-compliant. |
| Limitation of Liability | `liabilityCapAmount` | Unlimited liability exposure (`liabilityCapAmount` = 0) is strictly prohibited. Cap required. |
| Auto-Renewal Notice Window | `autoRenewNoticeDays`, `autoRenew` | Auto-renewing contracts must provide at least **30 days** notice to opt out. |
| One-Sided Indemnification | `clauseSummary`, `fullText` | Unilateral indemnification for counterparty gross negligence is unacceptable. |

**Assessment thresholds:**
- `APPROVED` — All legal rules satisfied (riskScore < 0.40)
- `FLAGGED` — Minor clause ambiguity or minor notice issue (riskScore 0.40–0.79)
- `ESCALATED` — Unlimited liability, non-standard jurisdiction (e.g. Cayman Islands), or severe unilateral indemnity → workflow escalated to `waiting_approval`

**CRITICAL:** The reasoning engine **never reads** pre-set `policyViolation` or `anomalyReason` fields from Firestore. All assessment is computed from raw text prose and contract fields by Gemini.

---

## Planted Policy-Violating Contract: `ctr-2026-005`

| Field | Value | Policy Rule | Violation |
|-------|-------|-------------|-----------|
| `vendorOrCounterparty` | Vortex Digital Marketing LLC | Vendor Agreement | Master Media Agreement |
| `governingLaw` | **Cayman Islands** | Delaware / NY / CA required | **Non-compliant jurisdiction** |
| `liabilityCapAmount` | **$0.0** (Unlimited) | Cap required (<= 2x fees) | **Unlimited liability exposure** |
| `autoRenewNoticeDays` | **3 days** | ≥ 30 days notice required | **27-day notice deficit** |
| `clauseSummary` | Unilateral indemnification | Mutual indemnification required | **One-sided indemnity for counterparty negligence** |

Three independent signals computed from raw prose text and fields.

---

## Directory Structure

| File | Purpose |
|------|---------|
| `agent.py` | Core ADK agent: fetches contract, calls reasoning engine, writes Memory, escalates workflow |
| `reasoning.py` | Vertex AI Gemini `gemini-3.5-flash` reasoning engine with OpenTelemetry tracing |
| `gateway_client.py` | Gateway client: all Firestore ops routed via AgentMesh Gateway |
| `main.py` | FastAPI HTTP endpoints: `POST /review`, `GET /health` |
| `telemetry.py` | OpenTelemetry → Cloud Trace initialiser |
| `test_agent.py` | Integration test: violating contract (ESCALATED) + normal contract (APPROVED) |
| `Dockerfile` | Cloud Run deployment container |
| `requirements.txt` | Python dependencies |

---

## Deployment Details

| Property | Value |
|----------|-------|
| Cloud Run Service | `agentmesh-legal-contract` |
| Region | `asia-south1` |
| Service Account | `agentmesh-legal-contract@agentmesh-fleet-2026.iam.gserviceaccount.com` |
| Live URL | `https://agentmesh-legal-contract-138003672216.asia-south1.run.app` |
