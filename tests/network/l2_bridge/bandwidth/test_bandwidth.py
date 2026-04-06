"""
Bandwidth throttling tests for Multus secondary network interface via bridge CNI.

RFE Reference:
https://redhat.atlassian.net/browse/RFE-7066
"""

import pytest


@pytest.mark.polarion("CNV-15244")
def test_bandwidth_limit_enforced_on_secondary_interface():
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


test_bandwidth_limit_enforced_on_secondary_interface.__test__ = False
