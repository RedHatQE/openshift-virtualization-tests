# Co-authored-by: Claude <noreply@anthropic.com>
"""Tests for scripts.manual_tests_reporter.cluster_info module.

See scripts/manual_tests_reporter/README.md for the tool this module belongs to.
"""

from __future__ import annotations

from unittest.mock import MagicMock, _patch, patch

from kubernetes.client.exceptions import ApiException
from urllib3.exceptions import HTTPError

from scripts.manual_tests_reporter.cluster_info import (
    ClusterAttributes,
    _extract_domain_from_api_url,
    cluster_attributes_to_run_attrs,
    get_cluster_attributes,
)

CLUSTER_INFO_MODULE = "scripts.manual_tests_reporter.cluster_info"


def _node_name_patch(*node_names: str) -> _patch:
    """Build a patch of Node.get yielding nodes with the given names."""
    node_mocks = []
    for node_name in node_names:
        node_mock = MagicMock()
        node_mock.name = node_name
        node_mocks.append(node_mock)
    return patch(target=f"{CLUSTER_INFO_MODULE}.Node.get", return_value=iter(node_mocks))


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
            cluster_attrs=ClusterAttributes(cluster_id="bm15a-tjxpz", ocp_version="4.22.0"),
        )
        assert result == [
            {"key": "ocp_version", "value": "4.22.0"},
            {"key": "cluster_id", "value": "bm15a-tjxpz"},
        ], f"Expected only the filled fields, got {result!r}"

    def test_full_mapping(self) -> None:
        """Verify all filled fields map to their run-attribute keys."""
        result = cluster_attributes_to_run_attrs(
            cluster_attrs=ClusterAttributes(
                ocp_version="4.22.0",
                cnv_version="4.22.0",
                cnv_xy_version="4.22",
                cluster_name="bm15a",
                cluster_id="bm15a-tjxpz",
                cluster_domain="bm15a.example.com",
                storage_class="OCS",
                channel="candidate",
                cni="OVNKubernetes",
            ),
        )
        attrs_by_key = {attr["key"]: attr["value"] for attr in result}
        assert attrs_by_key == {
            "ocp_version": "4.22.0",
            "cnv_version": "4.22.0",
            "cnv_xy_version": "4.22",
            "cluster": "bm15a",
            "cluster_id": "bm15a-tjxpz",
            "cluster_domain": "bm15a.example.com",
            "storage_class": "OCS",
            "cnv_channel": "candidate",
            "cni": "OVNKubernetes",
        }, f"Expected full mapping, got {attrs_by_key!r}"

    def test_manual_attribute_not_added_here(self) -> None:
        """Verify the MANUAL attribute is not injected by this converter."""
        result = cluster_attributes_to_run_attrs(cluster_attrs=ClusterAttributes(cluster_id="bm15a-tjxpz"))
        assert all(attr["key"] != "manual" for attr in result), (
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
            _node_name_patch("bm15a-tjxpz-master-0"),
            patch(target=f"{CLUSTER_INFO_MODULE}.get_clusterversion", side_effect=ApiException(status=403)),
            patch(target=f"{CLUSTER_INFO_MODULE}.HyperConverged", side_effect=ApiException(status=403)),
            patch(target=f"{CLUSTER_INFO_MODULE}.get_infrastructure", side_effect=ApiException(status=403)),
            patch(target=f"{CLUSTER_INFO_MODULE}.get_default_storage_class", side_effect=ApiException(status=403)),
            patch(target=f"{CLUSTER_INFO_MODULE}.Subscription.get", side_effect=ApiException(status=403)),
        ):
            attrs = get_cluster_attributes()

        assert attrs.cluster_id == "bm15a-tjxpz", f"Expected 'bm15a-tjxpz', got {attrs.cluster_id!r}"
        assert attrs.ocp_version is None, "Expected: failed queries leave fields as None"
        assert attrs.cnv_version is None, "Expected: failed queries leave fields as None"
        assert attrs.cluster_name is None, "Expected: failed queries leave fields as None"
        assert attrs.storage_class is None, "Expected: failed queries leave fields as None"
        assert attrs.channel is None, "Expected: failed queries leave fields as None"
        assert attrs.cni is None, "Expected: failed queries leave fields as None"

    def test_cni_derived_from_cluster_network(self) -> None:
        """Verify the cni attribute comes from the cluster Network status."""
        network_instance = MagicMock()
        network_instance.instance.status.networkType = "OVNKubernetes"
        with (
            patch(target=f"{CLUSTER_INFO_MODULE}.cache_admin_client", return_value=MagicMock()),
            _node_name_patch("bm15a-tjxpz-master-0"),
            patch(target=f"{CLUSTER_INFO_MODULE}.get_clusterversion", side_effect=ApiException(status=403)),
            patch(target=f"{CLUSTER_INFO_MODULE}.HyperConverged", side_effect=ApiException(status=403)),
            patch(target=f"{CLUSTER_INFO_MODULE}.get_infrastructure", side_effect=ApiException(status=403)),
            patch(target=f"{CLUSTER_INFO_MODULE}.get_default_storage_class", side_effect=ApiException(status=403)),
            patch(target=f"{CLUSTER_INFO_MODULE}.Subscription.get", side_effect=ApiException(status=403)),
            patch(target=f"{CLUSTER_INFO_MODULE}.ClusterNetwork", return_value=network_instance),
        ):
            attrs = get_cluster_attributes()

        assert attrs.cni == "OVNKubernetes", f"Expected 'OVNKubernetes', got {attrs.cni!r}"

    def test_cni_missing_api_group_degrades_to_warning(self) -> None:
        """Verify an undiscoverable Network API leaves cni unset instead of failing."""
        with (
            patch(target=f"{CLUSTER_INFO_MODULE}.cache_admin_client", return_value=MagicMock()),
            _node_name_patch("bm15a-tjxpz-master-0"),
            patch(target=f"{CLUSTER_INFO_MODULE}.get_clusterversion", side_effect=ApiException(status=403)),
            patch(target=f"{CLUSTER_INFO_MODULE}.HyperConverged", side_effect=ApiException(status=403)),
            patch(target=f"{CLUSTER_INFO_MODULE}.get_infrastructure", side_effect=ApiException(status=403)),
            patch(target=f"{CLUSTER_INFO_MODULE}.get_default_storage_class", side_effect=ApiException(status=403)),
            patch(target=f"{CLUSTER_INFO_MODULE}.Subscription.get", side_effect=ApiException(status=403)),
            patch(
                target=f"{CLUSTER_INFO_MODULE}.ClusterNetwork",
                side_effect=NotImplementedError("Couldn't find Network in config.openshift.io api group"),
            ),
        ):
            attrs = get_cluster_attributes()

        assert attrs.cni is None, f"Expected cni to stay unset, got {attrs.cni!r}"
        assert attrs.cluster_id == "bm15a-tjxpz", "Expected: the other queries still fill their fields"

    def test_cluster_id_from_node_name_prefix(self) -> None:
        """Verify cluster_id is the node-name prefix (Jenkins CLUSTER_ID format)."""
        with (
            patch(target=f"{CLUSTER_INFO_MODULE}.cache_admin_client", return_value=MagicMock()),
            _node_name_patch("infd-vrf-412t0-n47k6-master-0"),
            patch(target=f"{CLUSTER_INFO_MODULE}.get_clusterversion", side_effect=ApiException(status=403)),
            patch(target=f"{CLUSTER_INFO_MODULE}.HyperConverged", side_effect=ApiException(status=403)),
            patch(target=f"{CLUSTER_INFO_MODULE}.get_infrastructure", side_effect=ApiException(status=403)),
            patch(target=f"{CLUSTER_INFO_MODULE}.get_default_storage_class", side_effect=ApiException(status=403)),
            patch(target=f"{CLUSTER_INFO_MODULE}.Subscription.get", side_effect=ApiException(status=403)),
        ):
            attrs = get_cluster_attributes()

        assert attrs.cluster_id == "infd-vrf-412t0-n47k6", f"Expected the node-name prefix, got {attrs.cluster_id!r}"

    def test_cluster_id_from_worker_node(self) -> None:
        """Verify a worker-only node list still yields the cluster id."""
        with (
            patch(target=f"{CLUSTER_INFO_MODULE}.cache_admin_client", return_value=MagicMock()),
            _node_name_patch("infd-vrf-412t0-n47k6-worker-0"),
            patch(target=f"{CLUSTER_INFO_MODULE}.get_clusterversion", side_effect=ApiException(status=403)),
            patch(target=f"{CLUSTER_INFO_MODULE}.HyperConverged", side_effect=ApiException(status=403)),
            patch(target=f"{CLUSTER_INFO_MODULE}.get_infrastructure", side_effect=ApiException(status=403)),
            patch(target=f"{CLUSTER_INFO_MODULE}.get_default_storage_class", side_effect=ApiException(status=403)),
            patch(target=f"{CLUSTER_INFO_MODULE}.Subscription.get", side_effect=ApiException(status=403)),
        ):
            attrs = get_cluster_attributes()

        assert attrs.cluster_id == "infd-vrf-412t0-n47k6", (
            f"Expected the worker node-name prefix, got {attrs.cluster_id!r}"
        )

    def test_cluster_id_skips_infra_node_sorted_first(self) -> None:
        """Verify an infra node sorting before masters does not defeat the derivation.

        Node.get returns name-sorted nodes; "<id>-infra-0" sorts before
        "<id>-master-0", so the derivation must scan past non-master/worker
        nodes instead of giving up on the first one.
        """
        with (
            patch(target=f"{CLUSTER_INFO_MODULE}.cache_admin_client", return_value=MagicMock()),
            _node_name_patch("bm15a-tjxpz-infra-0", "bm15a-tjxpz-master-0", "bm15a-tjxpz-worker-0"),
            patch(target=f"{CLUSTER_INFO_MODULE}.get_clusterversion", side_effect=ApiException(status=403)),
            patch(target=f"{CLUSTER_INFO_MODULE}.HyperConverged", side_effect=ApiException(status=403)),
            patch(target=f"{CLUSTER_INFO_MODULE}.get_infrastructure", side_effect=ApiException(status=403)),
            patch(target=f"{CLUSTER_INFO_MODULE}.get_default_storage_class", side_effect=ApiException(status=403)),
            patch(target=f"{CLUSTER_INFO_MODULE}.Subscription.get", side_effect=ApiException(status=403)),
        ):
            attrs = get_cluster_attributes()

        assert attrs.cluster_id == "bm15a-tjxpz", (
            f"Expected the master node prefix past the infra node, got {attrs.cluster_id!r}"
        )

    def test_cluster_id_none_on_bare_role_node_name(self) -> None:
        """Verify a bare role node name (SNO "master-0") yields no cluster_id.

        A bare role name has no cluster prefix; cluster_id stays unset
        instead of emitting an empty tag.
        """
        with (
            patch(target=f"{CLUSTER_INFO_MODULE}.cache_admin_client", return_value=MagicMock()),
            _node_name_patch("master-0", "worker-0"),
            patch(target=f"{CLUSTER_INFO_MODULE}.get_clusterversion", side_effect=ApiException(status=403)),
            patch(target=f"{CLUSTER_INFO_MODULE}.HyperConverged", side_effect=ApiException(status=403)),
            patch(target=f"{CLUSTER_INFO_MODULE}.get_infrastructure", side_effect=ApiException(status=403)),
            patch(target=f"{CLUSTER_INFO_MODULE}.get_default_storage_class", side_effect=ApiException(status=403)),
            patch(target=f"{CLUSTER_INFO_MODULE}.Subscription.get", side_effect=ApiException(status=403)),
        ):
            attrs = get_cluster_attributes()

        assert attrs.cluster_id is None, "Expected: bare role node names leave cluster_id as None"

    def test_cluster_id_none_on_empty_node_list(self) -> None:
        """Verify cluster_id is omitted when the cluster has no nodes."""
        with (
            patch(target=f"{CLUSTER_INFO_MODULE}.cache_admin_client", return_value=MagicMock()),
            patch(target=f"{CLUSTER_INFO_MODULE}.Node.get", return_value=iter(())),
            patch(target=f"{CLUSTER_INFO_MODULE}.get_clusterversion", side_effect=ApiException(status=403)),
            patch(target=f"{CLUSTER_INFO_MODULE}.HyperConverged", side_effect=ApiException(status=403)),
            patch(target=f"{CLUSTER_INFO_MODULE}.get_infrastructure", side_effect=ApiException(status=403)),
            patch(target=f"{CLUSTER_INFO_MODULE}.get_default_storage_class", side_effect=ApiException(status=403)),
            patch(target=f"{CLUSTER_INFO_MODULE}.Subscription.get", side_effect=ApiException(status=403)),
        ):
            attrs = get_cluster_attributes()

        assert attrs.cluster_id is None, "Expected: empty node list leaves cluster_id as None"

    def test_malformed_api_server_url_degrades_to_warning(self) -> None:
        """Verify a malformed apiServerURL fails soft instead of aborting the run."""
        infra_mock = MagicMock()
        infra_mock.instance.status.infrastructureName = "bm15a"
        infra_mock.instance.status.apiServerURL = "https://[::1"

        with (
            patch(target=f"{CLUSTER_INFO_MODULE}.cache_admin_client", return_value=MagicMock()),
            _node_name_patch("bm15a-tjxpz-master-0"),
            patch(target=f"{CLUSTER_INFO_MODULE}.get_clusterversion", side_effect=ApiException(status=403)),
            patch(target=f"{CLUSTER_INFO_MODULE}.HyperConverged", side_effect=ApiException(status=403)),
            patch(target=f"{CLUSTER_INFO_MODULE}.get_infrastructure", return_value=infra_mock),
            patch(target=f"{CLUSTER_INFO_MODULE}.get_default_storage_class", side_effect=ApiException(status=403)),
            patch(target=f"{CLUSTER_INFO_MODULE}.Subscription.get", side_effect=ApiException(status=403)),
        ):
            attrs = get_cluster_attributes()

        assert attrs.cluster_name == "bm15a", f"Expected 'bm15a', got {attrs.cluster_name!r}"
        assert attrs.cluster_domain is None, "Expected: malformed URL degrades to None, not a traceback"

    def test_transport_error_during_query_degrades_to_warning(self) -> None:
        """Verify a transport failure mid-query (HTTPError) fails soft per attribute."""
        with (
            patch(target=f"{CLUSTER_INFO_MODULE}.cache_admin_client", return_value=MagicMock()),
            patch(target=f"{CLUSTER_INFO_MODULE}.Node.get", side_effect=HTTPError("connection reset")),
            patch(target=f"{CLUSTER_INFO_MODULE}.get_clusterversion", side_effect=HTTPError("connection reset")),
            patch(target=f"{CLUSTER_INFO_MODULE}.HyperConverged", side_effect=HTTPError("connection reset")),
            patch(target=f"{CLUSTER_INFO_MODULE}.get_infrastructure", side_effect=HTTPError("connection reset")),
            patch(target=f"{CLUSTER_INFO_MODULE}.get_default_storage_class", side_effect=HTTPError("connection reset")),
            patch(target=f"{CLUSTER_INFO_MODULE}.Subscription.get", side_effect=HTTPError("connection reset")),
        ):
            attrs = get_cluster_attributes()

        assert attrs.cluster_id is None, "Expected: transport error degrades to None, not a traceback"
        assert attrs.ocp_version is None, "Expected: transport error degrades to None, not a traceback"
        assert attrs.cnv_version is None, "Expected: transport error degrades to None, not a traceback"
        assert attrs.cluster_name is None, "Expected: transport error degrades to None, not a traceback"
        assert attrs.storage_class is None, "Expected: transport error degrades to None, not a traceback"
        assert attrs.channel is None, "Expected: transport error degrades to None, not a traceback"
