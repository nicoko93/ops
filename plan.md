# Build Portal - Implementation Plans

## Crash Log Viewer (Completed)

### Overview
Added a crash log viewer to the build-portal that displays logs from `gs://app-crash-logs`, organized by **environment > namespace > deployment > pod**.

### GCS Source
- **Bucket**: `app-crash-logs`
- **Prefix**: `crash-logs/`
- **Path structure**: `crash-logs/{env}/{namespace}/{pod}/{container}_{timestamp}.log`

### Deployment Extraction Logic
Kubernetes pod names follow pattern: `{deployment}-{replicaset-hash}-{pod-hash}`
- Example: `my-app-7d4b8c9f5-abc12` → deployment: `my-app`
- Extract by removing last two `-` segments

### Hierarchy
```
Environment (dev/staging/prod)
└── Namespace
    └── Deployment (extracted from pod name)
        └── Pod
            └── Log files (with timestamps)
```

### Files Created/Modified

| File | Action | Description |
|------|--------|-------------|
| `app/config.py` | Modified | Added `CRASH_LOGS_BUCKET`, `CRASH_LOGS_PREFIX` |
| `app/crash_logs.py` | Created | Core crash log logic |
| `app/routes.py` | Modified | Added `crash_logs_bp` blueprint |
| `app/__init__.py` | Modified | Registered `crash_logs_bp` |
| `app/templates/crash_logs/list.html` | Created | Tree view with collapsible hierarchy |
| `app/templates/crash_logs/view.html` | Created | Log content viewer with prev/next nav |
| `app/templates/base.html` | Modified | Added nav link |
| `build-portal/templates/configmap.yaml` | Modified | Added env vars |
| `build-portal/values.yaml` | Modified | Added `crashLogs` config section |

### Routes

| Route | Description |
|-------|-------------|
| `GET /crash-logs/` | Main list view (all environments) |
| `GET /crash-logs/<env>/` | Filter by environment |
| `GET /crash-logs/<env>/<namespace>/` | Filter by namespace |
| `GET /crash-logs/view/<path:key>` | View log content |
| `GET /crash-logs/download/<path:key>` | Download via signed URL |

### Features

#### List View (`list.html`)
- Collapsible tree view (env → namespace → deployment → pod)
- Filter input for searching by any field
- Time range selector (1, 3, 7, 14, 30 days)
- Log count badges at each level
- Environment color coding (prod=red, staging=yellow, dev=blue)

#### Log Viewer (`view.html`)
- Metadata panel (env, namespace, deployment, pod, container, timestamp)
- Previous/Next navigation within same deployment
- Position indicator (e.g., "3 / 12 in my-app")
- Copy content button
- Download button
- Line count display
- Monospace font, syntax-friendly display

### Core Functions (`crash_logs.py`)

```python
extract_deployment_name(pod_name: str) -> str
    # Extract deployment from pod name

parse_crash_log_path(path: str) -> Dict
    # Parse path to extract metadata

list_crash_logs(env, namespace, days) -> List[Dict]
    # List logs from GCS with filtering

group_logs_by_hierarchy(logs) -> Dict
    # Group into nested env/ns/deployment/pod structure

get_crash_log_content(key: str) -> str
    # Download log content

get_crash_log_signed_url(key: str) -> str
    # Generate signed download URL

get_sibling_logs(key: str) -> Dict
    # Get prev/next logs in same deployment
```

### Helm Configuration

```yaml
# values.yaml
crashLogs:
  bucket: "app-crash-logs"
  prefix: "crash-logs/"
```

Environment variables added to ConfigMap:
- `CRASH_LOGS_BUCKET`
- `CRASH_LOGS_PREFIX`

### Prerequisites
The GCP service account needs `Storage Object Viewer` role on the `app-crash-logs` bucket.

---

## Future Improvements (Ideas)

- [ ] Add log search/grep functionality within log content
- [ ] Add log streaming for real-time updates
- [ ] Add log retention/cleanup indicators
- [ ] Add export functionality (zip multiple logs)
- [ ] Add alerting integration (link to related alerts)
- [ ] Add pod restart history correlation
