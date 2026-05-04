"""
Bandwidth throttling tests for Multus secondary network interface via bridge CNI.

RFE Reference:
https://redhat.atlassian.net/browse/RFE-7066
"""

from typing import Final

import pytest

from libs.net.ip import filter_link_local_addresses
from libs.net.vmspec import lookup_iface_status
from tests.network.l2_bridge.bandwidth.lib_helpers import (
    BANDWIDTH_RATE_BPS,
    BANDWIDTH_SECONDARY_IFACE_NAME,
    active_tcp_connection_output,
    assert_bidir_throughput_within_limit,
)

_BANDWIDTH_TOLERANCE: Final[float] = 1.1


@pytest.mark.polarion("CNV-15244")
def test_bandwidth_limit_enforced_on_secondary_interface(
    subtests,
    server_vm,
    client_vm,
    bandwidth_nad,
):
    """
    Test that bandwidth throttling is enforced on a secondary network interface.

    Preconditions:
        - Linux bridge NetworkAttachmentDefinition (Bridge CNI) configured with a 10 Mbps bandwidth limit
          on both ingress and egress using the CNI bandwidth plugin
        - Server VM running and attached to the bandwidth-limited secondary network
        - Client VM running and attached to the bandwidth-limited secondary network

    Steps:
        1. For each IP address on the server VM's secondary interface (based on the cluster network stack):
            a. Run a 10-second bidirectional iperf3 TCP session simultaneously between the client and server VMs
            b. Measure the average received throughput in both directions

    Expected:
        - Average throughput in both directions does not exceed the configured bandwidth limit (10 Mbps)
          with a 10% tolerance

    """
    iface = lookup_iface_status(vm=server_vm, iface_name=BANDWIDTH_SECONDARY_IFACE_NAME)
    for server_ip in filter_link_local_addresses(ip_addresses=iface.ipAddresses):
        with subtests.test(msg=f"Bandwidth limit for {server_ip}"):
            json_output = active_tcp_connection_output(
                server_vm=server_vm,
                client_vm=client_vm,
                server_ip=str(server_ip),
            )
            assert_bidir_throughput_within_limit(
                iperf3_json_report=json_output,
                rate_bps=BANDWIDTH_RATE_BPS,
                tolerance=_BANDWIDTH_TOLERANCE,
                server_ip=str(server_ip),
            )
