"""Offline coverage for target-to-dm-to-QEMU correlation and owned-map cleanup."""

from copy import deepcopy
from json import dumps
from pathlib import Path
from unittest.mock import MagicMock, patch

from pyhelper_utils.shell import run_command
from pytest import mark, raises
from timeout_sampler import TimeoutExpiredError

from tests.storage.iscsi_pr.conftest import (
    iscsi_pr_persistent_reservations,
    iscsi_pr_windows_vms,
)
from tests.storage.iscsi_pr.multipath import (
    LunMultipath,
    host_multipath_snapshot,
    qemu_block_devices,
    remaining_multipath_maps,
    retire_orphan_map,
    target_path,
    validate_launcher_lun,
    validate_lun_multipath,
    validate_windows_luns,
    vm_multipath_readiness,
    windows_shared_luns,
)
from tests.storage.iscsi_pr.networking import guest_networks
from tests.storage.iscsi_pr.utils import IscsiTarget, target_attachments
from utilities.windows import run_powershell

pytestmark = mark.unit


class TestHostMultipath:
    @mark.parametrize(
        "fault",
        [
            None,
            "missing_path",
            "same_device",
            "missing_map",
            "duplicate_map",
            "readonly",
            "suspended",
            "failed_path",
            "extra_path",
            "path_number",
            "slaves",
            "kernel_uuid",
            "map_size",
        ],
    )
    def test_lun_requires_healthy_exact_mapping(self, fault: str | None) -> None:
        paths = [
            {
                "device": "sdb",
                "portal": "192.0.2.10",
                "lun": 0,
                "size": 50 * 1024**3,
                "dev_t": "8:16",
                "serial": "lio-serial",
                "wwid": "36001234",
            },
            {
                "device": "sdc",
                "portal": "198.51.100.10",
                "lun": 0,
                "size": 50 * 1024**3,
                "dev_t": "8:32",
                "serial": "lio-serial",
                "wwid": "36001234",
            },
        ]
        daemon_paths = [
            {"dev": path["device"], "dev_t": path["dev_t"], "dm_st": "active", "dev_st": "running", "chk_st": "ready"}
            for path in paths
        ]
        mapping = {
            "uuid": "36001234",
            "sysfs": "dm-7",
            "dm_st": "active",
            "write_prot": "rw",
            "path_groups": [{"paths": daemon_paths}],
        }
        detail = {"uuid": "mpath-36001234", "dev_t": "253:7", "size": 50 * 1024**3, "slaves": ["sdc", "sdb"]}
        snapshot = {"maps": [mapping], "details": {"dm-7": detail}}
        if fault == "missing_path":
            daemon_paths.pop()
        elif fault == "same_device":
            daemon_paths[1]["dev"] = "sdb"
        elif fault == "missing_map":
            snapshot["maps"] = []
        elif fault == "duplicate_map":
            snapshot["maps"].append(deepcopy(mapping))
        elif fault == "readonly":
            mapping["write_prot"] = "ro"
        elif fault == "suspended":
            mapping["dm_st"] = "suspend"
        elif fault == "failed_path":
            daemon_paths[1]["chk_st"] = "faulty"
        elif fault == "extra_path":
            daemon_paths.append(dict(daemon_paths[0], dev="sdd"))
        elif fault == "path_number":
            daemon_paths[1]["dev_t"] = "8:99"
        elif fault == "slaves":
            detail["slaves"] = ["sdb", "sdd"]
        elif fault == "kernel_uuid":
            detail["uuid"] = "mpath-foreign"
        elif fault == "map_size":
            detail["size"] = 70 * 1024**3
        args = {"snapshot": snapshot, "paths": paths, "lun": 0, "worker_name": "worker-a"}
        if fault:
            with raises(AssertionError, match="Worker worker-a"):
                validate_lun_multipath(**args)
        else:
            assert validate_lun_multipath(**args) == LunMultipath(
                lun=0, wwid="36001234", dm_device="dm-7", dev_t="253:7", paths=("sdb", "sdc")
            )

    @mark.parametrize("fault", [None, "pending", "wrong_iqn", "wrong_portal", "wrong_lun"])
    def test_path_is_verified_against_kernel_session(self, fault: str | None) -> None:
        target = IscsiTarget(iqn="iqn.2026-10.test:owned", portal_addresses=("192.0.2.10", "198.51.100.10"))
        sysfs_path = "/sys/devices/host3/session7/target3:0:0/3:0:0:0"
        if fault == "wrong_lun":
            sysfs_path = sysfs_path[:-1] + "1"
        identity = [target.iqn, "192.0.2.10", "3260"]
        if fault == "wrong_iqn":
            identity[0] = "iqn.2026-10.test:foreign"
        elif fault == "wrong_portal":
            identity[1] = "198.51.100.10"
        executor = MagicMock()
        executor.exec.side_effect = [
            "pending" if fault == "pending" else f"/dev/sdb\n{sysfs_path}\n{50 * 1024**3}\n8:16",
            "\n".join(identity),
        ]
        args = {"executor": executor, "target": target, "portal": "192.0.2.10", "lun": 0}
        if fault in ("wrong_iqn", "wrong_portal", "wrong_lun"):
            with raises(AssertionError):
                target_path(**args)
        elif fault == "pending":
            assert target_path(**args) is None
        else:
            result = target_path(**args)
            assert result["device"] == "sdb" and result["dev_t"] == "8:16"
        for call in executor.exec.call_args_list:
            success, _, _ = run_command(command=["bash", "-n", "-c", call.kwargs["command"]], check=False)
            assert success, "Generated read-only host probe must have valid shell syntax"

    @mark.parametrize("state", ["ready", "pending"])
    def test_snapshot_refreshes_owned_maps_without_reidentifying_paths(self, state: str) -> None:
        executor = MagicMock()
        executor.exec.side_effect = [
            dumps({
                "maps": [
                    {"uuid": "36001234", "sysfs": "dm-7" if state == "ready" else "undef"},
                    {"uuid": "36009999", "sysfs": "dm-9"},
                ]
            }),
            f"mpath-36001234\n253:7\n{50 * 1024**3}\nsdb\nsdc",
        ]
        with patch("tests.storage.iscsi_pr.multipath.target_path") as identify:
            snapshot = host_multipath_snapshot(executor=executor, wwids={"36001234"})
        assert set(snapshot["details"]) == ({"dm-7"} if state == "ready" else set())
        identify.assert_not_called()
        commands = [call.kwargs["command"] for call in executor.exec.call_args_list]
        assert len(commands) == (2 if state == "ready" else 1)
        assert not any("dm-9" in command or "show paths" in command for command in commands)


class TestLauncherConsumption:
    @mark.parametrize(
        "fault", [None, "physical_source", "qemu_not_open", "disk_instead_of_lun", "wrong_bus", "cache", "pr_helper"]
    )
    def test_live_disk_and_open_descriptor_must_use_dm(self, fault: str | None) -> None:
        mapping = LunMultipath(lun=0, wwid="36001234", dm_device="dm-7", dev_t="253:7", paths=("sdb", "sdc"))
        disk = {
            "@type": "block",
            "@device": "lun",
            "target": {"@bus": "scsi"},
            "driver": {"@cache": "none"},
            "source": {"reservations": {"source": {"@type": "unix", "@path": "/var/run/qemu-pr-helper.sock"}}},
        }
        source_dev_t = "253:7"
        qemu_devices = {"253:7", "253:99"}
        if fault == "physical_source":
            source_dev_t = "8:16"
        elif fault == "qemu_not_open":
            qemu_devices = {"8:16", "253:99"}
        elif fault == "disk_instead_of_lun":
            disk["@device"] = "disk"
        elif fault == "wrong_bus":
            disk["target"]["@bus"] = "virtio"
        elif fault == "cache":
            disk["driver"]["@cache"] = "writeback"
        elif fault == "pr_helper":
            disk["source"]["reservations"]["source"]["@path"] = ""
        args = {
            "disk": disk,
            "mapping": mapping,
            "source_dev_t": source_dev_t,
            "qemu_devices": qemu_devices,
            "vm_name": "windows-a",
        }
        if fault:
            with raises(AssertionError, match="VM windows-a"):
                validate_launcher_lun(**args)
        else:
            validate_launcher_lun(**args)

    @mark.parametrize("fault", [None, "unreadable"])
    def test_qemu_probe_returns_decimal_device_numbers_from_privileged_worker(self, fault: str | None) -> None:
        executor = MagicMock()
        executor.exec.return_value = "fd:7\n8:10\nfd:7\n"
        if fault:
            executor.exec.side_effect = RuntimeError("QEMU descriptors unreadable")
            with raises(RuntimeError, match="descriptors unreadable"):
                qemu_block_devices(executor=executor, domain_uuid="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
        else:
            assert qemu_block_devices(executor=executor, domain_uuid="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee") == {
                "253:7",
                "8:16",
            }
        command = executor.exec.call_args.kwargs["command"]
        success, _, _ = run_command(command=["bash", "-n", "-c", command], check=False)
        assert success
        assert "-uuid" in command and 'test "$found" -eq 1' in command
        assert 'test -r "$process/fd"' in command
        assert "container" not in executor.exec.call_args.kwargs

    @mark.parametrize(
        "fault", [None, "worker_error", "unvalidated_worker", "failed_path", "changed_map", "unshared_lun"]
    )
    def test_vm_uses_prepared_maps_and_requires_healthy_paths(self, fault: str | None) -> None:
        vm, worker, executor = MagicMock(), MagicMock(), MagicMock()
        vm.name, worker.name = "windows-a", "worker-a"
        vm.vmi.instance.spec.domain.devices.disks = [
            {"name": f"shared-lun-{lun}", "shareable": fault != "unshared_lun"} for lun in range(2)
        ]
        vm.vmi.get_node.return_value = worker
        mappings = tuple(
            LunMultipath(lun=lun, wwid=f"3600123{lun}", dm_device=f"dm-{lun}", dev_t=f"253:{lun}", paths=("sdb", "sdc"))
            for lun in range(2)
        )
        maps = [
            {
                "uuid": mapping.wwid,
                "sysfs": mapping.dm_device,
                "dm_st": "active",
                "write_prot": "rw",
                "path_groups": [
                    {
                        "paths": [
                            {"dev": device, "dm_st": "active", "dev_st": "running", "chk_st": "ready"}
                            for device in mapping.paths
                        ]
                    }
                ],
            }
            for mapping in mappings
        ]
        if fault == "failed_path":
            maps[0]["path_groups"][0]["paths"][1]["chk_st"] = "faulty"
        elif fault == "changed_map":
            maps[0]["uuid"] = "foreign"
        executor.exec.side_effect = RuntimeError("worker unavailable") if fault == "worker_error" else None
        executor.exec.return_value = dumps({"maps": maps})
        vm.vmi.get_xml_dict.return_value = {
            "domain": {
                "uuid": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
                "devices": {
                    "disk": [
                        {"alias": {"@name": f"ua-shared-lun-{lun}"}, "source": {"@dev": f"/dev/shared-lun-{lun}"}}
                        for lun in range(2)
                    ]
                },
            }
        }
        vm.vmi.get_virt_launcher_pod.return_value.execute.side_effect = ["fd:0", "fd:1"]
        with (
            patch("tests.storage.iscsi_pr.multipath.ExecCommandOnPod", return_value=executor),
            patch("tests.storage.iscsi_pr.multipath.qemu_block_devices", return_value={"253:0", "253:1"}) as probe,
            patch("tests.storage.iscsi_pr.multipath.validate_launcher_lun") as validate,
        ):
            args = {
                "vm": vm,
                "client": MagicMock(),
                "utility_pods": [],
                "mappings_by_worker": {} if fault == "unvalidated_worker" else {worker.name: mappings},
            }
            if fault:
                with raises(RuntimeError if fault == "worker_error" else AssertionError):
                    vm_multipath_readiness(**args)
            else:
                vm_multipath_readiness(**args)
                assert [call.kwargs["source_dev_t"] for call in validate.call_args_list] == ["253:0", "253:1"]
                probe.assert_called_once_with(executor=executor, domain_uuid="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
        assert executor.exec.call_count == (0 if fault == "unvalidated_worker" else 1)


class TestGuestLuns:
    @mark.parametrize("fault", [None, "missing", "duplicate", "root", "capacity", "bus", "identity"])
    @mark.parametrize("bus_type", ["SCSI", "SAS"])
    def test_guest_luns_exclude_root_and_have_distinct_identities(self, fault: str | None, bus_type: str) -> None:
        disks = [{"SerialNumber": None, "IsBoot": True, "IsSystem": True}]
        disks.extend(
            {
                "SerialNumber": f"lio-{lun} ",
                "IsBoot": False,
                "IsSystem": False,
                "Size": size * 1024**3,
                "BusType": bus_type,
                "UniqueId": f"naa-{lun}",
            }
            for lun, size in enumerate((50, 70))
        )
        if fault == "missing":
            disks.pop()
        elif fault == "duplicate":
            disks.append(deepcopy(disks[1]))
        elif fault == "root":
            disks[1]["IsBoot"] = True
        elif fault == "capacity":
            disks[1]["Size"] = 70 * 1024**3
        elif fault == "bus":
            disks[1]["BusType"] = "SATA"
        elif fault == "identity":
            disks[2]["UniqueId"] = disks[1]["UniqueId"]
        args = {"disks": disks, "lun_wwns": ("lio-0", "lio-1"), "vm_name": "windows-a"}
        if fault:
            with raises(AssertionError, match="windows-a"):
                validate_windows_luns(**args)
        else:
            assert validate_windows_luns(**args) == ("naa-0", "naa-1")

    def test_guest_enumeration_retries_without_mutating_disks(self) -> None:
        vm = MagicMock()
        vm.name = "windows-a"
        disks = [
            {
                "SerialNumber": f"lio-{lun}",
                "IsBoot": False,
                "IsSystem": False,
                "Size": size * 1024**3,
                "BusType": "SCSI",
                "UniqueId": f"naa-{lun}",
            }
            for lun, size in enumerate((50, 70))
        ]
        with (
            patch(
                "tests.storage.iscsi_pr.multipath.TimeoutSampler", return_value=iter(["[]", "[]", dumps(disks)])
            ) as sampler,
            patch("tests.storage.iscsi_pr.multipath.LOGGER") as logger,
        ):
            assert windows_shared_luns(vm=vm, lun_wwns=("lio-0", "lio-1")) == ("naa-0", "naa-1")
            messages = [call.args[0] for call in logger.info.call_args_list]
            assert sum("check pending:" in message for message in messages) == 1
            assert "checks passed" in messages[-1]
        assert sampler.call_args.kwargs["func"] is run_powershell
        assert sampler.call_args.kwargs["ssh_exec"] is vm.ssh_exec
        script = sampler.call_args.kwargs["script"]
        assert "Get-Disk" in script and "ConvertTo-Json -InputObject" in script
        assert "Set-Disk" not in script and "Initialize-Disk" not in script

    def test_inventory_execution_failure_is_not_reported_as_timeout(self) -> None:
        vm = MagicMock()
        vm.name = "windows-a"
        failure = RuntimeError("PowerShell inventory failed")
        with (
            patch("tests.storage.iscsi_pr.multipath.run_powershell", autospec=True, side_effect=failure) as command,
            raises(
                AssertionError, match="guest LUN inventory probe failed: RuntimeError: PowerShell inventory failed"
            ) as error,
        ):
            windows_shared_luns(vm=vm, lun_wwns=("lio-0", "lio-1"))
        command.assert_called_once()
        assert isinstance(error.value.__cause__, TimeoutExpiredError)
        assert error.value.__cause__.last_exp is failure
        assert "timed out" not in str(error.value)

    def test_inventory_timeout_keeps_last_lun_validation_failure(self) -> None:
        vm = MagicMock()
        vm.name = "windows-a"
        with (
            patch("tests.storage.iscsi_pr.multipath.TimeoutSampler") as sampler,
            raises(AssertionError, match="guest LUN enumeration timed out:.*LUN 0") as error,
        ):
            sampler.return_value.__iter__.side_effect = lambda: sampler.return_value
            sampler.return_value.__next__.side_effect = ["[]", TimeoutExpiredError(value="inventory wait")]
            windows_shared_luns(vm=vm, lun_wwns=("lio-0", "lio-1"))
        assert isinstance(error.value.__cause__, TimeoutExpiredError)
        assert error.value.__cause__.last_exp is None


class TestMultipathCleanup:
    @mark.parametrize("state", ["empty", "owned_and_foreign", "unreadable"])
    def test_orphan_map_scan_uses_recorded_wwids(self, tmp_path: Path, state: str) -> None:
        executor = MagicMock()
        executor.exec.return_value = "dm-7|mpath-36001234\ndm-9|mpath-36009999\ndm-11|CRYPT-36001234"
        assert remaining_multipath_maps(executor=executor, observed={"36001234"}) == ["dm-7:mpath-36001234"]
        command = executor.exec.call_args.kwargs["command"].replace("/sys/class/block", str(tmp_path))
        if state != "empty":
            for name, device_uuid in (("dm-7", "mpath-36001234"), ("dm-9", "mpath-36009999")):
                directory = tmp_path / name / "dm"
                directory.mkdir(parents=True)
                if state == "owned_and_foreign":
                    (directory / "uuid").write_text(device_uuid + "\n")
        success, output, _ = run_command(command=["bash", "-c", command], check=False)
        if state == "unreadable":
            assert not success
        else:
            assert success
            executor.exec.return_value = output.strip()
            expected = ["dm-7:mpath-36001234"] if state == "owned_and_foreign" else []
            assert remaining_multipath_maps(executor=executor, observed={"36001234"}) == expected

    def test_sessions_and_orphan_maps_are_both_reported(self) -> None:
        target = IscsiTarget(iqn="iqn.2026-10.test:owned", portal_addresses=("192.0.2.10", "198.51.100.10"))
        executors = {"worker-a": MagicMock(), "worker-b": MagicMock()}
        with (
            patch("tests.storage.iscsi_pr.utils.target_sessions", return_value={"worker-a": ["session7"]}),
            patch("tests.storage.iscsi_pr.utils.remaining_multipath_maps", side_effect=[["dm-7:mpath-36001234"], []]),
        ):
            assert target_attachments(
                executors=executors, target=target, observed_wwids={"36001234"}, flush_orphan_maps=True
            ) == {"worker-a": ["session7", "dm-7:mpath-36001234"]}


class TestWindowsConsumerFixtures:
    @mark.parametrize("outcome", [None, "import", "boot", "guest", "map", "luns"])
    def test_windows_vms_have_private_roots_and_delete_before_volumes(self, outcome: str | None) -> None:
        volumes, vms = [MagicMock() for _ in range(3)], [MagicMock() for _ in range(3)]
        events = MagicMock()
        for index, (volume, vm) in enumerate(zip(volumes, vms, strict=True)):
            for context in (volume, vm):
                context.__enter__.return_value = context
                context.__exit__.return_value = False
            events.attach_mock(vm.__exit__, f"vm{index}")
            events.attach_mock(volume.__exit__, f"root{index}")
        if outcome == "import":
            volumes[1].__enter__.side_effect = RuntimeError("import failed")
        image = {"template_labels": {"os": "win2k19", "workload": "server", "flavor": "medium"}, "os_version": "2019"}
        workers = [MagicMock() for _ in range(3)]
        maps = {"worker": "prepared"}
        with (
            patch("tests.storage.iscsi_pr.conftest.get_windows_os_dict", return_value=image),
            patch("tests.storage.iscsi_pr.conftest.image_volume", side_effect=volumes) as imports,
            patch("tests.storage.iscsi_pr.conftest.IscsiConsumerVirtualMachine", side_effect=vms) as constructor,
            patch(
                "tests.storage.iscsi_pr.conftest.running_vm",
                side_effect=RuntimeError("boot failed") if outcome == "boot" else None,
            ),
            patch(
                "tests.storage.iscsi_pr.conftest.wait_for_windows_vm",
                side_effect=RuntimeError("guest failed") if outcome == "guest" else None,
            ),
            patch(
                "tests.storage.iscsi_pr.conftest.vm_multipath_readiness",
                side_effect=[None, RuntimeError("map failed")] if outcome == "map" else None,
            ) as check,
            patch(
                "tests.storage.iscsi_pr.conftest.windows_shared_luns",
                return_value=("naa-0", "naa-1"),
                side_effect=[("naa-0", "naa-1"), RuntimeError("luns failed")] if outcome == "luns" else None,
            ) as guest_disks,
        ):
            prepared = iscsi_pr_windows_vms.__wrapped__(
                admin_client=MagicMock(),
                namespace=MagicMock(),
                workers_utility_pods=[],
                iscsi_pr_target={"workers": workers, "lun_wwns": ("serial0", "serial1")},
                iscsi_pr_shared_claims=(MagicMock(), MagicMock()),
                iscsi_pr_guest_networks=guest_networks(),
                iscsi_pr_guest_nads=(MagicMock(), MagicMock()),
                iscsi_pr_router=MagicMock(),
                iscsi_pr_host_multipath=maps,
                artifactory_secret_scope_module=MagicMock(),
                artifactory_config_map_scope_module=MagicMock(),
            )
            if outcome:
                with raises(RuntimeError, match=outcome):
                    next(prepared)
            else:
                result = next(prepared)
                assert result["vms"] == tuple(vms) and result["roots"] == tuple(volumes)
                assert result["guest_luns"] == (("naa-0", "naa-1"),) * 3
                assert [call.kwargs["vm"] for call in check.call_args_list] == vms
                assert [call.kwargs["vm"] for call in guest_disks.call_args_list] == vms
                assert all(call.kwargs["mappings_by_worker"] is maps for call in check.call_args_list)
                assert len({call.kwargs["name"] for call in imports.call_args_list}) == 3
                assert [call.kwargs["memory_guest"] for call in constructor.call_args_list] == ["8Gi", "6Gi", "6Gi"]
                with raises(StopIteration):
                    next(prepared)
            if outcome in {"map", "luns"}:
                assert constructor.call_count == 2, "Storage failures must stop creation before the next Windows VM"
            names = [call[0] for call in events.mock_calls]
            assert max(index for index, name in enumerate(names) if name.startswith("vm")) < min(
                index for index, name in enumerate(names) if name.startswith("root")
            )

    def test_pr_patch_is_reconciled_and_restored_by_existing_context(self) -> None:
        hco = MagicMock()
        with patch("tests.storage.iscsi_pr.conftest.ResourceEditorValidateHCOReconcile") as editor:
            prepared = iscsi_pr_persistent_reservations.__wrapped__(
                admin_client=MagicMock(),
                hco_namespace=MagicMock(),
                hyperconverged_resource_scope_module=hco,
                iscsi_pr_hosts={},
            )
            assert next(prepared) is hco
            assert editor.call_args.kwargs["patches"][hco] == {
                "spec": {"storage": {"persistentReservationConfiguration": {"enabled": True}}}
            }
            assert editor.call_args.kwargs["wait_for_reconcile_post_update"]
            with raises(StopIteration):
                next(prepared)
            editor.return_value.__exit__.assert_called_once()


class TestOrphanMapRetirement:
    @mark.parametrize("state", ["waiting", "removed"])
    def test_retirement_guards_and_scopes_the_flush(self, state: str) -> None:
        executor = MagicMock()
        executor.exec.return_value = state
        assert retire_orphan_map(executor=executor, device="dm-7", wwid="36001234") == (state == "removed")
        command = executor.exec.call_args.kwargs["command"]
        success, _, _ = run_command(command=["bash", "-n", "-c", command], check=False)
        assert success
        assert "mpath-36001234" in command and "multipath -f 36001234" in command
        assert "/slaves" in command and "/holders" in command and "-o open" in command
        assert "multipath -F" not in command

    def test_no_flush_while_target_sessions_exist(self) -> None:
        target = IscsiTarget(iqn="iqn.2026-10.test:owned", portal_addresses=("192.0.2.10", "198.51.100.10"))
        with (
            patch("tests.storage.iscsi_pr.utils.target_sessions", return_value={"worker-a": ["session7"]}),
            patch("tests.storage.iscsi_pr.utils.remaining_multipath_maps", return_value=["dm-7:mpath-36001234"]),
            patch("tests.storage.iscsi_pr.utils.retire_orphan_map") as retire,
        ):
            target_attachments(
                executors={"worker-a": MagicMock()}, target=target, observed_wwids={"36001234"}, flush_orphan_maps=True
            )
            retire.assert_not_called()

    def test_maps_are_rechecked_after_scoped_flush(self) -> None:
        target = IscsiTarget(iqn="iqn.2026-10.test:owned", portal_addresses=("192.0.2.10", "198.51.100.10"))
        executor = MagicMock()
        with (
            patch("tests.storage.iscsi_pr.utils.target_sessions", return_value={}),
            patch("tests.storage.iscsi_pr.utils.remaining_multipath_maps", side_effect=[["dm-7:mpath-36001234"], []]),
            patch("tests.storage.iscsi_pr.utils.retire_orphan_map", return_value=True) as retire,
        ):
            assert (
                target_attachments(
                    executors={"worker-a": executor}, target=target, observed_wwids={"36001234"}, flush_orphan_maps=True
                )
                == {}
            )
            retire.assert_called_once_with(executor=executor, device="dm-7", wwid="36001234")


class TestOrphanGuardShell:
    @mark.parametrize("state", ["unused", "slaves", "holders", "open", "wrong_uuid", "read_failed"])
    def test_shell_never_flushes_referenced_or_unreadable_maps(self, tmp_path: Path, state: str) -> None:
        device = tmp_path / "dm-7"
        for directory in ("dm", "slaves", "holders"):
            (device / directory).mkdir(parents=True)
        (device / "dm" / "uuid").write_text("mpath-foreign" if state == "wrong_uuid" else "mpath-36001234")
        if state in ("slaves", "holders"):
            (device / state / "referenced").touch()
        executor = MagicMock()
        executor.exec.return_value = "waiting"
        retire_orphan_map(executor=executor, device="dm-7", wwid="36001234")
        script = executor.exec.call_args.kwargs["command"].replace("/sys/class/block", str(tmp_path))
        # Stub only the host commands which could change real device state.
        # All guard reads execute against synthetic sysfs directories.
        open_count = 1 if state == "open" else 0
        stubs = f"dmsetup() {{ echo {open_count}; }}\nmultipath() {{ echo called > {tmp_path}/flush-marker; }}\n"
        if state == "read_failed":
            stubs += "ls() { return 1; }\n"
        success, output, _ = run_command(command=["bash", "-c", stubs + script], check=False)
        if state == "read_failed":
            assert not success, "Failed guard reads must stop cleanup before any flush"
        else:
            assert success
            assert output.strip() == ("removed" if state == "unused" else "waiting")
        assert (tmp_path / "flush-marker").exists() == (state == "unused")
