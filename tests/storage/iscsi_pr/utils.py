"""Static shared iSCSI resources for the CNV-70031 environment."""

from __future__ import annotations

from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from ipaddress import IPv4Address, IPv4Interface
from json import loads
from logging import getLogger
from re import findall, fullmatch
from shlex import join, quote
from typing import TYPE_CHECKING

from ocp_resources.persistent_volume import PersistentVolume
from ocp_resources.persistent_volume_claim import PersistentVolumeClaim
from pyhelper_utils.shell import run_ssh_commands
from timeout_sampler import TimeoutExpiredError, TimeoutSampler

from tests.storage.iscsi_pr.multipath import remaining_multipath_maps, retire_orphan_map
from utilities.constants.timeouts import TIMEOUT_5MIN
from utilities.constants.virt import DV_DISK
from utilities.infra import ExecCommandOnPod

if TYPE_CHECKING:
    from collections.abc import Generator
    from typing import Any

    from kubernetes.dynamic import DynamicClient

    from utilities.virt import VirtualMachineForTests


LOGGER = getLogger(name=__name__)


@dataclass(frozen=True)
class IscsiTarget:
    """One IQN exposed through two distinct IPv4 portal addresses.

    Distinct addresses are necessary but do not establish path independence;
    host readiness must also verify the actual sessions and multipath mapping.
    """

    iqn: str
    portal_addresses: tuple[str, str]

    def __post_init__(self) -> None:
        if not self.iqn.startswith("iqn.") or any(character.isspace() for character in self.iqn):
            raise ValueError("The iSCSI target requires an IQN without whitespace")
        if len(self.portal_addresses) != 2:
            raise ValueError("The iSCSI target requires exactly two portal addresses")
        addresses = tuple(IPv4Address(address=address) for address in self.portal_addresses)
        if addresses[0] == addresses[1]:
            raise ValueError("The iSCSI target requires two distinct portal addresses")


@contextmanager
def shared_iscsi_claims(
    *, client: DynamicClient, namespace: str, target: IscsiTarget
) -> Generator[tuple[PersistentVolumeClaim, PersistentVolumeClaim]]:
    """Create and bind the 50/70 GiB claims, unwinding partial setup on failure.

    The exported LUNs use RWX/Block for sharing across workers and an empty storage
    class for static binding. The target's backing StorageClass need not support RWX.
    The caller must keep the target alive throughout this context and nest all
    consumers inside it, so that they detach before claims and PVs are removed.
    PV names include the test-owned namespace to avoid cross-run collisions.
    This context owns Kubernetes objects only; target and host-session cleanup
    belong to their respective resource lifecycles.

    Yields:
        The bound claims for LUN 0 (50 GiB) and LUN 1 (70 GiB).
    """
    with ExitStack() as stack:
        claims = []
        for lun, size in enumerate(("50Gi", "70Gi")):
            claim_name = f"shared-lun-{lun}"
            volume = stack.enter_context(
                cm=PersistentVolume(
                    client=client,
                    kind_dict={
                        "apiVersion": "v1",
                        "kind": "PersistentVolume",
                        "metadata": {"name": f"{namespace}-{claim_name}"},
                        "spec": {
                            "capacity": {"storage": size},
                            "volumeMode": "Block",
                            "accessModes": ["ReadWriteMany"],
                            "persistentVolumeReclaimPolicy": "Retain",
                            "storageClassName": "",
                            "claimRef": {"namespace": namespace, "name": claim_name},
                            "iscsi": {
                                "targetPortal": f"{target.portal_addresses[0]}:3260",
                                "portals": [f"{target.portal_addresses[1]}:3260"],
                                "iqn": target.iqn,
                                "lun": lun,
                                "readOnly": False,
                            },
                        },
                    },
                )
            )
            claim = stack.enter_context(
                cm=PersistentVolumeClaim(
                    client=client,
                    namespace=namespace,
                    kind_dict={
                        "apiVersion": "v1",
                        "kind": "PersistentVolumeClaim",
                        "metadata": {"name": claim_name, "namespace": namespace},
                        "spec": {
                            "storageClassName": "",
                            "volumeName": volume.name,
                            "volumeMode": "Block",
                            "accessModes": ["ReadWriteMany"],
                            "resources": {"requests": {"storage": size}},
                        },
                    },
                )
            )
            claim.wait_for_status(status=PersistentVolumeClaim.Status.BOUND, timeout=TIMEOUT_5MIN)
            claims.append(claim)
        yield claims[0], claims[1]


@dataclass(frozen=True)
class StorageNetwork:
    """Owned host bridge, isolated target address and storage-interface MTU."""

    bridge: str
    target_address: IPv4Interface
    mtu: int = 1500


def validate_storage_route(
    *, network: StorageNetwork, links: list[dict], addresses: list[dict], routes: list[dict]
) -> None:
    """Reject bridges or host routes that cannot supply the selected storage path."""
    assert len(links) == 1 and links[0]["linkinfo"]["info_kind"] == "bridge", (
        f"{network.bridge} must be an existing Linux bridge"
    )
    host_addresses = [
        IPv4Interface(f"{address['local']}/{address['prefixlen']}")
        for link in addresses
        for address in link["addr_info"]
        if address["family"] == "inet"
    ]
    assert any(address.network == network.target_address.network for address in host_addresses), (
        f"Bridge {network.bridge} needs a host address in {network.target_address.network}"
    )
    assert all(address.ip != network.target_address.ip for address in host_addresses), (
        f"Target address {network.target_address.ip} is already assigned to a worker"
    )
    assert len(routes) == 1 and routes[0]["dev"] == network.bridge, (
        f"Route to {network.target_address.ip} must use {network.bridge}"
    )


def add_target_backing_disks(*, template_spec: dict[str, Any], volume_names: tuple[str, str]) -> None:
    """Attach dedicated virtio backing volumes with deterministic guest serials."""
    for lun, volume_name in enumerate(volume_names):
        name = f"backing-{lun}"
        template_spec["domain"]["devices"]["disks"].append({
            "name": name,
            "disk": {"bus": "virtio"},
            "serial": f"cnv-iscsi-{lun}",
            "cache": "none",
        })
        template_spec["volumes"].append({"name": name, "dataVolume": {"name": volume_name}})


def vm_body_with_root(*, name: str, data_volume_template: dict[str, Any]) -> dict[str, Any]:
    """Embed a private DataSource clone as the first boot disk, before adding LUNs.

    The VM owns the DataVolume template. Its OS preference supplies the root bus.

    Returns:
        A VM body with a private boot disk and namespace-local DataVolume template.
    """
    return {
        "spec": {
            "dataVolumeTemplates": [data_volume_template],
            "template": {
                "metadata": {"labels": {"kubevirt.io/vm": name, "kubevirt.io/domain": name}},
                "spec": {
                    "domain": {"devices": {"rng": {}, "disks": [{"name": DV_DISK, "disk": {}, "bootOrder": 1}]}},
                    "volumes": [{"name": DV_DISK, "dataVolume": {"name": data_volume_template["metadata"]["name"]}}],
                },
            },
        }
    }


def target_setup_script(*, target: IscsiTarget, initiators: tuple[str, ...]) -> str:
    """Build a first-boot LIO configuration for the dedicated, disposable target.

    The guest exports only the serial-addressed blank volumes and restricts
    access to the selected workers' initiator IQNs. No disk is formatted.
    """
    if not initiators or any(not fullmatch(r"iqn\.[a-zA-Z0-9.:_-]+", initiator) for initiator in initiators):
        raise ValueError("Each consumer worker must provide a valid iSCSI initiator IQN")
    commands = ["#!/bin/bash", "set -euo pipefail"]
    for lun, size in enumerate((50, 70)):
        device = f"/dev/disk/by-id/virtio-cnv-iscsi-{lun}"
        commands.extend([
            f"test -b {device}",
            f'test "$(blockdev --getsize64 {device})" -eq {size * 1024**3}',
        ])
    commands.append("targetcli set global auto_add_default_portal=false")
    commands.append("targetcli set global auto_add_mapped_luns=true")
    commands.append("targetcli set global auto_enable_tpgt=true")
    commands.append(join(["targetcli", "/iscsi", "create", target.iqn]))
    tpg = f"/iscsi/{target.iqn}/tpg1"
    commands.append(join(["targetcli", tpg, "set", "attribute", "authentication=0", "generate_node_acls=0"]))
    for lun in range(2):
        commands.extend([
            join([
                "targetcli",
                "/backstores/block",
                "create",
                f"name=lun{lun}",
                f"dev=/dev/disk/by-id/virtio-cnv-iscsi-{lun}",
            ]),
            join(["targetcli", f"{tpg}/luns", "create", f"/backstores/block/lun{lun}", f"lun={lun}"]),
        ])
    for address in target.portal_addresses:
        commands.append(join(["targetcli", f"{tpg}/portals", "create", address, "3260"]))
    for initiator in sorted(set(initiators)):
        commands.append(join(["targetcli", f"{tpg}/acls", "create", initiator]))
    commands.extend([
        "targetcli saveconfig",
        "systemctl enable target",
        "systemctl enable --now firewalld",
        "firewall-cmd --permanent --new-zone=iscsi-storage",
        "firewall-cmd --permanent --zone=iscsi-storage --add-port=3260/tcp",
        "firewall-cmd --permanent --zone=iscsi-storage --add-interface=storage0",
        "firewall-cmd --permanent --zone=iscsi-storage --add-interface=storage1",
        "firewall-cmd --reload",
    ])
    return "\n".join(commands) + "\n"


def target_cloud_init(
    *,
    target: IscsiTarget,
    networks: tuple[StorageNetwork, StorageNetwork],
    macs: dict[str, str],
    initiators: tuple[str, ...],
) -> dict[str, Any]:
    """Configure guest networking and LIO once, while retaining DHCP management."""
    ethernets = {"management": {"match": {"macaddress": macs["management"]}, "dhcp4": True}}
    for index, network in enumerate(networks):
        name = f"storage{index}"
        ethernets[name] = {
            "match": {"macaddress": macs[name]},
            "set-name": name,
            "dhcp4": False,
            "dhcp6": False,
            "addresses": [str(network.target_address)],
            "mtu": network.mtu,
        }
    return {
        "networkData": {"version": 2, "ethernets": ethernets},
        "userData": {
            "packages": ["targetcli", "firewalld"],
            "write_files": [
                {
                    "path": "/usr/local/sbin/configure-iscsi-target",
                    "permissions": "0700",
                    "content": target_setup_script(target=target, initiators=initiators),
                }
            ],
            "runcmd": [["/usr/local/sbin/configure-iscsi-target"]],
        },
    }


def validate_target_configuration(
    *, configuration: dict[str, Any], target: IscsiTarget, initiators: tuple[str, ...], devices: list[dict[str, Any]]
) -> tuple[str, str]:
    """Correlate live LIO exports with guest backing paths; return the LUN WWNs."""
    targets = configuration["targets"]
    assert len(targets) == 1 and targets[0]["wwn"] == target.iqn, "Unexpected LIO target identity or extra targets"
    assert len(targets[0]["tpgs"]) == 1, "Expected one target portal group"
    tpg = targets[0]["tpgs"][0]
    assert tpg["enable"], "LIO target portal group is disabled"
    assert {(portal["ip_address"], portal["port"]) for portal in tpg["portals"]} == {
        (address, 3260) for address in target.portal_addresses
    }, "LIO must listen on exactly the two storage addresses"
    assert tpg["attributes"]["generate_node_acls"] == 0, "LIO must restrict access to explicit worker ACLs"
    assert {acl["node_wwn"] for acl in tpg["node_acls"]} == set(initiators), "Unexpected LIO initiator ACLs"
    assert len(tpg["luns"]) == 2, "LIO must export exactly two LUNs"
    assert {lun["index"]: lun["storage_object"] for lun in tpg["luns"]} == {
        0: "/backstores/block/lun0",
        1: "/backstores/block/lun1",
    }, "LIO LUN numbers do not match their backings"
    stores = configuration["storage_objects"]
    assert len(stores) == 2 and {store["name"] for store in stores} == {"lun0", "lun1"}, "Unexpected LIO backstores"
    assert len(devices) == 2 and devices[0]["path"] != devices[1]["path"], "Backings must be distinct block devices"
    wwids = []
    for lun, size in enumerate((50, 70)):
        device = devices[lun]
        store = next(store for store in stores if store["name"] == f"lun{lun}")
        assert device["serial"] == f"cnv-iscsi-{lun}" and device["size"] == size * 1024**3, (
            f"Backing {lun} has the wrong serial or capacity"
        )
        assert store["plugin"] == "block" and store["dev"] in (
            device["path"],
            f"/dev/disk/by-id/virtio-{device['serial']}",
        ), f"LUN {lun} uses the wrong backing"
        assert store["wwn"], f"LUN {lun} has no persistent identity"
        wwids.append(store["wwn"])
    assert wwids[0] != wwids[1], "The two LUNs must have distinct persistent identities"
    return wwids[0], wwids[1]


def host_storage_preflight(
    *,
    executors: dict[str, ExecCommandOnPod],
    networks: tuple[StorageNetwork, StorageNetwork],
) -> tuple[str, ...]:
    """Verify host services and paths; return distinct initiator IQNs."""
    assert executors, "The iSCSI target requires consumer workers"
    initiators = []
    for worker_name, executor in executors.items():
        service = executor.exec(command="systemctl is-active iscsid.service iscsid.socket || true")
        assert "active" in service.splitlines(), (
            f"Worker {worker_name} requires an active iscsid service or socket; observed: {service}"
        )
        daemon = executor.exec(command="multipathd show daemon")
        assert fullmatch(r"pid [1-9][0-9]* (idle|running)", daemon), (
            f"Worker {worker_name} requires a ready multipathd daemon; observed: {daemon}"
        )
        ports_by_path = []
        for network in networks:
            LOGGER.info(f"Checking iSCSI path {worker_name}/{network.bridge} to {network.target_address.ip}")
            validate_storage_route(
                network=network,
                links=loads(s=executor.exec(command=f"ip -j -d link show dev {quote(network.bridge)}")),
                addresses=loads(s=executor.exec(command=f"ip -j address show dev {quote(network.bridge)}")),
                routes=loads(s=executor.exec(command=f"ip -j route get {network.target_address.ip}")),
            )
            ports = set(executor.exec(command=f"ls /sys/class/net/{quote(network.bridge)}/brif").split())
            assert ports, f"Storage bridge {worker_name}/{network.bridge} has no external ports"
            ports_by_path.append(ports)
        assert ports_by_path[0].isdisjoint(ports_by_path[1]), f"Storage bridges on {worker_name} share a port"
        initiator_file = executor.exec(command="cat /etc/iscsi/initiatorname.iscsi")
        matches = findall(r"(?m)^InitiatorName=(iqn\.[a-zA-Z0-9.:_-]+)\s*$", initiator_file)
        assert len(matches) == 1, f"Worker {worker_name} needs a configured iSCSI initiator IQN"
        initiators.append(matches[0])
    assert len(set(initiators)) == len(initiators), "Consumer workers must have distinct initiator IQNs"
    return tuple(initiators)


def target_readiness(
    *,
    vm: VirtualMachineForTests,
    target: IscsiTarget,
    initiators: tuple[str, ...],
) -> tuple[str, str]:
    """Verify live LIO exports/backings; bootstrap later verifies actual portal logins."""
    LOGGER.info(f"Checking exported LUNs on target {vm.name}")
    run_ssh_commands(host=vm.ssh_exec, commands=["sudo", "targetcli", "saveconfig"])
    configuration = loads(
        s=run_ssh_commands(host=vm.ssh_exec, commands=["sudo", "cat", "/etc/target/saveconfig.json"])[0]
    )
    devices = []
    for lun in range(2):
        serial = f"cnv-iscsi-{lun}"
        path = f"/dev/disk/by-id/virtio-{serial}"
        outputs = run_ssh_commands(
            host=vm.ssh_exec,
            commands=[
                ["readlink", "-f", path],
                ["sudo", "blockdev", "--getsize64", path],
            ],
        )
        devices.append({"serial": serial, "path": outputs[0].strip(), "size": int(outputs[1])})
    wwids = validate_target_configuration(
        configuration=configuration,
        target=target,
        initiators=initiators,
        devices=devices,
    )
    return wwids


def target_sessions(*, executors: dict[str, ExecCommandOnPod], target: IscsiTarget) -> dict[str, list[str]]:
    """Return remaining sysfs session names for this run's exact IQN, per worker.

    Read-only sysfs inspection also works when there are no sessions. A session
    disappearing during teardown is expected; other read failures remain errors.
    No session belonging to another target is returned or modified.
    """
    command = f"""set -e
for session in /sys/class/iscsi_session/session*; do
    [ -e "$session" ] || continue
    if ! IFS= read -r target_name < "$session/targetname"; then
        [ ! -e "$session" ] && continue
        exit 1
    fi
    if [ "$target_name" = {quote(target.iqn)} ]; then
        printf '%s\n' "${{session##*/}}"
    fi
done
"""
    remaining = {}
    for worker_name, executor in executors.items():
        sessions = executor.exec(command=command).splitlines()
        if sessions:
            remaining[worker_name] = sessions
    return remaining


def target_attachments(
    *, executors: dict[str, ExecCommandOnPod], target: IscsiTarget, observed_wwids: set[str], flush_orphan_maps: bool
) -> dict[str, list[str]]:
    """Inspect attachments and optionally retire unused owned maps after logout.

    Returns:
        Remaining sessions/maps per worker. Flushing is permitted only when all
        selected workers have released sessions for this IQN.
    """
    remaining = target_sessions(executors=executors, target=target)
    sessions_gone = not remaining
    for worker_name, executor in executors.items():
        maps = remaining_multipath_maps(executor=executor, observed=observed_wwids)
        if flush_orphan_maps and sessions_gone and maps:
            for mapping in maps:
                device, device_uuid = mapping.split(":", 1)
                retire_orphan_map(executor=executor, device=device, wwid=device_uuid.removeprefix("mpath-"))
            maps = remaining_multipath_maps(executor=executor, observed=observed_wwids)
        if maps:
            remaining.setdefault(worker_name, []).extend(maps)
    return remaining


def wait_for_target_detach(*, workers: list, utility_pods: list, target: IscsiTarget, observed_wwids: set[str]) -> None:
    """Wait for logout and retire unused owned maps before releasing target resources.

    Raises:
        AssertionError: Sessions or recorded WWID maps remain after the bounded wait.
        Command execution errors: A worker cannot be inspected. Never treat an
            unreachable worker as a successful detach.
    """
    executors = {worker.name: ExecCommandOnPod(utility_pods=utility_pods, node=worker) for worker in workers}
    remaining = {}
    LOGGER.info(f"Waiting for kubelet to detach iSCSI target {target.iqn}")
    try:
        for remaining in TimeoutSampler(
            wait_timeout=TIMEOUT_5MIN,
            sleep=5,
            func=target_attachments,
            observed_wwids=observed_wwids,
            flush_orphan_maps=True,
            executors=executors,
            target=target,
            exceptions_dict={},
        ):
            if not remaining:
                return
    except TimeoutExpiredError as error:
        if error.last_exp is not None:
            raise AssertionError(
                f"iSCSI target {target.iqn}: worker inspection failed: {type(error.last_exp).__name__}: {error.last_exp}"
            ) from error
        raise AssertionError(
            f"iSCSI target {target.iqn} still has worker sessions or multipath maps: {remaining}"
        ) from error
