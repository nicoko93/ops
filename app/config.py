import os

class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "supersecretkey")
    PREFERRED_URL_SCHEME = "https"
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_SAMESITE = "Lax"

    # Google OAuth (OIDC)
    GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
    GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
    GOOGLE_ALLOWED_DOMAIN = os.getenv("GOOGLE_ALLOWED_DOMAIN", "example.org")
    GOOGLE_DISCOVERY_URL = "https://accounts.google.com/.well-known/openid-configuration"

    # GCP
    GCP_PROJECT_ID = os.getenv("GCP_PROJECT_ID", "my-project")
    GCP_SA_FILE = os.getenv("GCP_SA_FILE", "/var/secrets/google/key.json")

    # Buckets GCS
    # When GCS_AUTO_DISCOVER=1, all project buckets are scanned dynamically.
    # GCS_BUCKETS then acts as a fallback if discovery fails.
    GCS_AUTO_DISCOVER = os.getenv("GCS_AUTO_DISCOVER", "1") in ("1", "true", "yes")
    GCS_BUCKETS = os.getenv(
        "GCS_BUCKETS",
        ",".join([
            "game-staging",
            "game-production",
            "game-testing",
            "app-artifacts",
            "package-export",
            "unreal-builds",
            "sandbox-builds",
            "control-center",
            "bifrost",
            "sdk-builds"
        ])
    ).split(",")
    # Comma-separated bucket names to hide from the UI (e.g. infra buckets, logs, etc.)
    GCS_EXCLUDE_BUCKETS = [
        b.strip() for b in os.getenv("GCS_EXCLUDE_BUCKETS", "").split(",") if b.strip()
    ]
    # How long (seconds) to cache the bucket discovery result
    GCS_DISCOVER_CACHE_TTL = int(os.getenv("GCS_DISCOVER_CACHE_TTL", "300"))

    # AWS S3 (optionnel)
    AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
    AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
    AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
    # format: BUCKET:prefix;BUCKET:prefix
    S3_SOURCES = os.getenv(
        "S3_SOURCES",
        "asset-dev:internal/sdk/unreal-1.5/;asset-prod:internal/sdk/unreal-1.5/"
    )

    # Rapports
    REPORT_BUCKET = os.getenv("REPORT_BUCKET", "test-reports")
    CC_REPORT_PREFIX = os.getenv(
        "CC_REPORT_PREFIX",
        "control-center/App-control-center-multibranch/TestReport/"
    )

    # UI
    DEFAULT_RECENT_DAYS = int(os.getenv("DEFAULT_RECENT_DAYS", "2"))
    MAX_RECENT = int(os.getenv("MAX_RECENT", "50"))

    JENKINS_DEFAULT_URL = os.getenv(
        "JENKINS_DEFAULT_URL",
        "https://jenkins-production.example.com/job/Unity-LTS-Tests/",
    )

    # Crash Logs
    CRASH_LOGS_BUCKET = os.getenv("CRASH_LOGS_BUCKET", "app-crash-logs")
    CRASH_LOGS_PREFIX = os.getenv("CRASH_LOGS_PREFIX", "crash-logs/")

    # Rancher (Infra)
    RANCHER_BASE_URL = os.getenv("RANCHER_BASE_URL", "https://infra.example.com")
    # Mapping: environment -> Rancher cluster ID (find in Rancher URL when browsing a cluster)
    # Format: "env:cluster-id,env:cluster-id"
    RANCHER_CLUSTER_IDS = {
        pair.split(":")[0]: pair.split(":")[1]
        for pair in os.getenv(
            "RANCHER_CLUSTER_IDS",
            "dev:cluster-dev-id,prod:cluster-prod-id,ops:cluster-ops-id"
        ).split(",")
        if ":" in pair
    }

    # Deploy-Quest (Jenkins trigger)
    JENKINS_URL          = os.getenv("JENKINS_URL", "https://jenkins-production.example.com")
    JENKINS_DEPLOY_TOKEN = os.getenv("JENKINS_DEPLOY_TOKEN", "deploy-quest")