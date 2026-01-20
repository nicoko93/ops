# Build Portal - Claude Context

## Project Overview

Build Portal is a Flask web application that provides a unified interface to browse and download build artifacts from GCS and S3 buckets, view test reports, and monitor crash logs from Kubernetes deployments.

## Tech Stack

- **Backend**: Python 3, Flask
- **Frontend**: Jinja2 templates, Tailwind CSS (CDN), HTMX
- **Storage**: Google Cloud Storage (GCS), AWS S3
- **Database**: PostgreSQL (SQLAlchemy ORM)
- **Auth**: Google OAuth (OIDC)
- **Deployment**: Kubernetes (GKE), Helm chart, Jenkins CI/CD

## Project Structure

```
build-portal/
├── app/
│   ├── __init__.py         # Flask app factory, blueprint registration
│   ├── config.py           # Configuration from environment variables
│   ├── auth.py             # OAuth setup, login_required decorator
│   ├── routes.py           # All blueprints and routes
│   ├── storage.py          # GCS/S3 client helpers
│   ├── models.py           # SQLAlchemy models (TestRun, TestResult)
│   ├── crash_logs.py       # Crash log listing and viewing logic
│   └── templates/
│       ├── base.html       # Base template with nav
│       ├── index.html      # Main dashboard
│       ├── crash_logs/     # Crash log templates
│       │   ├── list.html   # Tree view of logs
│       │   └── view.html   # Log content viewer
│       └── ...
├── build-portal/           # Helm chart
│   ├── Chart.yaml
│   ├── values.yaml
│   └── templates/
│       ├── deployment.yaml
│       ├── configmap.yaml  # Environment variables
│       └── ...
├── Jenkinsfile             # CI/CD pipeline
├── Dockerfile
├── requirements.txt
└── wsgi.py                 # WSGI entry point
```

## Key Patterns

### Blueprints
Routes are organized into Flask Blueprints:
- `ui_bp` - Main UI routes (index, login, download)
- `test_results_api` - API endpoints for test results
- `test_results_ui` - Test results UI
- `crash_logs_bp` - Crash log viewer (`/crash-logs/`)

### Configuration
All config via environment variables in `app/config.py`:
```python
CRASH_LOGS_BUCKET = os.getenv("CRASH_LOGS_BUCKET", "app-crash-logs")
```

Helm chart passes env vars via ConfigMap (see `build-portal/templates/configmap.yaml`).

### GCS Access
Use the `gcs_client()` helper from `storage.py`:
```python
from .storage import gcs_client
client = gcs_client()
bucket = client.bucket(bucket_name)
```

### Authentication
All routes requiring login use the `@login_required` decorator from `auth.py`.

### Templates
- Extend `base.html` for consistent layout
- Use Tailwind CSS classes for styling
- Pass `user=session.get("user")` to templates for nav display

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `GCP_SA_FILE` | Path to GCP service account JSON | `/var/secrets/google/key.json` |
| `GCP_PROJECT_ID` | GCP project ID | `my-project` |
| `CRASH_LOGS_BUCKET` | GCS bucket for crash logs | `app-crash-logs` |
| `CRASH_LOGS_PREFIX` | Prefix path in bucket | `crash-logs/` |
| `GOOGLE_CLIENT_ID` | OAuth client ID | - |
| `GOOGLE_CLIENT_SECRET` | OAuth client secret | - |

## Deployment

Push to `master` branch triggers Jenkins pipeline which:
1. Builds Docker image
2. Pushes to Artifact Registry
3. Deploys via Helm to GKE

## Common Tasks

### Adding a new feature
1. Add config to `app/config.py`
2. Create module in `app/` (e.g., `crash_logs.py`)
3. Add blueprint and routes to `app/routes.py`
4. Register blueprint in `app/__init__.py`
5. Create templates in `app/templates/`
6. Update `base.html` nav if needed
7. Add env vars to Helm chart (`values.yaml`, `configmap.yaml`)

### Running locally
```bash
export GCP_SA_FILE=/path/to/key.json
export GOOGLE_CLIENT_ID=...
export GOOGLE_CLIENT_SECRET=...
flask run
```
