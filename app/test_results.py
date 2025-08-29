from flask import Blueprint, jsonify, request
from collections import defaultdict
import os
import xmltodict

from .storage import gcs_client
from .models import save_result, TestRun, TestResult, SessionLocal  # V1 models

tests_bp = Blueprint("tests_api", __name__)

# Config
API_KEY = os.getenv("API_KEY")
REPORT_BUCKET_NAME = os.getenv("REPORT_BUCKET_NAME", os.getenv("REPORT_BUCKET", "test-reports"))


def _read_xml_from_gcs(file_name: str) -> str | None:
    """
    Reads a GCS blob (full path) from the REPORT_BUCKET_NAME bucket and returns its text content.
    """
    client = gcs_client()
    bucket = client.bucket(REPORT_BUCKET_NAME)
    blob = bucket.blob(file_name)
    if not blob.exists():
        return None
    return blob.download_as_text()


@tests_bp.post("/parse-and-save")
def parse_and_save():
    """
    Receives JSON, reads the XML from GCS, parses it with xmltodict,
    and inserts a TestRun + TestResult* in the DB.
    Expected (JSON):
      - changeset_id, label, unity_version, developer_email, report_id, branch, project, file_name
      - (optional) jenkins_url
    Required header if API_KEY is set:
      - X-API-KEY: <key>
    """
    # Simple key-based auth
    if API_KEY:
        api_key = request.headers.get("X-API-KEY")
        if api_key != API_KEY:
            return jsonify({"error": "Unauthorized"}), 401

    data = request.get_json() or {}
    required = [
        "changeset_id", "label", "unity_version", "developer_email",
        "report_id", "branch", "project", "file_name",
    ]
    missing = [f for f in required if f not in data]
    if missing:
        return jsonify({"error": f"Missing required fields: {', '.join(missing)}"}), 400

    xml_text = _read_xml_from_gcs(data["file_name"])
    if xml_text is None:
        return jsonify({"error": f"File {data['file_name']} not found in bucket {REPORT_BUCKET_NAME}"}), 404

    # Parse XML (supports 'test-suite' or 'test-run')
    parsed = xmltodict.parse(xml_text)
    suite = parsed.get("test-suite") or parsed.get("test-run") or {}

    def attr(d: dict, key: str, default=None):
        return d.get(f"@{key}", default)

    suite_name = attr(suite, "name")
    result = attr(suite, "result")
    duration = attr(suite, "duration")
    total_tests = attr(suite, "testcasecount")
    passed_tests = attr(suite, "passed")
    failed_tests = attr(suite, "failed")
    inconclusive_tests = attr(suite, "inconclusive")
    skipped_tests = attr(suite, "skipped")
    failure_message = (suite.get("failure") or {}).get("message")

    # Create TestRun (stores the full XML in extra_data)
    run = TestRun(
        suite_name=suite_name,
        result=result,
        duration=duration,
        total_tests=total_tests,
        passed_tests=passed_tests,
        failed_tests=failed_tests,
        inconclusive_tests=inconclusive_tests,
        skipped_tests=skipped_tests,
        failure_message=failure_message,
        report_id=data["report_id"],          # ⚠️ your /stats page builds ${report_id}.xml
        branch=data["branch"],
        project=data["project"],
        jenkins_url=data.get("jenkins_url"),
        extra_data=parsed,
    )
    save_result(run)

    # Normalize test-case into a list
    cases = suite.get("test-case", [])
    if not isinstance(cases, list):
        cases = [cases]

    for tc in cases:
        test_name = tc.get("@fullname") or tc.get("@name")
        status = tc.get("@result", "Unknown")
        test_duration = tc.get("@duration", "0")
        failure = tc.get("failure") or {}
        message = failure.get("message", "Test passed")
        stack = failure.get("stack-trace", "No stack trace")
        output = tc.get("output", "No output")

        tr = TestResult(
            test_name=test_name,
            status=status,
            changeset_id=data["changeset_id"],
            label=data["label"],
            unity_version=data["unity_version"],
            developer_email=data["developer_email"],
            duration=test_duration,
            message=message,
            stack_trace=stack,
            output=output,
            test_run=run,
        )
        save_result(tr)

    return jsonify({"message": "OK"}), 200


@tests_bp.get("/stats")
def stats_json():
    """
    Returns the stats for the /stats (bootstrap) page by reading the DB, same as your V1.
    Structure:
    {
      total_tests, passed, failed, success_rate, projects_tested,
      latest_tests_grouped: [
        {
          changeset_id, report_id, jenkins_url, tests: [
            {project, test_name, status, developer_email, unity_version, duration}
          ]
        }, ...
      ]
    }
    """
    db = SessionLocal()
    try:
        total = db.query(TestResult).count()
        passed = db.query(TestResult).filter(TestResult.status == "Passed").count()
        failed = db.query(TestResult).filter(TestResult.status == "Failed").count()
        projects = db.query(TestRun.project).distinct().count()

        recent = (
            db.query(TestResult)
              .order_by(TestResult.id.desc())
              .limit(50)
              .all()
        )

        grouped = defaultdict(list)
        for t in recent:
            report_id = t.test_run.report_id if t.test_run else "unknown"
            changeset = t.changeset_id or "unknown"
            grouped[(changeset, report_id)].append(t)

        groups = []
        for (changeset_id, report_id), tests in grouped.items():
            most_recent_id = max(x.id for x in tests)
            groups.append({
                "changeset_id": changeset_id,
                "report_id": report_id,  # /stats frontend builds ${report_id}.xml
                "jenkins_url": tests[0].test_run.jenkins_url if tests and tests[0].test_run else None,
                "tests": [
                    {
                        "project": (tt.test_run.project if tt.test_run else "unknown"),
                        "test_name": tt.test_name,
                        "status": tt.status,
                        "developer_email": tt.developer_email,
                        "unity_version": tt.unity_version,
                        "duration": tt.duration,
                    }
                    for tt in tests
                ],
                "most_recent_id": most_recent_id,
            })

        groups.sort(key=lambda g: g["most_recent_id"], reverse=True)
        groups = groups[:10]

        success_rate = round((passed / total) * 100, 2) if total else 0.0

        return jsonify({
            "total_tests": total,
            "passed": passed,
            "failed": failed,
            "success_rate": success_rate,
            "projects_tested": projects,
            "latest_tests_grouped": groups,
        })
    finally:
        db.close()
