# HR Leave Assistant Agent (`agents/hr-leave`)

## Overview

The **HR Leave Assistant Agent** is an autonomous HR department reasoning agent built with Google Agent Development Kit (ADK) and Google GenAI Gemini (`gemini-3.5-flash`) via Vertex AI.

It evaluates employee leave and PTO requests from Northbridge Retail Co. against company HR leave policies, independently computing whether each request should be **APPROVED**, **FLAGGED** for HR review, or **ESCALATED** for manager approval.

## ADK Integration Architecture (Phase 9b)
The agent is rebuilt using native ADK abstractions, following the same pattern as `agents/fraud-finance`:
- **`google.adk.agents.LlmAgent`**: Agent identity, `gemini-3.5-flash` model, system instructions, and tool bindings.
- **`google.adk.tools.FunctionTool`**: Wraps all Gateway calls:
  - `fetch_leave_request` — reads leave request doc from sandbox_leave_requests via Gateway
  - `fetch_employee` — reads employee profile from sandbox_employees via Gateway
  - `write_memory` — writes findings to Firestore memory via Gateway
  - `update_workflow` — updates workflow state in Firestore via Gateway
- **`google.adk.runners.Runner`**: Multi-turn agent execution loop and tool calling runtime.
- **`google.adk.sessions.InMemorySessionService`**: ADK session state (no conflict with existing OTel telemetry.py).

## OpenTelemetry Observability
The agent's `telemetry.py` (`init_tracer`) instruments FastAPI and outbound requests. ADK's internal tracer runs on a separate namespace — no conflict or span duplication. Both export independently to GCP Cloud Trace.

---

## Security Architecture & Zero Bypass

This agent **NEVER** accesses Firestore directly. All reads, writes, memory logging, and workflow updates route strictly through the **AgentMesh Gateway** (`https://agentmesh-gateway-138003672216.asia-south1.run.app`) using its dedicated Cloud Run service identity:

```
agentmesh-hr-leave@agentmesh-fleet-2026.iam.gserviceaccount.com
```

Two-layer least-privilege enforcement:

1. **Firestore Security Rules** — `shared/firestore.rules` explicitly allows only `agentmesh-hr-leave` and `agentmesh-gateway` to read/write `sandbox_leave_requests`. All other agents (including `fraud-finance`, `expense-approval`, `it-security`, and `compliance`) are denied at the infra layer.
2. **Gateway policy check** — reads `agent_registry.leave-assistant.allowedCollections` and rejects any call to a collection outside `["sandbox_leave_requests", "sandbox_employees", "memory", "workflows", "audit_log"]`.

---

## HR Leave Policy Assessment Logic

The agent reasons against **Northbridge Retail Co. HR leave policy** using computable signals derived from raw Firestore fields:

| Signal | Field(s) Used | Policy Rule |
|--------|--------------|-------------|
| PTO Balance Deficit | `daysRequested`, `remainingBalance` | `daysRequested` must not exceed `remainingBalance`. |
| Advance Notice Window | `submittedDate`, `startDate`, `daysRequested` | Leaves > 10 days require at least **30 days** notice; 1–5 days leave requires **7 days** notice. |

**Assessment thresholds:**
- `APPROVED` — No policy violations found (riskScore < 0.40)
- `FLAGGED` — Minor notice deficit or single non-critical issue (riskScore 0.40–0.79)
- `ESCALATED` — Balance exceeded (daysRequested > remainingBalance) OR major notice violation → workflow escalated to `waiting_approval`

**CRITICAL:** The reasoning engine **never reads** pre-set `policyViolation` or `anomalyReason` fields from Firestore. All assessment is computed from raw numeric and date values by Gemini.

---

## Planted Policy-Violating Leave Request: `lvr-2026-006`

| Field | Value | Policy Rule | Violation |
|-------|-------|-------------|-----------|
| `employeeId` | `emp-002` (Marcus Chen) | HR employee profile | Senior AP Lead |
| `daysRequested` vs `remainingBalance` | **15 days requested vs 4 days balance** | `daysRequested` ≤ `remainingBalance` | **11-day deficit** (275% over balance) |
| `submittedDate` → `startDate` | **25 days notice** (Aug 7 → Sep 1) | ≥ 30 days notice for >10 day leave | 5-day notice deficit |

Two independent signals computed from raw fields.

---

## Directory Structure

| File | Purpose |
|------|---------|
| `agent.py` | Core ADK agent: fetches request & employee info, calls reasoning engine, writes Memory, escalates workflow |
| `reasoning.py` | Vertex AI Gemini `gemini-3.5-flash` reasoning engine with OpenTelemetry tracing |
| `gateway_client.py` | Gateway client: all Firestore ops routed via AgentMesh Gateway |
| `main.py` | FastAPI HTTP endpoints: `POST /review`, `GET /health` |
| `telemetry.py` | OpenTelemetry → Cloud Trace initialiser |
| `test_agent.py` | Integration test: violating request (ESCALATED) + normal request (APPROVED) |
| `Dockerfile` | Cloud Run deployment container |
| `requirements.txt` | Python dependencies |

---

## Deployment Details

| Property | Value |
|----------|-------|
| Cloud Run Service | `agentmesh-hr-leave` |
| Region | `asia-south1` |
| Service Account | `agentmesh-hr-leave@agentmesh-fleet-2026.iam.gserviceaccount.com` |
| Live URL | `https://agentmesh-hr-leave-138003672216.asia-south1.run.app` |
