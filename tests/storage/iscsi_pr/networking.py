"""Guest networking and routed egress for the reusable WSFC preparation."""

from __future__ import annotations

from dataclasses import dataclass
from ipaddress import IPv4Address, IPv4Interface, IPv4Network
from json import loads
from logging import getLogger
from typing import TYPE_CHECKING
from urllib.parse import urlsplit
from uuid import uuid4

from pyhelper_utils.shell import run_ssh_commands
from timeout_sampler import TimeoutExpiredError, TimeoutSampler

from tests.storage.iscsi_pr.scripts import render_powershell_script
from utilities.constants.timeouts import TIMEOUT_5MIN
from utilities.windows import run_powershell

if TYPE_CHECKING:
    from typing import Any

    from utilities.virt import VirtualMachineForTests


LOGGER = getLogger(name=__name__)


@dataclass(frozen=True)
class GuestNetwork:
    """Static addresses on one namespace-isolated OVN Layer 2 network."""

    name: str
    router: IPv4Interface
    members: tuple[IPv4Interface, IPv4Interface, IPv4Interface]


@dataclass(frozen=True)
class EgressEndpoint:
    """The existing CI artifact service, resolved before changing Windows DNS."""

    address: IPv4Address
    port: int


def guest_networks() -> tuple[GuestNetwork, GuestNetwork]:
    """Return the two isolated guest networks and the DC/member address assignments."""
    first, second = (
        GuestNetwork(
            name=f"guest{index}",
            router=IPv4Interface(f"192.168.{subnet}.254/24"),
            members=(
                IPv4Interface(f"192.168.{subnet}.1/24"),
                IPv4Interface(f"192.168.{subnet}.10/24"),
                IPv4Interface(f"192.168.{subnet}.15/24"),
            ),
        )
        for index, subnet in enumerate((33, 55))
    )
    return first, second


def guest_macs(names: tuple[str, ...]) -> dict[str, str]:
    """Allocate locally administered unicast MACs for deterministic guest NIC selection."""
    return {name: "02:" + ":".join(f"{value:02x}" for value in uuid4().bytes[:5]) for name in names}


def router_cloud_init(*, networks: tuple[GuestNetwork, GuestNetwork], macs: dict[str, str]) -> dict[str, Any]:
    """Configure forwarding/NAT once on the owned router, preserving management SSH."""
    ethernets = {"uplink": {"match": {"macaddress": macs["management"]}, "set-name": "uplink", "dhcp4": True}}
    for network in networks:
        ethernets[network.name] = {
            "match": {"macaddress": macs[network.name]},
            "set-name": network.name,
            "dhcp4": False,
            "dhcp6": False,
            "addresses": [str(network.router)],
        }
    commands = [
        "#!/bin/bash",
        "set -euo pipefail",
        "sysctl -p /etc/sysctl.d/90-wsfc-router.conf",
        "systemctl enable --now firewalld",
        "firewall-cmd --permanent --new-zone=wsfc-guests",
        "firewall-cmd --permanent --zone=wsfc-guests --add-forward",
        *(f"firewall-cmd --permanent --zone=wsfc-guests --change-interface={network.name}" for network in networks),
        "firewall-cmd --permanent --zone=external --change-interface=uplink",
        "firewall-cmd --permanent --zone=external --add-service=ssh",
        "firewall-cmd --permanent --zone=external --add-masquerade",
        "firewall-cmd --permanent --new-policy=wsfc-egress",
        "firewall-cmd --permanent --policy=wsfc-egress --add-ingress-zone=wsfc-guests",
        "firewall-cmd --permanent --policy=wsfc-egress --add-egress-zone=external",
        "firewall-cmd --permanent --policy=wsfc-egress --set-target=ACCEPT",
        "firewall-cmd --reload",
    ]
    return {
        "networkData": {"version": 2, "ethernets": ethernets},
        "userData": {
            "packages": ["firewalld"],
            "write_files": [
                {"path": "/etc/sysctl.d/90-wsfc-router.conf", "content": "net.ipv4.ip_forward=1\n"},
                {
                    "path": "/usr/local/sbin/configure-wsfc-router",
                    "permissions": "0700",
                    "content": "\n".join(commands),
                },
            ],
            "runcmd": [["/usr/local/sbin/configure-wsfc-router"]],
        },
    }


def validate_router_networks(
    *, addresses: list[dict[str, Any]], routes: list[dict[str, Any]], networks: tuple[GuestNetwork, GuestNetwork]
) -> None:
    """Reject missing static NICs or overlap with the management routing table."""
    defaults = [route for route in routes if route["dst"] == "default"]
    assert len(defaults) == 1 and defaults[0]["dev"] == "uplink", (
        f"Router must retain one management default route via uplink; observed: {defaults}"
    )
    for network in networks:
        matches = [interface for interface in addresses if interface["ifname"] == network.name]
        assert len(matches) == 1 and any(
            address["local"] == str(network.router.ip) and address["prefixlen"] == network.router.network.prefixlen
            for address in matches[0]["addr_info"]
        ), f"Router interface {network.name}: expected {network.router}; observed: {matches}"
        for route in routes:
            if route["dst"] != "default" and route["dev"] not in {entry.name for entry in networks}:
                assert not IPv4Network(route["dst"], strict=False).overlaps(network.router.network), (
                    f"Guest subnet {network.router.network} overlaps router management route {route['dst']}"
                )


def router_readiness(
    *, vm: VirtualMachineForTests, networks: tuple[GuestNetwork, GuestNetwork], artifact_url: str
) -> EgressEndpoint:
    """Check live and persistent router policy and resolve the CI-owned TCP endpoint."""
    LOGGER.info(f"VM {vm.name}: checking router interfaces, routes, forwarding and egress policy")
    outputs = run_ssh_commands(host=vm.ssh_exec, commands=[["ip", "-j", "-4", "addr"], ["ip", "-j", "-4", "route"]])
    validate_router_networks(addresses=loads(s=outputs[0]), routes=loads(s=outputs[1]), networks=networks)
    forwarding, _, policy_target = run_ssh_commands(
        host=vm.ssh_exec,
        commands=[
            ["sysctl", "-n", "net.ipv4.ip_forward"],
            ["sudo", "firewall-cmd", "--zone=external", "--query-masquerade"],
            ["sudo", "firewall-cmd", "--permanent", "--policy=wsfc-egress", "--get-target"],
        ],
    )
    assert forwarding.strip() == "1", f"VM {vm.name}: expected IPv4 forwarding=1, observed {forwarding!r}"
    assert policy_target.strip() == "ACCEPT", (
        f"VM {vm.name}: expected wsfc-egress policy target ACCEPT, observed {policy_target!r}"
    )
    endpoint = urlsplit(url=artifact_url)
    if endpoint.scheme not in {"http", "https"} or endpoint.hostname is None:
        raise ValueError("CI artifact service must have an HTTP(S) URL")
    resolved = run_ssh_commands(host=vm.ssh_exec, commands=["getent", "ahostsv4", endpoint.hostname])[0].splitlines()
    address = IPv4Address(address=resolved[0].split()[0])
    assert all(address not in network.router.network for network in networks), (
        "Artifact endpoint overlaps a guest subnet"
    )
    egress = EgressEndpoint(address=address, port=endpoint.port or (443 if endpoint.scheme == "https" else 80))
    LOGGER.info(f"VM {vm.name}: router checks passed; guest TCP endpoint={egress.address}:{egress.port}")
    return egress


def windows_network_setup_script(
    *, index: int, networks: tuple[GuestNetwork, GuestNetwork], macs: dict[str, str], egress: EgressEndpoint
) -> str:
    """Configure only MAC-selected guest NICs and prevent secondary/management DNS registration."""
    return render_powershell_script(
        name="configure_windows_network.ps1", index=index, networks=networks, macs=macs, egress=egress
    )


def windows_network_probe_script(
    *, index: int, networks: tuple[GuestNetwork, GuestNetwork], macs: dict[str, str], egress: EgressEndpoint
) -> str:
    """Check guest NICs and source-bound connectivity; return readiness and its failure reason."""
    return render_powershell_script(
        name="probe_windows_network.ps1",
        index=index,
        networks=networks,
        macs=macs,
        egress=egress,
        destinations={
            network.name: (
                network.router.ip,
                *(member.ip for member in network.members if member != network.members[index]),
            )
            for network in networks
        },
    )


def windows_network_readiness(
    *,
    vm: VirtualMachineForTests,
    index: int,
    networks: tuple[GuestNetwork, GuestNetwork],
    macs: dict[str, str],
    egress: EgressEndpoint,
) -> None:
    """Wait for guest readiness; retain the latest probe failure for timeout diagnostics."""
    LOGGER.info(
        f"VM {vm.name}: checking guest NICs, peer connectivity and TCP egress; "
        f"expected addresses={[str(network.members[index]) for network in networks]}, "
        f"MACs={macs}, gateway={networks[0].router.ip}, endpoint={egress.address}:{egress.port}"
    )
    script = windows_network_probe_script(index=index, networks=networks, macs=macs, egress=egress)
    last_failure = "No guest networking probe completed"
    try:
        for output in TimeoutSampler(
            wait_timeout=TIMEOUT_5MIN,
            sleep=5,
            func=run_powershell,
            ssh_exec=vm.ssh_exec,
            script=script,
            timeout=60,
            exceptions_dict={TimeoutError: []},
            print_func_args=False,
        ):
            result = loads(s=output)
            if result["Ready"]:
                LOGGER.info(f"VM {vm.name}: guest NIC, peer and TCP egress checks passed")
                return
            if result["Failure"] != last_failure:
                LOGGER.info(f"VM {vm.name}: guest network check pending: {result['Failure']}")
            last_failure = result["Failure"]
    except TimeoutExpiredError as error:
        if error.last_exp is not None:
            last_failure += f"; last probe exception: {type(error.last_exp).__name__}: {error.last_exp}"
        LOGGER.error(f"VM {vm.name}: guest networking timed out: {last_failure}")
        raise AssertionError(f"VM {vm.name}: guest networking timed out: {last_failure}") from error
