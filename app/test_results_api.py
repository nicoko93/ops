import sys
import os
import xmltodict
from models import init_db, save_result, TestRun, TestResult
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine
from dotenv import load_dotenv

load_dotenv()

# Load environment variables
API_KEY = os.getenv("API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")

# Initialize sessionmaker
SessionLocal = sessionmaker(bind=create_engine(DATABASE_URL))

def parse_nunit_xml(xml_file_path):
    # Read and parse the entire XML into a dict
    with open(xml_file_path, 'r') as f:
        xml_content = f.read()
    parsed_dict = xmltodict.parse(xml_content)

    # For our structured fields, assume the top-level element is "test-suite"
    suite_data = parsed_dict.get('test-suite', {})

    # Extract attributes using the "@" prefix (if present)
    suite_name = suite_data.get('@name')
    result = suite_data.get('@result')
    duration = suite_data.get('@duration')
    total_tests = suite_data.get('@testcasecount')
    passed_tests = suite_data.get('@passed')
    failed_tests = suite_data.get('@failed')
    inconclusive_tests = suite_data.get('@inconclusive')
    skipped_tests = suite_data.get('@skipped')
    
    # Get failure message if present
    failure_message = None
    if 'failure' in suite_data:
        failure = suite_data['failure']
        failure_message = failure.get('message')

    # Extract the relevant environment variables
    changeset = os.getenv("PLASTIC_CHANGESET", "unknown")
    label = os.getenv("PLASTIC_LABEL", "unknown")
    unity_version = os.getenv("UNITY_VERSION", "unknown")
    developer_email = os.getenv("DEVELOPER_EMAIL", "unknown")
    branch = os.getenv("PLASTIC_BRANCH", "unknown")
    jenkins_url = os.getenv("JENKINS_URL", "unknown")
    project = os.getenv("PROJECT_NAME", "unknown")

    # Generate a unique report ID (using the XML file path in this example)
    report_id = xml_file_path

    # Create a TestRun record and store the full parsed XML in extra_data
    session = SessionLocal()
    test_run = TestRun(
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
        project=project,
        branch=branch,
        jenkins_url=jenkins_url,
        extra_data=parsed_dict  # Store the entire XML structure
    )
    session.add(test_run)
    session.commit()
    session.refresh(test_run)  # Get the generated ID
    test_run_id = test_run.id
    session.close()

    results = []
    # Get the list of test-case entries; ensure it's a list even if a single test-case is present
    test_cases = suite_data.get('test-case', [])
    if not isinstance(test_cases, list):
        test_cases = [test_cases]

    # Iterate over each test-case and extract details
    for testcase in test_cases:
        test_name = testcase.get('@fullname', testcase.get('@name'))
        status = testcase.get('@result', 'Unknown')
        test_duration = testcase.get('@duration', '0')

        # Extract failure details if present
        msg_text = 'Test passed'
        stack_text = 'No stack trace'
        output_text = 'No output'
        if 'failure' in testcase:
            failure_info = testcase['failure']
            msg_text = failure_info.get('message', msg_text)
            stack_text = failure_info.get('stack-trace', stack_text)
        if 'output' in testcase:
            output_text = testcase['output']

        results.append({
            "test_name": test_name,
            "status": status,
            "changeset_id": changeset,
            "label": label,
            "unity_version": unity_version,
            "developer_email": developer_email,
            "duration": test_duration,
            "message": msg_text,
            "stack_trace": stack_text,
            "output": output_text,
            "report_id": report_id,
            "test_run_id": test_run_id,  # Updated foreign key field
            "branch": branch,
            "project": project
        })

    return results

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python parse_and_store.py <path_to_nunit_xml>")
        sys.exit(1)

    xml_file = sys.argv[1]

    # Initialize DB (create tables if they don't exist)
    init_db()

    # Parse the test file and store the results
    test_results = parse_nunit_xml(xml_file)

    # Insert test results into the database
    for result_data in test_results:
        test_result = TestResult(**result_data)
        save_result(test_result)

    print(f"✅ Inserted {len(test_results)} test results into the database.")
