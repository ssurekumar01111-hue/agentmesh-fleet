#!/usr/bin/env bash
# AgentMesh — one-time GCP project setup.
# Run this AFTER: `gcloud auth login` and `gcloud config set project <YOUR_PROJECT_ID>`

set -euo pipefail

PROJECT_ID=$(gcloud config get-value project)
REGION="asia-south1"   # change if you want a different region

echo "Setting up AgentMesh on project: $PROJECT_ID (region: $REGION)"

# 1. Enable required APIs
gcloud services enable \
  aiplatform.googleapis.com \
  run.googleapis.com \
  firestore.googleapis.com \
  pubsub.googleapis.com \
  secretmanager.googleapis.com \
  cloudtrace.googleapis.com \
  logging.googleapis.com \
  iam.googleapis.com \
  artifactregistry.googleapis.com

# 2. Create Firestore database (Native mode) if it doesn't exist
gcloud firestore databases create --location="$REGION" --type=firestore-native || \
  echo "Firestore database may already exist — continuing."

# 3. Create Pub/Sub topic + subscription for async agent job dispatch
gcloud pubsub topics create agent-jobs || echo "Topic agent-jobs may already exist."
gcloud pubsub subscriptions create agent-jobs-sub --topic=agent-jobs || \
  echo "Subscription agent-jobs-sub may already exist."

# 4. Create Artifact Registry repo for Cloud Run container images
gcloud artifacts repositories create agentmesh \
  --repository-format=docker \
  --location="$REGION" \
  --description="AgentMesh service images" || \
  echo "Artifact Registry repo agentmesh may already exist."

# 5. Create per-agent service accounts (least privilege — grant roles separately per agent)
for AGENT in fraud-finance it-security compliance gateway; do
  SA_NAME="agentmesh-${AGENT}"
  gcloud iam service-accounts create "$SA_NAME" \
    --display-name="AgentMesh - ${AGENT}" || \
    echo "Service account $SA_NAME may already exist."
done

echo ""
echo "Done. Next steps:"
echo "  1. Grant each service account only the IAM roles it needs (see docs/iam-roles.md)"
echo "  2. Store the GitHub sandbox PAT in Secret Manager:"
echo "     gcloud secrets create github-sandbox-pat --data-file=- <<< \"YOUR_TOKEN\""
echo "  3. Copy .env.example to .env and fill in PROJECT_ID / REGION"
echo "  4. Replace PROJECT_ID placeholder in shared/firestore.rules with: $PROJECT_ID"
echo "     then deploy: firebase deploy --only firestore:rules"
