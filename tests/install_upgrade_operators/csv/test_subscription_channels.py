import pytest

pytestmark = pytest.mark.sno


@pytest.mark.polarion("CNV-7169")
@pytest.mark.s390x
def test_channels_in_manifest(kubevirt_package_manifest_channels):
    expected_channels = {"stable", "dev-preview"}
    missing_channels = expected_channels - {channel.name for channel in kubevirt_package_manifest_channels}
    assert not missing_channels, f"Missing channels: {missing_channels}"


@pytest.mark.polarion("CNV-11944")
@pytest.mark.s390x
def test_cnv_subscription_channel(cnv_subscription_scope_session, kubevirt_package_manifest_current_channel):
    assert cnv_subscription_scope_session.instance.spec.channel == kubevirt_package_manifest_current_channel.name
