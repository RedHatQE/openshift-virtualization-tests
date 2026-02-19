import logging
import time

from kubernetes import watch

from libs.vm.vm import BaseVirtualMachine
from tests.network.libs import cloudinit
from tests.network.libs.ip import random_ipv4_address, random_ipv6_address

LOGGER = logging.getLogger(__name__)
TIMEOUT_SECONDS = 300


def vm_cloud_init_data(
    ipv4_supported_cluster: bool,
    ipv6_supported_cluster: bool,
) -> cloudinit.NetworkData:

    ethernets = {}

    # Configure primary interface (eth0/masquerade)
    if ipv6_supported_cluster:
        ethernets["eth0"] = cloudinit.EthernetDevice(
            addresses=["fd10:0:2::2/120"],
            gateway6="fd10:0:2::1",
            dhcp4=ipv4_supported_cluster,
            dhcp6=False,
        )

    secondary_addresses = []
    if ipv4_supported_cluster:
        secondary_addresses.append(f"{random_ipv4_address(net_seed=0, host_address=1)}/24")
    if ipv6_supported_cluster:
        secondary_addresses.append(f"{random_ipv6_address(net_seed=0, host_address=1)}/64")

    ethernets["eth1"] = cloudinit.EthernetDevice(addresses=secondary_addresses)

    return cloudinit.NetworkData(ethernets=ethernets)


def monitor_vmi_interfaces(vm: BaseVirtualMachine, context: str = "") -> None:
    vmi_name = vm.vmi.name
    namespace = vm.namespace
    context_msg = f" {context}" if context else ""

    LOGGER.info(
        f"Starting {TIMEOUT_SECONDS} seconds monitoring of ipAddress field stability on VMI {vmi_name}{context_msg}"
    )

    start_time = time.time()
    iteration = 0

    watcher = watch.Watch()
    vmi_resource = vm.vmi.client.resources.get(api_version="kubevirt.io/v1", kind="VirtualMachineInstance")

    try:
        for event in vmi_resource.watch(
            namespace=namespace,
            name=vmi_name,
            timeout=TIMEOUT_SECONDS,
            watcher=watcher,
        ):
            iteration += 1
            event_type = event["type"]
            vmi_obj = event["object"]

            # Check if timeout reached
            if time.time() - start_time >= TIMEOUT_SECONDS:
                LOGGER.info(
                    f"VMI {vmi_name} maintained stable ipAddress fields for {TIMEOUT_SECONDS} seconds{context_msg} "
                    f"({iteration} events)"
                )
                break

            # Only check MODIFIED status updates events
            if event_type != "MODIFIED":
                continue

            interfaces = vmi_obj.status.interfaces
            assert interfaces, f"VMI {vmi_name} has no interfaces{context_msg}"
            assert len(interfaces) == 2, (
                f"Expected 2 interfaces, found {len(interfaces)} on VMI {vmi_name}{context_msg}"
            )

            for interface in interfaces:
                assert interface.ipAddress, (
                    f"ipAddress field missing on interface {interface.name} of VMI {vmi_name}{context_msg}"
                )

            LOGGER.info(
                f"Event {iteration}: VMI {vmi_name} status updated{context_msg}, "
                f"ipAddress fields present on all interfaces"
            )
    finally:
        watcher.stop()
