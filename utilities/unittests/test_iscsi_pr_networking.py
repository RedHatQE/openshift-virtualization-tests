"""Offline checks for guest network probes and owned router lifecycles."""

from base64 import b64decode
from ipaddress import IPv4Address
from json import dumps
from unittest.mock import MagicMock, patch

from pyhelper_utils.shell import run_command
from pytest import mark, raises
from rrmngmnt.ssh import RemoteExecutor
from timeout_sampler import TimeoutExpiredError

from tests.storage.iscsi_pr.conftest import iscsi_pr_guest_nads, iscsi_pr_guest_networking, iscsi_pr_router
from tests.storage.iscsi_pr.networking import (
    EgressEndpoint,
    guest_networks,
    router_cloud_init,
    router_readiness,
    validate_router_networks,
    windows_network_probe_script,
    windows_network_readiness,
    windows_network_setup_script,
)
from utilities.windows import powershell_command

pytestmark = mark.unit


class TestRouterReadiness:
    @mark.parametrize(
        "fault", [None, "address", "prefix", "missing_nic", "management_overlap", "default", "two_defaults"]
    )
    def test_static_interfaces_and_management_routes(self, fault: str | None) -> None:
        networks = guest_networks()
        addresses = [
            {"ifname": network.name, "addr_info": [{"local": str(network.router.ip), "prefixlen": 24}]}
            for network in networks
        ]
        routes = [{"dst": "default", "dev": "uplink"}, {"dst": "10.0.2.0/24", "dev": "uplink"}]
        routes.extend({"dst": str(network.router.network), "dev": network.name} for network in networks)
        if fault == "address":
            addresses[0]["addr_info"][0]["local"] = "192.168.33.253"
        elif fault == "prefix":
            addresses[0]["addr_info"][0]["prefixlen"] = 16
        elif fault == "missing_nic":
            addresses.pop()
        elif fault == "management_overlap":
            routes.append({"dst": "192.168.0.0/16", "dev": "uplink"})
        elif fault == "default":
            routes[0]["dev"] = "guest0"
        elif fault == "two_defaults":
            routes.append({"dst": "default", "dev": "guest1"})
        if fault:
            with raises(AssertionError):
                validate_router_networks(addresses=addresses, routes=routes, networks=networks)
        else:
            validate_router_networks(addresses=addresses, routes=routes, networks=networks)

    def test_cloud_init_retains_management_and_persistent_firewall(self) -> None:
        macs = {"management": "02:00:00:00:00:01", "guest0": "02:00:00:00:00:02", "guest1": "02:00:00:00:00:03"}
        cloud_init = router_cloud_init(networks=guest_networks(), macs=macs)
        interfaces = cloud_init["networkData"]["ethernets"]
        assert interfaces["uplink"]["dhcp4"] and interfaces["uplink"]["match"]["macaddress"] == macs["management"]
        assert all(not interfaces[name]["dhcp4"] for name in ("guest0", "guest1"))
        script = cloud_init["userData"]["write_files"][1]["content"]
        success, _, errors = run_command(command=["bash", "-n", "-c", script], check=False)
        assert success, errors
        assert "--zone=external --add-service=ssh" in script
        assert "--policy=wsfc-egress --add-egress-zone=external" in script
        assert "--zone=external --add-masquerade" in script
        assert "--zone=wsfc-guests --add-forward" in script
        assert "reboot" not in script

    @mark.parametrize("fault", [None, "firewall", "dns", "overlap", "forwarding", "policy_target"])
    def test_endpoint_resolution_and_policy_errors(self, fault: str | None) -> None:
        resolved = "192.168.33.20 STREAM artifact.test" if fault == "overlap" else "192.0.2.80 STREAM artifact.test"
        with (
            patch("tests.storage.iscsi_pr.networking.validate_router_networks"),
            patch(
                "tests.storage.iscsi_pr.networking.run_ssh_commands",
                side_effect=[
                    ["[]", "[]"],
                    RuntimeError("policy failed")
                    if fault == "firewall"
                    else [
                        "0" if fault == "forwarding" else "1",
                        "yes",
                        "DROP" if fault == "policy_target" else "ACCEPT",
                    ],
                    RuntimeError("dns failed") if fault == "dns" else [resolved],
                ],
            ) as execute,
        ):
            if fault:
                with raises(AssertionError if fault in {"overlap", "forwarding", "policy_target"} else RuntimeError):
                    router_readiness(
                        vm=MagicMock(), networks=guest_networks(), artifact_url="https://artifact.test:8443"
                    )
            else:
                assert router_readiness(
                    vm=MagicMock(), networks=guest_networks(), artifact_url="https://artifact.test:8443"
                ) == EgressEndpoint(address=IPv4Address("192.0.2.80"), port=8443)
                guest_stubs = """sysctl() { test "$*" = '-n net.ipv4.ip_forward' && echo 1; }
sudo() { "$@"; }
firewall-cmd() {
    case "$*" in
        '--zone=external --query-masquerade') echo yes;;
        '--permanent --policy=wsfc-egress --get-target') echo ACCEPT;;
        *) return 2;;
    esac
}
"""
                outputs = []
                for command in execute.call_args_list[1].kwargs["commands"]:
                    remote_command = RemoteExecutor.Command(cmd=command, session=MagicMock()).cmd
                    success, output, errors = run_command(
                        command=["bash", "-c", guest_stubs + remote_command], check=False
                    )
                    assert success, errors
                    outputs.append(output.strip())
                assert outputs == ["1", "yes", "ACCEPT"]


class TestWindowsGuestNetworks:
    @mark.parametrize("failure", ["guest0: IPv4 address pending", "guest1: peer probe failed", "TCP egress failed"])
    def test_readiness_retries_pending_checks_and_preserves_timeout_reason(self, failure: str) -> None:
        vm = MagicMock()
        vm.name = "windows-0"
        arguments = {
            "vm": vm,
            "index": 0,
            "networks": guest_networks(),
            "macs": {"guest0": "02:00:00:00:00:01", "guest1": "02:00:00:00:00:02"},
            "egress": EgressEndpoint(address=IPv4Address("192.0.2.80"), port=443),
        }
        pending = dumps({"Ready": False, "Failure": failure})
        with (
            patch(
                "tests.storage.iscsi_pr.networking.TimeoutSampler",
                return_value=iter([pending, pending, dumps({"Ready": True, "Failure": ""})]),
            ),
            patch("tests.storage.iscsi_pr.networking.LOGGER") as logger,
        ):
            assert windows_network_readiness(**arguments) is None
            messages = [call.args[0] for call in logger.info.call_args_list]
            assert sum(f"check pending: {failure}" in message for message in messages) == 1
            assert "expected addresses=" in messages[0] and "checks passed" in messages[-1]
        with (
            patch("tests.storage.iscsi_pr.networking.TimeoutSampler") as sampler,
            raises(AssertionError, match=f"VM windows-0: guest networking timed out: {failure}"),
        ):
            sampler.return_value.__iter__.side_effect = lambda: sampler.return_value
            sampler.return_value.__next__.side_effect = [pending, TimeoutExpiredError(value="network wait")]
            windows_network_readiness(**arguments)

    @mark.parametrize("failure", [TimeoutError("guest: timeout(60)"), RuntimeError("script failed")])
    def test_real_sampler_retries_only_ssh_timeouts(self, failure: Exception) -> None:
        vm = MagicMock()
        vm.name = "windows-1"
        with (
            patch(
                "tests.storage.iscsi_pr.networking.run_powershell",
                side_effect=[failure, dumps({"Ready": True, "Failure": ""})],
                autospec=True,
            ) as execute,
            patch("timeout_sampler.time.sleep"),
        ):
            arguments = {
                "vm": vm,
                "index": 1,
                "networks": guest_networks(),
                "macs": {"guest0": "02:00:00:00:00:01", "guest1": "02:00:00:00:00:02"},
                "egress": EgressEndpoint(address=IPv4Address("192.0.2.80"), port=443),
            }
            if isinstance(failure, TimeoutError):
                assert windows_network_readiness(**arguments) is None
                assert execute.call_count == 2
            else:
                with raises(AssertionError, match="RuntimeError: script failed"):
                    windows_network_readiness(**arguments)
                execute.assert_called_once()

    def test_probe_timeout_is_included_in_final_failure(self) -> None:
        failure = TimeoutExpiredError(value="network wait", last_exp=TimeoutError("guest: timeout(60)"))
        with (
            patch("tests.storage.iscsi_pr.networking.TimeoutSampler", side_effect=failure),
            raises(AssertionError, match=r"TimeoutError: guest: timeout\(60\)"),
        ):
            windows_network_readiness(
                vm=MagicMock(),
                index=1,
                networks=guest_networks(),
                macs={"guest0": "02:00:00:00:00:01", "guest1": "02:00:00:00:00:02"},
                egress=EgressEndpoint(address=IPv4Address("192.0.2.80"), port=443),
            )

    def test_scripts_bind_guest_source_and_limit_configuration_to_owned_nics(self) -> None:
        macs = {"guest0": "02:00:00:00:00:01", "guest1": "02:00:00:00:00:02"}
        endpoint = EgressEndpoint(address=IPv4Address("192.0.2.80"), port=443)
        setup = windows_network_setup_script(index=1, networks=guest_networks(), macs=macs, egress=endpoint)
        assert setup.count("-DefaultGateway") == 1 and "192.168.33.10" in setup and "192.168.55.10" in setup
        assert "Where-Object InterfaceIndex -eq $nic.ifIndex" in setup
        assert "Restart" not in setup and "Disable-NetAdapter" not in setup
        probe = windows_network_probe_script(index=1, networks=guest_networks(), macs=macs, egress=endpoint)
        assert "TcpClient]::new($local)" in probe and "-LocalIPAddress '192.168.33.10'" in probe
        assert "-S '192.168.55.10'" in probe and "TTL=[0-9]+" in probe
        assert b64decode(powershell_command(probe)[-1]).decode("utf-16le") == probe

    @mark.parametrize("index", [0, 1, 2])
    def test_probe_checks_expected_nics_routes_and_both_networks(self, index: int) -> None:
        networks = guest_networks()
        macs = {"guest0": "02:00:00:00:00:01", "guest1": "02:00:00:00:00:02"}
        script = windows_network_probe_script(
            index=index,
            networks=networks,
            macs=macs,
            egress=EgressEndpoint(address=IPv4Address("192.0.2.80"), port=443),
        )
        for network in networks:
            assert f"MacAddress -ne '{macs[network.name].replace(':', '-')}'" in script
            assert f"IPAddress -ne '{network.members[index].ip}'" in script
            assert "PrefixLength -ne 24" in script and "AddressState -ne 'Preferred'" in script
            for destination in (
                network.router.ip,
                *(member.ip for member in network.members if member != network.members[index]),
            ):
                assert f"-S '{network.members[index].ip}' '{destination}'" in script
        assert script.count("ping.exe -4 -n 1") == 6
        assert "$defaults.Count -ne 1" in script and "$defaults.Count -ne 0" in script
        assert ".RegisterThisConnectionsAddress" in script
        assert "$dnsRegistration -ne $true" in script
        assert "$dnsRegistration -ne $false" in script and "$otherDns.Count" in script
        assert "Select-Object IPAddress,PrefixLength,AddressState" in script
        assert "Select-Object NextHop,InterfaceIndex,RouteMetric" in script
        assert "exit=$LASTEXITCODE; reply=" in script
        assert "$route[0].InterfaceIndex -ne $primaryIndex" in script
        assert "$route[0].NextHop -ne '192.168.33.254'" in script
        assert "finally {$tcp.Dispose()}" in script
        assert "@{Ready=$true; Failure=''}" in script

    @mark.parametrize("failure", [RuntimeError("SSH failure"), TimeoutExpiredError(value="network wait")])
    def test_transport_errors_propagate_and_timeout_is_diagnostic(self, failure: object) -> None:
        with patch("tests.storage.iscsi_pr.networking.TimeoutSampler", side_effect=failure):
            with raises(AssertionError if isinstance(failure, TimeoutExpiredError) else RuntimeError):
                windows_network_readiness(
                    vm=MagicMock(),
                    index=0,
                    networks=guest_networks(),
                    macs={"guest0": "02:00:00:00:00:01", "guest1": "02:00:00:00:00:02"},
                    egress=EgressEndpoint(address=IPv4Address("192.0.2.80"), port=443),
                )


class TestNetworkFixtures:
    def test_all_peers_are_configured_before_any_readiness_probe(self) -> None:
        vms = tuple(MagicMock(name=f"vm-{index}") for index in range(3))
        networks = guest_networks()
        macs = ({"guest0": "02:00:00:00:00:01", "guest1": "02:00:00:00:00:02"},) * 3
        events = MagicMock()
        with (
            patch("tests.storage.iscsi_pr.conftest.run_powershell") as setup,
            patch("tests.storage.iscsi_pr.conftest.windows_network_readiness", return_value=None) as readiness,
        ):
            events.attach_mock(setup, "setup")
            events.attach_mock(readiness, "probe")
            result = iscsi_pr_guest_networking.__wrapped__(
                iscsi_pr_windows_vms={"vms": vms, "macs": macs},
                iscsi_pr_router={
                    "vm": MagicMock(),
                    "egress": EgressEndpoint(address=IPv4Address("192.0.2.80"), port=443),
                },
                iscsi_pr_guest_networks=networks,
            )
            assert result["vms"] == vms
        assert [call[0] for call in events.mock_calls] == ["setup", "setup", "setup", "probe", "probe", "probe"]

    def test_partial_nad_creation_unwinds_and_names_are_namespace_isolated(self) -> None:
        first, second = MagicMock(), MagicMock()
        first.__enter__.return_value = first
        first.__exit__.return_value = False
        second.__enter__.side_effect = RuntimeError("second NAD failed")
        namespace = MagicMock()
        namespace.name = "owned"
        with patch("tests.storage.iscsi_pr.conftest.network_nad", side_effect=[first, second]) as create:
            prepared = iscsi_pr_guest_nads.__wrapped__(
                admin_client=MagicMock(), namespace=namespace, iscsi_pr_guest_networks=guest_networks()
            )
            with raises(RuntimeError, match="second NAD failed"):
                next(prepared)
            assert [call.kwargs["network_name"] for call in create.call_args_list] == [
                "owned-iscsi-guest0",
                "owned-iscsi-guest1",
            ]
            assert all(
                call.kwargs["topology"] == "layer2" and "ipam" not in call.kwargs for call in create.call_args_list
            )
        first.__exit__.assert_called_once()

    @mark.parametrize("failure_stage", [None, "boot", "cloud_init", "readiness"])
    def test_router_owns_root_clone_and_is_deleted_on_failure(self, failure_stage: str | None) -> None:
        root = {"metadata": {"name": "router-root"}}
        vm = MagicMock()
        vm.__enter__.return_value = vm
        vm.__exit__.return_value = False
        with (
            patch("tests.storage.iscsi_pr.conftest.VirtualMachineForTests", return_value=vm),
            patch("tests.storage.iscsi_pr.conftest.VirtualMachineClusterPreference"),
            patch(
                "tests.storage.iscsi_pr.conftest.data_volume_template_with_source_ref_dict", return_value=root
            ) as clone,
            patch.dict("tests.storage.iscsi_pr.conftest.py_config", {"default_storage_class": "ci-sc"}),
            patch("tests.storage.iscsi_pr.conftest.get_test_artifact_server_url", return_value="https://artifact.test"),
            patch(
                "tests.storage.iscsi_pr.conftest.running_vm",
                side_effect=RuntimeError("boot") if failure_stage == "boot" else None,
            ),
            patch(
                "tests.storage.iscsi_pr.conftest.wait_for_cloud_init_complete",
                side_effect=RuntimeError("cloud_init") if failure_stage == "cloud_init" else None,
            ) as wait_cloud_init,
            patch(
                "tests.storage.iscsi_pr.conftest.router_readiness",
                side_effect=RuntimeError("readiness") if failure_stage == "readiness" else None,
            ),
        ):
            data_source = MagicMock()
            prepared = iscsi_pr_router.__wrapped__(
                admin_client=MagicMock(),
                namespace=MagicMock(),
                iscsi_pr_hosts={"workers": [MagicMock()]},
                iscsi_pr_guest_networks=guest_networks(),
                iscsi_pr_guest_nads=(MagicMock(), MagicMock()),
                fedora_data_source_scope_module=data_source,
            )
            if failure_stage:
                with raises(RuntimeError, match=failure_stage):
                    next(prepared)
            else:
                assert next(prepared)["vm"] is vm, "The fixture must supply the configured router"
                wait_cloud_init.assert_called_once_with(vm=vm, timeout=600)
                with raises(StopIteration):
                    next(prepared)
        clone.assert_called_once_with(data_source=data_source, storage_class="ci-sc", name="iscsi-router-root")
        assert vm.body["spec"]["dataVolumeTemplates"] == [root], "The router VM must own its private clone"
        assert vm.body["spec"]["template"]["spec"]["networks"] == [{"name": "management", "pod": {}}], (
            "The router must retain its management pod network"
        )
        vm.__exit__.assert_called_once()
