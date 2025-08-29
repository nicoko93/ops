#!/usr/bin/env bash
set -euo pipefail

# Name of the GCP secret (can be overridden via SECRET_NAME)
SECRET_NAME="${SECRET_NAME:-build-portal}"
# GCP project (defaults to what you already use)
GCP_PROJECT="${CLOUDSDK_CORE_PROJECT:-my-company}"

# If the script is "sourced", export the variable and exit
if [[ "${BASH_SOURCE[0]}" != "$0" ]]; then
  # Ansible accepts either a path to a file or an executable returning the password
  export ANSIBLE_VAULT_PASSWORD_FILE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/$(basename "${BASH_SOURCE[0]}")"
  return 0 2>/dev/null || exit 0
fi

# Execution mode: print the password (no other output)
exec gcloud secrets versions access latest \
  --secret="${SECRET_NAME}" \
  --project="${GCP_PROJECT}" \
  --quiet
