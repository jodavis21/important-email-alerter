#!/bin/bash
# Set up Cloud Scheduler for periodic email checks and daily digest

# Configuration - UPDATE THESE VALUES
PROJECT_ID="your-project-id"  # Your Google Cloud project ID
REGION="us-central1"          # Cloud Run region
SERVICE_NAME="email-alerter"  # Cloud Run service name
TIMEZONE="America/Los_Angeles"  # Your timezone

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}=== Setting up Cloud Scheduler ===${NC}"

# Get service URL
SERVICE_URL=$(gcloud run services describe $SERVICE_NAME --region $REGION --format='value(status.url)')

if [ -z "$SERVICE_URL" ]; then
    echo "Error: Could not get service URL. Make sure the service is deployed."
    exit 1
fi

echo "Service URL: $SERVICE_URL"

# Create scheduler job for email checks (every 15 minutes)
echo -e "${YELLOW}Creating email check scheduler (every 15 minutes)...${NC}"
gcloud scheduler jobs create http email-check-job \
    --location $REGION \
    --schedule "*/15 * * * *" \
    --uri "${SERVICE_URL}/api/check-now" \
    --http-method POST \
    --time-zone "$TIMEZONE" \
    --attempt-deadline 300s \
    --description "Check emails every 15 minutes" \
    2>/dev/null || \
gcloud scheduler jobs update http email-check-job \
    --location $REGION \
    --schedule "*/15 * * * *" \
    --uri "${SERVICE_URL}/api/check-now" \
    --http-method POST \
    --time-zone "$TIMEZONE" \
    --attempt-deadline 300s

# Create scheduler job for daily digest (8 AM)
echo -e "${YELLOW}Creating daily digest scheduler (8 AM)...${NC}"
gcloud scheduler jobs create http daily-digest-job \
    --location $REGION \
    --schedule "0 8 * * *" \
    --uri "${SERVICE_URL}/api/send-digest" \
    --http-method POST \
    --time-zone "$TIMEZONE" \
    --attempt-deadline 120s \
    --description "Send daily email digest at 8 AM" \
    2>/dev/null || \
gcloud scheduler jobs update http daily-digest-job \
    --location $REGION \
    --schedule "0 8 * * *" \
    --uri "${SERVICE_URL}/api/send-digest" \
    --http-method POST \
    --time-zone "$TIMEZONE" \
    --attempt-deadline 120s

echo -e "${GREEN}=== Scheduler Setup Complete ===${NC}"
echo ""
echo "Created scheduler jobs:"
echo "  1. email-check-job - Runs every 15 minutes"
echo "  2. daily-digest-job - Runs at 8 AM daily"
echo ""
echo "View jobs at: https://console.cloud.google.com/cloudscheduler"
echo ""
echo "To test the jobs manually:"
echo "  gcloud scheduler jobs run email-check-job --location $REGION"
echo "  gcloud scheduler jobs run daily-digest-job --location $REGION"
