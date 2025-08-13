# Google Cloud Scheduler Setup Guide

This guide walks you through setting up Google Cloud Scheduler to trigger your GitHub Actions workflow every 5 minutes for continuous traffic monitoring.

## Overview

The setup involves:
1. **Google Cloud Scheduler** - Triggers the workflow every 5 minutes
2. **GitHub Actions** - Runs the traffic monitoring application
3. **Repository Dispatch** - Allows external triggers to start GitHub workflows

## Prerequisites

### 1. Google Cloud Platform
- Active GCP project with billing enabled
- Cloud Scheduler API enabled
- Appropriate IAM permissions

### 2. GitHub Repository
- Public repository (as mentioned)
- GitHub Actions enabled
- Repository secrets configured

### 3. Required Tools
- `gcloud` CLI installed and configured
- Access to Google Cloud Console

## Step-by-Step Setup

### Step 1: Enable Google Cloud APIs

```bash
# Enable Cloud Scheduler API
gcloud services enable cloudscheduler.googleapis.com

# Enable Cloud Build API (if needed for more complex setups)
gcloud services enable cloudbuild.googleapis.com
```

### Step 2: Create GitHub Personal Access Token

1. Go to GitHub → Settings → Developer settings → Personal access tokens → Tokens (classic)
2. Click "Generate new token (classic)"
3. Set expiration and select scopes:
   - ✅ `repo` (Full control of private repositories)
   - ✅ `workflow` (Update GitHub Action workflows)
4. Copy the generated token (save it securely!)

### Step 3: Create Cloud Scheduler Job

#### Option A: Using Google Cloud Console (Recommended)

1. **Navigate to Cloud Scheduler**
   - Go to [Google Cloud Console](https://console.cloud.google.com/)
   - Select your project
   - Navigate to "Cloud Scheduler"

2. **Create New Job**
   - Click "CREATE JOB"
   - Fill in the following details:

   **Basic Information:**
   ```
   Name: traffic-monitoring-trigger
   Description: Triggers GitHub Actions for traffic monitoring every 5 minutes
   Frequency: */5 * * * *
   Timezone: Australia/Brisbane (or your preferred timezone)
   ```

   **Execution Details:**
   ```
   Target Type: HTTP
   URL: https://api.github.com/repos/YOUR_USERNAME/YOUR_REPO_NAME/dispatches
   HTTP Method: POST
   ```

   **Headers:**
   ```
   Authorization: token YOUR_GITHUB_TOKEN
   Accept: application/vnd.github.v3+json
   User-Agent: Google-Cloud-Scheduler
   Content-Type: application/json
   ```

   **Body:**
   ```json
   {
     "event_type": "traffic-monitoring-trigger",
     "client_payload": {
       "triggered_by": "google-cloud-scheduler",
       "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
     }
   }
   ```

#### Option B: Using gcloud CLI

```bash
# Set your variables
PROJECT_ID="your-gcp-project-id"
GITHUB_USERNAME="your-github-username"
REPO_NAME="your-repository-name"
GITHUB_TOKEN="your-github-personal-access-token"

# Create the Cloud Scheduler job
gcloud scheduler jobs create http traffic-monitoring-trigger \
    --location=australia-southeast1 \
    --schedule="*/5 * * * *" \
    --uri="https://api.github.com/repos/${GITHUB_USERNAME}/${REPO_NAME}/dispatches" \
    --http-method=POST \
    --headers="Authorization=token ${GITHUB_TOKEN},Accept=application/vnd.github.v3+json,User-Agent=Google-Cloud-Scheduler,Content-Type=application/json" \
    --message-body='{"event_type":"traffic-monitoring-trigger","client_payload":{"triggered_by":"google-cloud-scheduler"}}' \
    --description="Triggers GitHub Actions for traffic monitoring every 5 minutes"
```

### Step 4: Configure GitHub Repository Secrets

In your GitHub repository, go to Settings → Secrets and variables → Actions, and add these secrets:

#### Required Secrets:
```
SUPABASE_URL: your_supabase_project_url
SUPABASE_KEY: your_supabase_anon_key
API_KEY: your_queensland_traffic_api_key
GEOCODE_API_KEY: your_locationiq_geocoding_key
GROQ_API_KEY: your_groq_ai_api_key
TABLE_NAME: traffic_events (or your preferred table name)
```

#### Optional Variables:
```
LOG_LEVEL: INFO (or DEBUG for more verbose logging)
```

### Step 5: Set Up Route Data

Since your repository is public, ensure your route data is handled securely:

#### Option A: Store route_data.json in repository
```bash
# Add your route data file to the data directory
git add data/route_data.json
git commit -m "Add route data for traffic analysis"
git push
```

#### Option B: Use GitHub Secrets for route data (recommended for sensitive data)
1. Base64 encode your route data:
   ```bash
   base64 -i data/route_data.json
   ```
2. Add the encoded string as a secret: `ROUTE_DATA_BASE64`
3. Modify the GitHub Actions workflow to decode it:
   ```yaml
   - name: Setup route data
     run: |
       echo "${{ secrets.ROUTE_DATA_BASE64 }}" | base64 -d > data/route_data.json
   ```

### Step 6: Test the Setup

#### Manual Test
1. Go to your repository → Actions tab
2. Find the "Traffic Monitoring & Route Analysis" workflow
3. Click "Run workflow" to test manually

#### Scheduler Test
```bash
# Trigger the job manually to test
gcloud scheduler jobs run traffic-monitoring-trigger --location=australia-southeast1
```

### Step 7: Monitor the Setup

#### Check Scheduler Logs
```bash
# List recent job executions
gcloud scheduler jobs describe traffic-monitoring-trigger --location=australia-southeast1

# View execution logs
gcloud logging read "resource.type=cloud_scheduler_job AND resource.labels.job_id=traffic-monitoring-trigger" --limit=10
```

#### Monitor GitHub Actions
- Go to your repository → Actions tab
- Monitor workflow runs and execution logs
- Set up notifications for failed runs in repository settings

## Troubleshooting

### Common Issues

#### 1. Authentication Errors
```
Error: 401 Unauthorized
```
**Solution:** Verify your GitHub token has correct permissions and isn't expired.

#### 2. API Rate Limits
```
Error: 403 API rate limit exceeded
```
**Solution:** 
- Use a GitHub App instead of personal access token for higher rate limits
- Reduce frequency if hitting limits

#### 3. Scheduler Job Failures
```
Error: HTTP 422 or 404
```
**Solution:**
- Verify repository name and username are correct
- Ensure repository has GitHub Actions enabled
- Check that the workflow file exists in `.github/workflows/`

#### 4. Workflow Not Triggering
**Solution:**
- Verify the `event_type` in scheduler matches the workflow file
- Check repository dispatch permissions
- Ensure workflow file is on the default branch

### Monitoring Commands

```bash
# Check job status
gcloud scheduler jobs describe traffic-monitoring-trigger --location=australia-southeast1

# List all jobs
gcloud scheduler jobs list --location=australia-southeast1

# View recent executions
gcloud scheduler jobs describe traffic-monitoring-trigger --location=australia-southeast1 | grep -A 5 "lastAttemptTime"

# Pause/resume job
gcloud scheduler jobs pause traffic-monitoring-trigger --location=australia-southeast1
gcloud scheduler jobs resume traffic-monitoring-trigger --location=australia-southeast1
```

## Cost Considerations

### Google Cloud Scheduler Pricing
- **Free tier:** 3 jobs per month
- **Paid tier:** $0.10 per job per month (after free tier)
- **API calls:** First 1,000,000 calls free per month

### GitHub Actions Pricing (Public Repositories)
- **Public repositories:** Unlimited minutes
- **Private repositories:** 2,000 free minutes/month

### Estimated Monthly Cost
For this setup (5-minute intervals):
- Cloud Scheduler: ~$0.10/month (1 job)
- GitHub Actions: Free (public repository)
- **Total: ~$0.10/month**

## Security Best Practices

1. **Token Management**
   - Use GitHub App tokens instead of personal access tokens when possible
   - Rotate tokens regularly
   - Use minimum required permissions

2. **Secret Management**
   - Never commit secrets to the repository
   - Use GitHub encrypted secrets
   - Regularly audit secret access

3. **Network Security**
   - Consider using VPC if handling sensitive data
   - Monitor API access logs

4. **Monitoring**
   - Set up alerts for failed executions
   - Monitor API usage and costs
   - Regular health checks

## Advanced Configuration

### Custom Scheduling
```bash
# Run every 10 minutes
--schedule="*/10 * * * *"

# Run only during business hours (9 AM - 5 PM AEST, Monday-Friday)
--schedule="0 9-17 * * 1-5"

# Run every hour at minute 30
--schedule="30 * * * *"
```

### Multiple Environment Support
Create separate scheduler jobs for different environments:
```bash
# Production (every 5 minutes)
gcloud scheduler jobs create http traffic-monitoring-prod \
    --schedule="*/5 * * * *" \
    --message-body='{"event_type":"traffic-monitoring-trigger","client_payload":{"environment":"production"}}'

# Staging (every 15 minutes)
gcloud scheduler jobs create http traffic-monitoring-staging \
    --schedule="*/15 * * * *" \
    --message-body='{"event_type":"traffic-monitoring-trigger","client_payload":{"environment":"staging"}}'
```

## Support and Maintenance

### Regular Maintenance Tasks
- [ ] Monitor job execution logs weekly
- [ ] Review API usage and costs monthly  
- [ ] Rotate authentication tokens quarterly
- [ ] Update dependencies and review security settings

### Getting Help
- **Google Cloud Support:** [Cloud Scheduler Documentation](https://cloud.google.com/scheduler/docs)
- **GitHub Actions Support:** [GitHub Actions Documentation](https://docs.github.com/en/actions)
- **Repository Issues:** Use GitHub Issues for application-specific problems

---

**Next Steps:** After completing this setup, monitor the first few executions to ensure everything works correctly, then let the automated system handle your traffic monitoring! 🚀
