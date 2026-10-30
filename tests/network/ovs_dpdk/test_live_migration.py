"""
OVS-DPDK live migration tests.

Preconditions:
    - Running reference VM with a ResourceClaimTemplate-backed OVS-DPDK network device
    - Running under-test VM with a ResourceClaimTemplate-backed OVS-DPDK network device

Markers:
    - ovs_dpdk
    - special_infra
"""

import pytest

from libs.net.traffic_generator import TcpServer, VMTcpClient, is_tcp_connection

pytestmark = [
    pytest.mark.ovs_dpdk,
    pytest.mark.special_infra,
]


@pytest.mark.parametrize(
    "ip_family",
    [
        pytest.param(4, marks=pytest.mark.ipv4, id="ipv4"),
        pytest.param(6, marks=pytest.mark.ipv6, id="ipv6"),
    ],
    indirect=True,
)
def test_connectivity_is_preserved_during_live_migration(
    ip_family: int,
    ovs_dpdk_live_migration_active_tcp_by_family: dict[int, tuple[VMTcpClient, TcpServer]],
):
    """
    Test that TCP connectivity from the under-test VM to the reference VM is preserved
    during live migration, for the parametrized IP family.

    STP: https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/blob/main/stps/sig-network/ovs-dpdk-tp-stp.md

    Parametrize:
        - ip_family:
            - ipv4 [Markers: ipv4]
            - ipv6 [Markers: ipv6]

    Preconditions:
        - Running under-test VM with a ResourceClaimTemplate-backed OVS-DPDK network device
        - Running reference VM with a ResourceClaimTemplate-backed OVS-DPDK network device
        - Active TCP connection established from the under-test VM to the reference VM
        - Live migration of the under-test VM has completed

    Steps:
        1.  Verify TCP connectivity from the under-test VM to the reference VM

    Expected:
        - The active TCP connection from the under-test VM to the reference VM is preserved
          during the migration
    """
    client, server = ovs_dpdk_live_migration_active_tcp_by_family[ip_family]
    assert is_tcp_connection(server=server, client=client), (
        f"TCP connection lost after live migration of {client.vm.name} over IPv{ip_family}"
    )
