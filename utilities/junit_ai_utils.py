"""Utility functions for JUnit XML AI analysis enrichment.

Source: https://github.com/myk-org/jenkins-job-insight/blob/main/examples/pytest-junitxml/conftest_junit_ai_utils.py
"""

import logging
import os
import shutil
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET
from xml.etree.ElementTree import Element

import requests
from dotenv import load_dotenv

logger = logging.getLogger("jenkins-job-insight")


def is_dry_run(config) -> bool:
    """Check if pytest was invoked in dry-run mode (--collectonly or --setupplan)."""
    return config.option.setupplan or config.option.collectonly


def setup_ai_analysis(session) -> None:
    """Configure AI analysis for test failure reporting.

    Loads .env, validates JJI_SERVER_URL, and sets defaults for AI provider/model.
    Disables analysis if JJI_SERVER_URL is missing or if pytest was invoked
    with --collectonly or --setupplan.

    Args:
        session: The pytest session containing config options.
    """
    if is_dry_run(session.config):
        session.config.option.analyze_with_ai = False
        return

    load_dotenv()

    logger.info("Setting up AI-powered test failure analysis")

    if not os.environ.get("JJI_SERVER_URL"):
        logger.warning("JJI_SERVER_URL is not set. Analyze with AI features will be disabled.")
        session.config.option.analyze_with_ai = False
    else:
        if not os.environ.get("JJI_AI_PROVIDER"):
            os.environ["JJI_AI_PROVIDER"] = "claude"

        if not os.environ.get("JJI_AI_MODEL"):
            os.environ["JJI_AI_MODEL"] = "claude-opus-4-6[1m]"


def enrich_junit_xml(session) -> None:
    """Parse failures from JUnit XML, send for AI analysis, and enrich the XML.

    Reads the JUnit XML that pytest already generated, extracts all failed
    testcases, sends them to the JJI server for AI analysis, and injects
    the analysis results back into the same XML.

    Args:
        session: The pytest session containing config options.
    """
    xml_path_raw = getattr(session.config.option, "xmlpath", None)
    if not xml_path_raw or not Path(xml_path_raw).exists():
        return

    xml_path = Path(xml_path_raw)

    ai_provider = os.environ.get("JJI_AI_PROVIDER")
    ai_model = os.environ.get("JJI_AI_MODEL")
    if not ai_provider or not ai_model:
        logger.warning("JJI_AI_PROVIDER and JJI_AI_MODEL must be set, skipping AI analysis enrichment")
        return

    failures = _extract_failures_from_xml(xml_path=xml_path)
    if not failures:
        logger.info("jenkins-job-insight: No failures found in JUnit XML, skipping AI analysis")
        return

    server_url = os.environ["JJI_SERVER_URL"]
    payload: dict[str, Any] = {
        "failures": failures,
        "ai_provider": ai_provider,
        "ai_model": ai_model,
    }

    analysis_map, html_report_url = _fetch_analysis_from_server(server_url=server_url, payload=payload)
    if not analysis_map:
        return

    _apply_analysis_to_xml(xml_path=xml_path, analysis_map=analysis_map, html_report_url=html_report_url)


def _extract_failures_from_xml(xml_path: Path) -> list[dict[str, str]]:
    """Extract test failures and errors from a JUnit XML file.

    Parses the XML and finds all testcase elements with failure or error
    child elements, extracting test name, error message, and stack trace.

    Args:
        xml_path: Path to the JUnit XML report file.

    Returns:
        List of failure dicts with test_name, error_message, stack_trace, and status.
    """
    tree = ET.parse(xml_path)
    failures: list[dict[str, str]] = []

    for testcase in tree.iter("testcase"):
        failure_elem = testcase.find("failure")
        error_elem = testcase.find("error")
        result_elem = failure_elem if failure_elem is not None else error_elem

        if result_elem is None:
            continue

        classname = testcase.get("classname", "")
        name = testcase.get("name", "")
        test_name = f"{classname}.{name}" if classname else name

        failures.append({
            "test_name": test_name,
            "error_message": result_elem.get("message", ""),
            "stack_trace": result_elem.text or "",
            "status": "ERROR" if error_elem is not None and failure_elem is None else "FAILED",
        })

    return failures


def _fetch_analysis_from_server(
    server_url: str, payload: dict[str, Any]
) -> tuple[dict[tuple[str, str], dict[str, Any]], str]:
    """Send collected failures to the JJI server and return the analysis map.

    Args:
        server_url: The JJI server base URL.
        payload: Request payload containing failures and AI config.

    Returns:
        Tuple of (analysis_map, html_report_url).
        analysis_map: Mapping of (classname, test_name) to analysis results.
        html_report_url: The HTML report URL, extracted from the server response
            or constructed from job_id and server_url when the response omits it.
            Empty string if neither is available.
        Returns ({}, "") on request failure.
    """
    try:
        timeout_value = int(os.environ.get("JJI_TIMEOUT", "600"))
    except ValueError:
        logger.warning("Invalid JJI_TIMEOUT value, using default 600 seconds")
        timeout_value = 600

    try:
        response = requests.post(
            f"{server_url.rstrip('/')}/analyze-failures", json=payload, timeout=timeout_value, verify=False
        )
        response.raise_for_status()
        result = response.json()
    except (requests.RequestException, ValueError) as exc:
        error_detail = ""
        if isinstance(exc, requests.RequestException) and exc.response is not None:
            try:
                error_detail = f" Response: {exc.response.text}"
            except Exception as detail_exc:
                logger.debug("Could not extract response detail: %s", detail_exc)
        logger.error("Server request failed: %s%s", exc, error_detail)
        return {}, ""

    job_id = result.get("job_id", "")
    html_report_url = result.get("html_report_url") or (
        f"{server_url.rstrip('/')}/results/{job_id}.html" if job_id else ""
    )

    analysis_map: dict[tuple[str, str], dict[str, Any]] = {}
    for failure in result.get("failures", []):
        test_name = failure.get("test_name", "")
        analysis = failure.get("analysis", {})
        if test_name and analysis:
            # test_name is "classname.name" from XML extraction; split on last dot
            dot_idx = test_name.rfind(".")
            if dot_idx > 0:
                analysis_map[(test_name[:dot_idx], test_name[dot_idx + 1 :])] = analysis
            else:
                analysis_map[("", test_name)] = analysis

    return analysis_map, html_report_url


def _apply_analysis_to_xml(
    xml_path: Path,
    analysis_map: dict[tuple[str, str], dict[str, Any]],
    html_report_url: str = "",
) -> None:
    """Apply AI analysis results to JUnit XML testcase elements.

    Uses exact (classname, name) matching since failures are extracted from
    the same XML file, guaranteeing identical attribute values.
    Backs up the original XML before modification and restores it on failure.

    Args:
        xml_path: Path to the JUnit XML report file.
        analysis_map: Mapping of (classname, test_name) to analysis results.
        html_report_url: URL to the HTML report, added as a testsuite-level property.
    """
    backup_path = xml_path.with_suffix(".xml.bak")
    shutil.copy2(xml_path, backup_path)

    try:
        tree = ET.parse(xml_path)
        matched_keys: set[tuple[str, str]] = set()
        for testcase in tree.iter("testcase"):
            key = (testcase.get("classname", ""), testcase.get("name", ""))
            analysis = analysis_map.get(key)
            if analysis:
                _inject_analysis(testcase, analysis)
                matched_keys.add(key)

        unmatched = set(analysis_map.keys()) - matched_keys
        if unmatched:
            logger.warning(
                "jenkins-job-insight: %d analysis results did not match any testcase: %s",
                len(unmatched),
                unmatched,
            )

        # Add html_report_url as a testsuite-level property
        if html_report_url:
            for testsuite in tree.iter("testsuite"):
                ts_props = testsuite.find("properties")
                if ts_props is None:
                    ts_props = ET.Element("properties")
                    testsuite.insert(0, ts_props)
                _add_property(ts_props, "html_report_url", html_report_url)

        tree.write(str(xml_path), encoding="unicode", xml_declaration=True)
        backup_path.unlink()  # Success - remove backup
    except Exception:
        # Restore original XML from backup
        shutil.copy2(backup_path, xml_path)
        backup_path.unlink()
        raise


def _inject_analysis(testcase: Element, analysis: dict[str, Any]) -> None:
    """Inject AI analysis into a JUnit XML testcase element.

    Adds structured properties (classification, code fix, bug report) and a
    human-readable summary to the testcase's system-out section.

    Args:
        testcase: The XML testcase element to enrich.
        analysis: Analysis dict with classification, details, affected_tests, etc.
    """
    # Add structured properties
    properties = testcase.find("properties")
    if properties is None:
        properties = ET.SubElement(testcase, "properties")

    _add_property(properties, "ai_classification", analysis.get("classification", ""))
    _add_property(properties, "ai_details", analysis.get("details", ""))

    affected = analysis.get("affected_tests", [])
    if affected:
        _add_property(properties, "ai_affected_tests", ", ".join(affected))

    # Code fix properties
    code_fix = analysis.get("code_fix")
    if code_fix and isinstance(code_fix, dict):
        _add_property(properties, "ai_code_fix_file", code_fix.get("file", ""))
        _add_property(properties, "ai_code_fix_line", str(code_fix.get("line", "")))
        _add_property(properties, "ai_code_fix_change", code_fix.get("change", ""))

    # Product bug properties
    bug_report = analysis.get("product_bug_report")
    if bug_report and isinstance(bug_report, dict):
        _add_property(properties, "ai_bug_title", bug_report.get("title", ""))
        _add_property(properties, "ai_bug_severity", bug_report.get("severity", ""))
        _add_property(properties, "ai_bug_component", bug_report.get("component", ""))
        _add_property(properties, "ai_bug_description", bug_report.get("description", ""))

        # Jira match properties
        jira_matches = bug_report.get("jira_matches", [])
        for idx, match in enumerate(jira_matches):
            if isinstance(match, dict):
                _add_property(properties, f"ai_jira_match_{idx}_key", match.get("key", ""))
                _add_property(properties, f"ai_jira_match_{idx}_summary", match.get("summary", ""))
                _add_property(properties, f"ai_jira_match_{idx}_status", match.get("status", ""))
                _add_property(properties, f"ai_jira_match_{idx}_url", match.get("url", ""))
                _add_property(
                    properties,
                    f"ai_jira_match_{idx}_priority",
                    match.get("priority", ""),
                )
                score = match.get("score")
                if score is not None:
                    _add_property(properties, f"ai_jira_match_{idx}_score", str(score))

    # Add human-readable system-out
    text = _format_analysis_text(analysis)
    if text:
        system_out = testcase.find("system-out")
        if system_out is None:
            system_out = ET.SubElement(testcase, "system-out")
            system_out.text = text
        else:
            # Append to existing system-out
            existing = system_out.text or ""
            system_out.text = f"{existing}\n\n--- AI Analysis ---\n{text}" if existing else text


def _add_property(properties_elem: Element, name: str, value: str) -> None:
    """Add a property sub-element if value is non-empty."""
    if value:
        prop = ET.SubElement(properties_elem, "property")
        prop.set("name", name)
        prop.set("value", value)


def _format_analysis_text(analysis: dict[str, Any]) -> str:
    """Format analysis dict as human-readable text for system-out."""
    parts = []

    classification = analysis.get("classification", "")
    if classification:
        parts.append(f"Classification: {classification}")

    details = analysis.get("details", "")
    if details:
        parts.append(f"\n{details}")

    code_fix = analysis.get("code_fix")
    if code_fix and isinstance(code_fix, dict):
        parts.append("\nCode Fix:")
        parts.append(f"  File: {code_fix.get('file', '')}")
        parts.append(f"  Line: {code_fix.get('line', '')}")
        parts.append(f"  Change: {code_fix.get('change', '')}")

    bug_report = analysis.get("product_bug_report")
    if bug_report and isinstance(bug_report, dict):
        parts.append("\nProduct Bug:")
        parts.append(f"  Title: {bug_report.get('title', '')}")
        parts.append(f"  Severity: {bug_report.get('severity', '')}")
        parts.append(f"  Component: {bug_report.get('component', '')}")
        parts.append(f"  Description: {bug_report.get('description', '')}")

        jira_matches = bug_report.get("jira_matches", [])
        if jira_matches:
            parts.append("\nPossible Jira Matches:")
            for match in jira_matches:
                if isinstance(match, dict):
                    key = match.get("key", "")
                    summary = match.get("summary", "")
                    status = match.get("status", "")
                    url = match.get("url", "")
                    parts.append(f"  {key}: {summary} [{status}] {url}")

    return "\n".join(parts) if parts else ""
