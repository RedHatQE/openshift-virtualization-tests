import pytest

pytestmark = pytest.mark.sno


@pytest.mark.polarion("CNV-7169")
def test_only_stable_or_candidate_channel_in_subscription(kubevirt_package_manifest_channel):
    """
    Check only stable or candidate channel is available on the CNV Subscription.
    """

    assert kubevirt_package_manifest_channel in ["stable", "candidate"], (
        f"channel is different then expected. Actual available channel {kubevirt_package_manifest_channel}"
    )
