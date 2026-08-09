# AgentMesh Control Plane Dashboard

The AgentMesh Control Plane Dashboard provides enterprise governance, fleet monitoring, and human approval gates for multi-agent fleets.

## Live Deployed Control Plane
- **Dashboard Web App URL**: [https://agentmesh-dashboard-138003672216.asia-south1.run.app](https://agentmesh-dashboard-138003672216.asia-south1.run.app)
- **Target Gateway URL**: `https://agentmesh-gateway-138003672216.asia-south1.run.app`

## Architecture & Data Flow
All data rendered in the dashboard is **100% real** and dynamically fetched from Firestore via the AgentMesh Gateway pipeline:
- Service Identity: `agentmesh-dashboard@agentmesh-fleet-2026.iam.gserviceaccount.com`
- Manifest: Registered in `agent_registry/dashboard` with explicit allowed collections.
- Gateway Endpoint: Calls `POST /v1/execute` via `x-emulated-sa` or OIDC authorization headers.

## Top 5 Navigation Tabs
1. **Overview**: Metric cards (Active Agents, Running Workflows, Threats Blocked, Avg Latency), Registry Preview, Live Activity Feed.
2. **Registry**: Full agent manifest browser with permission modal (Allowed collections & tools).
3. **Live Workflows**: Real-time state viewer & human approval page.
4. **Policies**: Enterprise access rules & zero-trust enforcement status.
5. **Observability**: Real-time audit logs & Gateway execution traces.

## Cloud Run Deployment
```bash
gcloud run deploy agentmesh-dashboard --source=dashboard --region=asia-south1 --service-account=agentmesh-dashboard@agentmesh-fleet-2026.iam.gserviceaccount.com
```

