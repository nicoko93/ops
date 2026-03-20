import logging
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Optional, Tuple
from google.cloud import storage
from google.oauth2 import service_account
import boto3
from flask import current_app

logger = logging.getLogger(__name__)

# ---------- In-memory cache for bucket discovery ----------
_bucket_cache: Dict[str, Any] = {"data": None, "ts": 0.0}
_bucket_cache_lock = threading.Lock()


def gcs_client():
    creds = service_account.Credentials.from_service_account_file(
        current_app.config["GCP_SA_FILE"]
    )
    return storage.Client(credentials=creds, project=current_app.config["GCP_PROJECT_ID"])

def _extract_gcs_meta(blob) -> Dict[str, Any]:
    """Lit les métadonnées custom (x-goog-meta-*) déjà présentes sur le blob.
    Nécessite que list_blobs(...) ait été appelé avec projection='full'."""
    m = getattr(blob, "metadata", None) or {}
    commit = m.get("commit")
    return {
        "commit":       commit,
        "commit_short": m.get("commit-short") or (commit[:8] if commit else None),
        "author":       m.get("author"),
        "message":      m.get("message"),
        "version":      m.get("version"),
        "environment":  m.get("environment"),
        "branch":       m.get("branch"),
    }

def _check_bucket_recent_activity(client, bucket_name: str, since: datetime) -> Optional[datetime]:
    """Sample a bucket to find the most recent blob. Returns its timestamp or None."""
    try:
        bucket = client.bucket(bucket_name)
        # GCS doesn't sort by date, so we sample the first page and check timestamps.
        # For most build buckets this is enough since recent uploads appear quickly.
        most_recent = None
        for blob in bucket.list_blobs(max_results=200):
            if blob.time_created and (most_recent is None or blob.time_created > most_recent):
                most_recent = blob.time_created
        return most_recent
    except Exception as e:
        logger.warning("Cannot inspect bucket %s: %s", bucket_name, e)
        return None


def discover_gcs_buckets() -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Discover all GCS buckets in the project and classify by recent activity.

    Returns (active_buckets, inactive_buckets) where each entry is:
        {"name": str, "last_activity": datetime|None}

    Active = has a blob created within the last 30 days.
    Results are cached for GCS_DISCOVER_CACHE_TTL seconds.
    """
    ttl = current_app.config.get("GCS_DISCOVER_CACHE_TTL", 300)

    with _bucket_cache_lock:
        if _bucket_cache["data"] is not None and (time.time() - _bucket_cache["ts"]) < ttl:
            return _bucket_cache["data"]

    exclude = set(current_app.config.get("GCS_EXCLUDE_BUCKETS", []))
    client = gcs_client()
    since = datetime.now(timezone.utc) - timedelta(days=30)

    active, inactive = [], []
    try:
        all_buckets = list(client.list_buckets())
    except Exception as e:
        logger.error("Failed to list GCS buckets: %s — falling back to GCS_BUCKETS", e)
        # Fallback: treat configured buckets as active
        return (
            [{"name": b, "last_activity": None} for b in current_app.config["GCS_BUCKETS"]],
            [],
        )

    for bucket in all_buckets:
        if bucket.name in exclude:
            continue
        last = _check_bucket_recent_activity(client, bucket.name, since)
        entry = {"name": bucket.name, "last_activity": last}
        if last and last > since:
            active.append(entry)
        else:
            inactive.append(entry)

    # Sort active by most recent first, inactive alphabetically
    active.sort(key=lambda b: b["last_activity"] or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    inactive.sort(key=lambda b: b["name"])

    result = (active, inactive)
    with _bucket_cache_lock:
        _bucket_cache["data"] = result
        _bucket_cache["ts"] = time.time()

    return result


def list_gcs_recent_buckets(days: int, limit: int) -> List[Dict[str, Any]]:
    client = gcs_client()
    since = datetime.now(timezone.utc) - timedelta(days=days)
    out: List[Dict[str, Any]] = []
    for bucket_name in current_app.config["GCS_BUCKETS"]:
        bucket = client.bucket(bucket_name)
        # projection='full' pour inclure metadata dans la réponse de listing
        for blob in bucket.list_blobs(projection="full"):
            if blob.time_created and blob.time_created > since:
                it = {
                    "provider": "gcs",
                    "bucket": bucket_name,
                    "key": blob.name,
                    "name": (blob.name.split("/")[-1] or blob.name),
                    "time_created": blob.time_created,
                    "size": blob.size,
                }
                it["meta"] = _extract_gcs_meta(blob)
                out.append(it)
    out.sort(key=lambda x: x["time_created"], reverse=True)
    return out[:limit]

def list_gcs_bucket(bucket: str) -> List[Dict[str, Any]]:
    client = gcs_client()
    bucket_ref = client.bucket(bucket)
    out: List[Dict[str, Any]] = []
    # projection='full' pour inclure metadata dans la réponse de listing
    for blob in bucket_ref.list_blobs(projection="full"):
        it = {
            "provider": "gcs",
            "bucket": bucket,
            "key": blob.name,
            "name": (blob.name.split("/")[-1] or blob.name),
            "time_created": blob.time_created,
            "size": blob.size,
        }
        it["meta"] = _extract_gcs_meta(blob)
        out.append(it)
    out.sort(key=lambda x: x["time_created"], reverse=True)
    return out

def s3_client():
    return boto3.client(
        "s3",
        aws_access_key_id=current_app.config.get("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=current_app.config.get("AWS_SECRET_ACCESS_KEY"),
        region_name=current_app.config.get("AWS_REGION"),
    )

def list_s3_recent(days: int, limit: int) -> List[Dict[str, Any]]:
    if not current_app.config.get("AWS_ACCESS_KEY_ID"):
        return []
    since = datetime.now(timezone.utc) - timedelta(days=days)
    out: List[Dict[str, Any]] = []
    client = s3_client()
    for source in current_app.config["S3_SOURCES"].split(";"):
        if not source:
            continue
        bucket, prefix = source.split(":", 1)
        resp = client.list_objects_v2(Bucket=bucket, Prefix=prefix)
        for obj in resp.get("Contents", []):
            if obj["LastModified"] > since:
                key = obj["Key"]
                out.append({
                    "provider": "s3",
                    "bucket": bucket,
                    "key": key,
                    "name": key[len(prefix):] if key.startswith(prefix) else key,
                    "time_created": obj["LastModified"],
                    "size": obj["Size"],
                })
    out.sort(key=lambda x: x["time_created"], reverse=True)
    return out[:limit]

def gcs_signed_url(bucket: str, key: str, seconds: int = 3600) -> str:
    client = gcs_client()
    blob = client.bucket(bucket).blob(key)
    return blob.generate_signed_url(version="v4", expiration=seconds)

def s3_signed_url(bucket: str, key: str, seconds: int = 3600) -> str:
    client = s3_client()
    return client.generate_presigned_url(
        "get_object", Params={"Bucket": bucket, "Key": key}, ExpiresIn=seconds
    )


def s3_client_eu():
    """S3 client for eu-central-1 region (Legacy Unreal bucket)."""
    return boto3.client(
        "s3",
        aws_access_key_id=current_app.config.get("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=current_app.config.get("AWS_SECRET_ACCESS_KEY"),
        region_name=current_app.config.get("LCK_UNREAL_REGION", "eu-central-1"),
    )


def s3_presigned_put_url(bucket: str, key: str, content_type: str, seconds: int = 3600) -> str:
    """Generate a presigned PUT URL for direct browser upload to S3."""
    client = s3_client_eu()
    return client.generate_presigned_url(
        "put_object",
        Params={
            "Bucket": bucket,
            "Key": key,
            "ContentType": content_type,
        },
        ExpiresIn=seconds,
    )


def list_legacy_unreal_files(prefix: str = "") -> List[Dict[str, Any]]:
    """List files in the Legacy Unreal S3 bucket."""
    bucket = current_app.config.get("LCK_UNREAL_BUCKET", "unreal-builds")
    if not current_app.config.get("AWS_ACCESS_KEY_ID"):
        return []

    client = s3_client_eu()
    out: List[Dict[str, Any]] = []

    paginator = client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            out.append({
                "key": key,
                "name": key.split("/")[-1] or key,
                "size": obj["Size"],
                "last_modified": obj["LastModified"],
            })

    out.sort(key=lambda x: x["last_modified"], reverse=True)
    return out


def legacy_unreal_public_url(key: str) -> str:
    """Generate public URL for an Legacy Unreal file (bucket must have public read)."""
    bucket = current_app.config.get("LCK_UNREAL_BUCKET", "unreal-builds")
    region = current_app.config.get("LCK_UNREAL_REGION", "eu-central-1")
    return f"https://{bucket}.s3.{region}.amazonaws.com/{key}"

def list_gcs_mygame_builds(days: int = 14) -> List[Dict[str, Any]]:
    """List recent MyGame Android builds from GCS for deploy-quest."""
    client = gcs_client()
    bucket = client.bucket("unreal-builds")
    since = datetime.now(timezone.utc) - timedelta(days=days)
    builds = []

    for blob in bucket.list_blobs(prefix="MyGame/", projection="full"):
        if not blob.name.endswith(".zip"):
            continue
        # Only Android variants (contain "mygame-" in filename)
        filename = blob.name.split("/")[-1]
        if "mygame-" not in filename:
            continue
        if blob.time_created and blob.time_created < since:
            continue

        # Parse path: MyGame/{branch}/{version}/{zipname}
        parts = blob.name.split("/")
        if len(parts) < 4:
            continue

        branch = parts[1]
        # Extract variant and version from filename: MyGame_{variant}_v{version}_{config}.zip
        # Each Android variant has its own version code baked into the APK and filename.
        variant = filename.split("_", 1)[1].rsplit("_v", 1)[0] if "_" in filename else filename
        name_parts = filename.rsplit("_v", 1)
        version = name_parts[1].split("_")[0] if len(name_parts) == 2 else parts[2]

        builds.append({
            "gcs_path": blob.name,
            "filename": filename,
            "branch": branch,
            "version": version,
            "variant": variant,
            "channel": variant,
            "size": blob.size,
            "time_created": blob.time_created,
        })

    builds.sort(key=lambda x: x["time_created"], reverse=True)
    return builds


def list_reports() -> List[Dict[str, Any]]:
    """Return REPORT_BUCKET + CC_REPORT_PREFIX (GCS)."""
    client = gcs_client()
    reports: List[Dict[str, Any]] = []

    # Old reports bucket
    bucket_old = client.bucket(current_app.config["REPORT_BUCKET"])
    for b in bucket_old.list_blobs():
        reports.append({
            "bucket": bucket_old.name,
            "key": b.name,
            "time_created": b.time_created,
        })

    # Control Center aggregated prefix
    cc_full = current_app.config["CC_REPORT_PREFIX"]
    if "/" in cc_full:
        cc_bucket, cc_prefix = cc_full.split("/", 1)
    else:
        cc_bucket, cc_prefix = cc_full, ""

    bucket_new = client.bucket(cc_bucket)
    for b in bucket_new.list_blobs(prefix=cc_prefix):
        if b.name == cc_prefix:
            continue
        reports.append({
            "bucket": cc_bucket,
            "key": b.name,
            "time_created": b.time_created,
        })

    reports.sort(key=lambda x: x["time_created"], reverse=True)
    return reports
