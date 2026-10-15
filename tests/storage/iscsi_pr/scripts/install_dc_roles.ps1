
$system=Get-CimInstance Win32_ComputerSystem
if ($system.PartOfDomain) {throw 'Expected a fresh workgroup DC image'}
$result=Install-WindowsFeature AD-Domain-Services,DNS -IncludeManagementTools
if (-not $result.Success) {throw 'AD DS/DNS role installation failed'}
$rename=$system.Name -ne '{{ domain.computer_names[0] }}'
if ($rename) {Rename-Computer -NewName '{{ domain.computer_names[0] }}' -Force}
$forwarders=@(Get-NetAdapter | Where-Object Name -notin @('guest0','guest1') | ForEach-Object {
 (Get-DnsClientServerAddress -InterfaceIndex $_.ifIndex -AddressFamily IPv4).ServerAddresses
} | Where-Object {$_ -ne '0.0.0.0' -and $_ -notlike '127.*'} | Select-Object -Unique)
@{Restart=($rename -or $result.RestartNeeded.ToString() -eq 'Yes'); Forwarders=$forwarders} | ConvertTo-Json -Compress
