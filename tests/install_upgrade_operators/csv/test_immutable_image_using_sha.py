import pytest

from tests.install_upgrade_operators.csv.utils import (
    get_kubevirt_package_manifest_images,
)

pytestmark = pytest.mark.sno


@pytest.fixture()
def hco_package_stable_channel_images(admin_client):
    """
    Get a list of all images in the kubevirt-hyperconverged package on the stable channel
    """
    return get_kubevirt_package_manifest_images(admin_client=admin_client)


@pytest.mark.polarion("CNV-4751")
def test_immutable_image_using_sha(hco_package_stable_channel_images):
    """
    check all images of the stable channel on the kubevirt-hyperconverged Package Manifest.
    make sure all images have SHA256 in their string (this indicates they are immutable)
    """
    # verify all images contain "sha256" in their name. on failure this will be a list of images without "sha256"
    assert not list(filter(lambda image: "sha256" not in image, hco_package_stable_channel_images))
