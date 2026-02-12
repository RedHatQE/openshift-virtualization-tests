"""
Pytest conftest for CNV-72329 NAD swap tests.

STP Reference: examples/CNV-72329/CNV-72329_test_description.yaml
Jira: CNV-72329
"""

import logging

import pytest

from utilities.infra import create_ns

LOGGER = logging.getLogger(__name__)


@pytest.fixture(scope="module")
def namespace(admin_client, unprivileged_client):
    """
    Test namespace for CNV-72329 NAD swap tests.

    Yields:
        Namespace: Test namespace resource
    """
    yield from create_ns(
        admin_client=admin_client,
        unprivileged_client=unprivileged_client,
        name="cnv-72329-nad-swap",
    )
