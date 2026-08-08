# AgentMesh — The Enterprise AI Control Plane

Built for the **All Things Agentic Hackathon** — Fortified Enterprise Fleet track.

AgentMesh is a real, production-grade control plane platform for publishing, discovering, orchestrating, protecting, and auditing a fleet of AI agents across departments — demoed live against a self-built synthetic enterprise, **Northbridge Retail Co.**

---

## Live System URLs

- **Control Plane Web Dashboard**: https://agentmesh-dashboard-138003672216.asia-south1.run.app
- **AgentMesh Gateway Service**: https://agentmesh-gateway-138003672216.asia-south1.run.app
- **Fraud & Finance Agent**: https://agentmesh-fraud-finance-138003672216.asia-south1.run.app
- **IT & Security Agent**: https://agentmesh-it-security-138003672216.asia-south1.run.app
- **Compliance Agent**: https://agentmesh-compliance-138003672216.asia-south1.run.app
- **GitHub Sandbox Repository**: https://github.com/ssurekumar01111-hue/Northbridge-Retail-Co.
- **GCP Cloud Trace Console**: https://console.cloud.google.com/traces/traces?project=agentmesh-fleet-2026

---

## Repository Structure

```text
agentmesh/
├── gateway/            # Cloud Run service — 6-stage pipeline (Auth, Identity, Policy, Armor, Tool Access, Audit)
├── agents/
│   ├── fraud-finance/  # Google ADK agent — invoice fraud investigation & state resumption
│   ├── it-security/    # Google ADK agent — GitHub repository monitoring & incident triage
│   └── compliance/     # Google ADK agent — cross-department policy audit & zero-trust denial
├── dashboard/          # Next.js 15 Control Plane UI (5 tabs: Fleet Overview, Registry, Live Workflows, Policy Playground, Observability)
├── sandbox-seed/       # Seeding scripts & schemas for Northbridge Retail Co.
├── shared/             # Shared Firestore schemas and domain models
└── docs/               # Architecture diagrams and design specifications
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
python sandbox-seed/seed_data.py
```

### 3. Service Deployments (Cloud Run)
Deploy all instrumented services to Cloud Run:
```bash
gcloud run deploy agentmesh-gateway --source=gateway --region=asia-south1
gcloud run deploy agentmesh-fraud-finance --source=agents/fraud-finance --region=asia-south1
gcloud run deploy agentmesh-it-security --source=agents/it-security --region=asia-south1
gcloud run deploy agentmesh-compliance --source=agents/compliance --region=asia-south1
gcloud run deploy agentmesh-dashboard --source=dashboard --region=asia-south1
```

### 4. Running End-to-End Test Suite
Run the comprehensive multi-agent workflow test suite locally or against deployed Cloud Run services:
```bash
python test_e2e_workflow.py
```

---

## Architecture & Design Documentation
Detailed system architecture diagrams, zero-trust pipeline flows, and OpenTelemetry trace specifications are available in [`docs/architecture.md`](file:///C:/Users/gfood/Documents/agentmesh/docs/architecture.md).
