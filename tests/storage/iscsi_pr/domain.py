"""AD/DNS preparation on the existing WSFC guests, with only required reboots."""

from __future__ import annotations

from dataclasses import dataclass, field
from ipaddress import IPv4Address
from json import dumps, loads
from logging import getLogger
from secrets import token_urlsafe
from typing import TYPE_CHECKING
from uuid import uuid4

from paramiko import SSHException
from timeout_sampler import TimeoutExpiredError, TimeoutSampler

from tests.storage.iscsi_pr.scripts import render_powershell_script
from utilities.constants.timeouts import TIMEOUT_5MIN, TIMEOUT_10MIN, TIMEOUT_25MIN, TIMEOUT_30MIN
from utilities.windows import run_powershell

if TYPE_CHECKING:
    from typing import Any

    from tests.storage.iscsi_pr.networking import GuestNetwork
    from utilities.virt import VirtualMachineForTests


LOGGER = getLogger(name=__name__)


@dataclass(frozen=True)
class DomainConfig:
    """An isolated disposable forest; passwords stay in memory and out of repr/logs."""

    name: str
    netbios_name: str = "WSFC"
    computer_names: tuple[str, str, str] = ("wsfc-dc", "wsfc-node1", "wsfc-node2")
    join_user: str = "wsfc-join"
    dsrm_password: str = field(default_factory=lambda: "Aa1!" + token_urlsafe(24), repr=False)
    join_password: str = field(default_factory=lambda: "Aa1!" + token_urlsafe(24), repr=False)


def isolated_domain() -> DomainConfig:
    """Allocate a new forest identity without requiring site credentials or configuration."""
    return DomainConfig(name=f"wsfc-{uuid4().hex[:12]}.test")


def guest_boot_identity(vm: VirtualMachineForTests) -> str:
    """Read a boot identity through authenticated guest management, not VMI Ready."""
    identity = run_powershell(
        ssh_exec=vm.ssh_exec,
        script="(Get-CimInstance Win32_OperatingSystem).LastBootUpTime.ToUniversalTime().Ticks.ToString()",
    ).strip()
    assert identity.isdigit() and int(identity) > 0, f"VM {vm.name}: guest boot timestamp is invalid"
    return identity


def reboot_windows(*, vm: VirtualMachineForTests, login_name: str | None = None) -> None:
    """Schedule one required reboot and wait for a changed boot identity over SSH.

    Args:
        vm: Existing running Windows VM; its launcher is kept alive.
        login_name: Account name required after promotion or domain membership.
    """
    before = guest_boot_identity(vm=vm)
    LOGGER.info(f"VM {vm.name}: scheduling required Windows reboot; previous boot timestamp={before}")
    run_powershell(
        ssh_exec=vm.ssh_exec,
        script="shutdown.exe /r /t 5 /f /d p:2:4; if ($LASTEXITCODE -ne 0) {throw 'Reboot scheduling failed'}",
    )
    if login_name is not None:
        vm.username = login_name
    wait_for_windows_reboot(vm=vm, before=before)


def wait_for_windows_reboot(*, vm: VirtualMachineForTests, before: str) -> None:
    """Wait for a scheduled reboot to restore SSH with a different boot timestamp.

    Args:
        vm: Existing Windows VM using the account required after reboot.
        before: Boot timestamp captured before the operation scheduling the reboot.
    """
    try:
        for identity in TimeoutSampler(
            wait_timeout=TIMEOUT_30MIN,
            sleep=15,
            func=guest_boot_identity,
            vm=vm,
            exceptions_dict={SSHException: [], ConnectionError: [], EOFError: [], TimeoutError: []},
            print_func_args=False,
        ):
            if identity and identity != before:
                LOGGER.info(f"VM {vm.name}: authenticated access restored after reboot; new boot timestamp={identity}")
                return
    except TimeoutExpiredError as error:
        raise AssertionError(
            f"VM {vm.name}: required reboot did not restore authenticated guest access; "
            f"previous boot timestamp={before}; last SSH exception: {error.last_exp}"
        ) from error


def ssh_domain_firewall_script() -> str:
    """Return a script allowing the running SSH server on the Domain firewall profile."""
    return """
$program=(Get-CimInstance Win32_Service -Filter "Name='sshd'").PathName.Trim('"')
$rules=@(Get-NetFirewallRule -PolicyStore ActiveStore | Where-Object {
 $_.Enabled -eq 'True' -and $_.Direction -eq 'Inbound' -and $_.Action -eq 'Allow'
} | Where-Object {($_ | Get-NetFirewallApplicationFilter).Program -eq $program})
if ($rules.Count -ne 1) {throw 'Expected one inbound SSH allow rule for the running executable'}
$rule=$rules[0]
if (($rule | Get-NetFirewallPortFilter).LocalPort -ne '22') {throw 'Expected SSH firewall port 22'}
if ($rule.Profile -ne 'Any') {
 Set-NetFirewallRule -Name $rule.Name -Profile ([int]$rule.Profile -bor 1)
}
"""


def dc_roles_script(domain: DomainConfig) -> str:
    """Install roles and rename before promotion, combining any resulting reboot."""
    return ssh_domain_firewall_script() + render_powershell_script(name="install_dc_roles.ps1", domain=domain)


def promotion_script(domain: DomainConfig) -> str:
    """Promote with normal prerequisite checks and an explicit subsequent reboot."""
    return f"""
$payload=ConvertFrom-Json $InputData
$dsrm=ConvertTo-SecureString $payload.password -AsPlainText -Force
Import-Module ADDSDeployment
$result=Install-ADDSForest -DomainName '{domain.name}' -DomainNetbiosName '{domain.netbios_name}' `
 -DomainMode WinThreshold -ForestMode WinThreshold -InstallDns -CreateDnsDelegation:$false `
 -SafeModeAdministratorPassword $dsrm -NoRebootOnCompletion -Force
@{{Status=$result.Status.ToString(); Context=[string]$result.Context; RebootRequired=[bool]$result.RebootRequired}} | ConvertTo-Json -Compress
"""


def dns_client_script(*, domain: DomainConfig, network: GuestNetwork) -> str:
    """Use only the domain DNS server, keeping other NICs out of domain registration."""
    return f"""
Get-NetAdapter | ForEach-Object {{
 Set-DnsClientServerAddress -InterfaceIndex $_.ifIndex -ServerAddresses '{network.members[0].ip}'
 Set-DnsClient -InterfaceIndex $_.ifIndex -RegisterThisConnectionsAddress ($_.Name -eq '{network.name}')
}}
Set-DnsClient -InterfaceAlias '{network.name}' -ConnectionSpecificSuffix '{domain.name}'
Clear-DnsClientCache
"""


def dc_dns_script(*, domain: DomainConfig, network: GuestNetwork, forwarders: tuple[str, ...]) -> str:
    """Restrict DC publication and reconcile only address records in the owned forest."""
    address = network.members[0].ip
    assert forwarders, "CI management DNS forwarders are missing"
    values = ",".join(f"'{IPv4Address(address=value)}'" for value in forwarders)
    return dns_client_script(domain=domain, network=network) + render_powershell_script(
        name="configure_dc_dns.ps1", domain=domain, network=network, address=address, values=values
    )


def join_account_script(domain: DomainConfig) -> str:
    """Create an ordinary forest user for two fresh machine joins, without Domain Admins."""
    return f"""
$payload=ConvertFrom-Json $InputData
$password=ConvertTo-SecureString $payload.password -AsPlainText -Force
$domain=Get-ADDomain
$quota=(Get-ADObject -Identity $domain.DistinguishedName -Properties ms-DS-MachineAccountQuota).'ms-DS-MachineAccountQuota'
if ($quota -lt 2) {{throw 'Forest policy does not permit the two machine joins'}}
New-ADUser -Name '{domain.join_user}' -SamAccountName '{domain.join_user}' `
 -UserPrincipalName '{domain.join_user}@{domain.name}' -AccountPassword $password -Enabled $true
"""


def member_join_script(*, domain: DomainConfig, network: GuestNetwork, index: int) -> str:
    """Rename, join and schedule one reboot in the same authenticated session."""
    return (
        ssh_domain_firewall_script()
        + dns_client_script(domain=domain, network=network)
        + render_powershell_script(name="join_domain.ps1", domain=domain, index=index)
    )


def domain_probe_script(*, domain: DomainConfig, network: GuestNetwork, index: int) -> str:
    """Check membership, DNS and services/trust; return readiness, failure, domain and role."""
    return render_powershell_script(
        name="probe_domain.ps1",
        domain=domain,
        network=network,
        index=index,
        dc_name=f"{domain.computer_names[0]}.{domain.name}",
    )


def domain_readiness(
    *, vm: VirtualMachineForTests, domain: DomainConfig, network: GuestNetwork, index: int
) -> dict[str, Any]:
    """Wait for domain role, intended DNS and trust without introducing another reboot."""
    LOGGER.info(
        f"VM {vm.name}: checking AD membership, services/trust and DNS; "
        f"expected computer={domain.computer_names[index]}, domain={domain.name}, "
        f"role={5 if index == 0 else 3}, DNS={network.members[0].ip}"
    )
    script = domain_probe_script(domain=domain, network=network, index=index)
    last_failure = "No domain probe completed"
    try:
        for output in TimeoutSampler(
            wait_timeout=TIMEOUT_10MIN,
            sleep=10,
            func=run_powershell,
            ssh_exec=vm.ssh_exec,
            script=script,
            exceptions_dict={},
            print_func_args=False,
        ):
            result = loads(s=output)
            if result["Ready"]:
                LOGGER.info(f"VM {vm.name}: AD membership, services/trust and DNS checks passed")
                return result
            if result["Failure"] != last_failure:
                LOGGER.info(f"VM {vm.name}: domain check pending: {result['Failure']}")
            last_failure = result["Failure"]
    except TimeoutExpiredError as error:
        if error.last_exp is not None:
            raise AssertionError(
                f"VM {vm.name}: domain readiness probe failed: {type(error.last_exp).__name__}: {error.last_exp}"
            ) from error
        raise AssertionError(f"VM {vm.name}: domain readiness timed out: {last_failure}") from error
    raise AssertionError(f"VM {vm.name}: domain readiness ended without success: {last_failure}")


def wait_for_dc_directory(*, vm: VirtualMachineForTests, domain: DomainConfig) -> None:
    """Wait for services, directory RPC and AD DNS zones before configuring DNS."""
    LOGGER.info(
        f"VM {vm.name}: waiting for promoted AD services, local directory access and DNS zones for {domain.name}"
    )
    script = render_powershell_script(name="probe_dc_directory.ps1", domain=domain)
    last_failure = "No directory probe completed"
    try:
        for output in TimeoutSampler(
            wait_timeout=TIMEOUT_10MIN,
            sleep=10,
            func=run_powershell,
            ssh_exec=vm.ssh_exec,
            script=script,
            exceptions_dict={},
            print_func_args=False,
        ):
            result = loads(s=output)
            if result["Ready"]:
                LOGGER.info(f"VM {vm.name}: promoted AD services, directory and DNS zones are ready")
                return
            if result["Failure"] != last_failure:
                LOGGER.info(f"VM {vm.name}: promoted directory check pending: {result['Failure']}")
            last_failure = result["Failure"]
    except TimeoutExpiredError as error:
        if error.last_exp is not None:
            raise AssertionError(
                f"VM {vm.name}: promoted directory/DNS probe failed: {type(error.last_exp).__name__}: {error.last_exp}"
            ) from error
        raise AssertionError(
            f"VM {vm.name}: promoted directory/DNS services did not become ready: {last_failure}"
        ) from error


def prepare_domain_controller(
    *, vm: VirtualMachineForTests, domain: DomainConfig, network: GuestNetwork
) -> dict[str, Any]:
    """Install/promote the existing DC, qualify its DNS and create an ordinary join user."""
    original_login = vm.username.split("\\")[-1].split("@")[0]
    LOGGER.info(f"VM {vm.name}: installing AD DS/DNS roles and setting computer name {domain.computer_names[0]}")
    roles = loads(s=run_powershell(ssh_exec=vm.ssh_exec, script=dc_roles_script(domain=domain), timeout=TIMEOUT_25MIN))
    LOGGER.info(
        f"VM {vm.name}: role installation completed; restart required={roles['Restart']}, DNS forwarders={roles['Forwarders']}"
    )
    forwarders = tuple(str(IPv4Address(address=value)) for value in roles["Forwarders"])
    assert forwarders, "CI management DNS forwarders are missing"
    if roles["Restart"]:
        reboot_windows(vm=vm)
    LOGGER.info(f"VM {vm.name}: configuring DC DNS client at {network.members[0].ip} before promotion")
    run_powershell(ssh_exec=vm.ssh_exec, script=dns_client_script(domain=domain, network=network))
    LOGGER.info(f"VM {vm.name}: promoting domain controller for forest {domain.name}")
    result = loads(
        s=run_powershell(
            ssh_exec=vm.ssh_exec,
            script=promotion_script(domain=domain),
            input_data=dumps({"password": domain.dsrm_password}),
            timeout=TIMEOUT_25MIN,
        )
    )
    LOGGER.info(
        f"VM {vm.name}: DC promotion returned status={result['Status']}, "
        f"context={result['Context']}, reboot required={result['RebootRequired']}"
    )
    assert result["Status"] == "Success", (
        f"VM {vm.name}: DC promotion failed: status={result['Status']}, context={result['Context']}"
    )
    reboot_windows(vm=vm, login_name=f"{domain.netbios_name}\\{original_login}")
    wait_for_dc_directory(vm=vm, domain=domain)
    LOGGER.info(f"VM {vm.name}: configuring domain DNS at {network.members[0].ip} and AD firewall rules")
    run_powershell(
        ssh_exec=vm.ssh_exec,
        script=dc_dns_script(domain=domain, network=network, forwarders=forwarders),
        timeout=TIMEOUT_5MIN,
    )
    evidence = domain_readiness(vm=vm, domain=domain, network=network, index=0)
    LOGGER.info(f"VM {vm.name}: creating ordinary join account and checking quota for two member joins")
    run_powershell(
        ssh_exec=vm.ssh_exec,
        script=join_account_script(domain=domain),
        input_data=dumps({"password": domain.join_password}),
    )
    LOGGER.info(f"VM {vm.name}: domain controller preparation completed for {domain.name}")
    return evidence


def prepare_domain_member(
    *, vm: VirtualMachineForTests, domain: DomainConfig, network: GuestNetwork, index: int
) -> dict[str, Any]:
    """Join/rename one existing member and prove its trust after the required reboot."""
    original_login = vm.username.split("\\")[-1].split("@")[0]
    before = guest_boot_identity(vm=vm)
    LOGGER.info(f"VM {vm.name}: configuring DNS and joining {domain.name} as {domain.computer_names[index]}")
    run_powershell(
        ssh_exec=vm.ssh_exec,
        script=member_join_script(domain=domain, network=network, index=index),
        input_data=dumps({"password": domain.join_password}),
        timeout=TIMEOUT_10MIN,
    )
    LOGGER.info(f"VM {vm.name}: domain join completed and reboot scheduled; waiting for authenticated access")
    vm.username = f"{domain.computer_names[index]}\\{original_login}"
    wait_for_windows_reboot(vm=vm, before=before)
    LOGGER.info(f"VM {vm.name}: configuring domain time hierarchy and registering DNS")
    run_powershell(
        ssh_exec=vm.ssh_exec,
        script="""
w32tm.exe /config /syncfromflags:domhier /update
if ($LASTEXITCODE -ne 0) {throw 'Domain time configuration failed'}
Restart-Service W32Time
Register-DnsClient
""",
    )
    return domain_readiness(vm=vm, domain=domain, network=network, index=index)
