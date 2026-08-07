# AgentMesh Gateway Service

The Gateway is the single entrypoint every agent request routes through in AgentMesh.

## 6-Stage Security Pipeline

1. **Authentication**: Validates caller's OIDC ID token (Cloud Run service identity).
2. **Identity Check**: Queries `agent_registry` for active status and allowed collections.
3. **Policy Check**: Evaluates zero-trust rules from `policies` collection (e.g. `pol-deny-finance-hr`).
4. **Model Armor**: Inline pattern + LLM scan for prompt injection, secret leaks, and PII leaks.
5. **Tool Access & Forwarding**: Dispatches request to target Firestore collection or external tool.
6. **Audit Logging**: Writes immutable, redacted log entries to `audit_log` in Firestore.

## Local Execution

To run locally with auth emulation enabled:

```bash
export ALLOW_LOCAL_AUTH_EMULATION=true
export GCP_PROJECT_ID=agentmesh-fleet-2026

uvicorn main:app --host 0.0.0.0 --port 8080
```

Run automated integration tests:

```bash
python test_gateway.py
```

## Cloud Run Deployment

Deploy to Google Cloud Run using the `agentmesh-gateway` service account:

```bash
gcloud run deploy agentmesh-gateway \
  --source . \
  --region asia-south1 \
  --service-account agentmesh-gateway@agentmesh-fleet-2026.iam.gserviceaccount.com \
  --set-env-vars GCP_PROJECT_ID=agentmesh-fleet-2026 \
  --allow-unauthenticated \
  --project agentmesh-fleet-2026
```
