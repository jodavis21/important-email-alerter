#!/bin/bash
# Deploy Important Email Alerter to Google Cloud Run

# Configuration - UPDATE THESE VALUES
PROJECT_ID="your-project-id"  # Your Google Cloud project ID
REGION="us-central1"          # Cloud Run region
SERVICE_NAME="email-alerter"  # Cloud Run service name

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}=== Deploying Important Email Alerter to Cloud Run ===${NC}"

# Check if gcloud is installed
if ! command -v gcloud &> /dev/null; then
    echo -e "${RED}Error: gcloud CLI is not installed${NC}"
    echo "Install it from: https://cloud.google.com/sdk/docs/install"
    exit 1
fi

# Check if logged in
if ! gcloud auth list --filter=status:ACTIVE --format="value(account)" | head -1 &> /dev/null; then
    echo -e "${YELLOW}Not logged in to gcloud. Running 'gcloud auth login'...${NC}"
    gcloud auth login
fi

# Set project
echo -e "${YELLOW}Setting project to ${PROJECT_ID}...${NC}"
gcloud config set project $PROJECT_ID

# Enable required APIs
echo -e "${YELLOW}Enabling required APIs...${NC}"
gcloud services enable run.googleapis.com
gcloud services enable cloudbuild.googleapis.com
gcloud services enable cloudscheduler.googleapis.com

# Build and deploy to Cloud Run
echo -e "${YELLOW}Building and deploying to Cloud Run...${NC}"
echo -e "${YELLOW}Note: You'll be prompted to set environment variables${NC}"

gcloud run deploy $SERVICE_NAME \
    --source . \
    --region $REGION \
    --platform managed \
    --allow-unauthenticated \
    --set-env-vars "DEBUG=false" \
    --set-env-vars "OAUTHLIB_INSECURE_TRANSPORT=0" \
    --timeout 300

# Get the service URL
SERVICE_URL=$(gcloud run services describe $SERVICE_NAME --region $REGION --format='value(status.url)')

echo -e "${GREEN}=== Deployment Complete ===${NC}"
echo -e "Service URL: ${GREEN}${SERVICE_URL}${NC}"
echo ""
echo -e "${YELLOW}=== IMPORTANT: Next Steps ===${NC}"
echo ""
echo "1. Set environment variables in Cloud Run Console:"
echo "   - Go to: https://console.cloud.google.com/run/detail/${REGION}/${SERVICE_NAME}/variables"
echo "   - Add the following environment variables:"
echo "     SECRET_KEY=<generate-a-secure-key>"
echo "     DATABASE_URL=<your-neon-postgresql-url>"
echo "     GOOGLE_CLIENT_ID=<your-google-client-id>"
echo "     GOOGLE_CLIENT_SECRET=<your-google-client-secret>"
echo "     GOOGLE_REDIRECT_URI=${SERVICE_URL}/auth/callback"
echo "     ANTHROPIC_API_KEY=<your-anthropic-api-key>"
echo "     PUSHOVER_USER_KEY=<your-pushover-user-key>"
echo "     PUSHOVER_API_TOKEN=<your-pushover-api-token>"
echo ""
echo "2. Update Google OAuth credentials:"
echo "   - Go to: https://console.cloud.google.com/apis/credentials"
echo "   - Edit your OAuth 2.0 Client"
echo "   - Add authorized redirect URI: ${SERVICE_URL}/auth/callback"
echo ""
echo "3. Set up Cloud Scheduler for automatic checks:"
echo "   Run: ./setup-scheduler.sh"
