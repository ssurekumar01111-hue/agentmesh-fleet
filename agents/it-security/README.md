# IT & Security Monitoring Agent (`agents/it-security`)

## Overview
The **IT/Security Agent** is an autonomous security monitoring agent built using Google ADK and Gemini (`gemini-2.5-flash`) via Vertex AI.

It scans repository commit histories and open issues for security threats, exposed secrets (e.g. AWS access keys, API tokens), and unauthorized configuration changes.

## Security Architecture & Zero Bypass
This agent **NEVER** communicates directly with Firestore or GitHub.
All repository queries, GitHub issue creation calls, memory logging, and incident tracking are forwarded through the **AgentMesh Gateway** (`https://agentmesh-gateway-138003672216.asia-south1.run.app`) using the dedicated Cloud Run service identity `agentmesh-it-security@agentmesh-fleet-2026.iam.gserviceaccount.com`.

The Gateway accesses the GitHub Personal Access Token (PAT) securely from GCP Secret Manager (`github-sandbox-pat`).

## Core Capabilities & Escalation Workflow
1. **GitHub Tool Proxying**: Calls Gateway `targetResource="github:issues"` for `list_issues`, `list_commits`, and `create_issue`.
2. **Security Reasoning**: Evaluates risk score ($\ge 0.70$ is `HIGH_RISK`).
3. **Automated Issue Remediation**: Automatically opens an issue on the target GitHub repository (`ssurekumar01111-hue/Northbridge-Retail-Co.`) documenting the risk score, summary, and specific findings.
4. **Firestore Tracking**: Updates `memory`, `workflows`, and `sandbox_incidents` (`inc-2026-001`).

## Directory Structure
- `agent.py`: ADK process flow for auditing repo activity and executing Gateway tool calls.
- `reasoning.py`: Vertex AI Gemini (`gemini-2.5-flash`) security risk evaluation engine.
- `gateway_client.py`: Gateway API client wrapper.
- `main.py`: FastAPI HTTP endpoint exposing `/audit` and `/health`.
- `test_agent.py`: Automated integration test script covering suspicious signal detection and clean state verification.
- `Dockerfile` & `requirements.txt`: Cloud Run deployment files.

## Deployment Details
- **Cloud Run Service**: `agentmesh-it-security`
- **Region**: `asia-south1`
- **Service Account**: `agentmesh-it-security@agentmesh-fleet-2026.iam.gserviceaccount.com`
- **Live Service URL**: `https://agentmesh-it-security-138003672216.asia-south1.run.app`
