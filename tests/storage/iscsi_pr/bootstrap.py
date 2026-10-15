"""Owned, reversible host preparation on the existing CI network underlay."""

from __future__ import annotations

from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from ipaddress import IPv4Address, IPv4Interface, IPv4Network, ip_address, ip_network
from json import loads
from logging import getLogger
from re import escape, fullmatch
from shlex import quote
from typing import TYPE_CHECKING
from uuid import uuid4

from ocp_resources.network_config_openshift_io import Network
from timeout_sampler import TimeoutSampler

from tests.storage.iscsi_pr.multipath import LunMultipath, host_multipath_snapshot, target_path, validate_lun_multipath
from tests.storage.iscsi_pr.utils import StorageNetwork, target_sessions
from utilities.constants.timeouts import TIMEOUT_2MIN, TIMEOUT_5MIN, TIMEOUT_30SEC
from utilities.infra import ExecCommandOnPod

if TYPE_CHECKING:
    from collections.abc import Iterator
    from typing import Any

    from kubernetes.dynamic import DynamicClient

    from tests.storage.iscsi_pr.utils import IscsiTarget

LOGGER = getLogger(name=__name__)
STATE_DIRECTORY = "/run/cnv-iscsi-pr"
HOST_FILES = ("/etc/multipath.conf", "/etc/multipath/wwids", "/etc/iscsi/initiatorname.iscsi")
HOST_UNITS = ("iscsid.socket", "iscsid.service", "multipathd.socket", "multipathd.service")


@dataclass(frozen=True)
class HostPlan:
    """Run-owned software paths and selected worker addresses; no physical isolation."""

    owner: str
    networks: tuple[StorageNetwork, StorageNetwork]
    addresses: tuple[str, ...]
    vxlan_names: tuple[str, str]
    vnis: tuple[int, int]


def storage_plan(*, owner: str, snapshots: list[dict[str, Any]], cluster_cidrs: list[str]) -> HostPlan:
    """Allocate two private overlay subnets after rejecting existing route/address overlaps.

    Returns:
        A plan for exactly three schedulable workers, with unique names and VNIs.
        Both VXLAN paths use the existing underlay and cannot qualify NIC failure.
    """
    assert fullmatch(r"[0-9a-f]{32}", owner), "Host owner must be a UUID hex string"
    assert len(snapshots) == 3, "WSFC preparation requires three schedulable workers"
    addresses = tuple(snapshot["address"] for snapshot in snapshots)
    assert len(set(addresses)) == 3, "Workers require distinct IPv4 InternalIP addresses"
    excluded = [ip_network(cidr) for cidr in cluster_cidrs]
    link_names = set()
    used_vnis = set()
    for snapshot in snapshots:
        for route in snapshot["routes"]:
            if route["dst"] != "default":
                excluded.append(ip_network(route["dst"], strict=False))
        for interface in snapshot["addresses"]:
            excluded.extend(
                IPv4Interface(f"{address['local']}/{address['prefixlen']}").network
                for address in interface["addr_info"]
                if address["family"] == "inet"
            )
        for link in snapshot["links"]:
            link_names.add(link["ifname"])
            info = link.get("linkinfo", {})
            if info.get("info_kind") == "vxlan":
                used_vnis.add(info["info_data"]["id"])
    available = [
        subnet
        for subnet in IPv4Network("198.18.0.0/15").subnets(new_prefix=24)
        if not any(subnet.overlaps(other) for other in excluded if other.version == 4)
    ]
    assert len(available) >= 2, "No two non-overlapping overlay storage subnets are available"
    start = int(owner[:8], 16) % len(available)
    subnets = (available[start], available[(start + 1) % len(available)])
    bridges = tuple(f"ip{owner[:6]}b{index}" for index in range(2))
    vxlan_names = tuple(f"ip{owner[:6]}v{index}" for index in range(2))
    assert not set(bridges + vxlan_names).intersection(link_names), "Owned link names already exist"
    first_vni = 1 + int(owner[8:14], 16) % (2**24 - 2)
    vnis = (first_vni, first_vni + 1)
    assert not set(vnis).intersection(used_vnis), "Owned VXLAN VNI already exists"
    mtu = min(snapshot["underlay_mtu"] for snapshot in snapshots) - 50
    assert mtu >= 1280, f"Underlay MTU is too small for storage VXLAN: {mtu + 50}"
    networks = tuple(
        StorageNetwork(bridge=bridge, target_address=IPv4Interface(f"{subnet[254]}/24"), mtu=mtu)
        for bridge, subnet in zip(bridges, subnets, strict=True)
    )
    return HostPlan(
        owner=owner,
        networks=(networks[0], networks[1]),
        addresses=addresses,
        vxlan_names=(vxlan_names[0], vxlan_names[1]),
        vnis=vnis,
    )


def idle_host_script() -> str:
    """Refuse changes while any existing iSCSI session or multipath map is present."""
    return """set -euo pipefail
for session in /sys/class/iscsi_session/session*; do
    [ ! -e "$session" ] || { echo 'Existing iSCSI sessions prevent host preparation/restore' >&2; exit 1; }
done
for device in /sys/class/block/dm-*; do
    [ -e "$device/dm/uuid" ] || continue
    case "$(cat "$device/dm/uuid")" in
        mpath-*) echo 'Existing multipath maps prevent host preparation/restore' >&2; exit 1;;
    esac
done
"""


def multipath_configuration(*, wwids: tuple[str, ...]) -> str:
    """Admit only observed test-owned WWIDs; never change another device's mapping."""
    assert all(fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.:-]*", wwid) for wwid in wwids), "Invalid observed WWID"
    exceptions = "\n".join(f'    wwid "^{escape(wwid)}$"' for wwid in wwids)
    return f"""defaults {{
    find_multipaths strict
    user_friendly_names no
    config_dir ""
    no_path_retry fail
}}
blacklist {{
    wwid ".*"
}}
blacklist_exceptions {{
{exceptions}
}}
"""


def prepare_host_script(*, plan: HostPlan, index: int) -> str:
    """Snapshot host files/service state before creating exclusively owned links."""
    script = idle_host_script()
    for file_index, path in enumerate(HOST_FILES):
        script += f"""if [ -e {path} ]; then
    test -f {path}; test ! -L {path}
    cp -a {path} {STATE_DIRECTORY}/file-{file_index}
    touch {STATE_DIRECTORY}/exists-{file_index}
fi
"""
    for unit in HOST_UNITS:
        script += f"if systemctl is-active --quiet {unit}; then touch {STATE_DIRECTORY}/{unit}; fi\n"
    script += f"""touch {STATE_DIRECTORY}/snapshot-complete
if ! grep -Eq '^InitiatorName=iqn\\.[a-zA-Z0-9.:_-]+$' /etc/iscsi/initiatorname.iscsi; then
    printf '%s\\n' 'InitiatorName=iqn.2026-10.com.redhat:cnv-{plan.owner}-{index}' > /etc/iscsi/initiatorname.iscsi
fi
cat > /etc/multipath.conf <<'CNV_MULTIPATH'
{multipath_configuration(wwids=())}CNV_MULTIPATH
restorecon /etc/multipath.conf /etc/iscsi/initiatorname.iscsi
modprobe vxlan
modprobe iscsi_tcp
modprobe dm_multipath
systemctl restart iscsid.service
systemctl start multipathd.service
multipathd reconfigure
"""
    for path_index, network in enumerate(plan.networks):
        vxlan = plan.vxlan_names[path_index]
        script += f"""ip link add {network.bridge} type bridge
ip link set dev {network.bridge} alias cnv-iscsi-pr:{plan.owner}
ip link set dev {network.bridge} mtu {network.mtu}
ip address add {network.target_address.network[index + 1]}/24 dev {network.bridge}
ip link set dev {network.bridge} up
ip link add {vxlan} type vxlan id {plan.vnis[path_index]} local {plan.addresses[index]} dstport 4789
ip link set dev {vxlan} alias cnv-iscsi-pr:{plan.owner}
ip link set dev {vxlan} mtu {network.mtu} master {network.bridge}
ip link set dev {vxlan} up
"""
        for peer in plan.addresses:
            if peer != plan.addresses[index]:
                script += f"bridge fdb append 00:00:00:00:00:00 dev {vxlan} dst {peer}\n"
    return script


def restore_host_script(*, plan: HostPlan) -> str:
    """Restore only a completed owned snapshot; leave evidence on unsafe detach."""
    script = f"""set -euo pipefail
test "$(cat {STATE_DIRECTORY}/owner)" = {plan.owner}
if [ -e {STATE_DIRECTORY}/snapshot-complete ]; then
{idle_host_script()}
"""
    for link in plan.vxlan_names + tuple(network.bridge for network in plan.networks):
        script += f"""if [ -e /sys/class/net/{link} ]; then
    test "$(cat /sys/class/net/{link}/ifalias)" = cnv-iscsi-pr:{plan.owner}
    ip link delete {link}
fi
"""
    for file_index, path in enumerate(HOST_FILES):
        script += f"""if [ -e {STATE_DIRECTORY}/exists-{file_index} ]; then
    cp -a {STATE_DIRECTORY}/file-{file_index} {path}
else
    rm -f {path}
fi
"""
    for unit in HOST_UNITS:
        script += f"""if [ ! -e {STATE_DIRECTORY}/{unit} ] && systemctl is-active --quiet {unit}; then
    systemctl stop {unit}
fi
"""
    script += "if systemctl is-active --quiet multipathd.service; then multipathd reconfigure; fi\n"
    script += f"fi\nrm -r {STATE_DIRECTORY}\n"
    return script


def restore_host(*, executor: ExecCommandOnPod, plan: HostPlan) -> None:
    """Attempt restoration; host command failures fail teardown and retain the journal."""
    LOGGER.info(f"Restoring worker {executor.pod.name} host state for {plan.owner}")
    executor.exec(command=restore_host_script(plan=plan))


@contextmanager
def prepared_hosts(*, client: DynamicClient, workers: list, utility_pods: list) -> Iterator[dict[str, Any]]:
    """Build two software paths and activate host tools with rollback on partial setup.

    Requires three reserved schedulable workers and installed host tools/kernel
    modules. No packages, persistent service enablement or worker reboot occurs.
    """
    assert len(workers) >= 3, "Reserve at least three schedulable workers for the Windows environment"
    selected = workers[:3]
    executors = {worker.name: ExecCommandOnPod(utility_pods=utility_pods, node=worker) for worker in selected}
    snapshots = []
    for worker in selected:
        executor = executors[worker.name]
        executor.exec(command=idle_host_script())
        executor.exec(
            command="set -e; for tool in ip bridge iscsiadm multipath multipathd dmsetup modprobe od udevadm restorecon; "
            'do command -v "$tool"; done; test -x /usr/lib/udev/scsi_id; '
            "test -d /etc/iscsi; test -d /etc/multipath; "
            'for module in vxlan iscsi_tcp dm_multipath; do modprobe -n "$module"; done; '
            "for unit in iscsid.service multipathd.service; do "
            'test "$(systemctl show -p LoadState --value "$unit")" = loaded; done'
        )
        node_addresses = [
            ip_address(item.address) for item in worker.instance.status.addresses if item.type == "InternalIP"
        ]
        address = next(item for item in node_addresses if isinstance(item, IPv4Address))
        links = loads(s=executor.exec(command="ip -j -d link show"))
        addresses = loads(s=executor.exec(command="ip -j -4 address show"))
        interface = next(
            item["ifname"]
            for item in addresses
            if any(item_address["local"] == str(address) for item_address in item["addr_info"])
        )
        snapshots.append({
            "address": str(address),
            "links": links,
            "addresses": addresses,
            "routes": loads(s=executor.exec(command="ip -j -4 route show table all")),
            "underlay_mtu": next(item["mtu"] for item in links if item["ifname"] == interface),
        })
    network = Network(name="cluster", client=client).instance.spec
    plan = storage_plan(
        owner=uuid4().hex,
        snapshots=snapshots,
        cluster_cidrs=[item.cidr for item in network.clusterNetwork] + list(network.serviceNetwork),
    )
    with ExitStack() as stack:
        for index, worker in enumerate(selected):
            executor = executors[worker.name]
            LOGGER.info(
                f"Preparing worker {worker.name}, owner {plan.owner}, software storage MTU {plan.networks[0].mtu}"
            )
            executor.exec(
                command=f"set -e; mkdir -m 700 {STATE_DIRECTORY}; printf '%s\\n' {plan.owner} > {STATE_DIRECTORY}/owner"
            )
            stack.push(exit=lambda *exception_info, executor=executor: restore_host(executor=executor, plan=plan))
            executor.exec(command=prepare_host_script(plan=plan, index=index))
        yield {"plan": plan, "workers": selected, "executors": executors}


def observed_lun_paths(
    *, executor: ExecCommandOnPod, target: IscsiTarget, lun_wwns: tuple[str, str]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]] | None:
    """Identify both paths of each LUN before configuring multipath.

    Returns:
        Verified path records grouped by LUN, or None while a path is missing.
        Retain these identities for map checks; serial/capacity failures propagate.
    """
    luns = []
    for lun, serial in enumerate(lun_wwns):
        paths = []
        for portal in target.portal_addresses:
            path = target_path(executor=executor, target=target, portal=portal, lun=lun)
            if path is None:
                return None
            assert path["size"] == (50, 70)[lun] * 1024**3, "Bootstrap LUN capacity differs from target"
            vpd = bytes.fromhex(
                executor.exec(command=f"od -An -v -tx1 /sys/class/block/{path['device']}/device/vpd_pg80")
            )
            assert vpd[1] == 0x80 and int.from_bytes(vpd[2:4]) == len(vpd) - 4, "Invalid VPD serial page"
            observed_serial = vpd[4:].removesuffix(b"\x00").decode().strip()
            assert observed_serial == serial, (
                f"Bootstrap VPD serial differs from owned LIO backstore: /dev/{path['device']}, "
                f"LUN {lun}, portal {portal}, expected {serial!r}, observed {observed_serial!r}"
            )
            path["wwid"] = executor.exec(command=f"/usr/lib/udev/scsi_id --whitelisted --device=/dev/{path['device']}")
            assert fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.:-]*", path["wwid"]), "Missing or invalid SCSI WWID"
            paths.append(path)
        assert paths[0]["device"] != paths[1]["device"] and paths[0]["wwid"] == paths[1]["wwid"], (
            "Storage portals require distinct paths with one WWID"
        )
        luns.append(paths)
    assert luns[0][0]["wwid"] != luns[1][0]["wwid"], "Shared LUNs require distinct SCSI WWIDs"
    return luns[0], luns[1]


def maps_unused(*, executors: dict[str, ExecCommandOnPod], wwids: set[str]) -> bool:
    """Check all owned map references in one scan per worker before logout."""
    if not wwids:
        return True
    owned = "|".join(quote(f"mpath-{wwid}") for wwid in sorted(wwids))
    for executor in executors.values():
        output = executor.exec(
            command=f"""set -e
for device in /sys/class/block/dm-*; do
    [ -e "$device" ] || continue
    if ! IFS= read -r device_uuid < "$device/dm/uuid"; then
        [ ! -e "$device" ] && continue
        exit 1
    fi
    case "$device_uuid" in
        {owned})
            dmsetup info -c --noheadings -o open "/dev/${{device##*/}}"
            if [ -n "$(ls "$device/holders")" ]; then echo 1; fi
            ;;
    esac
done
"""
        )
        if any(int(value) for value in output.split()):
            return False
    return True


def release_bootstrap_sessions(
    *, executors: dict[str, ExecCommandOnPod], target: IscsiTarget, observed: set[str]
) -> None:
    """Logout only the fresh target once owned maps have no consumer references.

    The enclosing claim fixture waits for full detach before releasing storage.
    """
    LOGGER.info(f"Releasing bootstrap sessions for {target.iqn}")
    for unused in TimeoutSampler(
        wait_timeout=TIMEOUT_5MIN, sleep=5, func=maps_unused, executors=executors, wwids=observed, exceptions_dict={}
    ):
        if unused:
            break
    sessions = target_sessions(executors=executors, target=target)
    for worker_name, executor in executors.items():
        for session in sessions.get(worker_name, []):
            assert fullmatch(r"session[0-9]+", session), f"Invalid owned session name: {session}"
            executor.exec(
                command=f"""set -e
session=/sys/class/iscsi_session/{session}
if [ -e "$session" ]; then
    test "$(cat "$session/targetname")" = {quote(target.iqn)}
    iscsiadm -m session -r {session.removeprefix("session")} --logout || test ! -e "$session"
fi
"""
            )
        executor.exec(
            command=f"set -e; if [ -d /var/lib/iscsi/nodes/{quote(target.iqn)} ]; then "
            f"iscsiadm -m node -T {quote(target.iqn)} --op delete; fi"
        )


def qualified_maps(
    *, executor: ExecCommandOnPod, luns: tuple[list[dict[str, Any]], list[dict[str, Any]]], worker_name: str
) -> tuple[LunMultipath, LunMultipath]:
    """Check current map state against the paths already verified during login."""
    snapshot = host_multipath_snapshot(executor=executor, wwids={paths[0]["wwid"] for paths in luns})
    mappings = tuple(
        validate_lun_multipath(snapshot=snapshot, paths=paths, lun=lun, worker_name=worker_name)
        for lun, paths in enumerate(luns)
    )
    return mappings[0], mappings[1]


def login_ready(*, executor: ExecCommandOnPod, node_command: str) -> bool:
    """Attempt a login to the owned node; retry only transport/timeouts or retry-again.

    Open-iSCSI codes 0/15 mean success/already logged in; 4/8/11/29 are retryable.
    Configuration/authentication failures and host execution errors propagate.
    """
    status = int(executor.exec(command=f"""{node_command} --login >&2; printf '%s\\n' "$?" """, timeout=TIMEOUT_30SEC))
    if status not in {0, 4, 8, 11, 15, 29}:
        raise RuntimeError(f"iSCSI login failed: {node_command}, exit code {status}")
    return status in {0, 15}


@contextmanager
def prepared_multipath(
    *, hosts: dict[str, Any], target: IscsiTarget, lun_wwns: tuple[str, str], observed: set[str]
) -> Iterator[dict[str, tuple[LunMultipath, LunMultipath]]]:
    """Login to the fresh target and create verified dm maps before starting Windows.

    Sessions and node records belong exclusively to this generated IQN. Consumer
    teardown precedes this context's logout; claims and target remain alive.
    The enclosing claim fixture owns the final detach wait.
    """
    executors = hosts["executors"]
    for executor in executors.values():
        executor.exec(command=f"test ! -e /var/lib/iscsi/nodes/{quote(target.iqn)}")
    with ExitStack() as stack:
        stack.push(
            exit=lambda *exception_info: release_bootstrap_sessions(
                executors=executors, target=target, observed=observed
            )
        )
        common_ids = None
        mappings = {}
        for worker_name, executor in executors.items():
            LOGGER.info(f"Connecting owned target {target.iqn} on worker {worker_name}")
            for portal in target.portal_addresses:
                node = f"iscsiadm -m node -T {quote(target.iqn)} -p {portal}:3260"
                executor.exec(command=f"{node} --op new")
                for name, value in (
                    ("node.session.timeo.replacement_timeout", 15),
                    ("node.conn[0].timeo.login_timeout", 10),
                    ("node.session.initial_login_retry_max", 1),
                ):
                    executor.exec(command=f"{node} --op update -n {quote(name)} -v {value}")
                for ready in TimeoutSampler(
                    wait_timeout=TIMEOUT_2MIN,
                    sleep=5,
                    func=login_ready,
                    executor=executor,
                    node_command=node,
                    exceptions_dict={},
                ):
                    if ready:
                        break
            for luns in TimeoutSampler(
                wait_timeout=TIMEOUT_5MIN,
                sleep=5,
                func=observed_lun_paths,
                executor=executor,
                target=target,
                lun_wwns=lun_wwns,
                exceptions_dict={},
            ):
                if luns:
                    break
            assert luns is not None, f"Owned LUN paths missing on {worker_name}"
            identities = tuple(paths[0]["wwid"] for paths in luns)
            observed.update(identities)
            if common_ids is None:
                common_ids = identities
            assert identities == common_ids, f"Workers disagree on owned LUN WWIDs: {worker_name}"
            command = (
                "set -e\ncat > /etc/multipath.conf <<'CNV_MULTIPATH'\n"
                f"{multipath_configuration(wwids=identities)}CNV_MULTIPATH\n"
                + "\n".join(f"multipath -a {quote(wwid)}" for wwid in identities)
                + "\nmultipathd reconfigure\nudevadm settle --timeout=30\n"
                + "\n".join(f"multipath /dev/{paths[0]['device']}" for paths in luns)
            )
            output = executor.exec(command=f"bash -c {quote(command)} 2>&1; printf '\n%s\n' \"$?\"")
            diagnostics, status = output.rsplit("\n", 1)
            assert status == "0", f"Multipath preparation failed on {worker_name}, exit code {status}:\n{diagnostics}"
            for ready in TimeoutSampler(
                wait_timeout=TIMEOUT_5MIN,
                sleep=5,
                func=qualified_maps,
                executor=executor,
                luns=luns,
                worker_name=worker_name,
                exceptions_dict={AssertionError: []},
            ):
                if ready:
                    mappings[worker_name] = ready
                    break
        assert common_ids is not None, "No workers prepared for multipath"
        yield mappings
