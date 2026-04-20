# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Build Portal is a Flask web application for browsing/downloading build artifacts from GCS and S3 buckets, viewing test reports, monitoring crash logs from Kubernetes deployments, and triggering Jenkins deploy pipelines.

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
- `JENKINS_URL`, `JENKINS_DEPLOY_TOKEN` - Jenkins trigger for Deploy-Quest

## Architecture

### Flask App Factory Pattern
Entry point is `wsgi.py` → `app.create_app()` in `app/__init__.py` which initializes OAuth, database, and registers all blueprints.

### Blueprints (all defined in `app/routes.py`)
All blueprints and route handlers live in the single `app/routes.py` file (not split per feature):
- `ui_bp` - Main UI: index, auth routes, file downloads, health check (`/`, `/login`, `/download/...`)
- `test_results_api` - CI webhook and stats API (`/api/parse-and-save`, `/api/stats`)
- `test_results_ui` - Test results UI (`/stats`)
- `crash_logs_bp` - Crash log viewer UI (`/crash-logs/`)
- `crash_logs_api` - Crash log REST API with Bearer token auth (`/api/crash-logs/`)
- `deploy_quest_bp` - Trigger Jenkins Deploy-Quest pipeline for Android builds (`/deploy-quest/`)

### Authentication - Two Patterns
1. **Browser sessions** (`app/auth.py`): Google OAuth via Authlib → `@login_required` decorator, `domain_allowed()` check against `GOOGLE_ALLOWED_DOMAIN`
2. **API Bearer tokens** (`app/token_auth.py`): Google OIDC ID tokens → `@require_bearer_token` decorator, validates JWT signature + issuer + hosted domain. Used by `crash_logs_api` for agent/service access.

### Key Modules
- `app/auth.py` - OAuth setup, `@login_required` decorator, `domain_allowed()` check
- `app/token_auth.py` - `@require_bearer_token` decorator for API routes (Google OIDC JWT validation)
- `app/storage.py` - GCS/S3 clients: `gcs_client()`, `s3_client()`, signed URLs, listing functions
- `app/crash_logs.py` - Crash log helpers: `list_crash_logs()`, `get_crash_log_content()`, `group_logs_by_hierarchy()`
- `app/models.py` - SQLAlchemy models: `TestRun`, `TestResult` (PostgreSQL + JSONB)
- `app/config.py` - All config via environment variables (single `Config` class)

### Database Models
- `TestRun` - Test suite execution metadata (suite_name, result, pass/fail counts, JSONB extra_data)
- `TestResult` - Individual test results linked to TestRun via `test_run_id`
- Database sessions use `SessionLocal()` from `app/models.py` (manual open/close, not Flask-SQLAlchemy)

### Storage Access
S3 uses `s3_client()` for us-east-1. GCS uses service account credentials from `GCP_SA_FILE`.

### Crash Logs Path Structure
Logs are stored in GCS with path: `crash-logs/{env}/{namespace}/{pod}/{container}_{timestamp}.log`
- Parsed by `parse_crash_log_path()` to extract environment, namespace, deployment, pod, container
- Deployment name extracted from pod name (strips replicaset and pod hash suffixes)

### HTMX Partials
Some pages use HTMX for dynamic content refresh. Partial templates are prefixed with `_` (e.g., `_builds_table.html`) and served from dedicated endpoints (e.g., `/deploy-quest/builds`).

### Template Pattern
- Extend `base.html` for consistent layout and nav
- Use Tailwind CSS classes (loaded via CDN)
- Pass `user=session.get("user")` to templates for nav display

## Deployment

- **CI/CD**: Push to `master` → Jenkins builds Docker image → pushes to Artifact Registry → deploys via Ansible/Helm to GKE
- **Staging**: Push to `dev` branch deploys to staging environment
- **Helm chart**: Located in `build-portal/` directory
- **Ansible playbooks**: Located in `ansible/` directory, with per-environment inventory vars and vaulted secrets

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
2. Add routes to `app/routes.py` as a new Blueprint (all routes live in this single file)
3. Register blueprint in `app/__init__.py`
4. Create templates in `app/templates/<feature>/` (use `_` prefix for HTMX partials)
5. Update `base.html` nav if adding a new section
6. For API-only routes: use `@require_bearer_token` from `app/token_auth.py`
7. Add env vars to Helm chart (`values.yaml`, `configmap.yaml`)
