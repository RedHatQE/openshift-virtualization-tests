"""Offline checks of isolation, rollback and pre-VM multipath preparation."""

from copy import deepcopy
from json import dumps
from pathlib import Path
from shlex import quote
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from pyhelper_utils.shell import run_command
from pytest import mark, raises
from timeout_sampler import TimeoutExpiredError

from tests.storage.iscsi_pr.bootstrap import (
    HOST_FILES,
    STATE_DIRECTORY,
    login_ready,
    maps_unused,
    multipath_configuration,
    observed_lun_paths,
    prepare_host_script,
    prepared_hosts,
    prepared_multipath,
    qualified_maps,
    release_bootstrap_sessions,
    restore_host_script,
    storage_plan,
)
from tests.storage.iscsi_pr.utils import IscsiTarget

pytestmark = mark.unit
OWNER = "0123456789abcdef0123456789abcdef"
SNAPSHOTS = [
    {
        "address": f"10.0.0.{index + 1}",
        "underlay_mtu": 1500,
        "routes": [{"dst": "default"}, {"dst": "10.0.0.0/24"}, {"dst": "198.18.0.0/24"}],
        "addresses": [
            {"ifname": "br-ex", "addr_info": [{"family": "inet", "local": f"10.0.0.{index + 1}", "prefixlen": 24}]}
        ],
        "links": [{"ifname": "br-ex", "mtu": 1500}],
    }
    for index in range(3)
]


class TestHostBootstrap:
    def test_plan_avoids_existing_routes_cluster_cidrs_and_guest_networks(self) -> None:
        plan = storage_plan(owner=OWNER, snapshots=SNAPSHOTS, cluster_cidrs=["198.18.1.0/24", "10.128.0.0/14"])
        assert all(network.mtu == 1450 for network in plan.networks)
        assert plan.vnis[0] != plan.vnis[1]
        assert len(set(plan.addresses)) == 3
        assert all(
            str(network.target_address.network) not in ("198.18.0.0/24", "198.18.1.0/24") for network in plan.networks
        )
        assert not plan.networks[0].target_address.network.overlaps(plan.networks[1].target_address.network)
        assert all(len(name) <= 15 for name in plan.vxlan_names)

    @mark.parametrize("fault", ["workers", "address", "subnets", "mtu", "name", "vni"])
    def test_rejects_conflicts_before_mutation(self, fault: str) -> None:
        snapshots = deepcopy(SNAPSHOTS)
        cidrs = []
        if fault == "workers":
            snapshots.pop()
        elif fault == "address":
            snapshots[1]["address"] = snapshots[0]["address"]
        elif fault == "subnets":
            cidrs.append("198.18.0.0/15")
        elif fault == "mtu":
            snapshots[0]["underlay_mtu"] = 1300
        elif fault == "name":
            snapshots[0]["links"].append({"ifname": "ip012345b0"})
        else:
            plan = storage_plan(owner=OWNER, snapshots=snapshots, cluster_cidrs=[])
            snapshots[0]["links"].append({
                "ifname": "existing",
                "linkinfo": {"info_kind": "vxlan", "info_data": {"id": plan.vnis[0]}},
            })
        with raises(AssertionError):
            storage_plan(owner=OWNER, snapshots=snapshots, cluster_cidrs=cidrs)

    def test_host_scripts_parse_and_never_enable_or_reboot_workers(self) -> None:
        plan = storage_plan(owner=OWNER, snapshots=SNAPSHOTS, cluster_cidrs=[])
        for script in (prepare_host_script(plan=plan, index=0), restore_host_script(plan=plan)):
            success, _, error = run_command(command=["bash", "-n", "-c", script], check=False)
            assert success, error
            assert "systemctl enable" not in script and "reboot" not in script
            assert "multipath -F" not in script
        source = prepare_host_script(plan=plan, index=0)
        assert source.index("snapshot-complete") < source.index("cat > /etc/multipath.conf")
        assert source.count("bridge fdb append") == 4

    def test_partial_setup_restores_files_and_initial_service_activation(self, tmp_path: Path) -> None:
        plan = storage_plan(owner=OWNER, snapshots=SNAPSHOTS, cluster_cidrs=[])
        state = tmp_path / "state"
        state.mkdir()
        (state / "owner").write_text(OWNER)
        units = tmp_path / "units"
        units.mkdir()
        (units / "iscsid.socket").touch()
        for path in HOST_FILES:
            (tmp_path / path.lstrip("/")).parent.mkdir(parents=True, exist_ok=True)
        original = "original multipath configuration\n"
        (tmp_path / "etc/multipath.conf").write_text(original)
        stubs = f"""systemctl() {{
    local action=$1; shift
    case "$action" in
        is-active) shift; test -e {quote(str(units))}/"$1";;
        start|restart) for unit in "$@"; do touch {quote(str(units))}/"$unit"; done;;
        stop) for unit in "$@"; do rm -f {quote(str(units))}/"$unit"; done;;
        *) return 1;;
    esac
}}
restorecon() {{ return 0; }}
modprobe() {{ return 0; }}
multipathd() {{ echo ok; }}
ip() {{ return 1; }}
"""
        prepare = (
            prepare_host_script(plan=plan, index=0)
            .replace(STATE_DIRECTORY, str(state))
            .replace("/etc/", str(tmp_path / "etc") + "/")
            .replace("/sys/", str(tmp_path / "sys") + "/")
        )
        success, _, _ = run_command(command=["bash", "-c", stubs + prepare], check=False)
        assert not success, "Injected link creation failure must propagate"
        assert (state / "snapshot-complete").exists()
        assert (units / "multipathd.service").exists()
        (tmp_path / "etc/multipath/wwids").write_text("owned WWID cache")
        restore = (
            restore_host_script(plan=plan)
            .replace(STATE_DIRECTORY, str(state))
            .replace("/etc/", str(tmp_path / "etc") + "/")
            .replace("/sys/", str(tmp_path / "sys") + "/")
        )
        success, _, error = run_command(command=["bash", "-c", stubs + restore], check=False)
        assert success, error
        assert (tmp_path / "etc/multipath.conf").read_text() == original
        assert not (tmp_path / "etc/multipath/wwids").exists()
        assert not (tmp_path / "etc/iscsi/initiatorname.iscsi").exists()
        assert {unit.name for unit in units.iterdir()} == {"iscsid.socket"}
        assert not state.exists()

    def test_second_worker_failure_rolls_back_acquired_workers_in_reverse_order(self) -> None:
        workers = [
            SimpleNamespace(
                name=f"worker-{index}",
                instance=SimpleNamespace(
                    status=SimpleNamespace(
                        addresses=[SimpleNamespace(type="InternalIP", address=f"10.0.0.{index + 1}")]
                    )
                ),
            )
            for index in range(3)
        ]
        executors = []
        for index, snapshot in enumerate(SNAPSHOTS):
            executor = MagicMock()
            executor.exec.side_effect = [
                "",
                "",
                dumps(snapshot["links"]),
                dumps(snapshot["addresses"]),
                dumps(snapshot["routes"]),
                "",
                RuntimeError("link failed") if index == 1 else "",
            ]
            executors.append(executor)
        network = SimpleNamespace(
            clusterNetwork=[SimpleNamespace(cidr="10.128.0.0/14")], serviceNetwork=["172.30.0.0/16"]
        )
        with (
            patch("tests.storage.iscsi_pr.bootstrap.ExecCommandOnPod", side_effect=executors),
            patch("tests.storage.iscsi_pr.bootstrap.Network") as resource,
            patch("tests.storage.iscsi_pr.bootstrap.restore_host", return_value=None) as restore,
        ):
            resource.return_value.instance.spec = network
            with (
                raises(RuntimeError, match="link failed"),
                prepared_hosts(client=MagicMock(), workers=workers, utility_pods=[]),
            ):
                raise AssertionError("Failed setup must not yield")
            assert [item.kwargs["executor"] for item in restore.call_args_list] == [executors[1], executors[0]]
            assert executors[2].exec.call_count == 5

    def test_whitelist_is_exact_and_disables_external_overrides(self) -> None:
        configuration = multipath_configuration(wwids=("3600140a1", "3600140a2"))
        assert "find_multipaths strict" in configuration and 'config_dir ""' in configuration
        assert 'wwid "^3600140a1$"' in configuration and 'wwid ".*"' in configuration
        with raises(AssertionError, match="Invalid observed WWID"):
            multipath_configuration(wwids=('unsafe"; command',))

    def test_restore_refuses_referenced_storage_and_retains_journal(self, tmp_path: Path) -> None:
        plan = storage_plan(owner=OWNER, snapshots=SNAPSHOTS, cluster_cidrs=[])
        state = tmp_path / "state"
        state.mkdir()
        (state / "owner").write_text(OWNER)
        (state / "snapshot-complete").touch()
        sessions = tmp_path / "sys/class/iscsi_session/session1"
        sessions.mkdir(parents=True)
        script = (
            restore_host_script(plan=plan)
            .replace(STATE_DIRECTORY, str(state))
            .replace("/sys/", str(tmp_path / "sys") + "/")
        )
        success, _, error = run_command(command=["bash", "-c", script], check=False)
        assert not success and "Existing iSCSI sessions" in error
        assert state.exists(), "Unsafe restore must retain the recovery journal"


class TestMultipathBootstrap:
    @mark.parametrize(
        "fault",
        [
            None,
            "serial",
            "capacity",
            "same_path",
            "different_wwid",
            "same_lun",
            "missing",
            "unterminated",
            "embedded_nul",
        ],
    )
    def test_observed_paths_require_actual_two_path_identity(self, fault: str | None) -> None:
        target = IscsiTarget(iqn="iqn.2026-10.test:owned", portal_addresses=("198.18.1.254", "198.18.2.254"))
        executor = MagicMock()
        serials = ("owned-lun-0", "owned-lun-1")
        paths = []
        responses = []
        for lun, serial in enumerate(serials):
            for index in range(2):
                paths.append({
                    "device": f"sd{chr(97 + lun * 2 + (0 if fault == 'same_path' else index))}",
                    "size": (50, 70)[lun] * 1024**3 + (1 if fault == "capacity" else 0),
                })
                vpd_serial = "foreign-serial" if fault == "serial" else serial
                payload = vpd_serial.encode()
                if fault == "embedded_nul":
                    payload = payload[:3] + b"\x00" + payload[3:]
                if fault != "unterminated":
                    payload += b"\x00"
                vpd = bytes([0, 0x80, 0, len(payload)]) + payload
                responses.extend((
                    vpd.hex(),
                    f"3600140a{0 if fault == 'same_lun' else lun}{index if fault == 'different_wwid' else 0}",
                ))
        executor.exec.side_effect = responses
        if fault == "missing":
            paths[0] = None
        with patch("tests.storage.iscsi_pr.bootstrap.target_path", side_effect=paths):
            if fault not in (None, "missing", "unterminated"):
                with raises(AssertionError) as failure:
                    observed_lun_paths(executor=executor, target=target, lun_wwns=serials)
                if fault == "serial":
                    assert "'owned-lun-0'" in str(failure.value) and "'foreign-serial'" in str(failure.value)
            else:
                result = observed_lun_paths(executor=executor, target=target, lun_wwns=serials)
                if fault == "missing":
                    assert result is None
                else:
                    assert result == (paths[:2], paths[2:])
                    assert tuple(lun_paths[0]["wwid"] for lun_paths in result) == ("3600140a00", "3600140a10")

    @mark.parametrize("open_counts", ["", "0", "1", "0\n1"])
    def test_sessions_are_retained_while_maps_are_referenced(self, open_counts: str) -> None:
        executor = MagicMock()
        executor.exec.return_value = open_counts
        assert maps_unused(executors={"worker": executor}, wwids={"3600140a1", "3600140a2"}) == (
            not any(int(value) for value in open_counts.split())
        )
        command = executor.exec.call_args.kwargs["command"]
        assert "mpath-3600140a1" in command and "mpath-3600140a2" in command and "holders" in command
        executor.exec.assert_called_once()
        assert "--logout" not in command

    @mark.parametrize("state", ["unused", "owned_open", "owned_holder", "foreign_open", "unreadable"])
    def test_map_scan_checks_both_owned_luns_and_ignores_foreign_references(self, tmp_path: Path, state: str) -> None:
        executor = MagicMock()
        executor.exec.return_value = "0"
        wwids = {"3600140a1", "3600140a2"}
        assert maps_unused(executors={"worker": executor}, wwids=wwids)
        command = executor.exec.call_args.kwargs["command"].replace("/sys/class/block", str(tmp_path))
        for device, wwid in (("dm-1", "3600140a1"), ("dm-2", "3600140a2"), ("dm-9", "foreign")):
            (tmp_path / device / "dm").mkdir(parents=True)
            (tmp_path / device / "holders").mkdir()
            if not (state == "unreadable" and device == "dm-2"):
                (tmp_path / device / "dm" / "uuid").write_text(f"mpath-{wwid}\n")
        if state == "owned_holder":
            (tmp_path / "dm-2" / "holders" / "consumer").touch()
        opened = "/dev/dm-2" if state == "owned_open" else "/dev/dm-9" if state == "foreign_open" else "none"
        script = f'dmsetup() {{ if [ "${{@: -1}}" = {quote(opened)} ]; then echo 1; else echo 0; fi; }}\n' + command
        success, output, _ = run_command(command=["bash", "-c", script], check=False)
        if state == "unreadable":
            assert not success, "An unreadable existing device must fail the scan"
        else:
            assert success
            executor.exec.return_value = output.strip()
            assert maps_unused(executors={"worker": executor}, wwids=wwids) == (
                state not in {"owned_open", "owned_holder"}
            )

    def test_no_map_scan_before_luns_are_observed(self) -> None:
        executor = MagicMock()
        assert maps_unused(executors={"worker": executor}, wwids=set())
        executor.exec.assert_not_called()

    @mark.parametrize("status", [0, 15, 4, 8, 11, 29, 5, 6, 7, 19, 24, 127])
    def test_login_retries_only_transient_statuses_and_preserves_command_exit_code(self, status: int) -> None:
        executor = MagicMock()
        executor.exec.return_value = str(status)
        node = "iscsiadm -m node -T iqn.2026-10.test:owned -p 198.18.1.254:3260"
        if status in {5, 6, 7, 19, 24, 127}:
            with raises(RuntimeError, match=f"owned.*exit code {status}"):
                login_ready(executor=executor, node_command=node)
        else:
            assert login_ready(executor=executor, node_command=node) == (status in {0, 15})
        assert executor.exec.call_args.kwargs["timeout"] == 30
        command = executor.exec.call_args.kwargs["command"]
        success, output, error = run_command(
            command=["bash", "-c", f"iscsiadm() {{ echo 'login output'; return {status}; }}\n" + command],
            check=False,
            verify_stderr=False,
        )
        assert success and output.strip() == str(status), "Login output must not hide or contaminate its exit code"
        assert error.strip() == "login output"

    def test_success_prepares_maps_before_yield_and_releases_sessions_after_consumer_scope(self) -> None:
        executor = MagicMock()
        executor.exec.return_value = "diagnostics\n0"
        target = IscsiTarget(iqn="iqn.2026-10.test:owned", portal_addresses=("198.18.1.254", "198.18.2.254"))
        hosts = {"workers": [MagicMock()], "executors": {"worker": executor}}
        observed = set()
        luns = ([{"wwid": "3600140a1", "device": "sde"}], [{"wwid": "3600140a2", "device": "sdf"}])
        with (
            patch(
                "tests.storage.iscsi_pr.bootstrap.TimeoutSampler",
                side_effect=[[False, True], [True], [luns], [("map0", "map1")]],
            ),
            patch("tests.storage.iscsi_pr.bootstrap.release_bootstrap_sessions", return_value=None) as release,
        ):
            with prepared_multipath(
                hosts=hosts, target=target, lun_wwns=("serial0", "serial1"), observed=observed
            ) as mappings:
                assert mappings == {"worker": ("map0", "map1")}
                assert observed == {"3600140a1", "3600140a2"}
                release.assert_not_called()
                command = executor.exec.call_args.kwargs["command"]
                assert 'wwid "^3600140a1$"' in command and "multipath -a 3600140a2" in command
                assert "serial0" not in command and "--logout" not in command
                assert "multipath /dev/sde\nmultipath /dev/sdf" in command
                assert "/dev/disk/by-path/" not in command, "Multipath must receive the verified kernel device names"
            release.assert_called_once()
        for item in executor.exec.call_args_list:
            success, _, error = run_command(command=["bash", "-n", "-c", item.kwargs["command"]], check=False)
            assert success, error

    @mark.parametrize("failed_stage", ["admit", "reconfigure", "settle", "map0", "map1"])
    def test_multipath_failure_preserves_output_stops_setup_and_releases_sessions(
        self, tmp_path: Path, failed_stage: str
    ) -> None:
        executor = MagicMock()
        executor.exec.return_value = "diagnostics\n0"
        target = IscsiTarget(iqn="iqn.2026-10.test:owned", portal_addresses=("198.18.1.254", "198.18.2.254"))
        hosts = {"executors": {"worker": executor}}
        luns = ([{"wwid": "3600140a1", "device": "sde"}], [{"wwid": "3600140a2", "device": "sdf"}])
        with (
            patch("tests.storage.iscsi_pr.bootstrap.TimeoutSampler", side_effect=[[True], [True], [luns], [True]]),
            patch("tests.storage.iscsi_pr.bootstrap.release_bootstrap_sessions", return_value=None),
            prepared_multipath(hosts=hosts, target=target, lun_wwns=("serial0", "serial1"), observed=set()),
        ):
            command = executor.exec.call_args.kwargs["command"]
        command = command.replace("/etc/multipath.conf", str(tmp_path / "multipath.conf"))
        script = f"""stage_result() {{
    echo "ran:$1"
    if [ "$1" = {quote(failed_stage)} ]; then
        echo "injected failure at $1" >&2
        return 7
    fi
}}
multipath() {{
    if [ "$1" = -a ]; then stage_result admit
    elif [ "${{@: -1}}" = /dev/sde ]; then stage_result map0
    else stage_result map1; fi
}}
multipathd() {{ stage_result reconfigure; }}
udevadm() {{ stage_result settle; }}
export -f stage_result multipath multipathd udevadm
{command}
"""
        success, output, error = run_command(command=["bash", "-c", script], check=False)
        assert success and not error, "The wrapper must return the captured output and real exit code"
        assert output.splitlines()[-1] == "7"
        assert f"injected failure at {failed_stage}" in output
        stages = [line.removeprefix("ran:") for line in output.splitlines() if line.startswith("ran:")]
        expected = ["admit", "admit", "reconfigure", "settle", "map0", "map1"]
        assert stages == expected[: expected.index(failed_stage) + 1], "Setup must stop at the first failing command"
        executor.reset_mock()
        executor.exec.return_value = output.strip()
        observed = set()
        with (
            patch("tests.storage.iscsi_pr.bootstrap.TimeoutSampler", side_effect=[[True], [True], [luns]]) as sampler,
            patch("tests.storage.iscsi_pr.bootstrap.release_bootstrap_sessions", return_value=None) as release,
            raises(AssertionError, match=f"worker, exit code 7:[\\s\\S]*injected failure at {failed_stage}"),
            prepared_multipath(hosts=hosts, target=target, lun_wwns=("serial0", "serial1"), observed=observed),
        ):
            raise AssertionError("Failed multipath setup must not yield")
        assert sampler.call_count == 3, "Map polling must not start after setup fails"
        release.assert_called_once_with(executors=hosts["executors"], target=target, observed=observed)

    def test_partial_login_failure_releases_only_owned_target(self) -> None:
        executor = MagicMock()
        executor.exec.side_effect = ["", "", "", "", "", RuntimeError("login failed")]
        target = IscsiTarget(iqn="iqn.2026-10.test:owned", portal_addresses=("198.18.1.254", "198.18.2.254"))
        hosts = {"workers": [MagicMock()], "executors": {"worker": executor}}
        observed = set()
        with (
            patch("tests.storage.iscsi_pr.bootstrap.release_bootstrap_sessions", return_value=None) as release,
            raises(TimeoutExpiredError, match="login failed") as failure,
            prepared_multipath(hosts=hosts, target=target, lun_wwns=("serial0", "serial1"), observed=observed),
        ):
            raise AssertionError("Failed login must not yield")
        release.assert_called_once_with(executors=hosts["executors"], target=target, observed=observed)
        assert isinstance(failure.value.last_exp, RuntimeError)
        assert executor.exec.call_count == 6, "Host execution errors must fail without another login attempt"
        commands = [item.kwargs["command"] for item in executor.exec.call_args_list]
        assert all(target.iqn in command for command in commands)
        assert not any("discovery" in command for command in commands)

    def test_logout_selects_only_owned_sessions_and_leaves_detach_wait_to_claims(self) -> None:
        executor = MagicMock()
        target = IscsiTarget(iqn="iqn.2026-10.test:owned", portal_addresses=("198.18.1.254", "198.18.2.254"))
        with (
            patch("tests.storage.iscsi_pr.bootstrap.TimeoutSampler", return_value=[True]),
            patch("tests.storage.iscsi_pr.bootstrap.target_sessions", return_value={"worker": ["session12"]}),
            patch("tests.storage.iscsi_pr.utils.wait_for_target_detach") as wait,
        ):
            release_bootstrap_sessions(executors={"worker": executor}, target=target, observed={"3600140a1"})
            wait.assert_not_called()
        command = executor.exec.call_args_list[0].kwargs["command"]
        assert "iscsiadm -m session -r 12 --logout" in command
        assert f'"$session/targetname")" = {target.iqn}' in command
        assert "--logoutall" not in command
        for item in executor.exec.call_args_list:
            success, _, error = run_command(command=["bash", "-n", "-c", item.kwargs["command"]], check=False)
            assert success, error


class TestRetainedLunPaths:
    def test_map_checks_reuse_paths_and_refresh_state(self) -> None:
        luns = ([{"wwid": "owned0"}], [{"wwid": "owned1"}])
        with (
            patch(
                "tests.storage.iscsi_pr.bootstrap.host_multipath_snapshot", side_effect=[{"sample": 1}, {"sample": 2}]
            ) as snapshot,
            patch(
                "tests.storage.iscsi_pr.bootstrap.validate_lun_multipath",
                side_effect=[AssertionError("pending"), "map0", "map1"],
            ) as validate,
            patch("tests.storage.iscsi_pr.bootstrap.target_path") as identify,
        ):
            executor = MagicMock()
            with raises(AssertionError, match="pending"):
                qualified_maps(executor=executor, luns=luns, worker_name="worker-a")
            assert qualified_maps(executor=executor, luns=luns, worker_name="worker-a") == ("map0", "map1")
            assert snapshot.call_count == 2
            assert all(call.kwargs["wwids"] == {"owned0", "owned1"} for call in snapshot.call_args_list)
            assert validate.call_args_list[-2].kwargs["paths"] is luns[0]
            assert validate.call_args_list[-1].kwargs["paths"] is luns[1]
            identify.assert_not_called()
