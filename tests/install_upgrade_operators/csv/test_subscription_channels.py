import pytest

pytestmark = [pytest.mark.sno, pytest.mark.s390x]


@pytest.mark.polarion("CNV-7169")
def test_channels_in_manifest(kubevirt_package_manifest_channels):
    expected_channels = {"stable", "dev-preview"}
    missing_channels = expected_channels - {channel.name for channel in kubevirt_package_manifest_channels}
    assert not missing_channels, f"Missing channels: {missing_channels}"


@pytest.mark.polarion("CNV-11944")
def test_cnv_subscription_channel(
    cnv_subscription_scope_session, kubevirt_package_manifest_channels, cnv_current_version
):
    subscription_channel = cnv_subscription_scope_session.instance.spec.channel

    available_channels_for_version = [
        channel.name
        for channel in kubevirt_package_manifest_channels
        if channel.currentCSVDesc.version == cnv_current_version
    ]

    assert subscription_channel in available_channels_for_version, (
        f"CNV subscription channel '{subscription_channel}' is not valid for version {cnv_current_version}. "
        f"Available channels for this version: {available_channels_for_version}"
    )
