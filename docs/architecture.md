# AgentMesh — Production Architecture & Implementation Diagram

## System Architecture

```mermaid
flowchart TD
    subgraph Frontend["Control Plane Web Dashboard (Next.js 15 on Cloud Run)"]
        UI["Dashboard UI (React / Tailwind / Lucide)"]
        UI_API["Internal API Proxy (/api/gateway)"]
        UI --> UI_API
    end

    subgraph SecurityGateway["AgentMesh Gateway (FastAPI on Cloud Run)"]
        GW_ENTRY["POST /v1/execute"]
        GW_SIM["POST /v1/simulate-policy"]
        
        subgraph Pipeline["6-Stage Zero-Trust Execution Pipeline"]
            S1["Stage 1: Auth Verification (OIDC Token Validation)"]
            S2["Stage 2: Identity Check (Firestore Registry Validation)"]
            S3["Stage 3: Policy Engine Check (Collection & Deny Rules)"]
            S4["Stage 4: Model Armor Inline Scan (PII & Injection Detection)"]
            S5["Stage 5: Tool Access Dispatcher"]
            S6["Stage 6: Immutable Audit Log Write (Firestore audit_log)"]
            
            S1 --> S2 --> S3 --> S4 --> S5 --> S6
        end

        GW_ENTRY --> S1
        GW_SIM --> S1
    end

    subgraph Agents["Domain Agent Fleet (Google ADK & Gemini 3.5 Flash on Cloud Run)"]
        AG_FRAUD["Fraud & Finance Agent\n(agentmesh-fraud-finance)"]
        AG_IT["IT & Security Agent\n(agentmesh-it-security)"]
        AG_COMP["Compliance Agent\n(agentmesh-compliance)"]

        GEMINI["Google Vertex AI\n(gemini-3.5-flash)"]

        
        AG_FRAUD -->|Gemini Reasoning| GEMINI
        AG_IT -->|Gemini Reasoning| GEMINI
        AG_COMP -->|Gemini Reasoning| GEMINI

        AG_FRAUD -->|OIDC Auth + Gateway API| GW_ENTRY
        AG_IT -->|OIDC Auth + Gateway API| GW_ENTRY
        AG_COMP -->|OIDC Auth + Gateway API| GW_ENTRY
    end

    subgraph External["External Integrations"]
        GITHUB["GitHub Sandbox Repo\n(ssurekumar01111-hue/Northbridge-Retail-Co.)"]
    end

    subgraph GCPInfra["Google Cloud Platform Infrastructure"]
        FIRESTORE[(Google Firestore NoSQL Database)]
        SECRET_MGR[GCP Secret Manager]
        PUBSUB[GCP Pub/Sub]
        TRACE[GCP Cloud Trace & OpenTelemetry]
    end

    UI_API --> GW_SIM
    S5 -->|Read / Write| FIRESTORE
    S5 -->|Read PAT| SECRET_MGR
    S5 -->|Issue Creation & Commits| GITHUB
    S6 --> FIRESTORE

    SecurityGateway -.->|OpenTelemetry Spans| TRACE
    Agents -.->|OpenTelemetry Spans| TRACE
```

---

## Live Cloud Run Service Endpoints & Resources

| Service / Component | Service ID / Identifier | Real Deployed URL |
|---|---|---|
| **Control Plane Dashboard** | `agentmesh-dashboard` | https://agentmesh-dashboard-138003672216.asia-south1.run.app |
| **AgentMesh Gateway** | `agentmesh-gateway` | https://agentmesh-gateway-138003672216.asia-south1.run.app |
| **Fraud & Finance Agent** | `agentmesh-fraud-finance` | https://agentmesh-fraud-finance-138003672216.asia-south1.run.app |
| **IT & Security Agent** | `agentmesh-it-security` | https://agentmesh-it-security-138003672216.asia-south1.run.app |
| **Compliance Agent** | `agentmesh-compliance` | https://agentmesh-compliance-138003672216.asia-south1.run.app |
| **GitHub Sandbox Repository** | `Northbridge-Retail-Co.` | https://github.com/ssurekumar01111-hue/Northbridge-Retail-Co. |
| **GCP Cloud Trace Console** | `agentmesh-fleet-2026` | https://console.cloud.google.com/traces/traces?project=agentmesh-fleet-2026 |

---

## Real Execution Flow & Zero-Trust Guarantees

1. **Identity & Auth Isolation**: Each agent runs as a distinct Google Service Account (`agentmesh-fraud-finance@...`, `agentmesh-it-security@...`, `agentmesh-compliance@...`).
2. **Gateway Mediation**: Agents never communicate directly with Firestore or GitHub; all tool access requests pass through the Gateway pipeline.
3. **Model Armor**: Every inbound payload and outbound response is scanned for prompt injection, secret leakage, and PII.
4. **Persisted Workflow Resumption**: Paused workflows store state in Firestore (`workflows` collection), surviving Cloud Run process restarts.
5. **Distributed OpenTelemetry Tracing**: Every pipeline execution emits spans exported directly to GCP Cloud Trace for end-to-end observability.
