"""Utility functions for JUnit XML AI analysis enrichment.

Source: https://github.com/myk-org/jenkins-job-insight/blob/main/examples/pytest-junitxml/conftest_junit_ai_utils.py

These functions handle server communication and XML enrichment.
They are not tied to pytest and can be used independently.
"""

import logging
import os
from pathlib import Path

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
    """Read JUnit XML, send to server for analysis, write enriched XML back.

    Reads the JUnit XML that pytest generated, POSTs the raw content to the
    JJI server's /analyze-failures endpoint, and writes the enriched XML
    (with analysis results) back to the same file.

    Args:
        session: The pytest session containing config options.
    """
    xml_path_raw = getattr(session.config.option, "xmlpath", None)
    if not xml_path_raw:
        logger.warning("xunit file not found; pass --junitxml. Skipping AI analysis enrichment")
        return

    xml_path = Path(xml_path_raw)
    if not xml_path.exists():
        logger.warning(
            "xunit file not found under %s. Skipping AI analysis enrichment",
            xml_path_raw,
        )
        return

    ai_provider = os.environ.get("JJI_AI_PROVIDER")
    ai_model = os.environ.get("JJI_AI_MODEL")
    if not ai_provider or not ai_model:
        logger.warning("JJI_AI_PROVIDER and JJI_AI_MODEL must be set, skipping AI analysis enrichment")
        return

    server_url = os.environ["JJI_SERVER_URL"]
    raw_xml = xml_path.read_text()

    try:
        timeout_value = int(os.environ.get("JJI_TIMEOUT", "600"))
    except ValueError:
        logger.warning("Invalid JJI_TIMEOUT value, using default 600 seconds")
        timeout_value = 600

    try:
        response = requests.post(
            f"{server_url.rstrip('/')}/analyze-failures",
            json={
                "raw_xml": raw_xml,
                "ai_provider": ai_provider,
                "ai_model": ai_model,
            },
            timeout=timeout_value,
            verify=False,
        )
        response.raise_for_status()
        result = response.json()
    except Exception as ex:
        logger.exception(f"Failed to enrich JUnit XML, original preserved. {ex}")
        return

    if enriched_xml := result.get("enriched_xml"):
        xml_path.write_text(enriched_xml)
        logger.info("JUnit XML enriched with AI analysis: %s", xml_path)
    else:
        logger.info("No enriched XML returned (no failures or analysis failed)")
