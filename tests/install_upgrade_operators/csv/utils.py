import logging

from utilities.infra import get_kubevirt_package_manifest

LOGGER = logging.getLogger(__name__)


class KubevirtManifestChannelNotFoundError(Exception):
    pass


def get_kubevirt_package_manifest_images(admin_client, channel_name="stable"):
    for channel in get_kubevirt_package_manifest(admin_client=admin_client).status.channels:
        if channel.name == channel_name:
            LOGGER.info("For kubevirt package manifest {channel_name} channel was found.")
            return channel.currentCSVDesc["relatedImages"]
    raise KubevirtManifestChannelNotFoundError(f"For kubevirt package manifest, could not find {channel_name} channel")
