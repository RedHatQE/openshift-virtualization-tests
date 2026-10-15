
$ErrorActionPreference='Stop'
& {
$system=Get-CimInstance Win32_ComputerSystem
$result=@{Domain=$system.Domain; Role=[int]$system.DomainRole; Ready=$false; Failure=''}
if ($system.Name -ne '{{ domain.computer_names[index] }}') {$result.Failure="Expected computer name {{ domain.computer_names[index] }}; observed $($system.Name)"; return $result}
if (-not $system.PartOfDomain -or $system.Domain -ne '{{ domain.name }}') {$result.Failure="Expected domain {{ domain.name }}; observed $($system.Domain), PartOfDomain=$($system.PartOfDomain)"; return $result}
if ($result.Role -ne {{ 5 if index == 0 else 3 }}) {$result.Failure="Expected domain role {{ 5 if index == 0 else 3 }}; observed $($result.Role)"; return $result}
{% if index == 0 %}
$services=@(Get-Service NTDS,DNS,Netlogon)
$shares=@(Get-SmbShare | Where-Object Name -in @('SYSVOL','NETLOGON'))
$servicesReady=(@($services | Where-Object Status -ne 'Running').Count -eq 0) -and ($shares.Count -eq 2)
if (-not $servicesReady) {
 $result.Failure="Expected NTDS/DNS/Netlogon Running and SYSVOL/NETLOGON shares; services=$($services | Select-Object Name,Status | ConvertTo-Json -Compress); shares=$($shares.Name -join ',')"
 return $result
}
{% else %}
if (-not (Test-ComputerSecureChannel -Server '{{ dc_name }}')) {$result.Failure='Secure channel check returned false for DC {{ dc_name }}'; return $result}
{% endif %}
try {
 $addresses=@(Resolve-DnsName '{{ dc_name }}' -Type A -Server '{{ network.members[0].ip }}' -DnsOnly |
  Where-Object Type -eq 'A' | ForEach-Object IPAddress)
 $defaultAddresses=@(Resolve-DnsName '{{ dc_name }}' -Type A -DnsOnly |
  Where-Object Type -eq 'A' | ForEach-Object IPAddress)
 $srv=@(Resolve-DnsName '_ldap._tcp.dc._msdcs.{{ domain.name }}' -Type SRV -Server '{{ network.members[0].ip }}' -DnsOnly |
  Where-Object Type -eq 'SRV')
} catch {
 if ($_.FullyQualifiedErrorId.Split(',')[0] -notin @(
  'DNS_ERROR_RCODE_NAME_ERROR','DNS_INFO_NO_RECORDS','DNS_ERROR_RCODE_SERVER_FAILURE','ERROR_TIMEOUT')) {throw}
 $result.Failure="Domain DNS records pending: $($_.FullyQualifiedErrorId)"; return $result
}
if ($addresses.Count -ne 1 -or $addresses[0] -ne '{{ network.members[0].ip }}' -or
 $defaultAddresses.Count -ne 1 -or $defaultAddresses[0] -ne '{{ network.members[0].ip }}') {
 $result.Failure="Expected DC A record {{ network.members[0].ip }}; explicit DNS=$($addresses -join ','), default DNS=$($defaultAddresses -join ',')"; return $result
}
if ($srv.Count -ne 1 -or $srv[0].NameTarget.TrimEnd('.') -ne '{{ dc_name }}' -or $srv[0].Port -ne 389) {
 $result.Failure="Expected one LDAP SRV {{ dc_name }}:389; observed $($srv | Select-Object NameTarget,Port | ConvertTo-Json -Compress)"; return $result
}
$result.Ready=$true
$result
} | ConvertTo-Json -Compress
