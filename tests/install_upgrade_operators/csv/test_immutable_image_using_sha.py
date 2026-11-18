import pytest

pytestmark = [pytest.mark.sno, pytest.mark.s390x, pytest.mark.skip_must_gather_collection]


def test_immutable_image_using_sha(kubevirt_package_manifest_current_channel):
    """
    Jira: https://redhat.atlassian.net/browse/KNIP-1206 # <skip-jira-utils-check>
    Polarion: CNV-4751

    check all images of the current channel on the kubevirt-hyperconverged Package Manifest.
    make sure all images have SHA256 in their string (this indicates they are immutable)
    """
    related_images = kubevirt_package_manifest_current_channel.currentCSVDesc["relatedImages"]
    images_without_sha256 = [image for image in related_images if "sha256" not in image]
    assert not images_without_sha256, f"The following images are mutable: {images_without_sha256}"
