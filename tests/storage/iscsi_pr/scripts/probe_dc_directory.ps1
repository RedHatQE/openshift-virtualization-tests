
& {
$services=@(Get-Service NTDS,DNS,Netlogon)
if (@($services | Where-Object Status -ne 'Running').Count -gt 0) {
 return @{Ready=$false; Failure="Expected AD services Running; observed $($services | Select-Object Name,Status | ConvertTo-Json -Compress)"}
}
Import-Module ActiveDirectory
try {Get-ADDomain -Server localhost | Out-Null}
catch [Microsoft.ActiveDirectory.Management.ADServerDownException] {
 return @{Ready=$false; Failure='Local AD directory RPC is not ready'}
}
$zones=@(Get-DnsServerZone | ForEach-Object ZoneName)
if ('{{ domain.name }}' -notin $zones -or '_msdcs.{{ domain.name }}' -notin $zones) {
 return @{Ready=$false; Failure="Expected zones {{ domain.name }}, _msdcs.{{ domain.name }}; observed $($zones -join ',')"}
}
@{Ready=$true; Failure=''}
} | ConvertTo-Json -Compress
