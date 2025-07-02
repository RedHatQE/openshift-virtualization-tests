import os.path
import re

import pytest
from pyhelper_utils.shell import run_command

from utilities.constants import AMD_64
from utilities.infra import get_machine_platform

pytestmark = [pytest.mark.post_upgrade, pytest.mark.sno, pytest.mark.gating]

ARM_64 = "arm64"


def validate_virtctl_versions(virtctl_bin):
    _, virtctl_output, _ = run_command(
        command=[f"{virtctl_bin} version"],
        shell=True,
        check=False,
    )
    client_and_server_versions = re.findall(
        r'(?:Client|Server).*version.*{GitVersion:"v(.*)",\s+GitCommit',
        virtctl_output,
    )

    assert len(client_and_server_versions) == 2, (
        "regex did not produced the expected number of matches: {virtctl_output}"
    )
    assert len(set(client_and_server_versions)) == 1, (
        f"Compare error: virtctl client and server versions are not identical: versions={client_and_server_versions}"
    )


class TestDisconnectedVirtctlDownload:
    @pytest.mark.parametrize(
        "downloaded_and_extracted_virtctl_binary_for_os",
        [
            pytest.param(
                {"os": "win", "machine_type": AMD_64},
                marks=(pytest.mark.polarion("CNV-6914"),),
                id="test_download_virtcli_binary_win_amd64",
            ),
            pytest.param(
                {"os": "win", "machine_type": ARM_64},
                marks=(pytest.mark.polarion("CNV-10098"), pytest.mark.arm64),
                id="test_download_virtcli_binary_win_arm64",
            ),
            pytest.param(
                {"os": "mac", "machine_type": AMD_64},
                marks=(pytest.mark.polarion("CNV-6954"),),
                id="test_download_virtcli_binary_mac_amd64",
            ),
            pytest.param(
                {"os": "mac", "machine_type": ARM_64},
                marks=(pytest.mark.polarion("CNV-10099"), pytest.mark.arm64),
                id="test_download_virtcli_binary_mac_arm64",
            ),
        ],
        indirect=True,
    )
    @pytest.mark.s390x
    def test_download_virtcli_binary(
        self,
        downloaded_and_extracted_virtctl_binary_for_os,
    ):
        assert os.path.exists(downloaded_and_extracted_virtctl_binary_for_os)


class TestDisconnectedVirtctlDownloadAndExecute:
    @pytest.mark.parametrize(
        ("downloaded_and_extracted_virtctl_binary_for_os", "platform"),
        [
            pytest.param(
                {"os": "linux", "machine_type": AMD_64},
                AMD_64,
                marks=(pytest.mark.polarion("CNV-6913"),),
                id="test_download_virtcli_binary_linux_amd64",
            ),
            pytest.param(
                {"os": "linux", "machine_type": ARM_64},
                ARM_64,
                marks=(pytest.mark.polarion("CNV-10097"), pytest.mark.arm64),
                id="test_download_virtcli_binary_linux_arm64",
            ),
        ],
        indirect=["downloaded_and_extracted_virtctl_binary_for_os"],
    )
    @pytest.mark.s390x
    def test_download_and_execute_virtcli_binary_linux(self, downloaded_and_extracted_virtctl_binary_for_os, platform):
        assert os.path.exists(downloaded_and_extracted_virtctl_binary_for_os)
        # this part should only be repeated if the execution is being done on a matching platform:
        if get_machine_platform() == platform:
            validate_virtctl_versions(virtctl_bin=downloaded_and_extracted_virtctl_binary_for_os)


@pytest.mark.arm64
class TestDisconnectedVirtctlAllLinksInternal:
    @pytest.mark.polarion("CNV-6915")
    @pytest.mark.s390x
    def test_all_links_internal(self, all_virtctl_urls, non_internal_fqdns):
        assert not non_internal_fqdns, (
            "Found virtctl URLs that do not point to the cluster internally: "
            f"violating_fqdns={non_internal_fqdns} all_virtctl_urls={all_virtctl_urls}"
        )
