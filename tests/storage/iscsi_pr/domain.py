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
    return (
        ssh_domain_firewall_script()
        + f"""
$system=Get-CimInstance Win32_ComputerSystem
if ($system.PartOfDomain) {{throw 'Expected a fresh workgroup DC image'}}
$result=Install-WindowsFeature AD-Domain-Services,DNS -IncludeManagementTools
if (-not $result.Success) {{throw 'AD DS/DNS role installation failed'}}
$rename=$system.Name -ne '{domain.computer_names[0]}'
if ($rename) {{Rename-Computer -NewName '{domain.computer_names[0]}' -Force}}
$forwarders=@(Get-NetAdapter | Where-Object Name -notin @('guest0','guest1') | ForEach-Object {{
 (Get-DnsClientServerAddress -InterfaceIndex $_.ifIndex -AddressFamily IPv4).ServerAddresses
}} | Where-Object {{$_ -ne '0.0.0.0' -and $_ -notlike '127.*'}} | Select-Object -Unique)
@{{Restart=($rename -or $result.RestartNeeded.ToString() -eq 'Yes'); Forwarders=$forwarders}} | ConvertTo-Json -Compress
"""
    )


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
    return (
        dns_client_script(domain=domain, network=network)
        + f"""
$forwarders=@({values})
Import-Module DnsServer
Set-DnsServerForwarder -IPAddress $forwarders -UseRootHint $false
$settings=Get-DnsServerSetting -All
$settings.ListeningIPAddress=@('{address}')
Set-DnsServerSetting -InputObject $settings
New-ItemProperty -Path 'HKLM:\\SYSTEM\\CurrentControlSet\\Services\\DNS\\Parameters' `
 -Name PublishAddresses -PropertyType String -Value '{address}' -Force | Out-Null
New-ItemProperty -Path 'HKLM:\\SYSTEM\\CurrentControlSet\\Services\\Netlogon\\Parameters' `
 -Name DnsAvoidRegisterRecords -PropertyType MultiString -Value @('LdapIpAddress','GcIpAddress') -Force | Out-Null
Restart-Service DNS
Restart-Service Netlogon
$updates=@(
 @{{Zone='{domain.name}'; Name='{domain.computer_names[0]}'}},
 @{{Zone='{domain.name}'; Name='@'}},
 @{{Zone='_msdcs.{domain.name}'; Name='gc'}}
)
foreach ($update in $updates) {{
 $records=@(Get-DnsServerResourceRecord -ZoneName $update.Zone | Where-Object HostName -eq $update.Name)
 $records | Where-Object {{ $_.RecordType -eq 'AAAA' -or
  ($_.RecordType -eq 'A' -and $_.RecordData.IPv4Address.IPAddressToString -ne '{address}') }} |
  ForEach-Object {{Remove-DnsServerResourceRecord -ZoneName $update.Zone -InputObject $_ -Force}}
 if (-not ($records | Where-Object {{ $_.RecordType -eq 'A' -and
  $_.RecordData.IPv4Address.IPAddressToString -eq '{address}' }})) {{
  Add-DnsServerResourceRecordA -ZoneName $update.Zone -Name $update.Name -IPv4Address '{address}'
 }}
}}
nltest.exe /dsregdns
if ($LASTEXITCODE -ne 0) {{throw 'DC locator registration failed'}}
Register-DnsClient
New-NetFirewallRule -Name 'CNV-70031-domain-tcp' -DisplayName 'CNV-70031 domain TCP' `
 -Direction Inbound -Action Allow -Profile Any -InterfaceAlias '{network.name}' `
 -RemoteAddress '{network.router.network}' -Protocol TCP -LocalPort 53,88,135,389,445,464,636,3268,3269,'49152-65535' | Out-Null
New-NetFirewallRule -Name 'CNV-70031-domain-udp' -DisplayName 'CNV-70031 domain UDP' `
 -Direction Inbound -Action Allow -Profile Any -InterfaceAlias '{network.name}' `
 -RemoteAddress '{network.router.network}' -Protocol UDP -LocalPort 53,88,123,389,464 | Out-Null
"""
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
        + f"""
$system=Get-CimInstance Win32_ComputerSystem
if ($system.PartOfDomain) {{throw 'Expected a fresh workgroup member image'}}
$payload=ConvertFrom-Json $InputData
$password=ConvertTo-SecureString $payload.password -AsPlainText -Force
$credential=[System.Management.Automation.PSCredential]::new('{domain.join_user}@{domain.name}',$password)
Rename-Computer -NewName '{domain.computer_names[index]}' -Force
$result=Add-Computer -DomainName '{domain.name}' -Server '{domain.computer_names[0]}.{domain.name}' `
 -Credential $credential -Options JoinWithNewName,AccountCreate -PassThru -Force
if (-not $result.HasSucceeded) {{throw 'Domain join failed'}}
shutdown.exe /r /t 5 /f /d p:2:4
if ($LASTEXITCODE -ne 0) {{throw 'Reboot scheduling failed'}}
"""
    )


def domain_probe_script(*, domain: DomainConfig, network: GuestNetwork, index: int) -> str:
    """Check membership, DNS and services/trust; return readiness, failure, domain and role."""
    dc_name = f"{domain.computer_names[0]}.{domain.name}"
    script = f"""
$ErrorActionPreference='Stop'
& {{
$system=Get-CimInstance Win32_ComputerSystem
$result=@{{Domain=$system.Domain; Role=[int]$system.DomainRole; Ready=$false; Failure=''}}
if ($system.Name -ne '{domain.computer_names[index]}') {{$result.Failure="Expected computer name {domain.computer_names[index]}; observed $($system.Name)"; return $result}}
if (-not $system.PartOfDomain -or $system.Domain -ne '{domain.name}') {{$result.Failure="Expected domain {domain.name}; observed $($system.Domain), PartOfDomain=$($system.PartOfDomain)"; return $result}}
if ($result.Role -ne {5 if index == 0 else 3}) {{$result.Failure="Expected domain role {5 if index == 0 else 3}; observed $($result.Role)"; return $result}}
"""
    if index == 0:
        script += """
$services=@(Get-Service NTDS,DNS,Netlogon)
$shares=@(Get-SmbShare | Where-Object Name -in @('SYSVOL','NETLOGON'))
$servicesReady=(@($services | Where-Object Status -ne 'Running').Count -eq 0) -and ($shares.Count -eq 2)
if (-not $servicesReady) {
 $result.Failure="Expected NTDS/DNS/Netlogon Running and SYSVOL/NETLOGON shares; services=$($services | Select-Object Name,Status | ConvertTo-Json -Compress); shares=$($shares.Name -join ',')"
 return $result
}
"""
    else:
        script += f"""
if (-not (Test-ComputerSecureChannel -Server '{dc_name}')) {{$result.Failure='Secure channel check returned false for DC {dc_name}'; return $result}}
"""
    script += f"""
try {{
 $addresses=@(Resolve-DnsName '{dc_name}' -Type A -Server '{network.members[0].ip}' -DnsOnly |
  Where-Object Type -eq 'A' | ForEach-Object IPAddress)
 $defaultAddresses=@(Resolve-DnsName '{dc_name}' -Type A -DnsOnly |
  Where-Object Type -eq 'A' | ForEach-Object IPAddress)
 $srv=@(Resolve-DnsName '_ldap._tcp.dc._msdcs.{domain.name}' -Type SRV -Server '{network.members[0].ip}' -DnsOnly |
  Where-Object Type -eq 'SRV')
}} catch {{
 if ($_.FullyQualifiedErrorId.Split(',')[0] -notin @(
  'DNS_ERROR_RCODE_NAME_ERROR','DNS_INFO_NO_RECORDS','DNS_ERROR_RCODE_SERVER_FAILURE','ERROR_TIMEOUT')) {{throw}}
 $result.Failure="Domain DNS records pending: $($_.FullyQualifiedErrorId)"; return $result
}}
if ($addresses.Count -ne 1 -or $addresses[0] -ne '{network.members[0].ip}' -or
 $defaultAddresses.Count -ne 1 -or $defaultAddresses[0] -ne '{network.members[0].ip}') {{
 $result.Failure="Expected DC A record {network.members[0].ip}; explicit DNS=$($addresses -join ','), default DNS=$($defaultAddresses -join ',')"; return $result
}}
if ($srv.Count -ne 1 -or $srv[0].NameTarget.TrimEnd('.') -ne '{dc_name}' -or $srv[0].Port -ne 389) {{
 $result.Failure="Expected one LDAP SRV {dc_name}:389; observed $($srv | Select-Object NameTarget,Port | ConvertTo-Json -Compress)"; return $result
}}
$result.Ready=$true
$result
}} | ConvertTo-Json -Compress
"""
    return script


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
    script = f"""
& {{
$services=@(Get-Service NTDS,DNS,Netlogon)
if (@($services | Where-Object Status -ne 'Running').Count -gt 0) {{
 return @{{Ready=$false; Failure="Expected AD services Running; observed $($services | Select-Object Name,Status | ConvertTo-Json -Compress)"}}
}}
Import-Module ActiveDirectory
try {{Get-ADDomain -Server localhost | Out-Null}}
catch [Microsoft.ActiveDirectory.Management.ADServerDownException] {{
 return @{{Ready=$false; Failure='Local AD directory RPC is not ready'}}
}}
$zones=@(Get-DnsServerZone | ForEach-Object ZoneName)
if ('{domain.name}' -notin $zones -or '_msdcs.{domain.name}' -notin $zones) {{
 return @{{Ready=$false; Failure="Expected zones {domain.name}, _msdcs.{domain.name}; observed $($zones -join ',')"}}
}}
@{{Ready=$true; Failure=''}}
}} | ConvertTo-Json -Compress
"""
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
