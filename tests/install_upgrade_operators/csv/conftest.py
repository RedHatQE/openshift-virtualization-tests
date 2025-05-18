import logging

import pytest
from pytest_testconfig import py_config

from utilities.infra import get_kubevirt_package_manifest

LOGGER = logging.getLogger(__name__)


class KubevirtManifestChannelNotFoundError(Exception):
    pass


@pytest.fixture(scope="package")
def kubevirt_package_manifest_channels(admin_client):
    kubevirt_package_manifest = get_kubevirt_package_manifest(admin_client=admin_client)
    assert kubevirt_package_manifest, f"Package manifest {py_config['hco_cr_name']} not found"
    return kubevirt_package_manifest.status.channels


@pytest.fixture(scope="package")
def kubevirt_package_manifest_current_channel(kubevirt_package_manifest_channels, cnv_current_version):
    for channel in kubevirt_package_manifest_channels:
        if channel.currentCSVDesc.version == cnv_current_version:
            LOGGER.info(f"Channel {channel.name} is associated with cnv version: {cnv_current_version}")
            return channel
    raise KubevirtManifestChannelNotFoundError(
        f"Not able to find channel matching {cnv_current_version} in the package manifest."
        f"Available channels: {[channel.name for channel in kubevirt_package_manifest_channels]}"
    )


@pytest.fixture()
def csv_annotation(csv_scope_session):
    """
    Gets csv annotation for csv_scope_session.ApiGroup.INFRA_FEATURES
    """
    return csv_scope_session.instance.metadata.annotations.get(
        f"{csv_scope_session.ApiGroup.OPERATORS_OPENSHIFT_IO}/infrastructure-features"
    )
