# AgentMesh — The Enterprise AI Control Plane

[![Repo](https://img.shields.io/badge/GitHub-agentmesh--fleet-181717?logo=github)](https://github.com/ssurekumar01111-hue/agentmesh-fleet)
[![All Things Agentic Hackathon](https://img.shields.io/badge/Hackathon-All%20Things%20Agentic-4285F4)](https://all-things-agentic.devpost.com/)

Built for the **All Things Agentic Hackathon** — Fortified Enterprise Fleet track.

AgentMesh is a real, production-grade control plane platform for publishing, discovering, orchestrating, protecting, and auditing a fleet of AI agents across departments — demoed live against a self-built synthetic enterprise, **Northbridge Retail Co.**

---

## Live System URLs

| Service | URL |
|---------|-----|
| **Control Plane Web Dashboard** | https://agentmesh-dashboard-138003672216.asia-south1.run.app |
| **AgentMesh Gateway** | https://agentmesh-gateway-138003672216.asia-south1.run.app |
| **Fraud & Finance Agent** | https://agentmesh-fraud-finance-138003672216.asia-south1.run.app |
| **IT & Security Agent** | https://agentmesh-it-security-138003672216.asia-south1.run.app |
| **Compliance Agent** | https://agentmesh-compliance-138003672216.asia-south1.run.app |
| **Expense Approval Agent** | https://agentmesh-expense-approval-138003672216.asia-south1.run.app |
| **HR Leave Assistant Agent** | https://agentmesh-hr-leave-138003672216.asia-south1.run.app |
| **GitHub Sandbox Repo** | https://github.com/ssurekumar01111-hue/Northbridge-Retail-Co. |
| **This Repo** | https://github.com/ssurekumar01111-hue/agentmesh-fleet |
| **GCP Cloud Trace** | https://console.cloud.google.com/traces/traces?project=agentmesh-fleet-2026 |

---

## Repository Structure

```text
agentmesh/
├── gateway/                # Cloud Run — 6-stage pipeline (Auth, Identity, Policy, Armor, Tool Access, Audit)
├── agents/
│   ├── fraud-finance/      # ADK agent — invoice fraud investigation & state resumption
│   ├── it-security/        # ADK agent — GitHub repo monitoring & incident triage
│   ├── compliance/         # ADK agent — cross-department policy audit & zero-trust denial
│   ├── expense-approval/   # ADK agent — employee expense policy review & workflow escalation
│   └── hr-leave/           # ADK agent — employee leave request policy review & balance check
├── dashboard/              # Next.js 15 Control Plane UI (5 tabs: Overview, Registry, Workflows, Policies, Observability)
├── sandbox-seed/           # Seeding scripts for Northbridge Retail Co. synthetic data
├── shared/                 # Firestore schema definitions and security rules
└── docs/                   # Architecture diagrams and design specifications
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
To populate Firestore with Northbridge Retail Co. synthetic records, run:
```bash
python sandbox-seed/seed.py
```

### 3. Service Deployments (Cloud Run)
Deploy all instrumented services to Cloud Run:
```bash
gcloud run deploy agentmesh-gateway --source=gateway --region=asia-south1
gcloud run deploy agentmesh-fraud-finance --source=agents/fraud-finance --region=asia-south1
gcloud run deploy agentmesh-it-security --source=agents/it-security --region=asia-south1
gcloud run deploy agentmesh-compliance --source=agents/compliance --region=asia-south1
gcloud run deploy agentmesh-expense-approval --source=agents/expense-approval --region=asia-south1
gcloud run deploy agentmesh-dashboard --source=dashboard --region=asia-south1
```

### 4. Running End-to-End Test Suite
Run the comprehensive multi-agent workflow test suite locally or against deployed Cloud Run services:
```bash
python test_e2e_workflow.py
```

---

## Architecture & Design Documentation
Detailed system architecture diagrams, zero-trust pipeline flows, and OpenTelemetry trace specifications are available in [`docs/architecture.md`](docs/architecture.md).
