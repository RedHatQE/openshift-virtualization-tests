# -*- coding: utf-8 -*-

"""
Test to check, SELinuxLauncher Type in kubevirt config map
"""

import pytest

pytestmark = [pytest.mark.post_upgrade, pytest.mark.arm64]


@pytest.mark.polarion("CNV-4296")
@pytest.mark.s390x
def test_selinuxlaunchertype_in_kubevirt_config(kubevirt_config):
    selinux_launcher_type = "selinuxLauncherType"
    assert selinux_launcher_type not in kubevirt_config, f"{selinux_launcher_type} is found in {kubevirt_config}"
