Got it — I’ll answer in **English** from now on. Here’s a clean, copy-pasteable README section in English that covers running the playbook and managing the Ansible Vault.

---

# Build Portal 2.0

Flask + Authlib + Tailwind + Postgres, deployable with **Helm** via **Ansible**.

## Environment variables

* `SECRET_KEY`
* `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`
* `GOOGLE_ALLOWED_DOMAIN` (e.g. `example.com`)
* `GCP_PROJECT_ID` (default: `my-project`)
* `GCP_SA_FILE` (default: `/var/secrets/google/key.json`)
* `GCS_BUCKETS` (comma-separated)
* `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION`
* `S3_SOURCES` (e.g. `bucketA:path/;bucketB:path/`)
* `REPORT_BUCKET`, `CC_REPORT_PREFIX`
* `DATABASE_URL` (Postgres SQLAlchemy URL)
* `API_KEY` (CI webhook `/api/parse-and-save`)
* `JENKINS_DEFAULT_URL`

## Local development

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export FLASK_APP=wsgi.py
flask run -p 8080
```

---

## Deploy with **Ansible + Helm** (no temp files)

**Layout (inside `ansible/`)**

```
ansible/
├── ansible.cfg
├── collections/requirements.yml
├── deploy-build-portal.yml
├── build-portal-values.yml.j2        # Helm values template (Jinja2)
├── group_vars/
│   └── all.yml                       # common vars for all envs
├── inventories/
│   ├── staging/
│   │   └── group_vars/
│   │       ├── all.yml               # non-secret env vars (staging)
│   │       └── secrets.yml           # vaulted (staging)
│   └── production/
│       └── group_vars/
│           ├── all.yml               # non-secret env vars (prod)
│           └── secrets.yml           # vaulted (prod)
└── vault-password.sh                 # echoes the vault password
```

**Prereqs**

* `kubectl` points to the cluster you want to deploy to.
* `helm` is installed on the machine running Ansible.
* Install required collections:

  ```bash
  cd ansible
  ansible-galaxy collection install -r collections/requirements.yml
  ```

**Run the playbook**

Staging:

```bash
cd ansible
ansible-playbook -i inventories/staging deploy-build-portal.yml
```

Production:

```bash
cd ansible
ansible-playbook -i inventories/production deploy-build-portal.yml
```

Optional overrides:

```bash
ansible-playbook -i inventories/staging deploy-build-portal.yml \
  -e release_name=build-portal \
  -e k8s_namespace=build-portal \
  -e docker_image_tag=$(git rev-parse --short HEAD)
```

The playbook loads:

1. `ansible/group_vars/all.yml`
2. `ansible/inventories/<env>/group_vars/all.yml`
3. `ansible/inventories/<env>/group_vars/secrets.yml` (vault)
   Then renders `build-portal-values.yml.j2` **in memory** and feeds it to Helm.

---

## Ansible Vault management

Your `ansible.cfg`:

```ini
[defaults]
inventory = inventories
vault_password_file = ./vault-password.sh
stdout_callback = yaml
host_key_checking = False
retry_files_enabled = False
interpreter_python = auto
```

`vault-password.sh`:

```bash
#!/usr/bin/env bash
echo "<REDACTED_VAULT_PASSWORD>"
```

> **WSL / world-writable note:**
> Ansible ignores `ansible.cfg` if your working dir is world-writable.
> Fix by running from a non world-writable path (e.g. under `/home/<user>`), **or** pass `--vault-password-file ./vault-password.sh` explicitly on each `ansible-vault` command.

**Encrypt for the first time**

```bash
# Staging
ansible-vault encrypt inventories/staging/group_vars/secrets.yml \
  --vault-password-file ./vault-password.sh

# Production
ansible-vault encrypt inventories/production/group_vars/secrets.yml \
  --vault-password-file ./vault-password.sh
```

**Edit the vault**

```bash
ansible-vault edit inventories/staging/group_vars/secrets.yml \
  --vault-password-file ./vault-password.sh
```

**View the vault**

```bash
ansible-vault view inventories/staging/group_vars/secrets.yml \
  --vault-password-file ./vault-password.sh
```

**Rekey (change password)**

```bash
ansible-vault rekey inventories/staging/group_vars/secrets.yml \
  --vault-password-file ./vault-password.sh \
  --new-vault-password-file ./vault-password.sh
```

---

## Example variables

`inventories/staging/group_vars/secrets.yml` (vaulted):

```yaml
secret_key: "change-me-staging"
google_client_id: "xxxxx.apps.googleusercontent.com"
google_client_secret: "xxxxx"
api_key: "super-secret-api-key"
database_url: "postgresql+psycopg2://buildportal:buildportal@build-portal-postgresql:5432/buildportal"
```

`inventories/staging/group_vars/all.yml`:

```yaml
release_name: build-portal
k8s_namespace: build-portal

image_repository: europe-west1-docker.pkg.dev/my-project/main/build-portal-v2
docker_image_tag: latest   # You can override with -e docker_image_tag=$(git rev-parse --short HEAD)

gateway:
  enabled: true
  host: builds-new.example.com
  parentRef:
    name: cluster-gateway
    namespace: gateway-system
    sectionName: https

env:
  google_allowed_domain: "example.com"
  gcp_project_id: "my-project"
  report_bucket_name: "test-reports"
  jenkins_default_url: "https://jenkins-production.example.com/job/Unity-LTS-Tests/"
```

`build-portal-values.yml.j2` (snippet):

```jinja2
image:
  repository: {{ image_repository }}
  tag: "{{ docker_image_tag }}"

gateway:
  enabled: {{ gateway.enabled | default(true) }}
  host: {{ gateway.host | quote }}
  parentRef:
    name: {{ gateway.parentRef.name }}
    namespace: {{ gateway.parentRef.namespace }}
    sectionName: {{ gateway.parentRef.sectionName }}

config:
  SECRET_KEY: "{{ secret_key }}"
  GOOGLE_CLIENT_ID: "{{ secret.google_client_id }}"
  GOOGLE_CLIENT_SECRET: "{{ secret.google_client_secret }}"
  GOOGLE_ALLOWED_DOMAIN: "{{ config.google_allowed_domain }}"
  GCP_PROJECT_ID: "{{ config.gcp_project_id }}"
  GCP_SA_FILE: "/var/secrets/google/key.json"
  REPORT_BUCKET_NAME: "{{ config.report_bucket_name }}"
  JENKINS_DEFAULT_URL: "{{ config.jenkins_default_url }}"
  API_KEY: "{{ api_key }}"
  DATABASE_URL: "{{ database_url }}"
```

---

## Uninstall the Helm release

```bash
helm uninstall build-portal -n build-portal
# optionally remove PVCs and namespace:
kubectl delete pvc -n build-portal --all
kubectl delete namespace build-portal
```