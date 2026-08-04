# Networking Tests

Validate and verify virtualization networking topologies like SR-IOV, L2 Bridging, and IPv6 by writing robust network tests. This guide shows how to ensure VirtualMachines correctly route traffic, apply network policies, and handle complex network configurations reliably.

## Prerequisites

*   An OpenShift cluster configured with the desired networking operators (e.g., NMState, SR-IOV Network Operator).
*   Test fixtures providing running VirtualMachines (VMs) connected to the target networks.
*   Familiarity with test markers and execution (see [Running and Filtering Tests](running-tests.html)).

## Quick Example

The most common network test validates basic connectivity (e.g., pinging from one VM to another over a specific interface). Here is a simple example using built-in network utilities:

```python
import pytest
from libs.net.vmspec import lookup_iface_status_ip
from utilities.network import assert_ping_successful

@pytest.mark.ipv4
def test_vm_basic_connectivity(vm_a, vm_b, target_network):
    # Lookup the destination IP on VM B's secondary interface
    dst_ip = lookup_iface_status_ip(
        vm=vm_b,
        iface_name=target_network.name,
        ip_family=4
    )

    # Assert successful ping from VM A to VM B's IP
    assert_ping_successful(src_vm=vm_a, dst_ip=dst_ip)
```

## Step-by-Step: Testing Network Configurations

When developing tests for complex networking features like L2 bridges or SR-IOV, follow these steps to ensure reliable results.

### 1. Extract the Destination IP Address

Do not hardcode or assume IP addresses. Always dynamically look up the IP address of the target VM on the specific interface being tested.

```python
from libs.net.vmspec import lookup_iface_status_ip

# Fetch IPv4 address for a specific interface
ip_address = lookup_iface_status_ip(
    vm=my_target_vm,
    iface_name="bridge-network",
    ip_family=4
)
```

### 2. Verify Connectivity or Packet Loss

Instead of using raw sub-processes or direct SSH libraries, use the project's utility functions to verify connectivity behaviors (like pings or packet loss) with built-in retry logic and robust logging.

*   **Successful Ping:** `assert_ping_successful(src_vm, dst_ip)`
*   **Failed Ping (Negative Test):** `assert_no_ping(src_vm, dst_ip)`

> **Tip:** If you need to test connectivity *during* an event (e.g., during live migration), use polling functions like `wait_for_no_packet_loss_after_connection` from the L2 bridge utilities.

### 3. Tag with Special Infrastructure Markers

Networking features often require specific hardware (like GPUs or physical network cards) or cluster configurations. You MUST tag tests requiring non-standard capabilities using the appropriate infrastructure markers.

```python
import pytest

pytestmark = [
    pytest.mark.special_infra,
    pytest.mark.sriov,  # Requires SR-IOV hardware
]
```

See [Implementing New Tests](implementing-tests.html) for more details on properly tagging infrastructure requirements.

## Advanced Usage

### Testing Network Policies

When testing network policies, you often need to verify that specific ports are blocked or allowed. Use the `run_ssh_commands` utility to execute commands like `curl` directly from the source VM.

```python
import shlex
import pytest
from pyhelper_utils.exceptions import CommandExecFailed
from pyhelper_utils.shell import run_ssh_commands

def test_network_policy_deny_http(vm_a, vm_b, deny_all_policy):
    dst_ip = vm_b.vmi.interfaces[0].ipAddress
    command = shlex.split(f"curl --connect-timeout 5 -I http://{dst_ip}:80")

    # Expect the command to fail because the policy denies the traffic
    with pytest.raises(CommandExecFailed):
        run_ssh_commands(
            host=vm_a.ssh_exec,
            commands=[command]
        )
```

### IPv6 and Link-Local Addresses

If your test operates in an IPv6 environment, standard IP lookups might return a list of addresses including link-local addresses. You can filter these specifically if your scenario requires routing via `fe80::` addresses:

```python
from libs.net.ip import filter_link_local_addresses
from libs.net.vmspec import lookup_iface_status

def test_ipv6_link_local_ping(vm_a, vm_b, ipv6_network):
    # Fetch all IPs for the interface
    all_ips = lookup_iface_status(vm=vm_b, iface_name=ipv6_network.name)["ipAddresses"]

    # Filter for link-local addresses only
    link_local_ips = filter_link_local_addresses(ip_addresses=all_ips)

    for dst_ip in link_local_ips:
         assert_ping_successful(src_vm=vm_a, dst_ip=dst_ip)
```

### Testing L2 Protocols (DHCP, Custom Ethernet Types)

When testing lower-level protocols over bridging configurations (like OVS or Linux Bridges), you might need to broadcast or send custom Ethernet types.

| Traffic Type | Implementation Strategy |
|---|---|
| **DHCP Broadcast** | Use `TimeoutSampler` to poll `lookup_iface_status_ip` until an IP in the DHCP range is assigned. |
| **Custom EtherTypes** | Execute tools like `nping -e eth1 --ether-type 0x88B6` via `run_ssh_commands` and parse the output. |
| **Multicast** | Use `assert_ping_successful` targeting multicast IPs (e.g., `224.0.0.1`). |

See [Resource Lifecycle & Validation](resource-lifecycle.html) for detailed usage of polling timeouts during network traffic evaluation.

## Troubleshooting

*   **Interface IP Not Found:** If `lookup_iface_status_ip` fails or returns `None`, the VM might still be booting or the secondary network might be incorrectly configured. Wrap the lookup in a timeout loop to wait for the IP to appear.
*   **SSH Command Timeouts:** Commands executed over SSH might hang indefinitely if a network policy silently drops traffic. Always use `--connect-timeout` (or equivalent flags) in tools like `curl` to ensure they fail fast.
*   **Fixture Collection Errors:** If tests complain about missing networking components or undefined fixtures, ensure your test environment supports the requested network type and that you haven't forgotten required decorators (e.g., `@pytest.mark.ipv4`).

## Related Pages

- [Virtualization Tests](virt-tests.html)
- [Storage Tests](storage-tests.html)
- [Infrastructure & Observability](infrastructure-observability.html)
