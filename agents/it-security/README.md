# IT & Security Monitoring Agent (`agents/it-security`)

## Overview
The **IT/Security Agent** is an autonomous security monitoring agent built using the official **Google Agent Development Kit (`google-adk` v2.6+)** and Google GenAI Gemini models (`gemini-3.5-flash`) via Vertex AI.

It scans repository commit histories and open issues for security threats, exposed secrets (e.g. AWS access keys, API tokens), and unauthorized configuration changes.

## ADK Integration Architecture (Phase 9b)
The agent is constructed using native ADK abstractions, following the same pattern as `agents/fraud-finance`:
- **`google.adk.agents.LlmAgent`**: Defines the agent's identity, `gemini-3.5-flash` model reference, system instructions, and tool bindings.
- **`google.adk.tools.FunctionTool`**: Wraps all Gateway calls into native ADK tool definitions:
  - `list_issues` — lists GitHub repo issues via Gateway
  - `list_commits` — lists GitHub repo commits via Gateway
  - `create_issue` — creates GitHub issues via Gateway
  - `write_memory` — writes findings to Firestore memory via Gateway
  - `update_incident` — updates incident records via Gateway
  - `update_workflow` — updates workflow state via Gateway
- **`google.adk.runners.Runner`**: Manages the multi-turn agent execution loop and tool calling runtime.
- **`google.adk.sessions.InMemorySessionService`**: Provides ADK session state management (no conflict with existing telemetry).

## Security Architecture & Zero Bypass
This agent **NEVER** communicates directly with Firestore or GitHub.
All repository queries, GitHub issue creation calls, memory logging, and incident tracking are forwarded through the **AgentMesh Gateway** (`https://agentmesh-gateway-138003672216.asia-south1.run.app`) using the dedicated Cloud Run service identity `agentmesh-it-security@agentmesh-fleet-2026.iam.gserviceaccount.com`.

The Gateway accesses the GitHub Personal Access Token (PAT) securely from GCP Secret Manager (`github-sandbox-pat`).

## Core Capabilities & Escalation Workflow
1. **GitHub Tool Proxying**: Calls Gateway `targetResource="github:issues"` for `list_issues`, `list_commits`, and `create_issue`.
2. **Security Reasoning**: Evaluates risk score ($\ge 0.70$ is `HIGH_RISK`).
3. **Automated Issue Remediation**: Automatically opens an issue on the target GitHub repository (`ssurekumar01111-hue/Northbridge-Retail-Co.`) documenting the risk score, summary, and specific findings.
4. **Firestore Tracking**: Updates `memory`, `workflows`, and `sandbox_incidents` (`inc-2026-001`).

## OpenTelemetry Observability
The agent uses the existing `telemetry.py` (`init_tracer`) for FastAPI + requests instrumentation.
ADK uses its own internal tracer (`google.adk.*`) on a separate namespace — no conflict or duplication with the agent's tracer. Spans from both are exported independently to GCP Cloud Trace.

## Directory Structure
- `agent.py`: Native ADK agent implementation using `LlmAgent`, `FunctionTool`, `Runner`, and `InMemorySessionService`.
- `reasoning.py`: Vertex AI Gemini (`gemini-3.5-flash`) security risk evaluation engine.
- `gateway_client.py`: Gateway API client wrapper.
- `main.py`: FastAPI HTTP endpoint exposing `/audit` and `/health`.
- `test_agent.py`: Automated integration test script covering suspicious signal detection and clean state verification.
- `Dockerfile` & `requirements.txt`: Cloud Run deployment files (`google-adk>=2.6.0`).

## Deployment Details
- **Cloud Run Service**: `agentmesh-it-security`
- **Region**: `asia-south1`
- **Service Account**: `agentmesh-it-security@agentmesh-fleet-2026.iam.gserviceaccount.com`
- **Live Service URL**: `https://agentmesh-it-security-138003672216.asia-south1.run.app`
