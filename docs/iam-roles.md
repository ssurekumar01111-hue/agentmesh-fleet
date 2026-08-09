# IAM Roles — Gateway-only Firestore access

Replace `$PROJECT_ID` with your Google Cloud project ID. Agent service accounts
must not receive `roles/datastore.*` or Secret Manager access; all enterprise
data and external-tool access is mediated by the Gateway.

## Gateway (`agentmesh-gateway`)

The Gateway is the sole workload identity with direct Firestore and GitHub PAT
access.

```bash
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

## Domain agents

Each of `agentmesh-fraud-finance`, `agentmesh-it-security`,
`agentmesh-compliance`, `agentmesh-expense-approval`, `agentmesh-hr-leave`,
and `agentmesh-legal-contract` receives only:

```bash
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:<AGENT_NAME>@$PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/aiplatform.user"

gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:<AGENT_NAME>@$PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/cloudtrace.agent"
```

To enforce the boundary on an existing project, remove any legacy bindings:

```bash
gcloud projects remove-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:<AGENT_NAME>@$PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/datastore.user"

gcloud projects remove-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:<AGENT_NAME>@$PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/datastore.viewer"
```

Firebase Security Rules govern client-SDK traffic; they are not an IAM boundary
for Firestore server SDK calls. Gateway-only access is therefore enforced by
withholding all direct Firestore IAM permissions from agent service accounts.
