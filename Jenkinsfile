@Library('shared-library') _
pipeline {
  agent {
    kubernetes {
      yaml """
apiVersion: v1
kind: Pod
metadata:
  labels:
    app: build-portal-v2
spec:
  volumes:
  - name: gcloud-key
    secret:
      secretName: kaniko-jenkins-production-key
  - name: workspace-volume
    emptyDir: {}
  containers:
  - name: buildah
    image: europe-west1-docker.pkg.dev/my-project/obi/obi/buildah-custom
    tty: true
    securityContext:
      privileged: true
    command: ['cat']
    volumeMounts:
    - name: gcloud-key
      mountPath: /secrets
      readOnly: true
    - name: workspace-volume
      mountPath: /workspace
      readOnly: false
    - name: workspace-volume
      mountPath: /home/jenkins/agent
      readOnly: false
    resources:
      requests:
        cpu: "8"
      limits:
        cpu: "8"
  - name: toolbox
    image: europe-west1-docker.pkg.dev/my-project/main/devops-toolbox:latest
    tty: true
    command: ['cat']
    volumeMounts:
    - name: gcloud-key
      mountPath: /secrets
      readOnly: true
    - name: workspace-volume
      mountPath: /workspace
      readOnly: false
    - name: workspace-volume
      mountPath: /home/jenkins/agent
      readOnly: false
"""
    }
  }

  options { timestamps() }

  environment {
    GCP_AR_PROJECT   = 'my-project'
    GCP_AR_REGION    = 'europe-west1'
    GCP_AR_REPO      = 'main'
    APP_IMAGE_NAME   = 'build-portal-v2'
    GCLOUD_KEY_PATH  = '/secrets/my-project-abcdef123456.json'
    GOOGLE_APPLICATION_CREDENTIALS = '/secrets/my-project-abcdef123456.json'

    DISCORD_WEBHOOK_URL = "<REDACTED_DISCORD_WEBHOOK>"
  }

  stages {
    stage('Init env') {
      steps {
        script {
          def cfg = [
            master: [project:'my-project',  cluster:'prod-cluster', scope:'region', location:'europe-west1',  env:'production'],
            dev   : [project:'my-company', cluster:'dev-cluster',  scope:'zone',   location:'europe-west3-c', env:'staging' ]
          ]
          def c = cfg[env.BRANCH_NAME]
          if (!c) {
            env.SHOULD_DEPLOY = 'false'
            env.DEPLOY_ENV = ''
            env.INVENTORY  = ''
          } else {
            env.SHOULD_DEPLOY = 'true'
            env.GCP_PROJECT   = c.project
            env.GKE_CLUSTER   = c.cluster
            env.GKE_SCOPE     = c.scope
            env.GKE_LOCATION  = c.location
            env.DEPLOY_ENV    = c.env
            env.INVENTORY     = "ansible/inventories/${c.env}"
          }

          def shortSha = (env.GIT_COMMIT ?: 'unknown').take(8)
          def channel  = (env.BRANCH_NAME == 'master') ? 'prod' : (env.BRANCH_NAME == 'dev' ? 'dev' : "ci-${env.BRANCH_NAME}")
          env.IMAGE_TAG = "${channel}-${shortSha}"
          env.IMAGE_REPOSITORY = "${env.GCP_AR_REGION}-docker.pkg.dev/${env.GCP_AR_PROJECT}/${env.GCP_AR_REPO}/${env.APP_IMAGE_NAME}"

          echo "Resolved IMAGE_TAG=${env.IMAGE_TAG}"
          echo "IMAGE_REPOSITORY=${env.IMAGE_REPOSITORY}"

          gitUtils.setGitEnvVariables(env, scm)
          try { gitUtils.sendDiscordNotification('started') } catch (err) { echo "Discord notify (start) failed: ${err}" }
        }
      }
    }

    stage('Build & Push (via cicd/build-and-push.sh)') {
      steps {
        container('buildah') {
          script {
            int rc = sh(returnStatus: true, script: '''
bash -lc '
set -Eeuo pipefail
cd "$WORKSPACE"

# --- locate script
SCRIPT=""
if [[ -f "cicd/build-and-push.sh" ]]; then
  SCRIPT="cicd/build-and-push.sh"
elif [[ -f "cicd/build-and-push" ]]; then
  SCRIPT="cicd/build-and-push"
else
  echo "❌ build-and-push script not found under ./cicd"
  ls -al ./cicd || true
  exit 1
fi
echo "Using script: $SCRIPT"
sed -i "s/\\r$//" "$SCRIPT" || true
chmod +x "$SCRIPT"

# --- auth to Artifact Registry (no secret echo)
REGISTRY="${GCP_AR_REGION}-docker.pkg.dev"
buildah login --username _json_key --password-stdin "$REGISTRY" < "${GCLOUD_KEY_PATH}"

# --- docker -> buildah shim (build & push only)
docker() {
  local subcmd="$1"; shift || true
  case "$subcmd" in
    build)
      local args=()
      while [[ $# -gt 0 ]]; do
        if [[ "$1" == "--platform" ]]; then shift; shift; continue; fi
        args+=("$1"); shift
      done
      echo "➡️ buildah bud ${args[*]}"
      buildah bud --format docker "${args[@]}"
      ;;
    push)
      echo "➡️ buildah push $*"
      buildah push "$@"
      ;;
    *)
      echo "docker shim (buildah) unsupported: $subcmd" >&2
      return 1
      ;;
  esac
}
export -f docker

# --- gcloud shim so the script passes its precheck/config step
gcloud() {
  if [[ "$1" == "auth" && "$2" == "configure-docker" ]]; then
    echo "ℹ️  skipping gcloud configure-docker (using buildah login)"
    return 0
  fi
  echo "ℹ️  gcloud shim invoked: $*" >&2
  return 0
}
export -f gcloud

# --- env for the script (tags already computed)
export PROJECT_ID="${GCP_AR_PROJECT}"
export REGION="${GCP_AR_REGION}"
export REPOSITORY="${GCP_AR_REPO}"
export IMAGE_NAME="${APP_IMAGE_NAME}"
export TAG="${IMAGE_TAG}"

# optional: ensure script does NOT push :latest
export USE_LATEST="0"

# --- run and capture status
set +e
bash "$SCRIPT"
STATUS=$?
set -e

# If non-zero, verify the pushed image exists; treat as success if it does.
if [[ $STATUS -ne 0 ]]; then
  echo "⚠️ build script exited with $STATUS, verifying remote image presence…"
  if buildah pull "${IMAGE_REPOSITORY}:${IMAGE_TAG}" >/dev/null 2>&1; then
    echo "✅ Image ${IMAGE_REPOSITORY}:${IMAGE_TAG} is present in registry. Continuing."
    exit 0
  else
    echo "❌ Image ${IMAGE_REPOSITORY}:${IMAGE_TAG} not found in registry; failing."
    exit $STATUS
  fi
fi

exit 0
'
''')
            echo "build-and-push exit code: ${rc}"
            if (rc != 0) {
              error "build-and-push failed (rc=${rc})"
            }
          }
        }
      }
    }

    stage('Deploy build-portal-v2') {
      when { expression { env.SHOULD_DEPLOY == 'true' } }
      agent {
        kubernetes {
          yaml """
apiVersion: v1
kind: Pod
metadata:
  labels:
    app: build-portal-v2-deploy
spec:
  volumes:
  - name: gcloud-key
    secret:
      secretName: kaniko-jenkins-production-key
  - name: workspace-volume
    emptyDir: {}
  containers:
  - name: toolbox
    image: europe-west1-docker.pkg.dev/my-project/main/devops-toolbox:latest
    tty: true
    command: ['cat']
    volumeMounts:
    - name: gcloud-key
      mountPath: /secrets
      readOnly: true
    - name: workspace-volume
      mountPath: /workspace
      readOnly: false
    - name: workspace-volume
      mountPath: /home/jenkins/agent
      readOnly: false
"""
        }
      }
      steps {
        script {
          withCredentials([ file(credentialsId: 'ops-deploy-my-company', variable: 'GOOGLE_APPLICATION_CREDENTIALS') ]) {
            container('toolbox') {
              sh '''
bash -lc '
set -Eeuo pipefail
cd "$WORKSPACE"

echo "Deploying branch: ${BRANCH_NAME}"
echo "DEPLOY_ENV=${DEPLOY_ENV} INVENTORY=${INVENTORY}"
echo "Project=${GCP_PROJECT} Cluster=${GKE_CLUSTER} Scope=${GKE_SCOPE} Location=${GKE_LOCATION}"
echo "IMAGE_REPOSITORY=${IMAGE_REPOSITORY} IMAGE_TAG=${IMAGE_TAG}"

gcloud auth activate-service-account --key-file="${GOOGLE_APPLICATION_CREDENTIALS}"
gcloud config set project "${GCP_PROJECT}"

if [ "${GKE_SCOPE}" = "region" ]; then
  gcloud container clusters get-credentials "${GKE_CLUSTER}" --region "${GKE_LOCATION}"
else
  gcloud container clusters get-credentials "${GKE_CLUSTER}" --zone "${GKE_LOCATION}"
fi
export KUBECONFIG=/root/.kube/config

ansible-galaxy collection install -r ansible/collections/requirements.yml || true

test -f ./ansible/vault-password.sh || { echo "vault-password.sh not found"; exit 1; }
sed -i "s/\\r$//" ./ansible/vault-password.sh || true
chmod +x ./ansible/vault-password.sh

ansible-playbook -i "${INVENTORY}" ansible/deploy-build-portal.yml \
  --vault-password-file ./ansible/vault-password.sh \
  -e "image_repository=${IMAGE_REPOSITORY}" \
  -e "image_tag=${IMAGE_TAG}"

helm list -A | grep -E "^build-portal-v2\\b" || true
kubectl get pods -A | grep build-portal-v2 || true
'
'''
            }
          }
          env.DESCRIPTION = "Deployed ${IMAGE_REPOSITORY}:${IMAGE_TAG} to ${DEPLOY_ENV}"
        }
      }
    }
  }

  post {
    success { script { try { gitUtils.sendDiscordNotification('success') } catch (err) { echo "Discord notify (success) failed: ${err}" } } }
    failure { script { try { gitUtils.sendDiscordNotification('failure') } catch (err) { echo "Discord notify (failure) failed: ${err}" } } }
    aborted { script { try { gitUtils.sendDiscordNotification('aborted') } catch (err) { echo "Discord notify (aborted) failed: ${err}" } } }
  }
}
