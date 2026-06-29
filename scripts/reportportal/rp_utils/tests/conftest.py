"""Conftest for rp_utils tests."""

import os
from collections.abc import Generator

import pytest

from scripts.reportportal.tests_common import ORIGINAL_ARCH


@pytest.fixture(autouse=True, scope="session")
def _mock_cluster_architecture() -> Generator[None]:
    """Restore original architecture env var after tests complete."""
    yield
    if ORIGINAL_ARCH is None:
        os.environ.pop("OPENSHIFT_VIRTUALIZATION_TEST_IMAGES_ARCH", None)
    else:
        os.environ["OPENSHIFT_VIRTUALIZATION_TEST_IMAGES_ARCH"] = ORIGINAL_ARCH
