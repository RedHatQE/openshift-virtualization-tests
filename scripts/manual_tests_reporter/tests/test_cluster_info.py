# Co-authored-by: Claude <noreply@anthropic.com>
"""Tests for scripts.manual_tests_reporter.cluster_info module.

See scripts/manual_tests_reporter/README.md for the tool this module belongs to.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from kubernetes.client.exceptions import ApiException
from urllib3.exceptions import HTTPError

from scripts.manual_tests_reporter.cluster_info import (
    ClusterAttributes,
    _extract_domain_from_api_url,
    cluster_attributes_to_run_attrs,
    get_cluster_attributes,
)

CLUSTER_INFO_MODULE = "scripts.manual_tests_reporter.cluster_info"


class TestExtractDomainFromApiUrl:
    def test_api_prefix_stripped_with_port(self) -> None:
        """Verify the api. prefix is stripped and the port is ignored."""
        result = _extract_domain_from_api_url(api_url="https://api.bm15a.example.com:6443")
        assert result == "bm15a.example.com", f"Expected 'bm15a.example.com', got {result!r}"

    def test_no_api_prefix_kept(self) -> None:
        """Verify a hostname without the api. prefix is returned unchanged."""
        result = _extract_domain_from_api_url(api_url="https://foo.example.com:6443")
        assert result == "foo.example.com", f"Expected 'foo.example.com', got {result!r}"

    def test_empty_url_returns_none(self) -> None:
        """Verify an empty URL yields None so the attribute is omitted."""
        result = _extract_domain_from_api_url(api_url="")
        assert result is None, "Expected: empty URL yields None"

    def test_unparseable_url_returns_none(self) -> None:
        """Verify an unparseable URL yields None so the attribute is omitted."""
        result = _extract_domain_from_api_url(api_url="not a url")
        assert result is None, "Expected: unparseable URL yields None"


class TestClusterAttributesToRunAttrs:
    def test_none_fields_excluded(self) -> None:
        """Verify None fields are omitted from the run attributes."""
        result = cluster_attributes_to_run_attrs(
            cluster_attrs=ClusterAttributes(arch="amd64", ocp_version="4.22.0"),
        )
        assert result == [
            {"key": "ARCH", "value": "amd64"},
            {"key": "OCP", "value": "4.22.0"},
        ], f"Expected only the filled fields, got {result!r}"

    def test_full_mapping(self) -> None:
        """Verify all filled fields map to their run-attribute keys."""
        result = cluster_attributes_to_run_attrs(
            cluster_attrs=ClusterAttributes(
                arch="amd64",
                ocp_version="4.22.0",
                cnv_xy_version="4.22",
                bundle="v4.22.0.rhel9-102",
                cluster_name="bm15a",
                cluster_domain="bm15a.example.com",
                storage_class="OCS",
                channel="candidate",
            ),
        )
        attrs_by_key = {attr["key"]: attr["value"] for attr in result}
        assert attrs_by_key == {
            "ARCH": "amd64",
            "OCP": "4.22.0",
            "CNV_XY_VER": "4.22",
            "BUNDLE": "v4.22.0.rhel9-102",
            "CLUSTER_NAME": "bm15a",
            "CLUSTER_DOMAIN": "bm15a.example.com",
            "SC": "OCS",
            "CHANNEL": "candidate",
        }, f"Expected full mapping, got {attrs_by_key!r}"

    def test_manual_attribute_not_added_here(self) -> None:
        """Verify the MANUAL attribute is not injected by this converter."""
        result = cluster_attributes_to_run_attrs(cluster_attrs=ClusterAttributes(arch="amd64"))
        assert all(attr["key"] != "MANUAL" for attr in result), (
            "Expected: MANUAL is added by _build_run_attributes, not here"
        )


class TestGetClusterAttributes:
    def test_client_creation_api_exception_returns_empty_attrs(self) -> None:
        """Verify an ApiException during client creation degrades to empty attributes."""
        with patch(
            target=f"{CLUSTER_INFO_MODULE}.cache_admin_client",
            side_effect=ApiException(status=401, reason="Unauthorized"),
        ):
            attrs = get_cluster_attributes()

        assert attrs == ClusterAttributes(), f"Expected all-None attributes, got {attrs!r}"

    def test_partial_failures_fill_only_available_fields(self) -> None:
        """Verify per-query failures warn and leave only the filled fields."""
        with (
            patch(target=f"{CLUSTER_INFO_MODULE}.cache_admin_client", return_value=MagicMock()),
            patch(target=f"{CLUSTER_INFO_MODULE}.get_cluster_architecture", return_value={"amd64"}),
            patch(target=f"{CLUSTER_INFO_MODULE}.get_clusterversion", side_effect=ApiException(status=403)),
            patch(target=f"{CLUSTER_INFO_MODULE}.HyperConverged", side_effect=ApiException(status=403)),
            patch(target=f"{CLUSTER_INFO_MODULE}.get_infrastructure", side_effect=ApiException(status=403)),
            patch(target=f"{CLUSTER_INFO_MODULE}.get_default_storage_class", side_effect=ApiException(status=403)),
            patch(target=f"{CLUSTER_INFO_MODULE}.Subscription", side_effect=ApiException(status=403)),
        ):
            attrs = get_cluster_attributes()

        assert attrs.arch == "amd64", f"Expected 'amd64', got {attrs.arch!r}"
        assert attrs.ocp_version is None, "Expected: failed queries leave fields as None"
        assert attrs.bundle is None, "Expected: failed queries leave fields as None"
        assert attrs.cluster_name is None, "Expected: failed queries leave fields as None"
        assert attrs.storage_class is None, "Expected: failed queries leave fields as None"
        assert attrs.channel is None, "Expected: failed queries leave fields as None"

    def test_malformed_api_server_url_degrades_to_warning(self) -> None:
        """Verify a malformed apiServerURL fails soft instead of aborting the run."""
        infra_mock = MagicMock()
        infra_mock.instance.status.infrastructureName = "bm15a"
        infra_mock.instance.status.apiServerURL = "https://[::1"

        with (
            patch(target=f"{CLUSTER_INFO_MODULE}.cache_admin_client", return_value=MagicMock()),
            patch(target=f"{CLUSTER_INFO_MODULE}.get_cluster_architecture", side_effect=ApiException(status=403)),
            patch(target=f"{CLUSTER_INFO_MODULE}.get_clusterversion", side_effect=ApiException(status=403)),
            patch(target=f"{CLUSTER_INFO_MODULE}.HyperConverged", side_effect=ApiException(status=403)),
            patch(target=f"{CLUSTER_INFO_MODULE}.get_infrastructure", return_value=infra_mock),
            patch(target=f"{CLUSTER_INFO_MODULE}.get_default_storage_class", side_effect=ApiException(status=403)),
            patch(target=f"{CLUSTER_INFO_MODULE}.Subscription", side_effect=ApiException(status=403)),
        ):
            attrs = get_cluster_attributes()

        assert attrs.cluster_name == "bm15a", f"Expected 'bm15a', got {attrs.cluster_name!r}"
        assert attrs.cluster_domain is None, "Expected: malformed URL degrades to None, not a traceback"

    def test_transport_error_during_query_degrades_to_warning(self) -> None:
        """Verify a transport failure mid-query (HTTPError) fails soft per attribute."""
        with (
            patch(target=f"{CLUSTER_INFO_MODULE}.cache_admin_client", return_value=MagicMock()),
            patch(target=f"{CLUSTER_INFO_MODULE}.get_cluster_architecture", side_effect=HTTPError("connection reset")),
            patch(target=f"{CLUSTER_INFO_MODULE}.get_clusterversion", side_effect=HTTPError("connection reset")),
            patch(target=f"{CLUSTER_INFO_MODULE}.HyperConverged", side_effect=HTTPError("connection reset")),
            patch(target=f"{CLUSTER_INFO_MODULE}.get_infrastructure", side_effect=HTTPError("connection reset")),
            patch(target=f"{CLUSTER_INFO_MODULE}.get_default_storage_class", side_effect=HTTPError("connection reset")),
            patch(target=f"{CLUSTER_INFO_MODULE}.Subscription", side_effect=HTTPError("connection reset")),
        ):
            attrs = get_cluster_attributes()

        assert attrs.arch is None, "Expected: transport error degrades to None, not a traceback"
        assert attrs.ocp_version is None, "Expected: transport error degrades to None, not a traceback"
        assert attrs.bundle is None, "Expected: transport error degrades to None, not a traceback"
        assert attrs.cluster_name is None, "Expected: transport error degrades to None, not a traceback"
        assert attrs.storage_class is None, "Expected: transport error degrades to None, not a traceback"
        assert attrs.channel is None, "Expected: transport error degrades to None, not a traceback"
