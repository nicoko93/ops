#!/usr/bin/env bash
set -euo pipefail

# ---------- Defaults (overridable via env) ----------
PROJECT_ID="${PROJECT_ID:-my-project}"
REGION="${REGION:-europe-west1}"
REPOSITORY="${REPOSITORY:-main}"                  # AR repo name (not Git)
IMAGE_NAME="${IMAGE_NAME:-build-portal-v2}"
PLATFORM="${PLATFORM:-linux/amd64}"              # used for Docker path only
REGISTRY_HOST="${REGION}-docker.pkg.dev"
IMAGE_URI="${REGISTRY_HOST}/${PROJECT_ID}/${REPOSITORY}/${IMAGE_NAME}"

# Choose builder: docker|buildah|auto
BUILDER="${BUILDER:-auto}"
USE_LATEST="${USE_LATEST:-0}"                    # 1 to also tag/push :latest
KEY_PATH="${KEY_PATH:-${GOOGLE_APPLICATION_CREDENTIALS:-}}"

# ---------- Tag ----------
# Priority: argv $1 > TAG env > short git SHA > date
ARG_TAG="${1:-}"
ENV_TAG="${TAG:-}"
if [[ -n "${ARG_TAG}" ]]; then
  TAG="${ARG_TAG}"
elif [[ -n "${ENV_TAG}" ]]; then
  TAG="${ENV_TAG}"
else
  if git rev-parse --git-dir >/dev/null 2>&1; then
    TAG="$(git rev-parse --short HEAD)"
  else
    TAG="$(date -u +%Y%m%d%H%M%S)"
  fi
fi

echo "-------------------------------------------"
echo "Project        : ${PROJECT_ID}"
echo "Region         : ${REGION}"
echo "Repository     : ${REPOSITORY}"
echo "Image          : ${IMAGE_NAME}"
echo "Platform       : ${PLATFORM}"
echo "Tag            : ${TAG}"
echo "Full Image URI : ${IMAGE_URI}"
echo "-------------------------------------------"

# ---------- Pick builder ----------
if [[ "${BUILDER}" == "auto" ]]; then
  if command -v docker >/dev/null 2>&1; then
    BUILDER="docker"
  elif command -v buildah >/dev/null 2>&1; then
    BUILDER="buildah"
  else
    echo "❌ Neither docker nor buildah found"; exit 1
  fi
fi
echo "Builder        : ${BUILDER}"

# ---------- Prechecks ----------
[[ -f "Dockerfile" ]] || { echo "❌ Dockerfile introuvable dans le dossier courant"; exit 1; }

if [[ "${BUILDER}" == "docker" ]]; then
  command -v gcloud >/dev/null 2>&1 || { echo "❌ gcloud manquant"; exit 1; }
  command -v docker >/dev/null 2>&1 || { echo "❌ docker manquant"; exit 1; }
  echo "🔐 Docker login via gcloud to ${REGISTRY_HOST}…"
  gcloud auth configure-docker "${REGISTRY_HOST}" -q
else
  command -v buildah >/dev/null 2>&1 || { echo "❌ buildah manquant"; exit 1; }
  [[ -n "${KEY_PATH}" && -f "${KEY_PATH}" ]] || { echo "❌ KEY_PATH/GOOGLE_APPLICATION_CREDENTIALS invalide: ${KEY_PATH:-unset}"; exit 1; }
  echo "🔐 Buildah login to ${REGISTRY_HOST} with JSON key (stdin)…"
  # Avoid leaking the JSON key in logs:
  buildah login --username _json_key --password-stdin "${REGISTRY_HOST}" < "${KEY_PATH}"
fi

# ---------- Build ----------
GIT_SHA="$(git rev-parse --short HEAD 2>/dev/null || echo nosha)"
if [[ "${BUILDER}" == "docker" ]]; then
  echo "🏗️  docker build…"
  docker build \
    --platform "${PLATFORM}" \
    --build-arg GIT_TAG="${TAG}" \
    --build-arg GIT_SHA="${GIT_SHA}" \
    -t "${IMAGE_URI}:${TAG}" \
    $( [[ "${USE_LATEST}" == "1" ]] && echo "-t ${IMAGE_URI}:latest" ) \
    .
else
  echo "🏗️  buildah bud…"
  # --platform is not always supported by buildah; omit by default
  buildah bud --format docker -t "${IMAGE_URI}:${TAG}" .
  if [[ "${USE_LATEST}" == "1" ]]; then
    buildah tag "${IMAGE_URI}:${TAG}" "${IMAGE_URI}:latest"
  fi
fi

# ---------- Push ----------
echo "🚀 Push ${IMAGE_URI}:${TAG}"
if [[ "${BUILDER}" == "docker" ]]; then
  docker push "${IMAGE_URI}:${TAG}"
else
  buildah push "${IMAGE_URI}:${TAG}"
fi

if [[ "${USE_LATEST}" == "1" ]]; then
  echo "🚀 Push ${IMAGE_URI}:latest"
  if [[ "${BUILDER}" == "docker" ]]; then
    docker push "${IMAGE_URI}:latest"
  else
    buildah push "${IMAGE_URI}:latest"
  fi
fi

echo "✅ Terminé !"
echo "    ${IMAGE_URI}:${TAG}"
[[ "${USE_LATEST}" == "1" ]] && echo "    ${IMAGE_URI}:latest"
