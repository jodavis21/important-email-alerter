# Important Email Alerter

A smart email monitoring application that uses AI to identify important emails and sends push notifications via Pushover.

## Features

- Monitor up to 3 Gmail accounts
- AI-powered importance detection using Claude Haiku
- Push notifications via Pushover for important emails
- Whitelist trusted senders and domains
- Web interface for configuration and monitoring
- Automatic checks every 15 minutes (when deployed)

## Quick Start

### 1. Prerequisites

- Python 3.11+
- A Neon PostgreSQL database (free tier: https://neon.tech)
- Google Cloud project with Gmail API enabled
- Anthropic API key (for Claude)
- Pushover account ($5 one-time: https://pushover.net)

### 2. Setup

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Copy and configure environment
cp .env.example .env
# Edit .env with your credentials

# Initialize database
python scripts/init_db.py

# Run locally
python run.py
```

### 3. Connect Gmail Accounts

1. Open http://localhost:5000 in your browser
2. Click "Accounts" in the navigation
3. Click "Connect Account" and authorize with Google
4. Repeat for up to 3 accounts

### 4. Configure Whitelist

1. Click "Whitelist" in the navigation
2. Add email addresses or domains you want to prioritize
3. Whitelisted senders get a +15% importance boost

### 5. Test Notifications

1. Click "Check Now" in the navigation bar
2. If important emails are found, you'll receive a Pushover notification

## Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URL` | PostgreSQL connection string | Required |
| `GOOGLE_CLIENT_ID` | Google OAuth client ID | Required |
| `GOOGLE_CLIENT_SECRET` | Google OAuth client secret | Required |
| `GOOGLE_REDIRECT_URI` | OAuth callback URL | `http://localhost:5000/auth/callback` |
| `ANTHROPIC_API_KEY` | Claude API key | Required |
| `PUSHOVER_USER_KEY` | Pushover user key | Required |
| `PUSHOVER_API_TOKEN` | Pushover API token | Required |
| `IMPORTANCE_THRESHOLD` | Minimum score to notify (0.0-1.0) | `0.7` |
| `CHECK_INTERVAL_MINUTES` | How often to check | `15` |
| `MAX_EMAILS_PER_CHECK` | Max emails per account | `50` |

## Deployment to Google Cloud Run

### 1. Create Google Cloud Project

```bash
# Set project
gcloud config set project YOUR_PROJECT_ID

# Enable required APIs
gcloud services enable run.googleapis.com
gcloud services enable cloudbuild.googleapis.com
gcloud services enable secretmanager.googleapis.com
```

### 2. Store Secrets

```bash
# Create secrets
echo -n "your-database-url" | gcloud secrets create DATABASE_URL --data-file=-
echo -n "your-client-id" | gcloud secrets create GOOGLE_CLIENT_ID --data-file=-
echo -n "your-client-secret" | gcloud secrets create GOOGLE_CLIENT_SECRET --data-file=-
echo -n "your-anthropic-key" | gcloud secrets create ANTHROPIC_API_KEY --data-file=-
echo -n "your-pushover-user" | gcloud secrets create PUSHOVER_USER_KEY --data-file=-
echo -n "your-pushover-token" | gcloud secrets create PUSHOVER_API_TOKEN --data-file=-
echo -n "$(openssl rand -hex 32)" | gcloud secrets create SECRET_KEY --data-file=-
```

### 3. Deploy

```bash
# Deploy using Cloud Build
gcloud builds submit --config cloudbuild.yaml
```

### 4. Set Up Cloud Scheduler

```bash
# Create scheduler job for every 15 minutes
gcloud scheduler jobs create http email-check-job \
    --location=us-central1 \
    --schedule="*/15 * * * *" \
    --uri="https://YOUR-SERVICE-URL/api/check-now" \
    --http-method=POST \
    --oidc-service-account-email=YOUR-SERVICE-ACCOUNT@PROJECT.iam.gserviceaccount.com
```

### 5. Update OAuth Redirect URI

Update your Google Cloud Console OAuth settings to include:
- `https://YOUR-SERVICE-URL/auth/callback`

## How It Works

1. **Polling**: Every 15 minutes, the system checks each connected Gmail account
2. **Fetching**: Uses Gmail API to fetch unread emails (incremental sync)
3. **Analysis**: Each email is analyzed by Claude Haiku for importance
4. **Scoring**: Emails are scored 0.0-1.0 based on content, sender, urgency
5. **Whitelist Boost**: Whitelisted senders get +15% score boost
6. **Notification**: Emails scoring >= 0.7 trigger Pushover notifications

### What Gets High Scores (0.7+)

- Financial alerts (fraud, bills, payments)
- Government/legal notices (tax deadlines, legal documents)
- Security alerts (unauthorized access, password resets)
- Account deactivation warnings
- Time-sensitive deadlines
- Health/medical communications

### What Gets Low Scores (<0.3)

- Marketing/promotional emails
- Newsletters
- Social media notifications
- Automated receipts (unless large amounts)
- Cold outreach

## Costs

| Service | Cost |
|---------|------|
| Google Cloud Run | Free tier (2M requests/month) |
| Neon PostgreSQL | Free tier (3 GB) |
| Claude Haiku | ~$1-2/month for typical usage |
| Pushover | $5 one-time |
| **Total** | **~$5 setup + $1-2/month** |

## License

MIT
