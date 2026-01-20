import pytest

pytestmark = [pytest.mark.sno, pytest.mark.s390x, pytest.mark.skip_must_gather_collection]


@pytest.mark.polarion("CNV-7169")
def test_stable_channel_in_manifest(kubevirt_package_manifest_channels):
    channels_names_from_manifest = [channel.name for channel in kubevirt_package_manifest_channels]
    assert "stable" in channels_names_from_manifest, (
        f"Stable channel must be on package manifest\nAvailable channels: {channels_names_from_manifest}"
    )


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
