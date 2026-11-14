"""Conftest for manual_tests_reporter tests."""

import os
from collections.abc import Generator
from pathlib import Path
from unittest.mock import patch

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
def isolated_git_identity(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Make owner derivation independent of any local git identity.

    The reporter derives the ``owner`` tag from the scanned checkout's git
    identity, so without this a developer's own ``user.email`` leaks into the
    suite and CI (no git identity at all) fails where a laptop passes.

    All three sources are cut off, not just the global one:
    ``GIT_CONFIG_GLOBAL``/``GIT_CONFIG_SYSTEM`` point at an empty file, and
    ``GIT_CEILING_DIRECTORIES`` stops git from walking up out of the temporary
    test tree into an enclosing clone's repository-local config.

    Tests that exercise owner derivation patch ``_get_git_user_email`` (as
    ``test_get_git_user_email_reads_tests_checkout`` needs the real function)
    or pass ``--owner`` explicitly.
    """
    empty_config = tmp_path / "gitconfig"
    empty_config.write_text(data="", encoding="utf-8")
    monkeypatch.setenv(name="GIT_CONFIG_GLOBAL", value=str(empty_config))
    monkeypatch.setenv(name="GIT_CONFIG_SYSTEM", value=str(empty_config))
    monkeypatch.setenv(name="GIT_CEILING_DIRECTORIES", value=str(tmp_path))


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


@pytest.fixture
def datadog_upload_ready(monkeypatch: pytest.MonkeyPatch) -> Generator[None]:
    """Satisfy the pre-upload preflight without a real datadog-ci.

    The reporter refuses to start collecting verdicts unless an API key is set
    and ``datadog-ci`` is on PATH. Tests that exercise the post-verdict path
    patch the upload function itself, so a stub key and a fake PATH hit are
    enough.
    """
    monkeypatch.setenv(name="DATADOG_API_KEY", value="test-key")
    # Patched by string target: importing the reporter module here would run
    # before this conftest's arch_env_bootstrap import sets the architecture
    # env var the utilities import chain resolves at import time.
    with patch(
        target="scripts.manual_tests_reporter.manual_tests_reporter.shutil.which",
        return_value="/usr/bin/datadog-ci",
    ):
        yield
