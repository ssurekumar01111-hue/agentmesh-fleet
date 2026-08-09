# Fraud & Finance Agent (`agents/fraud-finance`)

## Overview
The **Fraud/Finance Agent** is an autonomous enterprise reasoning agent built using the official **Google Agent Development Kit (`google-adk` v2.6+)** and Google GenAI Gemini models (`gemini-3.5-flash`) via Vertex AI.

It evaluates incoming vendor invoices for financial fraud, payment anomalies, and compliance risk.

## ADK Integration Architecture
The agent is constructed using native ADK abstractions:
- **`google.adk.agents.LlmAgent`**: Defines the agent's identity, `gemini-3.5-flash` model reference, system instructions, and tool bindings.
- **`google.adk.tools.FunctionTool`**: Wraps Gateway calls (`fetch_invoice`, `fetch_vendor_history`, `write_memory`, `update_workflow`) into native ADK tool definitions.
- **`google.adk.runners.Runner`**: Manages the multi-turn agent execution loop and tool calling runtime.
- **`google.adk.sessions.InMemorySessionService`**: Provides ADK session state management.

## Security Architecture & Zero Bypass
This agent **NEVER** accesses Firestore directly. All reads, writes, memory logging, and workflow updates are routed strictly through the **AgentMesh Gateway** (`https://agentmesh-gateway-138003672216.asia-south1.run.app`) using the dedicated Cloud Run service identity `agentmesh-fraud-finance@agentmesh-fleet-2026.iam.gserviceaccount.com`.

## Anomaly Reasoning Logic
The agent computes anomaly risk **independently** by analyzing raw invoice amounts against vendor historical payment baselines (`sandbox_vendors`). It explicitly ignores pre-set flags like `is_anomalous`.

- **High-Risk Threshold**: Risk score $\ge 0.70$
- **Escalation**: Escalates high-risk cases to `workflows` collection with status `"waiting_approval"` and current step `"human_approval_gate"`.
- **Low-Risk Completion**: Standard invoices within historical ranges are logged to `memory` and marked `"completed"`.

## Directory Structure
- `agent.py`: Native ADK agent implementation using `LlmAgent`, `FunctionTool`, `Runner`, and `SessionService`.
- `reasoning.py`: Vertex AI Gemini (`gemini-3.5-flash`) reasoning engine.
- `gateway_client.py`: Client wrapper enforcing all request forwarding through AgentMesh Gateway.
- `main.py`: FastAPI HTTP endpoint serving `/investigate`, `/resume`, and `/health`.
- `test_agent.py`: Automated integration test verifying anomalous (`inv-2026-007`) vs normal (`inv-2026-001`) invoices.
- `Dockerfile` & `requirements.txt`: Cloud Run deployment artifacts including `google-adk>=2.6.0`.


## Deployment Details
- **Cloud Run Service**: `agentmesh-fraud-finance`
- **Region**: `asia-south1`
- **Service Account**: `agentmesh-fraud-finance@agentmesh-fleet-2026.iam.gserviceaccount.com`
- **Live URL**: `https://agentmesh-fraud-finance-138003672216.asia-south1.run.app`
