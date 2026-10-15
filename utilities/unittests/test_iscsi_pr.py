"""Offline checks of the feature-local static iSCSI resource adapters."""

from copy import deepcopy
from ipaddress import IPv4Interface
from json import dumps
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from pyhelper_utils.shell import run_command
from pytest import mark, raises
from timeout_sampler import TimeoutExpiredError

from tests.storage.iscsi_pr.conftest import (
    iscsi_pr_hosts,
    iscsi_pr_shared_claims,
    iscsi_pr_target,
)
from tests.storage.iscsi_pr.utils import (
    IscsiPersistentVolume,
    IscsiPersistentVolumeClaim,
    IscsiTarget,
    StorageNetwork,
    add_shared_lun_disks,
    add_target_backing_disks,
    configured_linux_vm,
    host_storage_preflight,
    image_volume,
    shared_iscsi_claims,
    target_cloud_init,
    target_sessions,
    validate_storage_route,
    validate_target_configuration,
    wait_for_target_detach,
)

pytestmark = mark.unit


class TestStaticIscsiResources:
    def test_volume_and_claim_have_explicit_static_binding(self) -> None:
        client = MagicMock()
        target = IscsiTarget(iqn="iqn.2026-10.test:owned", portal_addresses=("192.0.2.10", "198.51.100.10"))
        volume = IscsiPersistentVolume(
            name="owned-lun-0",
            namespace="owned",
            claim_name="shared-lun-0",
            client=client,
            target=target,
            lun=0,
            size="50Gi",
        )
        claim = IscsiPersistentVolumeClaim(
            name="shared-lun-0", namespace="owned", client=client, volume_name=volume.name, size="50Gi"
        )
        volume.to_dict()
        claim.to_dict()
        assert volume.res["kind"] == "PersistentVolume", "Subclass must retain the Kubernetes resource kind"
        assert claim.res["kind"] == "PersistentVolumeClaim", "Subclass must retain the Kubernetes resource kind"
        assert volume.res["spec"]["claimRef"] == {"namespace": "owned", "name": claim.name}, "PV is not reserved"
        assert claim.res["spec"]["volumeName"] == volume.name, "Claim must select its owned PV"
        for resource in (volume, claim):
            assert resource.res["spec"]["storageClassName"] == "", "Default provisioning must be disabled"
            assert resource.res["spec"]["volumeMode"] == "Block", "Shared LUNs must not be filesystem volumes"
            assert resource.res["spec"]["accessModes"] == ["ReadWriteMany"], "All consumers need shared access"
        assert volume.res["spec"]["persistentVolumeReclaimPolicy"] == "Retain", "Backing must remain target-owned"
        assert volume.res["spec"]["iscsi"] == {
            "targetPortal": "192.0.2.10:3260",
            "portals": ["198.51.100.10:3260"],
            "iqn": target.iqn,
            "lun": 0,
            "readOnly": False,
        }, "Both portals must address the same target and LUN"

    def test_duplicate_portals_are_rejected(self) -> None:
        with raises(ValueError, match="distinct"):
            IscsiTarget(iqn="iqn.2026-10.test:owned", portal_addresses=("192.0.2.10", "192.0.2.10"))

    @mark.parametrize("failure_stage", [None, "claim_create", "claim_bind", "consumer"])
    def test_claim_lifecycle_unwinds_created_resources(self, failure_stage: str | None) -> None:
        target = IscsiTarget(iqn="iqn.2026-10.test:owned", portal_addresses=("192.0.2.10", "198.51.100.10"))
        volume_first, volume_second = MagicMock(name="pv0"), MagicMock(name="pv1")
        claim_first, claim_second = MagicMock(name="pvc0"), MagicMock(name="pvc1")
        resources = (volume_first, claim_first, volume_second, claim_second)
        events = MagicMock()
        for index, resource in enumerate(resources):
            resource.__enter__.return_value = resource
            resource.__exit__.return_value = False
            events.attach_mock(resource.__exit__, f"exit_{index}")
        if failure_stage == "claim_create":
            claim_second.__enter__.side_effect = RuntimeError("claim_create")
        elif failure_stage == "claim_bind":
            claim_second.wait_for_status.side_effect = RuntimeError("claim_bind")
        with (
            patch(
                "tests.storage.iscsi_pr.utils.IscsiPersistentVolume", side_effect=[volume_first, volume_second]
            ) as pv,
            patch(
                "tests.storage.iscsi_pr.utils.IscsiPersistentVolumeClaim", side_effect=[claim_first, claim_second]
            ) as pvc,
        ):
            if failure_stage:
                with raises(RuntimeError, match=failure_stage):
                    with shared_iscsi_claims(client=MagicMock(), namespace="owned", target=target):
                        if failure_stage == "consumer":
                            raise RuntimeError("consumer")
            else:
                with shared_iscsi_claims(client=MagicMock(), namespace="owned", target=target) as claims:
                    assert claims == (claim_first, claim_second), "Both bound claims must be supplied to consumers"
                    assert not events.mock_calls, "Claims must remain alive while consumers use them"
        expected_exits = (
            ["exit_2", "exit_1", "exit_0"]
            if failure_stage == "claim_create"
            else ["exit_3", "exit_2", "exit_1", "exit_0"]
        )
        assert [event[0] for event in events.mock_calls] == expected_exits, "Cleanup must unwind in reverse order"
        assert [call.kwargs["size"] for call in pv.call_args_list] == ["50Gi", "70Gi"], "Incorrect LUN capacities"
        assert [call.kwargs["lun"] for call in pv.call_args_list] == [0, 1], "Incorrect target LUN numbers"
        assert [call.kwargs["name"] for call in pv.call_args_list] == ["owned-shared-lun-0", "owned-shared-lun-1"], (
            "Cluster-scoped PV names must include the owned namespace"
        )
        assert [call.kwargs["volume_name"] for call in pvc.call_args_list] == [volume_first.name, volume_second.name], (
            "Each claim must select its own PV"
        )


class TestSharedLunDevices:
    def test_shared_luns_preserve_private_root(self) -> None:
        spec = {
            "domain": {"devices": {"disks": [{"name": "root", "disk": {"bus": "sata"}, "bootOrder": 1}]}},
            "volumes": [{"name": "root", "dataVolume": {"name": "private-root"}}],
        }
        original = deepcopy(spec)
        add_shared_lun_disks(template_spec=spec, claim_names=("shared-lun-0", "shared-lun-1"))
        assert spec["volumes"][0] == original["volumes"][0], "Root volume must stay private and unchanged"
        disks = spec["domain"]["devices"]["disks"]
        assert disks[0] == original["domain"]["devices"]["disks"][0], "Root disk and boot order must be preserved"
        assert [disk["lun"] for disk in disks[1:]] == [
            {"bus": "scsi", "reservation": True},
            {"bus": "scsi", "reservation": True},
        ], "Each shared disk must use reservation-enabled SCSI LUN passthrough"
        assert all(disk["shareable"] for disk in disks[1:]), "Both LUNs must permit shared access"
        assert all(disk["cache"] == "none" for disk in disks[1:]), "Shared LUNs must bypass the host page cache"
        snapshot = deepcopy(spec)
        with raises(ValueError, match="already contains"):
            add_shared_lun_disks(template_spec=spec, claim_names=("shared-lun-0", "shared-lun-1"))
        assert spec == snapshot, "Reject repeated attachment before changing the VM"

    def test_duplicate_claims_do_not_modify_vm(self) -> None:
        spec = {"domain": {"devices": {"disks": []}}, "volumes": []}
        original = deepcopy(spec)
        with raises(ValueError, match="distinct"):
            add_shared_lun_disks(template_spec=spec, claim_names=("same", "same"))
        assert spec == original, "Invalid shared storage must not partially modify the VM"


class TestTargetPreparation:
    @mark.parametrize("route_device", ["br-storage0", "br-ex"])
    def test_management_route_is_not_accepted_as_storage(self, route_device: str) -> None:
        network = StorageNetwork(bridge="br-storage0", target_address=IPv4Interface("192.0.2.10/24"))
        args = {
            "network": network,
            "links": [{"linkinfo": {"info_kind": "bridge"}}],
            "addresses": [{"addr_info": [{"family": "inet", "local": "192.0.2.1", "prefixlen": 24}]}],
            "routes": [{"dev": route_device}],
        }
        if route_device == "br-ex":
            with raises(AssertionError, match="must use br-storage0"):
                validate_storage_route(**args)
        else:
            validate_storage_route(**args)

    def test_bootstrap_uses_serials_and_preserves_management(self, tmp_path) -> None:
        networks = (
            StorageNetwork(bridge="br-storage0", target_address=IPv4Interface("192.0.2.10/24")),
            StorageNetwork(bridge="br-storage1", target_address=IPv4Interface("198.51.100.10/24")),
        )
        target = IscsiTarget(iqn="iqn.2026-10.test:owned", portal_addresses=("192.0.2.10", "198.51.100.10"))
        data = target_cloud_init(
            target=target,
            networks=networks,
            initiators=("iqn.2026-10.test:worker",),
            macs={"management": "02:00:00:00:00:01", "storage0": "02:00:00:00:00:02", "storage1": "02:00:00:00:00:03"},
        )
        script = data["userData"]["write_files"][0]["content"]
        script_path = tmp_path / "target.sh"
        script_path.write_text(script)
        assert run_command(command=["bash", "-n", str(script_path)])[0], "Guest bootstrap must be valid bash"
        spec = {
            "domain": {"devices": {"disks": [{"name": "root", "disk": {"bus": "virtio"}}]}},
            "volumes": [{"name": "root", "dataVolume": {"name": "root-dv"}}],
        }
        add_target_backing_disks(template_spec=spec, volume_names=("blank50", "blank70"))
        disks = spec["domain"]["devices"]["disks"]
        for disk in disks[1:]:
            assert f"/dev/disk/by-id/virtio-{disk['serial']}" in script, "Bootstrap must match VM disk serials"
        assert spec["volumes"][0]["dataVolume"]["name"] == "root-dv", "Backing injection must preserve the root"
        assert "auto_add_default_portal=false" in script, "Do not expose a wildcard portal"
        assert "generate_node_acls=0" in script, "Do not grant access to arbitrary initiators"
        assert "mkfs" not in script and "reboot" not in script, "Preparation must not format disks or add a reboot"
        ethernets = data["networkData"]["ethernets"]
        assert ethernets["management"]["dhcp4"], "Management must retain DHCP"
        assert ethernets["storage1"]["addresses"] == ["198.51.100.10/24"], "Wrong secondary storage address"
        assert not ethernets["storage0"]["dhcp4"], "Storage must not acquire a competing default route"

    @mark.parametrize(
        "fault",
        [None, "serial_alias", "swapped_backing", "size", "portal", "acl", "duplicate_wwn", "extra_lun"],
    )
    def test_export_readiness_rejects_inconsistent_lio_state(self, fault: str | None) -> None:
        target = IscsiTarget(iqn="iqn.2026-10.test:owned", portal_addresses=("192.0.2.10", "198.51.100.10"))
        configuration = {
            "targets": [
                {
                    "wwn": target.iqn,
                    "tpgs": [
                        {
                            "enable": True,
                            "attributes": {"generate_node_acls": 0},
                            "portals": [{"ip_address": address, "port": 3260} for address in target.portal_addresses],
                            "luns": [
                                {"index": lun, "storage_object": f"/backstores/block/lun{lun}"} for lun in range(2)
                            ],
                            "node_acls": [
                                {
                                    "node_wwn": "iqn.2026-10.test:worker",
                                    "mapped_luns": [
                                        {"index": lun, "tpg_lun": lun, "write_protect": False} for lun in range(2)
                                    ],
                                }
                            ],
                        }
                    ],
                }
            ],
            "storage_objects": [
                {"name": "lun0", "plugin": "block", "dev": "/dev/vdc", "wwn": "first-wwn"},
                {"name": "lun1", "plugin": "block", "dev": "/dev/vdb", "wwn": "second-wwn"},
            ],
        }
        devices = [
            {"serial": "cnv-iscsi-0", "path": "/dev/vdc", "size": 50 * 1024**3},
            {"serial": "cnv-iscsi-1", "path": "/dev/vdb", "size": 70 * 1024**3},
        ]
        tpg = configuration["targets"][0]["tpgs"][0]
        if fault == "serial_alias":
            configuration["storage_objects"][0]["dev"] = "/dev/disk/by-id/virtio-cnv-iscsi-0"
        elif fault == "swapped_backing":
            configuration["storage_objects"][0]["dev"] = "/dev/vdb"
        elif fault == "size":
            devices[0]["size"] = 70 * 1024**3
        elif fault == "portal":
            tpg["portals"][0]["ip_address"] = "0.0.0.0"
        elif fault == "acl":
            tpg["node_acls"] = []
        elif fault == "duplicate_wwn":
            configuration["storage_objects"][1]["wwn"] = "first-wwn"
        elif fault == "extra_lun":
            tpg["luns"].append({"index": 2, "storage_object": "/backstores/block/unexpected"})
        args = {
            "configuration": configuration,
            "target": target,
            "initiators": ("iqn.2026-10.test:worker",),
            "devices": devices,
        }
        if fault not in (None, "serial_alias"):
            with raises(AssertionError):
                validate_target_configuration(**args)
        else:
            assert validate_target_configuration(**args) == ("first-wwn", "second-wwn"), (
                "Disk enumeration order must not determine the exported LUN identity"
            )

    @mark.parametrize("failure", [None, "backing", "readiness"])
    def test_target_owns_resources_and_unwinds_partial_setup(self, failure: str | None) -> None:
        networks = (
            StorageNetwork(bridge="br-storage0", target_address=IPv4Interface("192.0.2.10/24")),
            StorageNetwork(bridge="br-storage1", target_address=IPv4Interface("198.51.100.10/24")),
        )
        root, first, second, linux = (MagicMock() for _ in range(4))
        for context in (root, first, second, linux):
            context.__enter__.return_value = context
            context.__exit__.return_value = False
        if failure == "backing":
            second.__enter__.side_effect = RuntimeError("backing failed")
        events = MagicMock()
        events.attach_mock(linux.__exit__, "delete_vm")
        events.attach_mock(first.__exit__, "delete_backing")
        events.attach_mock(root.__exit__, "delete_root")
        with (
            patch("tests.storage.iscsi_pr.conftest.network_nad"),
            patch("tests.storage.iscsi_pr.conftest.image_volume", return_value=root),
            patch("tests.storage.iscsi_pr.conftest.create_dv", side_effect=[first, second]) as create,
            patch("tests.storage.iscsi_pr.conftest.IscsiTargetVirtualMachine"),
            patch("tests.storage.iscsi_pr.conftest.configured_linux_vm", return_value=linux),
            patch("tests.storage.iscsi_pr.conftest.target_cloud_init"),
            patch(
                "tests.storage.iscsi_pr.conftest.target_readiness",
                side_effect=RuntimeError("readiness failed") if failure == "readiness" else None,
                return_value=("serial0", "serial1"),
            ),
            patch.dict(
                "tests.storage.iscsi_pr.conftest.py_config",
                {
                    "latest_fedora_os_dict": {},
                    "default_storage_class": "ci-sc",
                    "default_access_mode": "ReadWriteOnce",
                },
            ),
        ):
            prepared = iscsi_pr_target.__wrapped__(
                admin_client=MagicMock(),
                namespace=MagicMock(),
                iscsi_pr_hosts={
                    "workers": [MagicMock()],
                    "initiators": ("iqn.2026-10.test:worker",),
                    "plan": MagicMock(networks=networks),
                },
                artifactory_secret_scope_module=MagicMock(),
                artifactory_config_map_scope_module=MagicMock(),
            )
            if failure:
                with raises(RuntimeError, match=failure):
                    next(prepared)
            else:
                result = next(prepared)
                assert result["lun_wwns"] == ("serial0", "serial1")
                assert result["target"].portal_addresses == ("192.0.2.10", "198.51.100.10")
                with raises(StopIteration):
                    next(prepared)
            assert [call.kwargs["size"] for call in create.call_args_list] == ["50Gi", "70Gi"]
            assert all(not call.kwargs["consume_wffc"] for call in create.call_args_list)
        first.__exit__.assert_called_once()
        root.__exit__.assert_called_once()
        names = [call[0] for call in events.mock_calls]
        assert names[-2:] == ["delete_backing", "delete_root"]
        if failure != "backing":
            assert names[0] == "delete_vm"

    @mark.parametrize("failure", [None, "boot", "cloud_init"])
    def test_linux_vm_is_deleted_before_cloud_init_secret(self, failure: str | None) -> None:
        vm, secret = MagicMock(), MagicMock()
        vm.__exit__.return_value = secret.__exit__.return_value = False
        secret.__enter__.return_value = secret
        events = MagicMock()
        events.attach_mock(vm.__exit__, "vm")
        events.attach_mock(secret.__exit__, "secret")
        with (
            patch("tests.storage.iscsi_pr.utils.Secret", return_value=secret),
            patch("tests.storage.iscsi_pr.utils.cloud_init_secret_data", return_value={}),
            patch(
                "tests.storage.iscsi_pr.utils.running_vm",
                side_effect=RuntimeError("boot") if failure == "boot" else None,
            ),
            patch(
                "tests.storage.iscsi_pr.utils.wait_for_cloud_init_complete",
                side_effect=RuntimeError("cloud_init") if failure == "cloud_init" else None,
            ),
        ):
            if failure:
                with raises(RuntimeError, match=failure), configured_linux_vm(vm=vm):
                    raise AssertionError("A failed VM must not be yielded")
            else:
                with configured_linux_vm(vm=vm) as result:
                    assert result is vm
        assert [call[0] for call in events.mock_calls] == ["vm", "secret"]

    def test_image_import_waits_for_pvc_without_consuming_wffc(self) -> None:
        with (
            patch("tests.storage.iscsi_pr.utils.create_dv") as create,
            patch("tests.storage.iscsi_pr.utils.get_test_artifact_server_url", return_value="https://artifact.test"),
            patch.dict(
                "tests.storage.iscsi_pr.utils.py_config",
                {
                    "default_storage_class": "ci-sc",
                    "default_access_mode": "ReadWriteOnce",
                    "default_volume_mode": "Block",
                },
            ),
        ):
            with image_volume(
                client=MagicMock(),
                namespace="owned",
                name="root",
                image={"image_path": "/image.qcow2", "dv_size": "60Gi"},
                secret=MagicMock(),
                certificate=MagicMock(),
            ) as root:
                root.pvc.wait.assert_called_once()
                assert not create.call_args.kwargs["consume_wffc"]
                assert create.call_args.kwargs["url"] == "https://artifact.test/image.qcow2"
            create.return_value.__exit__.assert_called_once()


class TestHostStoragePreparation:
    @mark.parametrize("failure_stage", [None, "services", "routes", "fedora.qcow2", "win2025.qcow2", "win2019.qcow2"])
    def test_hosts_fixture_verifies_before_yield_and_restores_on_failure(self, failure_stage: str | None) -> None:
        workers = [MagicMock(), MagicMock(), MagicMock()]
        for index, worker in enumerate(workers):
            worker.name = f"worker-{index}"
        master = MagicMock()
        master.name = "master-0"
        hosts = {"workers": workers, "plan": MagicMock(), "executors": {}}
        image_paths = ["fedora.qcow2", "win2025.qcow2", "win2019.qcow2"]
        image_failure = failure_stage in image_paths
        initiators = ("iqn.2026-10.test:worker-0", "iqn.2026-10.test:worker-1", "iqn.2026-10.test:worker-2")
        with (
            patch("tests.storage.iscsi_pr.conftest.prepared_hosts") as bootstrap,
            patch(
                "tests.storage.iscsi_pr.conftest.get_test_artifact_server_url", return_value="https://artifact.test/"
            ),
            patch(
                "tests.storage.iscsi_pr.conftest.get_windows_os_dict",
                side_effect=[{"image_path": path} for path in image_paths[1:]],
            ),
            patch(
                "tests.storage.iscsi_pr.conftest.validate_file_exists_in_url",
                side_effect=[RuntimeError(path) if failure_stage == path else True for path in image_paths],
            ) as validate_image,
            patch(
                "tests.storage.iscsi_pr.conftest.host_storage_preflight",
                side_effect=RuntimeError(failure_stage) if failure_stage else None,
                return_value=initiators,
            ) as preflight,
            patch.dict(
                "tests.storage.iscsi_pr.conftest.py_config",
                {
                    "default_storage_class": "ci-sc",
                    "default_access_mode": "ReadWriteOnce",
                    "latest_fedora_os_dict": {"image_path": image_paths[0]},
                },
            ),
        ):
            context = bootstrap.return_value
            context.__enter__.return_value = hosts
            context.__exit__.return_value = False
            client = MagicMock()
            prepared = iscsi_pr_hosts.__wrapped__(
                admin_client=client,
                schedulable_nodes=[master, *workers],
                workers=workers,
                workers_utility_pods=[],
            )
            if failure_stage:
                with raises(RuntimeError, match=failure_stage):
                    next(prepared)
                if image_failure:
                    bootstrap.assert_not_called()
                    preflight.assert_not_called()
                    assert [call.kwargs["url"] for call in validate_image.call_args_list] == [
                        f"https://artifact.test/{path}" for path in image_paths[: image_paths.index(failure_stage) + 1]
                    ]
                    return
                assert context.__exit__.call_args.args[0] is RuntimeError
            else:
                result = next(prepared)
                assert result is hosts
                assert result["initiators"] == initiators
                context.__exit__.assert_not_called()
                with raises(StopIteration):
                    next(prepared)
            preflight.assert_called_once_with(
                client=client,
                executors=hosts["executors"],
                networks=hosts["plan"].networks,
                storage_class="ci-sc",
                access_mode="ReadWriteOnce",
            )
            assert [call.kwargs["url"] for call in validate_image.call_args_list] == [
                f"https://artifact.test/{path}" for path in image_paths
            ]
            bootstrap.assert_called_once_with(client=client, workers=workers, utility_pods=[])
            context.__exit__.assert_called_once()

    @mark.parametrize(
        "state",
        [
            "service",
            "socket",
            "inactive",
            "daemon_down",
            "unsupported_storage",
            "invalid_iqn",
            "duplicate_iqn",
            "shared_ports",
        ],
    )
    def test_host_preflight_reuses_executors_and_verifies_storage_services_paths_and_iqns(self, state: str) -> None:
        networks = tuple(
            StorageNetwork(bridge=f"br-storage{index}", target_address=IPv4Interface(f"198.18.{index}.254/24"))
            for index in range(2)
        )
        executors = {"worker-a": MagicMock(), "worker-b": MagicMock()}
        for index, executor in enumerate(executors.values()):
            outputs = ["active\ninactive" if state == "service" else "inactive\nactive", "pid 123 idle"]
            if state == "inactive":
                outputs[0] = "inactive\ninactive"
            elif state == "daemon_down":
                outputs[1] = "error receiving packet"
            for network_index, network in enumerate(networks):
                outputs.extend([
                    dumps([{"linkinfo": {"info_kind": "bridge"}}]),
                    dumps([
                        {
                            "addr_info": [
                                {
                                    "family": "inet",
                                    "local": str(network.target_address.network[index + 1]),
                                    "prefixlen": 24,
                                }
                            ]
                        }
                    ]),
                    dumps([{"dev": network.bridge}]),
                    f"vx{0 if state == 'shared_ports' else network_index}",
                ])
            outputs.append(
                "invalid IQN"
                if state == "invalid_iqn"
                else f"InitiatorName=iqn.2026-10.test:worker-{0 if state == 'duplicate_iqn' else index}"
            )
            executor.exec.side_effect = outputs
        with patch("tests.storage.iscsi_pr.utils.StorageProfile") as profile:
            profile.return_value.instance.status.claimPropertySets = (
                []
                if state == "unsupported_storage"
                else [SimpleNamespace(volumeMode="Block", accessModes=["ReadWriteOnce"])]
            )
            arguments = {
                "client": MagicMock(),
                "executors": executors,
                "networks": networks,
                "storage_class": "ci-sc",
                "access_mode": "ReadWriteOnce",
            }
            if state in {"service", "socket"}:
                assert host_storage_preflight(**arguments) == ("iqn.2026-10.test:worker-0", "iqn.2026-10.test:worker-1")
            else:
                with raises(AssertionError):
                    host_storage_preflight(**arguments)
        commands = [call.kwargs["command"] for executor in executors.values() for call in executor.exec.call_args_list]
        assert all("start " not in command and "--login" not in command for command in commands), (
            "Preflight must leave host services and sessions unchanged"
        )

    @mark.parametrize("state", ["empty", "owned_and_foreign", "foreign", "unreadable"])
    def test_session_scan_matches_exact_iqn(self, tmp_path: Path, state: str) -> None:
        target = IscsiTarget(iqn="iqn.2026-10.test:owned", portal_addresses=("192.0.2.10", "198.51.100.10"))
        executor = MagicMock()
        executor.exec.return_value = "session7\nsession8"
        assert target_sessions(executors={"worker-a": executor}, target=target) == {
            "worker-a": ["session7", "session8"]
        }
        command = executor.exec.call_args.kwargs["command"].replace("/sys/class/iscsi_session", str(tmp_path))
        if state != "empty":
            foreign = tmp_path / "session9"
            foreign.mkdir()
            (foreign / "targetname").write_text(target.iqn + "-foreign\n")
        if state in ("owned_and_foreign", "unreadable"):
            for name in ("session7", "session8"):
                session = tmp_path / name
                session.mkdir()
                if state == "owned_and_foreign":
                    (session / "targetname").write_text(target.iqn + "\n")
        success, output, _ = run_command(command=["bash", "-c", command], check=False)
        if state == "unreadable":
            assert not success, "Existing but unreadable sessions must not be treated as detached"
        else:
            assert success
            assert set(output.splitlines()) == ({"session7", "session8"} if state == "owned_and_foreign" else set())
        executor.exec.return_value = ""
        assert target_sessions(executors={"worker-a": executor}, target=target) == {}

    @mark.parametrize("outcome", ["detached", "timeout"])
    def test_detach_wait_reports_remaining_sessions(self, outcome: str) -> None:
        worker = MagicMock()
        worker.name = "worker-a"
        target = IscsiTarget(iqn="iqn.2026-10.test:owned", portal_addresses=("192.0.2.10", "198.51.100.10"))
        with (
            patch("tests.storage.iscsi_pr.utils.ExecCommandOnPod"),
            patch("tests.storage.iscsi_pr.utils.TimeoutSampler") as sampler,
        ):
            sampler.return_value.__iter__.side_effect = lambda: sampler.return_value
            last = {} if outcome == "detached" else TimeoutExpiredError(value="expired")
            sampler.return_value.__next__.side_effect = [{"worker-a": ["session7"]}, last]
            if outcome == "detached":
                wait_for_target_detach(workers=[worker], utility_pods=[], target=target, observed_wwids=set())
            else:
                with raises(AssertionError, match="worker-a.*session7") as error:
                    wait_for_target_detach(workers=[worker], utility_pods=[], target=target, observed_wwids=set())
                assert isinstance(error.value.__cause__, TimeoutExpiredError)
            assert sampler.call_args.kwargs["exceptions_dict"] == {}, "Worker errors must fail immediately"
            assert sampler.call_args.kwargs["wait_timeout"] == 300, "Detach wait must stay bounded"

    @mark.parametrize("failure", [RuntimeError("worker unavailable"), ConnectionError("worker disconnected")])
    def test_detach_wait_reports_worker_inspection_failure(self, failure: Exception) -> None:
        worker = MagicMock()
        worker.name = "worker-a"
        target = IscsiTarget(iqn="iqn.2026-10.test:owned", portal_addresses=("192.0.2.10", "198.51.100.10"))
        with (
            patch("tests.storage.iscsi_pr.utils.ExecCommandOnPod"),
            patch(
                "tests.storage.iscsi_pr.utils.target_attachments", autospec=True, side_effect=failure
            ) as inspect_worker,
            raises(AssertionError, match=f"worker inspection failed: {type(failure).__name__}: {failure}") as error,
        ):
            wait_for_target_detach(workers=[worker], utility_pods=[], target=target, observed_wwids=set())
        inspect_worker.assert_called_once()
        assert isinstance(error.value.__cause__, TimeoutExpiredError)
        assert error.value.__cause__.last_exp is failure
        assert "still has worker sessions" not in str(error.value)

    @mark.parametrize("outcome", ["success", "consumer_failed", "detach_failed"])
    def test_claim_fixture_waits_before_releasing_resources(self, outcome: str) -> None:
        claims = (MagicMock(), MagicMock())
        target = {"target": MagicMock(), "workers": [MagicMock()], "wwids": set()}
        events = MagicMock()
        with (
            patch("tests.storage.iscsi_pr.conftest.shared_iscsi_claims") as context,
            patch("tests.storage.iscsi_pr.conftest.wait_for_target_detach") as detach,
        ):
            context.return_value.__enter__.return_value = claims
            context.return_value.__exit__.return_value = False
            events.attach_mock(detach, "detach")
            events.attach_mock(context.return_value.__exit__, "release_claims")
            prepared = iscsi_pr_shared_claims.__wrapped__(
                admin_client=MagicMock(),
                workers_utility_pods=[],
                namespace=MagicMock(),
                iscsi_pr_target=target,
                iscsi_pr_persistent_reservations=MagicMock(),
            )
            assert next(prepared) == claims
            assert not events.mock_calls, "Claims and target must remain available to consumer fixtures"
            if outcome == "consumer_failed":
                with raises(RuntimeError, match="consumer failed"):
                    prepared.throw(RuntimeError("consumer failed"))
            elif outcome == "detach_failed":
                detach.side_effect = AssertionError("detach failed")
                with raises(AssertionError, match="detach failed"):
                    next(prepared)
            else:
                with raises(StopIteration):
                    next(prepared)
            assert [call[0] for call in events.mock_calls] == ["detach", "release_claims"], (
                "Wait for kubelet logout before releasing Kubernetes storage, including failure paths"
            )
            detach.assert_called_once_with(
                workers=target["workers"], utility_pods=[], target=target["target"], observed_wwids=set()
            )
