"""Cluster binary download fixtures (virtctl, oc)."""

import logging
import os

import pytest

from utilities.constants.components import VIRTCTL_CLI_DOWNLOADS
from utilities.infra import download_file_from_cluster

LOGGER = logging.getLogger(__name__)


@pytest.fixture(scope="session")
def bin_directory(tmpdir_factory):
    return tmpdir_factory.mktemp("bin")


@pytest.fixture(scope="session")
def os_path_environment():
    return os.environ["PATH"]


@pytest.fixture(scope="session")
def virtctl_binary(installing_cnv, bin_directory, admin_client):
    if installing_cnv:
        return
    installed_virtctl = os.environ.get("CNV_TESTS_VIRTCTL_BIN")
    if installed_virtctl:
        LOGGER.warning(f"Using previously installed: {installed_virtctl}")
        return
    return download_file_from_cluster(
        get_console_spec_links_name=VIRTCTL_CLI_DOWNLOADS, dest_dir=bin_directory, admin_client=admin_client
    )


@pytest.fixture(scope="session")
def oc_binary(bin_directory, admin_client):
    installed_oc = os.environ.get("CNV_TESTS_OC_BIN")
    if installed_oc:
        LOGGER.warning(f"Using previously installed: {installed_oc}")
        return
    return download_file_from_cluster(
        get_console_spec_links_name="oc-cli-downloads", dest_dir=bin_directory, admin_client=admin_client
    )


@pytest.fixture(scope="session")
def bin_directory_to_os_path(os_path_environment, bin_directory, virtctl_binary, oc_binary):
    LOGGER.info(f"Adding {bin_directory} to $PATH")
    os.environ["PATH"] = f"{bin_directory}:{os_path_environment}"
