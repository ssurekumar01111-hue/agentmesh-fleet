# IAM Roles — per-agent least privilege

Run these after `gcp-setup.sh` creates the service accounts. Replace `$PROJECT_ID`.

## Gateway (`agentmesh-gateway`)
The Gateway is the only service allowed broad Firestore access (it enforces
per-agent scoping in application logic, backed by the registry). It also needs
to read Secret Manager (GitHub PAT) and write audit logs.

```
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:agentmesh-gateway@$PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/datastore.user"

gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:agentmesh-gateway@$PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"

gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:agentmesh-gateway@$PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/pubsub.publisher"
```

## Fraud/Finance Agent (`agentmesh-fraud-finance`)
Only needs Vertex AI + narrow Firestore access (enforced at Gateway; this IAM
grant is the infra-layer backstop, kept broad-but-collection-scoped via
Firestore security rules rather than IAM alone, since IAM doesn't do
per-collection granularity natively).

```
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:agentmesh-fraud-finance@$PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/aiplatform.user"

gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:agentmesh-fraud-finance@$PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/datastore.user"
```
(Collection-level restriction — e.g. no access to `sandbox_employees` HR data —
is enforced via Firestore Security Rules keyed on the service account identity,
see `shared/firestore.rules`.)

## IT/Security Agent (`agentmesh-it-security`)
Needs Vertex AI + Firestore + its own GitHub PAT (via Secret Manager, not IAM).

```
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:agentmesh-it-security@$PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/aiplatform.user"

gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:agentmesh-it-security@$PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/datastore.user"

gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:agentmesh-it-security@$PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"
```

## Compliance Agent (`agentmesh-compliance`)
Needs Vertex AI + read access to `policies` and `audit_log` collections.

```
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:agentmesh-compliance@$PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/aiplatform.user"

gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:agentmesh-compliance@$PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/datastore.viewer"
```

## Expense Approval Agent (`agentmesh-expense-approval`)
Only needs Vertex AI + Firestore access (enforced at Gateway; this IAM grant is
the infra-layer backstop). Collection-level restriction — no access to
`sandbox_invoices`, `sandbox_employees`, `sandbox_incidents`, or other departments'
data — is enforced via Firestore Security Rules keyed on the service account identity.

```
gcloud iam service-accounts create agentmesh-expense-approval \
  --display-name="AgentMesh Expense Approval Agent" \
  --project=$PROJECT_ID

gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:agentmesh-expense-approval@$PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/aiplatform.user"

gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:agentmesh-expense-approval@$PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/datastore.user"

gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:agentmesh-expense-approval@$PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/cloudtrace.agent"
```

## HR Leave Assistant Agent (`agentmesh-hr-leave`)
Needs Vertex AI + Firestore access + Cloud Trace access. Collection-level restriction —
allowed to access `sandbox_leave_requests` and `sandbox_employees` (for employee lookup),
explicitly NOT `sandbox_invoices`, `sandbox_expenses`, `sandbox_incidents` — is enforced
via Firestore Security Rules and Gateway policy.

```
gcloud iam service-accounts create agentmesh-hr-leave \
  --display-name="AgentMesh HR Leave Assistant Agent" \
  --project=$PROJECT_ID

gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:agentmesh-hr-leave@$PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/aiplatform.user"

gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:agentmesh-hr-leave@$PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/datastore.user"

gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:agentmesh-hr-leave@$PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/cloudtrace.agent"
```
(Collection-level restriction — e.g. no access to `sandbox_invoices` or
`sandbox_employees` data — is enforced via Firestore Security Rules keyed on the
service account identity, see `shared/firestore.rules`.)

## Principle

IAM grants here are intentionally coarse (Firestore doesn't support fine-grained
IAM at the collection level) — the **real** least-privilege enforcement happens
in two places, deliberately layered so no single bug exposes everything:

1. **Firestore Security Rules** — reject reads/writes to collections a service
   account isn't permitted to touch, regardless of what the app code tries.
2. **Gateway policy check** — reads `agent_registry.{agentId}.allowedCollections`
   before forwarding any request, as a second, independent check.

This is the two-layer design referenced in the build plan: IAM/Firestore Rules
are the machine-layer boundary; Gateway policy is the application-layer boundary.
