#!/bin/bash
# QueryMind — Cloud Run deploy script
# Usage: ./deploy.sh <your-gcp-project-id>

set -e

PROJECT_ID=${1:-"your-gcp-project-id"}
SERVICE_NAME="querymind"
REGION="asia-southeast1"
IMAGE="gcr.io/${PROJECT_ID}/${SERVICE_NAME}"

echo "🚀 Building and deploying QueryMind to Cloud Run..."
echo "Project: $PROJECT_ID | Region: $REGION"

# Build and push image
gcloud builds submit --tag "$IMAGE" --project "$PROJECT_ID"

# Deploy to Cloud Run
gcloud run deploy "$SERVICE_NAME" \
  --image "$IMAGE" \
  --platform managed \
  --region "$REGION" \
  --allow-unauthenticated \
  --memory 1Gi \
  --cpu 1 \
  --timeout 120 \
  --set-env-vars "GOOGLE_CLOUD_PROJECT=${PROJECT_ID}" \
  --project "$PROJECT_ID"

echo "✅ Deployed! Visit:"
gcloud run services describe "$SERVICE_NAME" --region "$REGION" --project "$PROJECT_ID" \
  --format "value(status.url)"
