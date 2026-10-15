"""Offline checks for domain readiness, minimal reboot ordering and credentials."""

from json import dumps, loads
from unittest.mock import MagicMock, patch

from paramiko import SSHException
from pytest import mark, raises
from timeout_sampler import TimeoutExpiredError

from tests.storage.iscsi_pr.conftest import iscsi_pr_environment
from tests.storage.iscsi_pr.domain import (
    DomainConfig,
    dc_dns_script,
    dc_roles_script,
    dns_client_script,
    domain_probe_script,
    domain_readiness,
    guest_boot_identity,
    isolated_domain,
    member_join_script,
    prepare_domain_controller,
    prepare_domain_member,
    promotion_script,
    reboot_windows,
    wait_for_dc_directory,
)
from tests.storage.iscsi_pr.networking import guest_networks

pytestmark = mark.unit


class TestDomainReadiness:
    @mark.parametrize("index", [0, 1, 2])
    def test_probe_checks_identity_and_dns_with_role_specific_services(self, index: int) -> None:
        domain = DomainConfig(name="owned.test")
        script = domain_probe_script(domain=domain, network=guest_networks()[0], index=index)
        assert f"$system.Name -ne '{domain.computer_names[index]}'" in script
        assert "$system.PartOfDomain" in script and "$system.Domain -ne 'owned.test'" in script
        assert f"$result.Role -ne {5 if index == 0 else 3}" in script
        assert script.count("Resolve-DnsName 'wsfc-dc.owned.test' -Type A") == 2
        assert "$addresses.Count -ne 1" in script and "$defaultAddresses.Count -ne 1" in script
        assert script.count("[0] -ne '192.168.33.1'") == 2
        assert "_ldap._tcp.dc._msdcs.owned.test" in script
        assert "$srv[0].NameTarget.TrimEnd('.') -ne 'wsfc-dc.owned.test'" in script
        assert "$srv[0].Port -ne 389" in script
        assert "-notin @(" in script and ")) {throw}" in script
        for error_id in (
            "DNS_ERROR_RCODE_NAME_ERROR",
            "DNS_INFO_NO_RECORDS",
            "DNS_ERROR_RCODE_SERVER_FAILURE",
            "ERROR_TIMEOUT",
        ):
            assert error_id in script
        if index == 0:
            assert "Get-Service NTDS,DNS,Netlogon" in script and "SYSVOL" in script and "NETLOGON" in script
            assert "Test-ComputerSecureChannel" not in script
        else:
            assert "Test-ComputerSecureChannel -Server 'wsfc-dc.owned.test'" in script
            assert "Get-Service NTDS,DNS,Netlogon" not in script

    @mark.parametrize(
        "failure",
        [
            "Guest is not in the owned domain",
            "Member secure channel is not ready",
            "Domain DNS records pending: ERROR_TIMEOUT",
        ],
    )
    def test_readiness_retries_and_returns_domain_role_or_last_failure(self, failure: str) -> None:
        vm = MagicMock()
        vm.name = "windows-1"
        arguments = {"vm": vm, "domain": DomainConfig(name="owned.test"), "network": guest_networks()[0], "index": 1}
        pending = dumps({"Ready": False, "Failure": failure, "Domain": "owned.test", "Role": 3})
        ready = {"Ready": True, "Failure": "", "Domain": "owned.test", "Role": 3}
        with (
            patch("tests.storage.iscsi_pr.domain.TimeoutSampler", return_value=iter([pending, pending, dumps(ready)])),
            patch("tests.storage.iscsi_pr.domain.LOGGER") as logger,
        ):
            assert domain_readiness(**arguments) == ready
            messages = [call.args[0] for call in logger.info.call_args_list]
            assert sum(f"check pending: {failure}" in message for message in messages) == 1
            assert "expected computer=wsfc-node1" in messages[0] and "checks passed" in messages[-1]
            assert all(arguments["domain"].dsrm_password not in message for message in messages)
            assert all(arguments["domain"].join_password not in message for message in messages)
        with (
            patch("tests.storage.iscsi_pr.domain.TimeoutSampler") as sampler,
            raises(AssertionError, match=f"VM windows-1: domain readiness timed out: {failure}"),
        ):
            sampler.return_value.__iter__.side_effect = lambda: sampler.return_value
            sampler.return_value.__next__.side_effect = [pending, TimeoutExpiredError(value="AD wait")]
            domain_readiness(**arguments)

    @mark.parametrize("probe", ["domain", "directory"])
    @mark.parametrize("failure", [RuntimeError("PowerShell failure"), SSHException("SSH unavailable")])
    def test_execution_errors_are_not_retried(self, probe: str, failure: Exception) -> None:
        vm = MagicMock()
        vm.name = "windows-1"
        domain = DomainConfig(name="owned.test")
        with (
            patch("tests.storage.iscsi_pr.domain.run_powershell", autospec=True, side_effect=failure) as command,
            raises(AssertionError, match=f"probe failed: {type(failure).__name__}: {failure}") as error,
        ):
            if probe == "domain":
                domain_readiness(vm=vm, domain=domain, network=guest_networks()[0], index=1)
            else:
                wait_for_dc_directory(vm=vm, domain=domain)
        command.assert_called_once()
        assert isinstance(error.value.__cause__, TimeoutExpiredError)
        assert error.value.__cause__.last_exp is failure
        assert "timed out" not in str(error.value)


class TestDomainPreparation:
    def test_generated_forest_and_scripts_do_not_embed_passwords(self) -> None:
        first, second = isolated_domain(), isolated_domain()
        assert first.name != second.name and first.dsrm_password != first.join_password
        assert first.dsrm_password not in repr(first) and first.join_password not in repr(first)
        scripts = [
            dc_roles_script(domain=first),
            promotion_script(domain=first),
            dc_dns_script(domain=first, network=guest_networks()[0], forwarders=("10.0.2.3",)),
            member_join_script(domain=first, network=guest_networks()[0], index=1),
        ]
        assert all(first.dsrm_password not in script and first.join_password not in script for script in scripts)
        assert "-SkipPreChecks" not in scripts[1] and "WinThreshold" in scripts[1]
        assert "-NoRebootOnCompletion" in scripts[1] and "-CreateDnsDelegation:$false" in scripts[1]
        assert "$result.Status.ToString()" in scripts[1] and "$result.Context" in scripts[1]
        assert "$result.ExitCode" not in scripts[1]
        assert "Rename-Computer -NewName 'wsfc-node1' -Force" in scripts[3]
        assert scripts[3].index("Rename-Computer") < scripts[3].index("Add-Computer")
        assert "-Options JoinWithNewName,AccountCreate" in scripts[3] and "-Restart" not in scripts[3]
        assert scripts[3].index("Domain join failed") < scripts[3].index("shutdown.exe /r /t 5 /f")
        assert "Reboot scheduling failed" in scripts[3]
        assert "-NewName" not in scripts[3].split("$result=Add-Computer", maxsplit=1)[1]
        for script in (scripts[0], scripts[3]):
            assert "Win32_Service -Filter \"Name='sshd'\"" in script
            assert "Get-NetFirewallApplicationFilter).Program -eq $program" in script
            assert (
                "if ($rule.Profile -ne 'Any') {\n"
                " Set-NetFirewallRule -Name $rule.Name -Profile ([int]$rule.Profile -bor 1)\n}"
            ) in script
            assert "System32" not in script and "Program Files" not in script
        assert scripts[0].index("Set-NetFirewallRule") < scripts[0].index("Install-WindowsFeature")
        assert scripts[3].index("Set-NetFirewallRule") < scripts[3].index("Add-Computer")
        assert "ListeningIPAddress=@('192.168.33.1')" in scripts[2]
        assert "DnsAvoidRegisterRecords" in scripts[2] and "-UseRootHint $false" in scripts[2]
        assert "10.0.2.3" in scripts[2] and "Remove-DnsServerResourceRecord" in scripts[2]
        assert "-Server 'wsfc-dc." in domain_probe_script(domain=first, network=guest_networks()[0], index=1)
        assert "Test-ComputerSecureChannel" not in domain_probe_script(
            domain=first, network=guest_networks()[0], index=0
        )

    @mark.parametrize("rename_required", [False, True])
    @mark.parametrize("promotion_status", ["Success", "Error", ""])
    def test_dc_only_reboots_for_rename_roles_and_successful_promotion(
        self, rename_required: bool, promotion_status: str
    ) -> None:
        vm = MagicMock()
        vm.username = "Administrator"
        domain = DomainConfig(name="owned.test")
        events = MagicMock()
        with (
            patch(
                "tests.storage.iscsi_pr.domain.run_powershell",
                side_effect=[
                    dumps({"Restart": rename_required, "Forwarders": ["10.0.2.3"]}),
                    "",
                    dumps({"Status": promotion_status, "Context": "DCPromo.General.3", "RebootRequired": True}),
                    "",
                    "",
                ],
            ) as execute,
            patch("tests.storage.iscsi_pr.domain.reboot_windows") as reboot,
            patch("tests.storage.iscsi_pr.domain.wait_for_dc_directory") as directory,
            patch("tests.storage.iscsi_pr.domain.domain_readiness", return_value={"domain": "ready"}) as readiness,
        ):
            events.attach_mock(execute, "execute")
            events.attach_mock(reboot, "reboot")
            events.attach_mock(directory, "directory")
            events.attach_mock(readiness, "ready")
            if promotion_status != "Success":
                with raises(AssertionError, match="promotion failed"):
                    prepare_domain_controller(vm=vm, domain=domain, network=guest_networks()[0])
                assert reboot.call_count == int(rename_required)
                directory.assert_not_called()
                readiness.assert_not_called()
            else:
                assert prepare_domain_controller(vm=vm, domain=domain, network=guest_networks()[0]) == {
                    "domain": "ready"
                }
                assert reboot.call_count == 1 + int(rename_required)
                assert reboot.call_args.kwargs["login_name"] == "WSFC\\Administrator"
                names = [call[0] for call in events.mock_calls]
                assert names.index("directory") < names.index("ready")
                assert "Domain Admins" not in execute.call_args.kwargs["script"]
                assert loads(execute.call_args.kwargs["input_data"])["password"] == domain.join_password
                assert domain.dsrm_password not in execute.call_args_list[2].kwargs["script"]
        assert execute.call_args_list[1].kwargs["script"] == dns_client_script(
            domain=domain, network=guest_networks()[0]
        )
        assert execute.call_args_list[2].kwargs["script"] == promotion_script(domain=domain)
        names = [call[0] for call in events.mock_calls]
        prefix = ["execute", *(["reboot"] if rename_required else []), "execute", "execute"]
        assert names[: len(prefix)] == prefix

    @mark.parametrize("join_fails", [False, True])
    def test_member_has_one_combined_join_rename_reboot(self, join_fails: bool) -> None:
        vm = MagicMock()
        vm.username = "Administrator"
        events = MagicMock()
        with (
            patch("tests.storage.iscsi_pr.domain.guest_boot_identity", return_value="100") as boot,
            patch(
                "tests.storage.iscsi_pr.domain.run_powershell",
                side_effect=RuntimeError("join failed") if join_fails else None,
            ) as execute,
            patch("tests.storage.iscsi_pr.domain.wait_for_windows_reboot") as reboot,
            patch("tests.storage.iscsi_pr.domain.domain_readiness", return_value={}) as ready,
        ):
            events.attach_mock(boot, "boot")
            events.attach_mock(execute, "execute")
            events.attach_mock(reboot, "wait")
            if join_fails:
                with raises(RuntimeError, match="join failed"):
                    prepare_domain_member(
                        vm=vm, domain=DomainConfig(name="owned.test"), network=guest_networks()[0], index=1
                    )
                reboot.assert_not_called()
                ready.assert_not_called()
            else:
                assert (
                    prepare_domain_member(
                        vm=vm, domain=DomainConfig(name="owned.test"), network=guest_networks()[0], index=1
                    )
                    == {}
                )
                reboot.assert_called_once_with(vm=vm, before="100")
                assert vm.username == "wsfc-node1\\Administrator"
            assert [call[0] for call in events.mock_calls][:2] == ["boot", "execute"]
            boot.assert_called_once_with(vm=vm)

    def test_reboot_waits_for_new_boot_and_new_login(self) -> None:
        vm = MagicMock()
        vm.username = "Administrator"
        with (
            patch("tests.storage.iscsi_pr.domain.guest_boot_identity", return_value="100"),
            patch("tests.storage.iscsi_pr.domain.run_powershell") as execute,
            patch("tests.storage.iscsi_pr.domain.TimeoutSampler", return_value=iter(["100", "200"])) as sampler,
        ):
            reboot_windows(vm=vm, login_name="WSFC\\Administrator")
        assert vm.username == "WSFC\\Administrator"
        assert "/r /t 5" in execute.call_args.kwargs["script"]
        assert SSHException in sampler.call_args.kwargs["exceptions_dict"]
        assert RuntimeError not in sampler.call_args.kwargs["exceptions_dict"]
        assert not sampler.call_args.kwargs["print_func_args"]
        assert sampler.call_args.kwargs["wait_timeout"] == 1800

    def test_reboot_timeout_preserves_original_failure(self) -> None:
        vm = MagicMock()
        vm.name = "windows-dc"
        vm.username = "Administrator"
        failure = TimeoutExpiredError(value="reboot wait", last_exp=SSHException("Error reading SSH protocol banner"))
        with (
            patch("tests.storage.iscsi_pr.domain.guest_boot_identity", return_value="100"),
            patch("tests.storage.iscsi_pr.domain.run_powershell") as execute,
            patch("tests.storage.iscsi_pr.domain.TimeoutSampler", side_effect=failure),
            raises(AssertionError, match="last SSH exception: Error reading SSH protocol banner") as error,
        ):
            reboot_windows(vm=vm, login_name="WSFC\\Administrator")
        assert error.value.__cause__ is failure
        execute.assert_called_once()

    @mark.parametrize("failure", ["NTDS is stopped", "Local AD directory RPC is not ready", "DNS zones missing"])
    def test_directory_waits_without_repeating_promotion(self, failure: str) -> None:
        vm = MagicMock()
        vm.name = "windows-dc"
        pending = dumps({"Ready": False, "Failure": failure})
        ready = dumps({"Ready": True, "Failure": ""})
        with (
            patch(
                "tests.storage.iscsi_pr.domain.TimeoutSampler", return_value=iter([pending, pending, ready])
            ) as sampler,
            patch("tests.storage.iscsi_pr.domain.LOGGER") as logger,
        ):
            wait_for_dc_directory(vm=vm, domain=DomainConfig(name="owned.test"))
            assert sum(f"check pending: {failure}" in call.args[0] for call in logger.info.call_args_list) == 1
        assert "Get-ADDomain" in sampler.call_args.kwargs["script"]
        assert "Install-ADDSForest" not in sampler.call_args.kwargs["script"]
        assert "Select-Object Name,Status" in sampler.call_args.kwargs["script"]
        assert "observed $($zones -join ',')" in sampler.call_args.kwargs["script"]
        with (
            patch("tests.storage.iscsi_pr.domain.TimeoutSampler") as sampler,
            raises(
                AssertionError, match=f"VM windows-dc: promoted directory/DNS services did not become ready: {failure}"
            ),
        ):
            sampler.return_value.__iter__.side_effect = lambda: sampler.return_value
            sampler.return_value.__next__.side_effect = [pending, TimeoutExpiredError(value="directory wait")]
            wait_for_dc_directory(vm=vm, domain=DomainConfig(name="owned.test"))

    def test_environment_uses_existing_guests_and_checks_hco(self) -> None:
        vms = tuple(MagicMock() for _ in range(3))
        environment = {"vms": vms, "networks": guest_networks(), "roots": (), "guest_luns": ()}
        with (
            patch("tests.storage.iscsi_pr.conftest.prepare_domain_controller", return_value={"Role": 5}) as dc,
            patch("tests.storage.iscsi_pr.conftest.prepare_domain_member", return_value={"Role": 3}) as member,
        ):
            hco = MagicMock()
            result = iscsi_pr_environment.__wrapped__(
                iscsi_pr_guest_networking=environment, iscsi_pr_persistent_reservations=hco
            )
            assert result["vms"] is vms
            assert [sample["Role"] for sample in result["members"]] == [5, 3, 3]
            assert dc.call_args.kwargs["vm"] is vms[0]
            assert [call.kwargs["vm"] for call in member.call_args_list] == list(vms[1:])
            hco.instance.spec.storage.persistentReservationConfiguration.enabled = False
            with raises(AssertionError, match="reservations"):
                iscsi_pr_environment.__wrapped__(
                    iscsi_pr_guest_networking=environment, iscsi_pr_persistent_reservations=hco
                )


class TestBootIdentity:
    @mark.parametrize("identity", ["", "not-a-timestamp", "0", "123456789"])
    def test_boot_identity_requires_an_actual_timestamp(self, identity: str) -> None:
        with patch("tests.storage.iscsi_pr.domain.run_powershell", return_value=identity):
            if identity == "123456789":
                assert guest_boot_identity(vm=MagicMock()) == identity
            else:
                with raises(AssertionError, match="timestamp"):
                    guest_boot_identity(vm=MagicMock())
