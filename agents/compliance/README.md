# Compliance Agent (`agents/compliance`)

## Overview
The **Compliance Agent** is an autonomous governance and policy evaluation agent built using the official **Google Agent Development Kit (`google-adk` v2.6+)** and Google GenAI Gemini models (`gemini-3.5-flash`) via Vertex AI.

It performs two primary responsibilities within AgentMesh:
1. **Workflow Compliance Review**: Evaluates paused invoice workflows (e.g. `wf-inv-2026-007` at `"waiting_approval"`) against enterprise governance rules, issuing a formal `ESCALATE`/`APPROVE`/`REJECT` assessment written to `memory`.
2. **Zero-Trust Denial Verification**: Demonstrates live policy enforcement where unauthorized requests to read HR employee records (`sandbox_employees`) are rejected with HTTP 403 by the Gateway pipeline.

## ADK Integration Architecture (Phase 9b)
The agent is constructed using native ADK abstractions, following the same pattern as `agents/fraud-finance`:
- **`google.adk.agents.LlmAgent`**: Defines the agent's identity, `gemini-3.5-flash` model, system instructions, and tool bindings.
- **`google.adk.tools.FunctionTool`**: Wraps all Gateway calls into native ADK tool definitions:
  - `fetch_workflow` — reads workflow doc from Firestore via Gateway
  - `fetch_memory` — reads memory/case doc from Firestore via Gateway
  - `fetch_policies` — streams **all** policy documents from Firestore via Gateway (see bug fix below)
  - `write_memory` — writes compliance findings to Firestore memory via Gateway
  - `read_hr_employees` — attempts unauthorized HR access (zero-trust test)
- **`google.adk.runners.Runner`**: Manages the multi-turn agent execution loop and tool calling runtime.
- **`google.adk.sessions.InMemorySessionService`**: Provides ADK session state management.

## Phase 9b Bug Fix: `get_policies()` — `action="query"` → `action="read"`

**Root cause**: The previous `gateway_client.py` called the Gateway with `action="query"`, which was not a handled action in the Gateway's Firestore dispatcher (`gateway/main.py`). It fell into the `else` branch returning `{"status":"forwarded","collection":"policies"}` — an empty shell with no document data. This caused the compliance agent to always reason with **zero policies**.

**Fix**: Changed to `action="read"` with an empty payload (no `docId`). The Gateway's handler at lines 383–389 routes `action="read"` with no `docId` to `db.collection(collectionName).limit(50).stream()`, which streams all documents in the collection. Policy documents are now genuinely present in the agent's reasoning context.

**Proof**: After the fix, test output shows `N policy document(s) fetched via Gateway` with real policy IDs and effects (e.g., `deny` policies for `firestore:sandbox_employees`).

## Security Architecture & Zero Bypass
All Firestore access is mediated through the **AgentMesh Gateway** (`https://agentmesh-gateway-138003672216.asia-south1.run.app`) using the dedicated identity `agentmesh-compliance@agentmesh-fleet-2026.iam.gserviceaccount.com`.

## Responsibilities Summary

### Responsibility 1: Workflow Policy Review
- Reads `workflows/wf-inv-2026-007`, `memory/case-inv-2026-007`, and streams all `policies/` docs via Gateway.
- Uses Gemini 3.5 Flash reasoning engine to assess governance compliance against **real** policy documents.
- Writes structured memory document to `memory/compliance-case-inv-2026-007`.

### Responsibility 2: Live Zero-Trust Denial
- Attempts read on `sandbox_employees/emp-001` using `agentmesh-compliance` service account.
- Blocked at Gateway Stage 3 (allowedCollections check).
- Returns HTTP 403 `denied` status and logs immutable entry to `audit_log`.

## OpenTelemetry Observability
The agent uses the existing `telemetry.py` (`init_tracer`) for FastAPI + requests instrumentation.
ADK uses its own internal tracer on a separate namespace — no conflict or duplication with the agent's OTel tracer.

## Directory Structure
- `agent.py`: Native ADK agent using `LlmAgent`, `FunctionTool`, `Runner`, `InMemorySessionService`; includes `get_policies` bug fix.
- `reasoning.py`: Vertex AI Gemini (`gemini-3.5-flash`) policy reasoning engine.
- `gateway_client.py`: Gateway HTTP client; `get_policies()` now uses `action="read"` (Phase 9b fix).
- `main.py`: FastAPI server serving `/health`, `/review`, and `/test-denied`.
- `test_agent.py`: Integration test suite verifying both responsibilities.
- `Dockerfile` & `requirements.txt`: Cloud Run deployment setup (`google-adk>=2.6.0`).

## Deployment & Execution
- **Service Account**: `agentmesh-compliance@agentmesh-fleet-2026.iam.gserviceaccount.com`
- **Cloud Run Service**: `agentmesh-compliance`
- **Region**: `asia-south1`
- **Live Service URL**: `https://agentmesh-compliance-138003672216.asia-south1.run.app`
