import os
import json
import secrets
import xml.etree.ElementTree as ET
from collections import defaultdict
from io import BytesIO

from flask import (
    Blueprint, render_template, redirect, url_for,
    session, request, jsonify, send_file, current_app
)

from google.cloud import storage as gcs
    # noqa
from google.oauth2 import service_account
import xmltodict

from .auth import oauth, login_required, domain_allowed
from .storage import (
    list_gcs_recent_buckets, list_s3_recent, list_gcs_bucket,
    gcs_signed_url, s3_signed_url, list_reports
)
from .models import TestRun, TestResult, SessionLocal
from .crash_logs import (
    list_crash_logs, group_logs_by_hierarchy,
    get_crash_log_content, get_crash_log_signed_url, parse_crash_log_path
)

# ---------- UI ----------
ui_bp = Blueprint("ui", __name__)

@ui_bp.route("/login")
def login():
    host = request.headers.get("X-Forwarded-Host", request.host)
    proto = request.headers.get("X-Forwarded-Proto", request.scheme)

    if host and host.endswith("builds-new.example.com"):
        proto = "https"

    redirect_uri = url_for("ui.auth_callback", _external=True, _scheme=proto)
    current_app.logger.info("OAuth redirect_uri generated: %s", redirect_uri)

    nonce = secrets.token_urlsafe(16)
    session["oidc_nonce"] = nonce

    hd = current_app.config.get("GOOGLE_ALLOWED_DOMAIN")
    kwargs = {"nonce": nonce}
    if hd:
        kwargs["hd"] = hd

    return oauth.google.authorize_redirect(redirect_uri, **kwargs)

@ui_bp.route("/auth/callback")
def auth_callback():
    token = oauth.google.authorize_access_token()
    nonce = session.pop("oidc_nonce", None)
    userinfo = oauth.google.parse_id_token(token, nonce=nonce)

    email = userinfo.get("email")
    if not email or not domain_allowed(email):
        return "Accès refusé", 403

    session["user"] = {"email": email, "name": userinfo.get("name")}
    return redirect(session.pop("next", url_for("ui.index")))

from flask import redirect, url_for, session, current_app
import requests

@ui_bp.route("/logout", methods=["POST", "GET"])
def logout():
    token = session.get("token") or {}
    access_token = token.get("access_token")
    if access_token:
        try:
            requests.post(
                "https://oauth2.googleapis.com/revoke",
                data={"token": access_token},
                timeout=3,
            )
        except Exception:
            pass

    session.clear()
    resp = redirect(url_for("ui.logged_out"))
    cookie_name = current_app.config.get("SESSION_COOKIE_NAME", "session")
    resp.delete_cookie(cookie_name, path="/")
    resp.headers["Cache-Control"] = "no-store"
    return resp

@ui_bp.route("/logged_out")
def logged_out():
    return render_template("logged_out.html")


@ui_bp.route("/")
@login_required
def index():
    days = current_app.config["DEFAULT_RECENT_DAYS"]
    limit = current_app.config["MAX_RECENT"]
    recent = list_gcs_recent_buckets(days, limit) + list_s3_recent(days, limit)
    recent.sort(key=lambda x: x["time_created"], reverse=True)

    sections = []
    for b in current_app.config["GCS_BUCKETS"]:
        items = list_gcs_bucket(b)
        sections.append((b, items))

    reports = list_reports()

    return render_template(
        "index.html",
        recent=recent,
        sections=sections,
        reports=reports,
        user=session.get("user"),
    )

@ui_bp.route("/download/gcs/<bucket>/<path:key>")
@login_required
def download_gcs(bucket, key):
    return redirect(gcs_signed_url(bucket, key), code=302)

@ui_bp.route("/download/s3/<bucket>/<path:key>")
@login_required
def download_s3(bucket, key):
    return redirect(s3_signed_url(bucket, key), code=302)

# --- Legacy route for backward-compat with old Discord links ---
# Old links used /download/<bucket>/<path>; keep them working by 301 to the new route.
@ui_bp.route("/download/<bucket>/<path:key>")
def download_legacy(bucket, key):
    return redirect(url_for("ui.download_gcs", bucket=bucket, key=key), code=301)

@ui_bp.route("/viewer-proxy/<path:key>")
@login_required
def proxy_xml_file(key):
    cfg = current_app.config
    cc_full = cfg["CC_REPORT_PREFIX"]
    if "/" in cc_full:
        cc_bucket, cc_prefix = cc_full.split("/", 1)
    else:
        cc_bucket, cc_prefix = cc_full, ""
    if key.startswith(cc_prefix):
        bucket_name = cc_bucket
        blob_name = key
    else:
        bucket_name = cfg["REPORT_BUCKET"]
        blob_name = key

    creds = service_account.Credentials.from_service_account_file(cfg["GCP_SA_FILE"])
    client = gcs.Client(credentials=creds, project=cfg["GCP_PROJECT_ID"])
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_name)
    if not blob.exists():
        return (f"❌ File {blob_name} not found in {bucket_name}", 404)
    data = blob.download_as_bytes()
    return send_file(BytesIO(data), mimetype="text/xml")

@ui_bp.route("/reports/index.html")
@login_required
def secure_report_viewer():
    path = os.path.join(current_app.root_path, "static", "reports", "index.html")
    if not os.path.exists(path):
        return "Viewer not found at /static/reports/index.html", 404
    return send_file(path)

# ---------- API & Stats ----------
template_dir = os.path.join(os.path.dirname(__file__), "templates")
test_results_api = Blueprint("test_results_api", __name__, template_folder=template_dir)
test_results_ui  = Blueprint("test_results_ui",  __name__)

API_KEY = os.getenv("API_KEY")
REPORT_BUCKET_NAME = os.getenv("REPORT_BUCKET_NAME", "test-reports")

# Protect the API by default; allow CI and health without login
@test_results_api.before_request
def _protect_api_except_ci():
    open_endpoints = {
        "test_results_api.parse_and_save",  # CI webhook (X-API-KEY)
        "test_results_api.healthz",         # health probe
    }
    if request.endpoint in open_endpoints:
        return None
    if "user" not in session:
        session["next"] = request.url
        return redirect(url_for("ui.login"))

def read_xml_from_gcs(file_name: str):
    """Lit un XML depuis GCS avec clé de service si fournie, sinon ADC."""
    sa_path = os.getenv("GCP_SA_FILE")
    project = os.getenv("GCP_PROJECT_ID")
    bucket_name = os.getenv("REPORT_BUCKET_NAME", REPORT_BUCKET_NAME)

    if sa_path and os.path.exists(sa_path):
        creds = service_account.Credentials.from_service_account_file(sa_path)
        client = gcs.Client(project=project, credentials=creds)
    else:
        client = gcs.Client(project=project)

    bucket = client.bucket(bucket_name)
    blob = bucket.blob(file_name)
    if not blob.exists():
        return None
    return blob.download_as_text()

def parse_nunit_xml(
    xml_content, changeset_id, label, unity_version,
    developer_email, report_id, branch, project, jenkins_url
):
    """Parse NUnit XML et sauvegarde TestRun + TestResults en UNE session."""
    root = ET.ElementTree(ET.fromstring(xml_content)).getroot()

    suite_name = root.attrib.get("name")
    result = root.attrib.get("result")
    duration = root.attrib.get("duration")
    total_tests = root.attrib.get("testcasecount")
    passed_tests = root.attrib.get("passed")
    failed_tests = root.attrib.get("failed")
    inconclusive_tests = root.attrib.get("inconclusive")
    skipped_tests = root.attrib.get("skipped")
    failure_message = root.find("failure/message").text if root.find("failure/message") is not None else None

    parsed_dict = xmltodict.parse(xml_content)

    db = SessionLocal()
    try:
        tr = TestRun(
            suite_name=suite_name,
            result=result,
            duration=duration,
            total_tests=total_tests,
            passed_tests=passed_tests,
            failed_tests=failed_tests,
            inconclusive_tests=inconclusive_tests,
            skipped_tests=skipped_tests,
            failure_message=failure_message,
            report_id=report_id,
            branch=branch,
            project=project,
            extra_data=parsed_dict,
            jenkins_url=jenkins_url,
        )
        db.add(tr)
        db.flush()  # obtient tr.id sans commit

        rows = []
        for test_case in root.iter("test-case"):
            test_name = test_case.attrib.get("fullname") or test_case.attrib.get("name")
            test_status = test_case.attrib.get("result")
            test_duration = test_case.attrib.get("duration")
            fail_msg = test_case.find("failure/message").text if test_case.find("failure/message") is not None else "No failure"
            stack_trace = test_case.find("failure/stack-trace").text if test_case.find("failure/stack-trace") is not None else "No stack trace"
            output = test_case.find("output").text if test_case.find("output") is not None else "No output"

            rows.append(TestResult(
                test_name=test_name,
                status=test_status,
                changeset_id=changeset_id,
                label=label,
                unity_version=unity_version,
                developer_email=developer_email,
                duration=test_duration,
                message=fail_msg,
                stack_trace=stack_trace,
                output=output,
                test_run_id=tr.id,  # on relie par ID (évite les objets détachés)
            ))

        if rows:
            db.add_all(rows)

        db.commit()
        return 1
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

@test_results_api.route("/parse-and-save", methods=["POST"])
def parse_and_save():
    api_key = request.headers.get("X-API-KEY")
    if api_key != API_KEY:
        return jsonify({"error": "Unauthorized"}), 401

    data = request.get_json() or {}
    required = ["changeset_id", "label", "unity_version", "developer_email", "report_id", "branch", "project", "file_name"]
    for f in required:
        if f not in data:
            return jsonify({"error": f"Missing required field: {f}"}), 400

    xml_content = read_xml_from_gcs(data["file_name"])
    if xml_content is None:
        return jsonify({"error": f"File {data['file_name']} not found in the bucket"}), 404

    try:
        count = parse_nunit_xml(
            xml_content,
            data["changeset_id"],
            data["label"],
            data["unity_version"],
            data["developer_email"],
            data["report_id"],
            data["branch"],
            data["project"],
            data.get("jenkins_url"),
        )
    except Exception as e:
        import traceback
        current_app.logger.error(
            f"Error in parse_nunit_xml for file {data['file_name']}: {e}\n{traceback.format_exc()}"
        )
        return jsonify({"error": "Internal parsing error"}), 500

    return jsonify({"message": f"Successfully parsed and saved {count} test run"}), 200

@test_results_api.route("/healthz", methods=["GET"])
def healthz():
    return "OK", 200

@ui_bp.route("/healthz")
def root_healthz():
    return "OK", 200


def _compute_stats():
    db = SessionLocal()
    try:
        total = db.query(TestResult).count()
        passed = db.query(TestResult).filter(TestResult.status == "Passed").count()
        failed = db.query(TestResult).filter(TestResult.status == "Failed").count()
        projects = db.query(TestRun.project).distinct().count()

        recent_tests = (
            db.query(TestResult)
              .order_by(TestResult.id.desc())
              .limit(50)
              .all()
        )

        grouped = defaultdict(list)
        for t in recent_tests:
            key = (t.changeset_id, t.test_run.report_id if t.test_run else "unknown")
            grouped[key].append(t)

        groups = []
        for (changeset_id, report_id), tests in grouped.items():
            max_id = max(test.id for test in tests)
            groups.append({
                "changeset_id": changeset_id,
                "report_id": report_id,
                "jenkins_url": tests[0].test_run.jenkins_url if tests and tests[0].test_run else None,
                "tests": [{
                    "project": test.test_run.project if test.test_run else "unknown",
                    "test_name": test.test_name,
                    "status": test.status,
                    "developer_email": test.developer_email,
                    "unity_version": test.unity_version,
                    "duration": test.duration,
                } for test in tests],
                "most_recent_id": max_id,
            })

        groups.sort(key=lambda g: g["most_recent_id"], reverse=True)
        groups = groups[:10]

        return {
            "total_tests": total,
            "passed": passed,
            "failed": failed,
            "success_rate": round((passed / total) * 100, 2) if total > 0 else 0.0,
            "projects_tested": projects,
            "latest_tests_grouped": groups,
        }
    finally:
        db.close()

@test_results_api.route("/stats", methods=["GET"])
def test_stats():
    stats = _compute_stats()

    # -------- content negotiation --------
    fmt = request.args.get("format", "").lower()
    accept = request.headers.get("Accept", "")
    jenkins_default = current_app.config.get(
        "JENKINS_DEFAULT_URL",
        "https://jenkins-production.example.com/job/Unity-LTS-Tests/"
    )

    # If browser (text/html) or explicit ?format=html → HTML page
    if fmt == "html" or "text/html" in accept:
        return render_template("api_stats.html", stats=stats, jenkins_default=jenkins_default)

    # If ?pretty=1 → pretty JSON
    if request.args.get("pretty") in ("1", "true", "yes"):
        return current_app.response_class(
            response=json.dumps(stats, indent=2),
            mimetype="application/json"
        )

    # Default: compact JSON
    return jsonify(stats)

# Optional: dedicated HTML route for /stats page (separate from /api)
@test_results_ui.route("/stats", methods=["GET"])
@login_required
def stats_page():
    return render_template("stats.html")


# ---------- Crash Logs ----------
crash_logs_bp = Blueprint("crash_logs", __name__, url_prefix="/crash-logs")


@crash_logs_bp.route("/")
@crash_logs_bp.route("/<env>/")
@crash_logs_bp.route("/<env>/<namespace>/")
@login_required
def list_logs(env=None, namespace=None):
    days = request.args.get("days", 7, type=int)
    logs = list_crash_logs(env=env, namespace=namespace, days=days)
    tree = group_logs_by_hierarchy(logs)
    return render_template(
        "crash_logs/list.html",
        tree=tree,
        logs=logs,
        current_env=env,
        current_namespace=namespace,
        days=days,
        user=session.get("user"),
    )


@crash_logs_bp.route("/view/<path:key>")
@login_required
def view_log(key):
    content = get_crash_log_content(key)
    meta = parse_crash_log_path(key)
    return render_template(
        "crash_logs/view.html",
        content=content,
        meta=meta,
        key=key,
        user=session.get("user"),
    )


@crash_logs_bp.route("/download/<path:key>")
@login_required
def download_log(key):
    url = get_crash_log_signed_url(key)
    return redirect(url)
