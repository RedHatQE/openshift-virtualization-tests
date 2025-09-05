import pytest

from tests.install_upgrade_operators.console_cli_download.utils import (
    CUSTOMIZED_VIRT_DL,
    validate_custom_cli_downloads_urls_updated,
    validate_custom_cli_urls_downloaded,
)


@pytest.mark.parametrize(
    "updated_cluster_ingress_downloads_spec_links",
    [
        pytest.param(
            {
                "new_hostname": CUSTOMIZED_VIRT_DL,
            },
        ),
    ],
    indirect=True,
)
@pytest.mark.usefixtures("updated_cluster_ingress_downloads_spec_links")
class TestCustomConsoleCliDownload:
    @pytest.mark.dependency(name="test_custom_console_cli_download")
    @pytest.mark.parametrize(
        "new_hostname",
        [
            pytest.param(
                CUSTOMIZED_VIRT_DL,
                marks=pytest.mark.polarion("CNV-12277"),
            ),
        ],
    )
    def test_custom_console_cli_download(
        self,
        admin_client,
        updated_cluster_ingress_downloads_spec_links,
        new_hostname,
    ):
        validate_custom_cli_downloads_urls_updated(
            admin_client=admin_client,
            new_hostname=new_hostname,
        )

    @pytest.mark.dependency(depends=["test_custom_console_cli_download"])
    @pytest.mark.polarion("CNV-12278")
    def test_custom_console_cli_download_links_downloadable(
        self,
        admin_client,
        tmpdir,
        updated_cluster_ingress_downloads_spec_links,
        virtctl_console_cli_downloads_spec_links,
    ):
        validate_custom_cli_urls_downloaded(
            urls=[url.href for url in virtctl_console_cli_downloads_spec_links],
            dest_dir=tmpdir,
        )
