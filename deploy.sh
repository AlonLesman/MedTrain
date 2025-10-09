#!/bin/bash
# Simple deployment script that uses your existing .env file

set -e

echo "🚀 Deploying MedTrain to Cloud Run"
echo "=================================="

# Load environment variables from .env
if [ -f ".env" ]; then
    echo "📋 Loading configuration from .env file..."
    # Load only valid KEY=VALUE lines, ignore comments and empty lines
    set -a
    source <(grep -E '^[A-Z_]+=' .env)
    set +a
else
    echo "❌ .env file not found!"
    exit 1
fi

# Configuration
SERVICE_NAME="medtrain"
REGION="us-central1"

# Check if gcloud is installed
if ! command -v gcloud &> /dev/null; then
    echo "❌ gcloud CLI not found. Please install it first:"
    echo "   https://cloud.google.com/sdk/docs/install"
    exit 1
fi

# Check authentication
if ! gcloud auth list --filter=status:ACTIVE --format="value(account)" | grep -q .; then
    echo "❌ Not authenticated. Running: gcloud auth login"
    gcloud auth login
fi

# Get project ID
if [ -z "$GOOGLE_CLOUD_PROJECT" ]; then
    echo ""
    echo "📋 Available projects:"
    gcloud projects list
    echo ""
    echo "⚠️  Enter the PROJECT_ID (first column), NOT the project number!"
    read -p "Enter your Project ID: " PROJECT_ID
else
    PROJECT_ID="$GOOGLE_CLOUD_PROJECT"
fi

echo ""
echo "📋 Deployment Configuration:"
echo "   Project: $PROJECT_ID"
echo "   Service: $SERVICE_NAME"
echo "   Region: $REGION"
echo "   OpenAI Key: ${OPENAI_API_KEY:0:20}..."
echo "   Password: ${PIPELINE_PASSWORD:-'not set'}"
echo ""

# Set defaults if not loaded
PIPELINE_PASSWORD=${PIPELINE_PASSWORD:-"changeme"}
FLASK_SECRET_KEY=${FLASK_SECRET_KEY:-$(openssl rand -hex 32 2>/dev/null || echo "dev-secret-$(date +%s)")}
MODEL=${MODEL:-"gpt-4.1"}

# Set the project
gcloud config set project $PROJECT_ID

# Enable required APIs
echo "🔧 Enabling required APIs..."
gcloud services enable run.googleapis.com
gcloud services enable secretmanager.googleapis.com
gcloud services enable forms.googleapis.com
gcloud services enable drive.googleapis.com

# Deploy to Cloud Run
echo ""
echo "🚀 Deploying to Cloud Run..."
gcloud run deploy $SERVICE_NAME \
    --source . \
    --platform managed \
    --region $REGION \
    --allow-unauthenticated \
    --memory 2Gi \
    --cpu 2 \
    --timeout 1800 \
    --max-instances 10 \
    --set-env-vars "ENVIRONMENT=production,OPENAI_API_KEY=$OPENAI_API_KEY,PIPELINE_PASSWORD=$PIPELINE_PASSWORD,FLASK_SECRET_KEY=$FLASK_SECRET_KEY,MODEL=$MODEL"

# Upload Google OAuth secrets
echo ""
echo "📦 Setting up Google OAuth credentials..."

if [ -f "client_secret.json" ]; then
    echo "Uploading client_secret.json..."
    gcloud secrets create client-secret --data-file=client_secret.json 2>/dev/null || \
    gcloud secrets versions add client-secret --data-file=client_secret.json
    
    gcloud run services update $SERVICE_NAME \
        --region $REGION \
        --update-secrets /secrets/client_secret.json=client-secret:latest
    echo "✅ client_secret.json uploaded"
else
    echo "⚠️  client_secret.json not found"
fi

if [ -f "token.pkl" ]; then
    echo "Uploading token.pkl..."
    gcloud secrets create oauth-token --data-file=token.pkl 2>/dev/null || \
    gcloud secrets versions add oauth-token --data-file=token.pkl
    
    gcloud run services update $SERVICE_NAME \
        --region $REGION \
        --update-secrets /secrets/token.pkl=oauth-token:latest
    echo "✅ token.pkl uploaded"
else
    echo "⚠️  token.pkl not found"
fi

# Get the service URL
SERVICE_URL=$(gcloud run services describe $SERVICE_NAME --region $REGION --format="value(status.url)")

echo ""
echo "✅ Deployment Complete!"
echo "=================================="
echo "🌐 Your app is live at:"
echo "   $SERVICE_URL"
echo ""
echo "🔐 Login with:"
echo "   Password: $PIPELINE_PASSWORD"
echo ""
echo "📊 Useful commands:"
echo "   Logs:    gcloud run services logs read $SERVICE_NAME --region $REGION --limit 50"
echo "   Update:  ./deploy_simple.sh"
echo ""

