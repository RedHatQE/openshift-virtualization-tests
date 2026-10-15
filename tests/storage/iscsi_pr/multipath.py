"""Read-only correlation of iSCSI exports, host multipath maps and live VM disks."""

from __future__ import annotations

from dataclasses import dataclass
from json import loads
from logging import getLogger
from re import findall, fullmatch
from shlex import quote
from typing import TYPE_CHECKING
from uuid import UUID

from timeout_sampler import TimeoutExpiredError, TimeoutSampler

from utilities.constants.timeouts import TIMEOUT_5MIN
from utilities.infra import ExecCommandOnPod
from utilities.windows import run_powershell

if TYPE_CHECKING:
    from typing import Any

    from kubernetes.dynamic import DynamicClient

    from tests.storage.iscsi_pr.utils import IscsiTarget
    from utilities.virt import VirtualMachineForTests

LOGGER = getLogger(name=__name__)


@dataclass(frozen=True)
class LunMultipath:
    """One target LUN, identified by its observed WWID and kernel dm device."""

    lun: int
    wwid: str
    dm_device: str
    dev_t: str
    paths: tuple[str, str]


def target_path(*, executor: ExecCommandOnPod, target: IscsiTarget, portal: str, lun: int) -> dict[str, Any] | None:
    """Resolve a portal/LUN symlink and verify its kernel target/session identity.

    Returns:
        Path identity and capacity, or None while kubelet has not attached it.
        Command failures propagate; the caller must not treat them as readiness.
    """
    link = f"/dev/disk/by-path/ip-{portal}:3260-iscsi-{target.iqn}-lun-{lun}"
    output = executor.exec(
        command=f"""set -e
[ -e {quote(link)} ] || {{ echo pending; exit 0; }}
test -b {quote(link)}
device=$(readlink -e {quote(link)})
printf '%s\\n' "$device"
readlink -e "/sys/class/block/${{device##*/}}/device"
blockdev --getsize64 "$device"
cat "/sys/class/block/${{device##*/}}/dev"
"""
    )
    if output == "pending":
        return None
    device_path, sysfs_path, capacity, dev_t = output.splitlines()
    device = device_path.removeprefix("/dev/")
    assert fullmatch(r"sd[a-z]+", device), f"Unexpected iSCSI path device {device_path}"
    sessions = findall(r"/session([0-9]+)/", sysfs_path)
    assert len(sessions) == 1, f"Path {device} is not attached through one iSCSI session: {sysfs_path}"
    hctl = sysfs_path.rsplit("/", 1)[1]
    assert fullmatch(r"[0-9]+:[0-9]+:[0-9]+:[0-9]+", hctl) and int(hctl.rsplit(":", 1)[1]) == lun, (
        f"Path {device} has the wrong kernel LUN: {hctl}"
    )
    session_id = sessions[0]
    identity = executor.exec(
        command=f"""set -e
cat /sys/class/iscsi_session/session{session_id}/targetname
for connection in /sys/class/iscsi_connection/connection{session_id}:*; do
    test -d "$connection"
    cat "$connection/persistent_address"
    cat "$connection/persistent_port"
done
"""
    ).splitlines()
    assert identity == [target.iqn, portal, "3260"], f"Path {device} has unexpected target/portal identity: {identity}"
    return {"device": device, "portal": portal, "lun": lun, "size": int(capacity), "dev_t": dev_t}


def host_multipath_snapshot(*, executor: ExecCommandOnPod, wwids: set[str]) -> dict[str, Any]:
    """Read current daemon/kernel map state for the previously identified LUNs."""
    maps = loads(s=executor.exec(command="multipathd show maps json"))["maps"]
    details = {}
    for mapping in maps:
        if mapping["uuid"] not in wwids or mapping["sysfs"] == "undef":
            continue
        device = mapping["sysfs"]
        assert fullmatch(r"dm-[0-9]+", device), f"Unexpected multipath sysfs name: {device}"
        output = executor.exec(
            command=f"""set -e
cat /sys/class/block/{device}/dm/uuid
cat /sys/class/block/{device}/dev
blockdev --getsize64 /dev/{device}
ls /sys/class/block/{device}/slaves
"""
        ).splitlines()
        details[device] = {"uuid": output[0], "dev_t": output[1], "size": int(output[2]), "slaves": output[3:]}
    return {"maps": maps, "details": details}


def validate_lun_multipath(
    *, snapshot: dict[str, Any], paths: list[dict[str, Any]], lun: int, worker_name: str
) -> LunMultipath:
    """Require a writable map with both previously identified paths healthy.

    Returns:
        The kernel map identity used later to verify actual QEMU consumption.
    """
    context = f"Worker {worker_name}, LUN {lun}"
    devices = {path["device"] for path in paths}
    wwid, capacity = paths[0]["wwid"], paths[0]["size"]
    maps = [mapping for mapping in snapshot["maps"] if mapping["uuid"] == wwid]
    assert len(maps) == 1, f"{context}: expected exactly one multipath map for {wwid}"
    mapping = maps[0]
    assert mapping["dm_st"] == "active" and mapping["write_prot"] == "rw", f"{context}: dm map is not active/writable"
    daemon_paths = [path for group in mapping["path_groups"] for path in group["paths"]]
    assert len(daemon_paths) == 2 and {path["dev"] for path in daemon_paths} == devices, (
        f"{context}: map contains missing, extra or unrelated paths"
    )
    assert all(
        path["dm_st"] == "active" and path["dev_st"] == "running" and path["chk_st"] == "ready" for path in daemon_paths
    ), f"{context}: both multipath paths must be active/running/ready"
    for path in paths:
        daemon_path = next(item for item in daemon_paths if item["dev"] == path["device"])
        assert daemon_path["dev_t"] == path["dev_t"], f"{context}: daemon path device number differs from sysfs"
    device = mapping["sysfs"]
    assert device in snapshot["details"], f"{context}: dm map is not present in the kernel"
    detail = snapshot["details"][device]
    assert detail["uuid"] == f"mpath-{wwid}" and set(detail["slaves"]) == devices and detail["size"] == capacity, (
        f"{context}: kernel dm UUID, membership or capacity differs from the target"
    )
    return LunMultipath(lun=lun, wwid=wwid, dm_device=device, dev_t=detail["dev_t"], paths=tuple(sorted(devices)))


def qemu_block_devices(*, executor: ExecCommandOnPod, domain_uuid: str) -> set[str]:
    """Read matching QEMU block descriptors through the privileged worker executor.

    Returns:
        Decimal major:minor device numbers. No process arguments or unrelated
        file names are emitted; a missing/unreadable QEMU process is an error.
    """
    domain_uuid = str(UUID(domain_uuid))
    command = f"""set -e
found=0
for process in /proc/[0-9]*; do
    [ -r "$process/comm" ] || continue
    if ! IFS= read -r process_name < "$process/comm"; then
        [ ! -e "$process" ] && continue
        exit 1
    fi
    case "$process_name" in qemu-kvm|qemu-system-*) ;; *) continue ;; esac
    mapfile -d '' -t arguments < "$process/cmdline"
    matches=0
    for ((index=0; index+1<${{#arguments[@]}}; index++)); do
        if [ "${{arguments[index]}}" = -uuid ] && [ "${{arguments[index+1]}}" = {quote(domain_uuid)} ]; then
            matches=1
        fi
    done
    [ "$matches" -eq 1 ] || continue
    found=$((found+1))
    test -r "$process/fd"
    test -x "$process/fd"
    for descriptor in "$process"/fd/*; do
        [ -b "$descriptor" ] || continue
        stat -L -c '%t:%T' "$descriptor"
    done
done
test "$found" -eq 1
"""
    output = executor.exec(command=command)
    return {":".join(str(int(component, 16)) for component in row.split(":")) for row in output.splitlines()}


def validate_launcher_lun(
    *, disk: dict[str, Any], mapping: LunMultipath, source_dev_t: str, qemu_devices: set[str], vm_name: str
) -> None:
    """Require a reservation-enabled live SCSI LUN opened by QEMU on the dm map."""
    context = f"VM {vm_name}, LUN {mapping.lun}"
    assert disk["@type"] == "block" and disk["@device"] == "lun" and disk["target"]["@bus"] == "scsi", (
        f"{context}: live disk is not SCSI LUN passthrough"
    )
    assert disk["driver"]["@cache"] == "none", f"{context}: live LUN cache must be none"
    reservations = disk["source"]["reservations"]
    assert reservations["source"]["@type"] == "unix" and reservations["source"]["@path"], (
        f"{context}: live domain has no PR-helper socket"
    )
    assert source_dev_t == mapping.dev_t, (
        f"{context}: launcher source is {source_dev_t}, expected {mapping.dm_device}/{mapping.dev_t}"
    )
    assert mapping.dev_t in qemu_devices, (
        f"{context}: QEMU has no open descriptor for {mapping.dm_device}/{mapping.dev_t}; "
        f"observed block devices: {sorted(qemu_devices)}"
    )


def vm_multipath_readiness(
    *,
    vm: VirtualMachineForTests,
    client: DynamicClient,
    utility_pods: list,
    mappings_by_worker: dict[str, tuple[LunMultipath, LunMultipath]],
) -> None:
    """Check path health and actual QEMU consumption of the previously verified maps."""
    worker = vm.vmi.get_node(privileged_client=client)
    assert worker.name in mappings_by_worker, f"VM {vm.name} is placed on an unvalidated worker"
    mappings = mappings_by_worker[worker.name]
    executor = ExecCommandOnPod(utility_pods=utility_pods, node=worker)
    maps = loads(s=executor.exec(command="multipathd show maps json"))["maps"]
    xml = vm.vmi.get_xml_dict(privileged_client=client)["domain"]
    pod = vm.vmi.get_virt_launcher_pod(privileged_client=client)
    qemu_devices = qemu_block_devices(executor=executor, domain_uuid=xml["uuid"])
    disks = xml["devices"]["disk"]
    if isinstance(disks, dict):
        disks = [disks]
    for mapping in mappings:
        configured = [
            disk for disk in vm.vmi.instance.spec.domain.devices.disks if disk["name"] == f"shared-lun-{mapping.lun}"
        ]
        assert len(configured) == 1 and configured[0]["shareable"], (
            f"VM {vm.name}: VMI shared LUN {mapping.lun} must have shareable enabled"
        )
        current = [item for item in maps if item["uuid"] == mapping.wwid and item["sysfs"] == mapping.dm_device]
        assert len(current) == 1, f"VM {vm.name}: prepared map {mapping.wwid} is missing or changed"
        paths = [path for group in current[0]["path_groups"] for path in group["paths"]]
        assert current[0]["dm_st"] == "active" and current[0]["write_prot"] == "rw", (
            f"VM {vm.name}: prepared map {mapping.wwid} is not active/writable"
        )
        assert (
            len(paths) == 2
            and {path["dev"] for path in paths} == set(mapping.paths)
            and all(
                path["dm_st"] == "active" and path["dev_st"] == "running" and path["chk_st"] == "ready"
                for path in paths
            )
        ), f"VM {vm.name}: both prepared paths must remain healthy for {mapping.wwid}"
        selected = [disk for disk in disks if disk.get("alias", {}).get("@name") == f"ua-shared-lun-{mapping.lun}"]
        assert len(selected) == 1, f"VM {vm.name}: live shared LUN {mapping.lun} not found uniquely"
        disk = selected[0]
        source = disk["source"]["@dev"]
        output = pod.execute(command=["stat", "-L", "-c", "%t:%T", source], container="compute").strip()
        dev_t = ":".join(str(int(component, 16)) for component in output.split(":"))
        validate_launcher_lun(
            disk=disk,
            mapping=mapping,
            source_dev_t=dev_t,
            qemu_devices=qemu_devices,
            vm_name=vm.name,
        )
    LOGGER.info(f"VM {vm.name} on {worker.name} uses verified multipath LUNs: {mappings}")


def remaining_multipath_maps(*, executor: ExecCommandOnPod, observed: set[str]) -> list[str]:
    """Find kernel dm maps with recorded test WWIDs, including daemon-orphan maps."""
    output = executor.exec(
        command="""set -e
for device in /sys/class/block/dm-*; do
    [ -e "$device" ] || continue
    if ! IFS= read -r device_uuid < "$device/dm/uuid"; then
        [ ! -e "$device" ] && continue
        exit 1
    fi
    printf '%s|%s\\n' "${device##*/}" "$device_uuid"
done
"""
    )
    remaining = []
    for row in output.splitlines():
        device, device_uuid = row.split("|", 1)
        if device_uuid.removeprefix("mpath-") in observed and device_uuid.startswith("mpath-"):
            remaining.append(f"{device}:{device_uuid}")
    return remaining


def validate_windows_luns(*, disks: list[dict[str, Any]], lun_wwns: tuple[str, str], vm_name: str) -> tuple[str, str]:
    """Correlate guest disk serials/capacities without bringing disks online.

    Returns:
        Windows disk UniqueIds for the two shared LUNs, excluding the private root.
    """
    identities = []
    for lun, serial in enumerate(lun_wwns):
        matches = [
            disk for disk in disks if disk["SerialNumber"] is not None and disk["SerialNumber"].strip() == serial
        ]
        assert len(matches) == 1, f"VM {vm_name}: LUN {lun} serial is missing or duplicated in Windows"
        disk = matches[0]
        assert not disk["IsBoot"] and not disk["IsSystem"], f"VM {vm_name}: shared LUN {lun} resolves to a root disk"
        expected_size = (50, 70)[lun] * 1024**3
        assert disk["Size"] == expected_size, (
            f"VM {vm_name}: LUN {lun} guest capacity differs: "
            f"expected {expected_size} bytes, observed {disk['Size']} bytes"
        )
        # Windows vioscsi reports SAS (BusType 10) for the virtio-scsi controller.
        assert disk["BusType"] in {"SCSI", "SAS"}, (
            f"VM {vm_name}: LUN {lun} guest bus differs: expected SCSI/SAS, observed {disk['BusType']!r}"
        )
        assert disk["UniqueId"] is not None and disk["UniqueId"].strip(), (
            f"VM {vm_name}: LUN {lun} has no guest identity"
        )
        identities.append(disk["UniqueId"].strip())
    assert identities[0] != identities[1], f"VM {vm_name}: shared LUNs have identical Windows identities"
    return identities[0], identities[1]


def windows_shared_luns(*, vm: VirtualMachineForTests, lun_wwns: tuple[str, str]) -> tuple[str, str]:
    """Read Windows disk inventory and wait for the two exported LUNs to enumerate."""
    LOGGER.info(
        f"VM {vm.name}: checking shared guest LUNs; expected serials={lun_wwns}, capacities=50/70 GiB, bus=SCSI/SAS"
    )
    script = (
        "$ErrorActionPreference='Stop'; $disks=@(Get-Disk | Select-Object SerialNumber,UniqueId,Size,IsBoot,IsSystem,"
        "@{Name='BusType';Expression={$_.BusType.ToString()}}); ConvertTo-Json -InputObject $disks -Depth 3 -Compress"
    )
    last_failure = "No guest inventory collected"
    try:
        for output in TimeoutSampler(
            wait_timeout=TIMEOUT_5MIN,
            sleep=5,
            func=run_powershell,
            ssh_exec=vm.ssh_exec,
            script=script,
            exceptions_dict={},
            print_func_args=False,
        ):
            disks = loads(s=output)
            try:
                identities = validate_windows_luns(disks=disks, lun_wwns=lun_wwns, vm_name=vm.name)
            except AssertionError as error:
                if str(error) != last_failure:
                    LOGGER.info(f"VM {vm.name}: guest LUN check pending: {error}")
                last_failure = str(error)
            else:
                LOGGER.info(f"VM {vm.name}: shared guest LUN checks passed; identities={identities}")
                return identities
    except TimeoutExpiredError as error:
        if error.last_exp is not None:
            raise AssertionError(
                f"VM {vm.name}: guest LUN inventory probe failed: {type(error.last_exp).__name__}: {error.last_exp}"
            ) from error
        raise AssertionError(f"VM {vm.name}: guest LUN enumeration timed out: {last_failure}") from error
    raise AssertionError(f"VM {vm.name}: guest LUN enumeration ended without success: {last_failure}")


def retire_orphan_map(*, executor: ExecCommandOnPod, device: str, wwid: str) -> bool:
    """Flush one recorded, unused orphan map after all target sessions are gone.

    The caller must establish target ownership and completed consumer teardown.
    Recheck the kernel UUID and require no slaves, holders or open references.
    Never flush a reused device number or a map still used by another resource.

    Returns:
        True if the map disappeared or was flushed; False while it is in use.
    """
    assert fullmatch(r"dm-[0-9]+", device) and fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.:-]*", wwid), (
        "Invalid owned-map identity"
    )
    output = executor.exec(
        command=f"""set -euo pipefail
[ -e /sys/class/block/{device} ] || {{ echo removed; exit 0; }}
device_uuid=$(cat /sys/class/block/{device}/dm/uuid)
[ "$device_uuid" = {quote("mpath-" + wwid)} ] || {{ echo waiting; exit 0; }}
slaves=$(ls /sys/class/block/{device}/slaves)
[ -z "$slaves" ] || {{ echo waiting; exit 0; }}
holders=$(ls /sys/class/block/{device}/holders)
[ -z "$holders" ] || {{ echo waiting; exit 0; }}
open_count=$(dmsetup info -c --noheadings -o open /dev/{device} | tr -d ' ')
[ "$open_count" = 0 ] || {{ echo waiting; exit 0; }}
multipath -f {quote(wwid)}
echo removed
"""
    )
    assert output in ("removed", "waiting"), f"Unexpected orphan-map cleanup response for {device}: {output}"
    if output == "removed":
        LOGGER.info(f"Retired owned multipath map {device}/{wwid}")
    return output == "removed"
