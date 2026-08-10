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
            S4["Stage 4: Threat Shield Inline Scan (PII & Injection Detection)"]
            S5["Stage 5: Tool Access Dispatcher"]
            S6["Stage 6: Immutable Audit Log Write (Firestore audit_log)"]
            
            S1 --> S2 --> S3 --> S4 --> S5 --> S6
        end

        GW_ENTRY --> S1
        GW_SIM --> S1
    end

    subgraph Agents["Domain Agent Fleet (Google ADK v2.6+ & Gemini 3.5 Flash on Cloud Run)"]
        AG_FRAUD["Fraud & Finance Agent\n(agentmesh-fraud-finance)\n[LlmAgent + FunctionTools: fetch_invoice,\nfetch_vendor_history, write_memory,\nupdate_workflow]"]
        AG_IT["IT & Security Agent\n(agentmesh-it-security)\n[LlmAgent + FunctionTools: list_issues,\nlist_commits, create_issue, write_memory,\nupdate_incident, update_workflow]"]
        AG_COMP["Compliance Agent\n(agentmesh-compliance)\n[LlmAgent + FunctionTools: fetch_workflow,\nfetch_memory, fetch_policies, write_memory,\nread_hr_employees]\n[Phase 9b: get_policies bug fix — action=read]"]
        AG_EXPENSE["Expense Approval Agent\n(agentmesh-expense-approval)\n[LlmAgent + FunctionTools: fetch_expense,\nwrite_memory, update_workflow]"]
        AG_LEAVE["HR Leave Agent\n(agentmesh-hr-leave)\n[LlmAgent + FunctionTools: fetch_leave_request,\nfetch_employee, write_memory, update_workflow]"]
        AG_LEGAL["Legal Contract Agent\n(agentmesh-legal-contract)\n[LlmAgent + FunctionTools: fetch_contract,\nwrite_memory, update_workflow]"]

        GEMINI["Google Vertex AI\n(gemini-3.5-flash)"]

        AG_FRAUD -->|Gemini Reasoning| GEMINI
        AG_IT -->|Gemini Reasoning| GEMINI
        AG_COMP -->|Gemini Reasoning| GEMINI
        AG_EXPENSE -->|Gemini Reasoning| GEMINI
        AG_LEAVE -->|Gemini Reasoning| GEMINI
        AG_LEGAL -->|Gemini Reasoning| GEMINI

        AG_FRAUD -->|OIDC Auth + Gateway API| GW_ENTRY
        AG_IT -->|OIDC Auth + Gateway API| GW_ENTRY
        AG_COMP -->|OIDC Auth + Gateway API| GW_ENTRY
        AG_EXPENSE -->|OIDC Auth + Gateway API| GW_ENTRY
        AG_LEAVE -->|OIDC Auth + Gateway API| GW_ENTRY
        AG_LEGAL -->|OIDC Auth + Gateway API| GW_ENTRY
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
| **Expense Approval Agent** | `agentmesh-expense-approval` | https://agentmesh-expense-approval-138003672216.asia-south1.run.app |
| **HR Leave Agent** | `agentmesh-hr-leave` | https://agentmesh-hr-leave-138003672216.asia-south1.run.app |
| **Legal Contract Agent** | `agentmesh-legal-contract` | https://agentmesh-legal-contract-138003672216.asia-south1.run.app |
| **GitHub Sandbox Repository** | `Northbridge-Retail-Co.` | https://github.com/ssurekumar01111-hue/Northbridge-Retail-Co. |
| **GCP Cloud Trace Console** | `agentmesh-fleet-2026` | https://console.cloud.google.com/traces/traces?project=agentmesh-fleet-2026 |

---

## ADK Adoption Status (All 6 Agents — Genuine ADK Runner Rollout Complete)

| Agent | ADK LlmAgent | FunctionTools (Exclusive Call Path) | ADK Runner (`run_async`) | Session Service | Status |
|---|---|---|---|---|---|
| fraud-finance | ✅ | fetch_invoice, fetch_vendor_history, write_memory, update_workflow | ✅ | InMemorySessionService | Phase 13a Verified |
| it-security | ✅ | list_issues, list_commits, create_issue, write_memory, update_incident, update_workflow | ✅ | InMemorySessionService | Phase 13b Verified |
| compliance | ✅ | fetch_workflow, fetch_memory, fetch_policies, write_memory, read_hr_employees | ✅ | InMemorySessionService | Phase 13b Verified |
| expense-approval | ✅ | fetch_expense, write_memory, update_workflow | ✅ | InMemorySessionService | Phase 13b Verified |
| hr-leave | ✅ | fetch_leave_request, fetch_employee, write_memory, update_workflow | ✅ | InMemorySessionService | Phase 13b Verified |
| legal-contract | ✅ | fetch_contract, write_memory, update_workflow | ✅ | InMemorySessionService | Phase 13b Verified |

---

## Real Execution Flow & Zero-Trust Guarantees

1. **Identity & Auth Isolation**: Each agent runs as a distinct Google Service Account (`agentmesh-fraud-finance@...`, `agentmesh-it-security@...`, `agentmesh-compliance@...`, `agentmesh-expense-approval@...`, `agentmesh-hr-leave@...`, `agentmesh-legal-contract@...`).
2. **Genuine ADK Runner Loop**: All 6 domain agents run tool calls exclusively through Google ADK `Runner.run_async()` tool-execution loop (`LlmAgent` + `FunctionTool` closures). There are no manual or out-of-band call paths to these functions outside the Runner.
3. **Gateway Mediation**: Agents never communicate directly with Firestore or GitHub; all tool access requests pass through the Gateway pipeline via ADK FunctionTools wrapping GatewayClient calls.
4. **Authoritative Timestamps**: All write actions use ISO 8601 UTC timestamps set dynamically (`datetime.now(timezone.utc).isoformat()`), replacing literal placeholders.
5. **Threat Shield (Guard Pipeline)**: Every inbound payload and outbound response is scanned for prompt injection, secret leakage, and PII.
6. **Persisted Workflow Resumption**: Paused workflows store state in Firestore (`workflows` collection), surviving Cloud Run process restarts.
7. **Distributed OpenTelemetry Tracing**: Every pipeline execution emits spans exported directly to GCP Cloud Trace for end-to-end observability. ADK's internal tracer runs on a separate namespace — no conflict with each agent's `telemetry.py` tracer.
