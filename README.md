# AgentMesh — The Enterprise AI Control Plane

Built for the **All Things Agentic Hackathon** — Fortified Enterprise Fleet track.

AgentMesh is a real, production-grade platform for publishing, discovering, orchestrating,
protecting, and auditing a fleet of AI agents across departments — demoed live against a
self-built but fully real sandbox company, **Northbridge Retail Co.**

## Repo structure

```
agentmesh/
├── gateway/            # Cloud Run service — auth, identity check, policy, Model Armor, routing
├── agents/
│   ├── fraud-finance/  # ADK agent — invoice fraud investigation
│   ├── it-security/    # ADK agent — GitHub repo monitoring
│   └── compliance/     # ADK agent — cross-agent policy enforcement
├── dashboard/          # React/Next control-plane UI (5 tabs)
├── sandbox-seed/       # Scripts to seed Northbridge Retail Co. sandbox data + GitHub repo
├── shared/             # Shared types/schemas used across services (registry manifest, memory schema)
└── docs/               # Architecture diagram, submission write-up
```

## Prerequisites

- Google Cloud project with billing enabled + $150 hackathon credit claimed
- `gcloud` CLI authenticated to the project
- Python 3.11+ (agents, gateway)
- Node.js 20+ (dashboard)
- Docker (for Cloud Run deploys)
- Firebase CLI (if deploying dashboard to Firebase Hosting)
- A GitHub PAT scoped to the sandbox repo only, stored in Secret Manager

## APIs to enable

```
gcloud services enable \
  aiplatform.googleapis.com \
  run.googleapis.com \
  firestore.googleapis.com \
  pubsub.googleapis.com \
  secretmanager.googleapis.com \
  cloudtrace.googleapis.com \
  iam.googleapis.com
```

## Local setup (per service)

See each subdirectory's own README for spin-up instructions:
- `gateway/README.md`
- `agents/<agent-name>/README.md`
- `dashboard/README.md`
- `sandbox-seed/README.md`

## Status

🚧 Week 1 — foundation phase. See `docs/build-plan.md` for the full roadmap.
