"""Cluster-independent regression tests for the EVPN OpenPERouter helpers."""

from collections.abc import Callable
from itertools import chain, repeat
from unittest.mock import Mock, patch

import pytest
from ocp_resources.exceptions import ExecOnPodError
from ocp_resources.pod import Pod
from timeout_sampler import TimeoutExpiredError

from tests.network.bgp.evpn.utils import (
    OpenPERouterAttachment,
    validate_openperouter_parent_interface,
    wait_for_openperouter_l2_vni,
    wait_for_openperouter_l3_vni,
    wait_for_openperouter_raw_frr_config,
)
from tests.network.libs.bgp import NET_TOOLS_CONTAINER_NAME

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    argnames="readiness_check, check_kwargs, expected_command",
    argvalues=[
        (
            wait_for_openperouter_l2_vni,
            {"vni": 10100},
            ["ip", "netns", "exec", "perouter", "ip", "link", "show", "br-pe-10100"],
        ),
        (
            wait_for_openperouter_l3_vni,
            {},
            ["ip", "netns", "exec", "perouter", "ip", "link", "show", "vrf-blue"],
        ),
        (
            wait_for_openperouter_raw_frr_config,
            {},
            ["cat", "/etc/perouter/frr/frr.conf"],
        ),
    ],
)
class TestOpenPERouterReadiness:
    @pytest.mark.parametrize(argnames="transient_failure", argvalues=[False, True])
    def test_ready_resource_completes_retry(
        self,
        readiness_check: Callable[..., bool],
        check_kwargs: dict[str, int],
        expected_command: list[str],
        transient_failure: bool,
    ) -> None:
        """Exercise the real retry decorator and sampler, including recovery."""
        diagnostics_pod = Mock(spec=Pod)
        successful_output = "route-map evpn-to-ocp permit 10"
        diagnostics_pod.execute.side_effect = [
            *([ExecOnPodError(command=expected_command, rc=1, out="", err="not ready")] if transient_failure else []),
            successful_output,
        ]
        with (
            patch(target="timeout_sampler.TimeoutWatch") as timeout_watch,
            patch(target="timeout_sampler.time.sleep"),
        ):
            timeout_watch.return_value.remaining_time.side_effect = chain(repeat(1, times=10), repeat(0))
            assert readiness_check(diagnostics_pod=diagnostics_pod, **check_kwargs), "Ready resource did not complete"

        assert diagnostics_pod.execute.call_count == 1 + transient_failure, "Unexpected number of readiness attempts"
        diagnostics_pod.execute.assert_called_with(command=expected_command, container=NET_TOOLS_CONTAINER_NAME)

    def test_unavailable_resource_times_out(
        self,
        readiness_check: Callable[..., bool],
        check_kwargs: dict[str, int],
        expected_command: list[str],
    ) -> None:
        """A persistent command failure must not be reported as success."""
        diagnostics_pod = Mock(spec=Pod)
        diagnostics_pod.execute.side_effect = ExecOnPodError(command=expected_command, rc=1, out="", err="not ready")
        with (
            patch(target="timeout_sampler.TimeoutWatch") as timeout_watch,
            patch(target="timeout_sampler.time.sleep"),
        ):
            timeout_watch.return_value.remaining_time.side_effect = chain(repeat(1, times=10), repeat(0))
            with pytest.raises(expected_exception=TimeoutExpiredError):
                readiness_check(diagnostics_pod=diagnostics_pod, **check_kwargs)


class TestOpenPERouterRawConfig:
    def test_incomplete_config_is_retried(self) -> None:
        diagnostics_pod = Mock(spec=Pod)
        diagnostics_pod.execute.side_effect = ["router bgp 64000", "route-map evpn-to-ocp permit 10"]
        with (
            patch(target="timeout_sampler.TimeoutWatch") as timeout_watch,
            patch(target="timeout_sampler.time.sleep"),
        ):
            timeout_watch.return_value.remaining_time.side_effect = chain(repeat(1, times=10), repeat(0))
            assert wait_for_openperouter_raw_frr_config(diagnostics_pod=diagnostics_pod), (
                "Rendered config did not complete"
            )

        assert diagnostics_pod.execute.call_count == 2, "Incomplete config was not retried"

    def test_incomplete_config_times_out(self) -> None:
        diagnostics_pod = Mock(spec=Pod)
        diagnostics_pod.execute.return_value = "router bgp 64000"
        with (
            patch(target="timeout_sampler.TimeoutWatch") as timeout_watch,
            patch(target="timeout_sampler.time.sleep"),
        ):
            timeout_watch.return_value.remaining_time.side_effect = chain(repeat(1, times=10), repeat(0))
            with pytest.raises(expected_exception=TimeoutExpiredError):
                wait_for_openperouter_raw_frr_config(diagnostics_pod=diagnostics_pod)


class TestOpenPERouterParentInterface:
    @pytest.mark.parametrize(argnames="parent_present", argvalues=[False, True])
    def test_parent_interface_on_host(self, parent_present: bool) -> None:
        diagnostics_pod = Mock(spec=Pod)
        diagnostics_pod.node_name = "provider-worker"
        diagnostics_pod.execute.return_value = '[{"ifname": "lo"}, {"ifname": "ens1"}]' if parent_present else "[]"
        attachment = OpenPERouterAttachment(
            parent_interface="ens1", provider_ipv4="192.0.2.50/24", vtep_cidr="198.51.100.50/32"
        )
        if parent_present:
            validate_openperouter_parent_interface(diagnostics_pod=diagnostics_pod, attachment=attachment)
        else:
            with pytest.raises(expected_exception=ValueError, match="ens1.*provider-worker"):
                validate_openperouter_parent_interface(diagnostics_pod=diagnostics_pod, attachment=attachment)

        diagnostics_pod.execute.assert_called_once_with(
            command=["ip", "-j", "link", "show"], container=NET_TOOLS_CONTAINER_NAME
        )

    def test_inventory_failure_is_propagated(self) -> None:
        diagnostics_pod = Mock(spec=Pod)
        diagnostics_pod.execute.side_effect = ExecOnPodError(
            command=["ip", "-j", "link", "show"], rc=1, out="", err="permission denied"
        )
        attachment = OpenPERouterAttachment(
            parent_interface="ens1", provider_ipv4="192.0.2.50/24", vtep_cidr="198.51.100.50/32"
        )
        with pytest.raises(expected_exception=ExecOnPodError):
            validate_openperouter_parent_interface(diagnostics_pod=diagnostics_pod, attachment=attachment)
