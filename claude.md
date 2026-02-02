# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Build Portal is a Flask web application for browsing/downloading build artifacts from GCS and S3 buckets, viewing test reports, and monitoring crash logs from Kubernetes deployments.

**Tech Stack**: Python 3 / Flask, Jinja2 templates + Tailwind CSS + HTMX, PostgreSQL (SQLAlchemy), Google OAuth, GCS/S3 storage

## Development Commands

```bash
# Setup
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Run locally (requires env vars set)
export FLASK_APP=wsgi.py
flask run -p 8080

# Production server
gunicorn -b 0.0.0.0:8080 wsgi:app
```

### Environment Variables

**Required for local dev:**
- `GCP_SA_FILE` - Path to GCP service account JSON
- `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` - OAuth credentials

**Optional/Feature-specific:**
- `DATABASE_URL` - PostgreSQL connection string (required for test results features)
- `GOOGLE_ALLOWED_DOMAIN` - Restrict OAuth to domain (e.g., `example.com`)
- `GCS_BUCKETS` - Comma-separated list of GCS buckets to browse
- `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION` - S3 access
- `S3_SOURCES` - S3 sources format: `bucketA:path/;bucketB:path/`
- `API_KEY` - CI webhook authentication for `/api/parse-and-save`
- `CRASH_LOGS_BUCKET`, `CRASH_LOGS_PREFIX` - Crash log storage location
- `RANCHER_BASE_URL`, `RANCHER_CLUSTER_IDS` - Rancher integration for crash log quick links

## Architecture

### Flask App Factory Pattern
Entry point is `wsgi.py` → `app.create_app()` which initializes OAuth, database, and registers blueprints.

### Blueprints
- `ui_bp` - Main UI: index, auth routes, file downloads (`/`, `/login`, `/download/...`)
- `test_results_api` - CI webhook and stats API (`/api/parse-and-save`, `/api/stats`)
- `test_results_ui` - Test results UI (`/stats`)
- `crash_logs_bp` - Crash log viewer (`/crash-logs/`)

### Key Modules
- `app/auth.py` - OAuth setup, `@login_required` decorator, `domain_allowed()` check
- `app/storage.py` - GCS/S3 clients: `gcs_client()`, `list_gcs_bucket()`, `gcs_signed_url()`, etc.
- `app/crash_logs.py` - Crash log helpers: `list_crash_logs()`, `get_crash_log_content()`, `group_logs_by_hierarchy()`
- `app/models.py` - SQLAlchemy models: `TestRun`, `TestResult` (PostgreSQL + JSONB)
- `app/config.py` - All config via environment variables

### Database Models
- `TestRun` - Test suite execution metadata (suite_name, result, pass/fail counts, JSONB extra_data)
- `TestResult` - Individual test results linked to TestRun via `test_run_id`

### Crash Logs Path Structure
Logs are stored in GCS with path: `crash-logs/{env}/{namespace}/{pod}/{container}_{timestamp}.log`
- Parsed by `parse_crash_log_path()` to extract environment, namespace, deployment, pod, container
- Deployment name extracted from pod name (strips replicaset and pod hash suffixes)

### Configuration Pattern
All config is loaded from environment variables in `app/config.py`. For Kubernetes deployment, these are set via Helm chart ConfigMap (`build-portal/templates/configmap.yaml`).

### GCS Access Pattern
```python
from .storage import gcs_client
client = gcs_client()
bucket = client.bucket(bucket_name)
```

### Template Pattern
- Extend `base.html` for consistent layout and nav
- Use Tailwind CSS classes (loaded via CDN)
- Pass `user=session.get("user")` to templates for nav display

## Deployment

- **CI/CD**: Push to `master` → Jenkins builds Docker image → pushes to Artifact Registry → deploys via Ansible/Helm to GKE
- **Staging**: Push to `dev` branch deploys to staging environment
- **Helm chart**: Located in `build-portal/` directory
- **Ansible playbooks**: Located in `ansible/` directory

### Deploy Commands
```bash
cd ansible
# Staging
ansible-playbook -i inventories/staging deploy-build-portal.yml
# Production
ansible-playbook -i inventories/production deploy-build-portal.yml
# With overrides
ansible-playbook -i inventories/staging deploy-build-portal.yml \
  -e docker_image_tag=$(git rev-parse --short HEAD)
```

## Adding a New Feature

1. Add config to `app/config.py` (read from env var)
2. Create module in `app/` (e.g., `new_feature.py`)
3. Define blueprint and routes
4. Register blueprint in `app/__init__.py`
5. Create templates in `app/templates/`
6. Update `base.html` nav if adding a new section
7. Add env vars to Helm chart (`values.yaml`, `configmap.yaml`)
