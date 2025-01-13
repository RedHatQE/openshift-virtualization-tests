import pytest

pytestmark = pytest.mark.sno


@pytest.mark.polarion("CNV-7169")
def test_only_stable_channel_in_subscription(skip_if_nightly_channel, kubevirt_package_manifest_channel):
    """
    Check only stable channel is available on the CNV Subscription.
    """

    assert kubevirt_package_manifest_channel == "stable", (
        f"Expected only 'stable' channel.Actual available channels {kubevirt_package_manifest_channel}"
    )
