import pytest

from tests.install_upgrade_operators.console_cli_download.utils import (
    CUSTOMIZED_VIRT_DL,
    download_custom_cli_archive,
    validate_custom_cli_downloads_urls_updated,
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
    @pytest.mark.polarion("CNV-12277")
    def test_custom_console_cli_download(
        self,
        admin_client,
    ):
        validate_custom_cli_downloads_urls_updated(
            admin_client=admin_client,
            new_hostname=CUSTOMIZED_VIRT_DL,
        )

    @pytest.mark.dependency(depends=["test_custom_console_cli_download"])
    @pytest.mark.polarion("CNV-12278")
    def test_custom_console_cli_download_links_downloadable(
        self,
        tmpdir,
        all_virtctl_urls_scope_function,
    ):
        invalid_urls = [
            url for url in all_virtctl_urls_scope_function if not download_custom_cli_archive(tmpdir=tmpdir, url=url)
        ]
        assert not invalid_urls, f"Some urls are not valid, {invalid_urls}"
