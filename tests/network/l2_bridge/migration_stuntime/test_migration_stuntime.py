"""
Linux bridge migration stuntime measurement tests over live migration.

Tests measure the connectivity gap (stuntime) during VM live migration on Linux bridge
secondary network, for both IPv4 and IPv6, for regression detection.
Stuntime is defined as the connectivity gap from last successful reply before loss
to first successful reply after recovery.

STP Reference:
https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/blob/main/stps/sig-network/stuntime_measurement.md
"""

import pytest

__test__ = False

"""
Parametrize:
    - ip_family:
        - ipv4 [Markers: ipv4]
        - ipv6 [Markers: ipv6]
"""


@pytest.mark.polarion("CNV-00001")
def test_client_migrates_same_to_different():
    """
    Test that measured stuntime does not exceed the global threshold when the client
    VM migrates from the node hosting the server VM into a different node.

    Preconditions:
        - Under-test server VM on Linux bridge secondary network.
        - Under-test client VM on Linux bridge secondary network, running on the same node as the server VM.
        - Ping initiated from the client to the server.

    Steps:
        1. Initiate live migration of the client VM to a node different from the node hosting the server VM
           and wait for migration completion.
        2. Stop the continuous ping.
        3. Compute stuntime from the ping results.

    Expected:
        - Measured stuntime does not exceed the global threshold.
    """


@pytest.mark.polarion("CNV-00002")
def test_client_migrates_between_different():
    """
    Test that measured stuntime does not exceed the global threshold when the client VM migrates between nodes
    while the client and server VMs remain on different nodes.

    Preconditions:
        - Under-test server VM on Linux bridge secondary network.
        - Under-test client VM on Linux bridge secondary network, running on a worker node other than the node
          hosting the server VM.
        - Ping initiated from the client to the server.

    Steps:
        1. Initiate live migration of the client VM to a node different from the node hosting the server VM
           and wait for migration completion.
        2. Stop the continuous ping.
        3. Compute stuntime from the ping results.

    Expected:
        - Measured stuntime does not exceed the global threshold.
    """


@pytest.mark.polarion("CNV-00003")
def test_client_migrates_different_to_same():
    """
    Test that measured stuntime does not exceed the global threshold when the client VM migrates
    from a node other than the node hosting the server VM onto the node hosting the server VM.

    Preconditions:
        - Under-test server VM on Linux bridge secondary network.
        - Under-test client VM on Linux bridge secondary network, running on a worker node other than the node
          hosting the server VM.
        - Ping initiated from the client to the server.

    Steps:
        1. Initiate live migration of the client VM to the node hosting the server VM
           and wait for migration completion.
        2. Stop the continuous ping.
        3. Compute stuntime from the ping results.

    Expected:
        - Measured stuntime does not exceed the global threshold.
    """


@pytest.mark.polarion("CNV-00004")
def test_server_migrates_same_to_different():
    """
    Test that measured stuntime does not exceed the global threshold when the server
    VM migrates from the node hosting the client VM into a different node.

    Preconditions:
        - Under-test server VM on Linux bridge secondary network.
        - Under-test client VM on Linux bridge secondary network, running on the same node as the server VM.
        - Ping initiated from the client to the server.

    Steps:
        1. Initiate live migration of the server VM to a node different from the node hosting the client VM
           and wait for migration completion.
        2. Stop the continuous ping.
        3. Compute stuntime from the ping results.

    Expected:
        - Measured stuntime does not exceed the global threshold.
    """


@pytest.mark.polarion("CNV-00005")
def test_server_migrates_between_different():
    """
    Test that measured stuntime does not exceed the global threshold when the server VM migrates between nodes
    while the client and server VMs remain on different nodes.

    Preconditions:
        - Under-test server VM on Linux bridge secondary network.
        - Under-test client VM on Linux bridge secondary network, running on a worker node other than the node
          hosting the server VM (before and after migration).
        - Ping initiated from the client to the server.

    Steps:
        1. Initiate live migration of the server VM to a node different from the node hosting the client VM
           and wait for migration completion.
        2. Stop the continuous ping.
        3. Compute stuntime from the ping results.

    Expected:
        - Measured stuntime does not exceed the global threshold.
    """


@pytest.mark.polarion("CNV-00006")
def test_server_migrates_different_to_same():
    """
    Test that measured stuntime does not exceed the global threshold when the server VM migrates from a node
    other than the node hosting the client VM onto the node hosting the client VM.

    Preconditions:
        - Under-test server VM on Linux bridge secondary network.
        - Under-test client VM on Linux bridge secondary network, running on a worker node other than the node
          hosting the server VM.
        - Ping initiated from the client to the server.

    Steps:
        1. Initiate live migration of the server VM to the node hosting the client VM
           and wait for migration completion.
        2. Stop the continuous ping.
        3. Compute stuntime from the ping results.

    Expected:
        - Measured stuntime does not exceed the global threshold.
    """
