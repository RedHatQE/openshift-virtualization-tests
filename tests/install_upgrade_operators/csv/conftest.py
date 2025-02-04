import logging

import pytest
from pytest_testconfig import py_config

from tests.install_upgrade_operators.csv.utils import (
    KubevirtManifestChannelNotFoundError,
)
from utilities.infra import get_kubevirt_package_manifest

LOGGER = logging.getLogger(__name__)


@pytest.fixture()
def kubevirt_package_manifest(admin_client):
    """
    Find kubevirt raw package manifest associated with hco-catalogsource.
    """
    package_manifest = get_kubevirt_package_manifest(admin_client=admin_client)
    assert package_manifest, f"Package manifest{py_config['hco_cr_name']} not found"
    return package_manifest


@pytest.fixture()
def kubevirt_package_manifest_channel(kubevirt_package_manifest, cnv_current_version):
    """
    Return channel name from Kubevirt Package Manifest.
    """
    channels = kubevirt_package_manifest.status.channels
    for channel in channels:
        if channel.currentCSVDesc.version == cnv_current_version:
            LOGGER.info(f"Getting channel associated with cnv version: {cnv_current_version}")
            return channel.name
    raise KubevirtManifestChannelNotFoundError(
        f"Not able to find channel matching {cnv_current_version} in the package manifest."
        f" Avaliable channels: {channels}"
    )


@pytest.fixture()
def csv_annotation(csv_scope_session):
    """
    Gets csv annotation for csv_scope_session.ApiGroup.INFRA_FEATURES
    """
    return csv_scope_session.instance.metadata.annotations.get(
        f"{csv_scope_session.ApiGroup.OPERATORS_OPENSHIFT_IO}/infrastructure-features"
    )
