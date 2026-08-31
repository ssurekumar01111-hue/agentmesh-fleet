# AgentMesh — The Enterprise AI Control Plane

[![Repo](https://img.shields.io/badge/GitHub-agentmesh--fleet-181717?logo=github)](https://github.com/ssurekumar01111-hue/agentmesh-fleet)
[![All Things Agentic Hackathon](https://img.shields.io/badge/Hackathon-All%20Things%20Agentic-4285F4)](https://all-things-agentic.devpost.com/)

Enterprises don't struggle to deploy their first AI agent. They struggle six months later, once there are ten of them, and nobody can say which one touched what, or why. AgentMesh is built to answer that.

Built for the **All Things Agentic Hackathon** — Fortified Enterprise Fleet track.

AgentMesh is a real, production-grade control plane platform for publishing, discovering, orchestrating, protecting, and auditing a fleet of AI agents across departments — demoed live against a self-built synthetic enterprise, **Northbridge Retail Co.**

---

## Live System URLs

> **Agent and Gateway URLs are backend APIs — visiting them directly now shows service status. Start with the Dashboard for the live interactive demo.**
>
> **Agent and Gateway URLs require Google Cloud IAM authentication — visiting them directly without credentials will show a 403 Forbidden page. This is intentional zero-trust access control, not a broken link. See [docs/iam-roles.md](docs/iam-roles.md) for the security model, or use the Dashboard for the live interactive demo.**

| Service | URL |
|---------|-----|
| 🟢 **Control Plane Web Dashboard** ← **Start here** | **[https://agentmesh-dashboard-138003672216.asia-south1.run.app](https://agentmesh-dashboard-138003672216.asia-south1.run.app)** |
| **AgentMesh Gateway** | https://agentmesh-gateway-138003672216.asia-south1.run.app |
| **Fraud & Finance Agent** | https://agentmesh-fraud-finance-138003672216.asia-south1.run.app |
| **IT & Security Agent** | https://agentmesh-it-security-138003672216.asia-south1.run.app |
| **Compliance Agent** | https://agentmesh-compliance-138003672216.asia-south1.run.app |
| **Expense Approval Agent** | https://agentmesh-expense-approval-138003672216.asia-south1.run.app |
| **HR Leave Assistant Agent** | https://agentmesh-hr-leave-138003672216.asia-south1.run.app |
| **Legal Contract Agent** | https://agentmesh-legal-contract-138003672216.asia-south1.run.app |
| **GitHub Sandbox Repo** | https://github.com/ssurekumar01111-hue/Northbridge-Retail-Co. |
| **This Repo** | https://github.com/ssurekumar01111-hue/agentmesh-fleet |
| **GCP Cloud Trace** | https://console.cloud.google.com/traces/traces?project=agentmesh-fleet-2026 |

---

## Repository Structure

```text
agentmesh/
├── gateway/                # Cloud Run — 6-stage pipeline (Auth, Identity, Policy, Threat Shield, Tool Access, Audit) + Spending Policy Guard
├── agents/
│   ├── fraud-finance/      # ADK agent — invoice fraud investigation & state resumption
│   ├── it-security/        # ADK agent — GitHub repo monitoring & incident triage
│   ├── compliance/         # ADK agent — cross-department policy audit & zero-trust denial
│   ├── expense-approval/   # ADK agent — employee expense policy review & spending limit checks
│   ├── hr-leave/           # ADK agent — employee leave request policy review & balance check
│   └── legal-contract/     # ADK agent — contract prose & clause policy review
├── dashboard/              # Next.js 15 Control Plane UI (5 tabs: Overview, Registry, Workflows, Policies, Observability)
├── sandbox-seed/           # Seeding scripts for Northbridge Retail Co. synthetic data & spending policies
├── shared/                 # Firestore schema definitions and security rules
└── docs/                   # Architecture diagrams, async runtime, and design specifications
```

---

## Prerequisites & Spin-Up Guide

### 1. GCP Project & CLI Prerequisites
- Google Cloud project ID: `agentmesh-fleet-2026`
- Active GCP services enabled:
  ```bash
  gcloud services enable \
    aiplatform.googleapis.com \
    run.googleapis.com \
    firestore.googleapis.com \
    pubsub.googleapis.com \
    secretmanager.googleapis.com \
    cloudtrace.googleapis.com \
    iam.googleapis.com
  ```

### 2. Sandbox Data Seeding
To populate Firestore with Northbridge Retail Co. synthetic records and spending policy registry entries, run:
```bash
python sandbox-seed/seed.py
```

### 3. Service Deployments (Cloud Run)
Deploy all instrumented services to Cloud Run:
```bash
gcloud run deploy agentmesh-gateway --source=gateway --region=asia-south1 --service-account=agentmesh-gateway@agentmesh-fleet-2026.iam.gserviceaccount.com
gcloud run deploy agentmesh-fraud-finance --source=agents/fraud-finance --region=asia-south1 --service-account=agentmesh-fraud-finance@agentmesh-fleet-2026.iam.gserviceaccount.com
gcloud run deploy agentmesh-it-security --source=agents/it-security --region=asia-south1 --service-account=agentmesh-it-security@agentmesh-fleet-2026.iam.gserviceaccount.com
gcloud run deploy agentmesh-compliance --source=agents/compliance --region=asia-south1 --service-account=agentmesh-compliance@agentmesh-fleet-2026.iam.gserviceaccount.com
gcloud run deploy agentmesh-expense-approval --source=agents/expense-approval --region=asia-south1 --service-account=agentmesh-expense-approval@agentmesh-fleet-2026.iam.gserviceaccount.com
gcloud run deploy agentmesh-hr-leave --source=agents/hr-leave --region=asia-south1 --service-account=agentmesh-hr-leave@agentmesh-fleet-2026.iam.gserviceaccount.com
gcloud run deploy agentmesh-legal-contract --source=agents/legal-contract --region=asia-south1 --service-account=agentmesh-legal-contract@agentmesh-fleet-2026.iam.gserviceaccount.com
gcloud run deploy agentmesh-dashboard --source=dashboard --region=asia-south1 --service-account=agentmesh-dashboard@agentmesh-fleet-2026.iam.gserviceaccount.com
```

### 4. Running the Test Suites
Each agent has its own integration test suite that verifies the full async 202/queued → Firestore polling → terminal state pipeline against the live deployed Cloud Run services:

```bash
# Per-agent test suites (async 202/poll pattern, all verified against live Cloud Run)
python agents/fraud-finance/test_agent.py
python agents/it-security/test_agent.py
python agents/compliance/test_agent.py
python agents/expense-approval/test_agent.py
python agents/hr-leave/test_agent.py
python agents/legal-contract/test_agent.py

# Gateway-level zero-trust, spending policy accumulation, and routing verification
python gateway/test_gateway.py
python gateway/test_spending_accumulation.py
```

Each suite posts a trigger to the agent's Cloud Run endpoint (expects HTTP 202 + `{"status":"queued","workflowId":...}`), polls Firestore every 2 seconds until a terminal state (`waiting_approval`, `completed`, or `failed`) is reached, and asserts on real workflow document state.


---

## Core Security & Architecture Highlights

1. **6-Stage Zero-Trust Gateway**: Enforces IAM Caller Identity, Agent Registry Whitelisting, Dynamic Policy Enforcement, Threat Shield (Guard Pipeline for prompt injection & data exfiltration), Tool Access Proxying, and Immutable Audit Logging.
2. **Spending Policy Enforcement**: Dynamic limits on agent financial actions (`maxTransactionAmount`, `dailySpendLimit`, `approvalThreshold`) with daily spend calculated on-the-fly from audit logs.
3. **Asynchronous Pub/Sub Runtime**: Idempotent execution with 202 Accepted response, atomic Firestore workflow claiming, and live polling in the Control Plane Dashboard.
4. **Human-in-the-Loop Resumption**: Workflows exceeding threshold pause at `waiting_approval`, resumed via Dashboard to agent `/resume` endpoint.
5. **Distributed OpenTelemetry Tracing**: End-to-end W3C `traceparent` propagation across Dashboard, Gateway, Agents, and Google Cloud Trace.

---

## Architecture & Design Documentation
Detailed system architecture diagrams, zero-trust pipeline flows, and OpenTelemetry trace specifications are available in [`docs/architecture.md`](docs/architecture.md).

---

## Findings & Learnings

- **Governance matters more than model intelligence in production.** Gemini can reason well, but enterprise agents still need identity, policy, authorization, observability, and human oversight outside the model.
- **The LLM cannot be the security boundary.** Moving authorization into the Gateway and Google Cloud IAM prevents agents from accessing systems they are not explicitly allowed to use.
- **Memory and workflow state are different concerns.** Agent memory stores what the system learned; durable workflow state stores where the business process is and enables pause/resume across restarts.
- **Async systems must assume duplicate delivery.** Pub/Sub redelivery made idempotency and atomic workflow claims essential for safe execution.
- **Agents need economic guardrails, not just data guardrails.** Transaction caps, daily limits, and approval thresholds can be enforced centrally so agents never calculate or enforce their own budgets.
- **Observability becomes critical in multi-service agent systems.** Distributed traces and structured audit logs make agent actions, policy decisions, tool calls, latency, and failures explainable after the fact.

---


## License
Apache 2.0 — see [LICENSE](LICENSE)
