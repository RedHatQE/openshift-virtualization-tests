"""Conftest for manual_tests_reporter tests."""

import os
from collections.abc import Generator
from pathlib import Path

import pytest

from scripts.manual_tests_reporter import config as config_module
from scripts.manual_tests_reporter.tests.arch_env_bootstrap import ORIGINAL_ARCH


@pytest.fixture(autouse=True, scope="session")
def restored_arch_env() -> Generator[None]:
    """Original architecture env var, restored after the test session."""
    yield
    if ORIGINAL_ARCH is None:
        os.environ.pop("OPENSHIFT_VIRTUALIZATION_TEST_IMAGES_ARCH", None)
    else:
        os.environ["OPENSHIFT_VIRTUALIZATION_TEST_IMAGES_ARCH"] = ORIGINAL_ARCH


@pytest.fixture(autouse=True)
def isolated_config_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Generator[None]:
    """Config auto-discovery pinned to a nonexistent path.

    Keeps the suite hermetic: a developer's real
    ``~/.config/manual_tests_reporter/config.yaml`` must not leak defaults
    into tests that expect unset attributes.
    """
    monkeypatch.setattr(
        target=config_module,
        name="DEFAULT_CONFIG_PATH",
        value=tmp_path / "absent-config.yaml",
    )
    yield
