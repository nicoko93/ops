import re
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Any, Optional
from collections import defaultdict
from flask import current_app
from .storage import gcs_client


def extract_deployment_name(pod_name: str) -> str:
    """
    Extract deployment name from pod name.
    Pod format: {deployment}-{replicaset-hash}-{pod-hash}
    Example: my-app-7d4b8c9f5-abc12 -> my-app
    """
    parts = pod_name.rsplit("-", 2)
    if len(parts) >= 3:
        return parts[0]
    return pod_name


def parse_crash_log_path(path: str) -> Optional[Dict[str, Any]]:
    """
    Parse crash log path to extract metadata.
    Path: crash-logs/{env}/{namespace}/{pod}/{container}_{timestamp}.log
    """
    match = re.match(
        r'crash-logs/([^/]+)/([^/]+)/([^/]+)/([^_]+)_(\d{8}_\d{6})\.log$',
        path
    )
    if not match:
        return None

    env, namespace, pod, container, ts = match.groups()
    deployment = extract_deployment_name(pod)
    timestamp = datetime.strptime(ts, "%Y%m%d_%H%M%S")

    return {
        "path": path,
        "environment": env,
        "namespace": namespace,
        "deployment": deployment,
        "pod": pod,
        "container": container,
        "timestamp": timestamp,
    }


def list_crash_logs(
    env: str = None,
    namespace: str = None,
    days: int = 7
) -> List[Dict[str, Any]]:
    """List crash logs from GCS bucket."""
    client = gcs_client()
    bucket_name = current_app.config.get("CRASH_LOGS_BUCKET", "app-crash-logs")
    prefix = current_app.config.get("CRASH_LOGS_PREFIX", "crash-logs/")

    if env:
        prefix = f"crash-logs/{env}/"
        if namespace:
            prefix = f"crash-logs/{env}/{namespace}/"

    bucket = client.bucket(bucket_name)
    since = datetime.now(timezone.utc) - timedelta(days=days)
    logs = []

    for blob in bucket.list_blobs(prefix=prefix):
        if not blob.name.endswith(".log"):
            continue
        if blob.time_created and blob.time_created < since:
            continue

        meta = parse_crash_log_path(blob.name)
        if meta:
            meta["size"] = blob.size
            meta["time_created"] = blob.time_created
            logs.append(meta)

    logs.sort(key=lambda x: x["timestamp"], reverse=True)
    return logs


def group_logs_by_hierarchy(logs: List[Dict]) -> Dict:
    """
    Group logs into nested structure:
    {env: {namespace: {deployment: {pod: [logs]}}}}
    """
    tree = defaultdict(lambda: defaultdict(lambda: defaultdict(lambda: defaultdict(list))))

    for log in logs:
        tree[log["environment"]][log["namespace"]][log["deployment"]][log["pod"]].append(log)

    return tree


def get_crash_log_content(key: str) -> str:
    """Download and return crash log content."""
    client = gcs_client()
    bucket_name = current_app.config.get("CRASH_LOGS_BUCKET", "app-crash-logs")
    blob = client.bucket(bucket_name).blob(key)
    return blob.download_as_text()


def get_crash_log_signed_url(key: str, seconds: int = 3600) -> str:
    """Generate signed URL for crash log download."""
    client = gcs_client()
    bucket_name = current_app.config.get("CRASH_LOGS_BUCKET", "app-crash-logs")
    blob = client.bucket(bucket_name).blob(key)
    return blob.generate_signed_url(version="v4", expiration=seconds)
