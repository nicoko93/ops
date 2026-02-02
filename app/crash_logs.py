import re
from urllib.parse import quote
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


def get_sibling_logs(key: str) -> Dict[str, Optional[Dict[str, Any]]]:
    """
    Get previous and next logs within the same deployment folder.
    Returns dict with 'prev' and 'next' keys containing log metadata or None.
    """
    meta = parse_crash_log_path(key)
    if not meta:
        return {"prev": None, "next": None}

    env = meta["environment"]
    namespace = meta["namespace"]
    deployment = meta["deployment"]

    client = gcs_client()
    bucket_name = current_app.config.get("CRASH_LOGS_BUCKET", "app-crash-logs")
    prefix = f"crash-logs/{env}/{namespace}/"

    bucket = client.bucket(bucket_name)
    logs = []

    for blob in bucket.list_blobs(prefix=prefix):
        if not blob.name.endswith(".log"):
            continue
        log_meta = parse_crash_log_path(blob.name)
        if log_meta and log_meta["deployment"] == deployment:
            logs.append(log_meta)

    logs.sort(key=lambda x: x["timestamp"], reverse=True)

    current_idx = None
    for i, log in enumerate(logs):
        if log["path"] == key:
            current_idx = i
            break

    if current_idx is None:
        return {"prev": None, "next": None}

    prev_log = logs[current_idx - 1] if current_idx > 0 else None
    next_log = logs[current_idx + 1] if current_idx < len(logs) - 1 else None

    return {
        "prev": prev_log,
        "next": next_log,
        "current_index": current_idx + 1,
        "total": len(logs),
    }


def get_rancher_links(environment: str, namespace: str, pod: str) -> Dict[str, Optional[str]]:
    """
    Generate Rancher links for quick navigation to the cluster.
    Returns dict with URLs for namespace, events, and workloads views.
    """
    base_url = current_app.config.get("RANCHER_BASE_URL", "https://infra.example.com")
    cluster_ids = current_app.config.get("RANCHER_CLUSTER_IDS", {})

    cluster_id = cluster_ids.get(environment)
    if not cluster_id:
        return {
            "configured": False,
            "namespace_url": None,
            "events_url": None,
            "workloads_url": None,
            "pod_url": None,
        }

    # URL encode namespace and pod names
    ns_encoded = quote(namespace, safe="")
    pod_encoded = quote(pod, safe="")

    # Rancher dashboard URLs (Rancher 2.x format)
    return {
        "configured": True,
        "base_url": base_url,
        "cluster_id": cluster_id,
        # Namespace overview
        "namespace_url": f"{base_url}/dashboard/c/{cluster_id}/explorer/namespace/{ns_encoded}",
        # Events filtered by namespace
        "events_url": f"{base_url}/dashboard/c/{cluster_id}/explorer/event?q=metadata.namespace%3D{ns_encoded}",
        # Workloads in namespace (deployments, pods, etc.)
        "workloads_url": f"{base_url}/dashboard/c/{cluster_id}/explorer/workload?q=metadata.namespace%3D{ns_encoded}",
        # Direct pod link (may 404 if pod is deleted)
        "pod_url": f"{base_url}/dashboard/c/{cluster_id}/explorer/pod/{ns_encoded}/{pod_encoded}",
    }
