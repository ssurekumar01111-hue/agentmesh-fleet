# Compliance Agent (`agents/compliance`)

## Overview
The **Compliance Agent** is an autonomous governance and policy evaluation agent built using the Google Agent Development Kit (ADK) and Gemini reasoning (`gemini-3.5-flash`) via Vertex AI.

It performs two primary responsibilities within AgentMesh:
1. **Workflow Compliance Review**: Evaluates paused invoice workflows (e.g. `wf-inv-2026-007` at `"waiting_approval"`) against enterprise governance rules (e.g. $50,000 dual sign-off threshold for vendors onboarded < 6 months), issuing a formal `ESCALATE`/`APPROVE`/`REJECT` assessment written directly to `memory`.
2. **Zero-Trust Denial Verification**: Demonstrates live policy enforcement where unauthorized requests to read HR employee records (`sandbox_employees`) are rejected with HTTP 403 by the Gateway pipeline.

## Security Architecture & Zero Bypass
All Firestore access is mediated through the **AgentMesh Gateway** (`https://agentmesh-gateway-138003672216.asia-south1.run.app`) using the dedicated identity `agentmesh-compliance@agentmesh-fleet-2026.iam.gserviceaccount.com`.

## Responsibilities Summary

### Responsibility 1: Workflow Policy Review
- Reads `workflows/wf-inv-2026-007`, `memory/case-inv-2026-007`, and `policies/` via Gateway.
- Uses Gemini 2.5 Flash reasoning engine to assess governance compliance.
- Writes structured memory document to `memory/compliance-case-inv-2026-007`.

### Responsibility 2: Live Zero-Trust Denial
- Attempts read on `sandbox_employees/emp-001` using `agentmesh-compliance` service account.
- Blocked at Gateway Stage 3 (Check 3a: allowedCollections check).
- Returns HTTP 403 `denied` status and logs immutable entry to `audit_log`.

## Directory Structure
- `agent.py`: Core agent logic for workflow review and zero-trust HR data test.
- `reasoning.py`: Vertex AI Gemini (`gemini-3.5-flash`) policy reasoning engine.
- `gateway_client.py`: Gateway HTTP client for Compliance Agent identity.
- `main.py`: FastAPI server serving `/health`, `/review`, and `/test-denied`.
- `test_agent.py`: Integration test suite verifying both responsibilities.
- `Dockerfile` & `requirements.txt`: Cloud Run deployment setup.

## Deployment & Execution
- **Service Account**: `agentmesh-compliance@agentmesh-fleet-2026.iam.gserviceaccount.com`
- **Cloud Run Service**: `agentmesh-compliance`
- **Region**: `asia-south1`
- **Live Service URL**: `https://agentmesh-compliance-138003672216.asia-south1.run.app`
