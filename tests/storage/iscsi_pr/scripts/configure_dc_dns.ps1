
$forwarders=@({{ values }})
Import-Module DnsServer
Set-DnsServerForwarder -IPAddress $forwarders -UseRootHint $false
$settings=Get-DnsServerSetting -All
$settings.ListeningIPAddress=@('{{ address }}')
Set-DnsServerSetting -InputObject $settings
New-ItemProperty -Path 'HKLM:\SYSTEM\CurrentControlSet\Services\DNS\Parameters' `
 -Name PublishAddresses -PropertyType String -Value '{{ address }}' -Force | Out-Null
New-ItemProperty -Path 'HKLM:\SYSTEM\CurrentControlSet\Services\Netlogon\Parameters' `
 -Name DnsAvoidRegisterRecords -PropertyType MultiString -Value @('LdapIpAddress','GcIpAddress') -Force | Out-Null
Restart-Service DNS
Restart-Service Netlogon
$updates=@(
 @{Zone='{{ domain.name }}'; Name='{{ domain.computer_names[0] }}'},
 @{Zone='{{ domain.name }}'; Name='@'},
 @{Zone='_msdcs.{{ domain.name }}'; Name='gc'}
)
foreach ($update in $updates) {
 $records=@(Get-DnsServerResourceRecord -ZoneName $update.Zone | Where-Object HostName -eq $update.Name)
 $records | Where-Object { $_.RecordType -eq 'AAAA' -or
  ($_.RecordType -eq 'A' -and $_.RecordData.IPv4Address.IPAddressToString -ne '{{ address }}') } |
  ForEach-Object {Remove-DnsServerResourceRecord -ZoneName $update.Zone -InputObject $_ -Force}
 if (-not ($records | Where-Object { $_.RecordType -eq 'A' -and
  $_.RecordData.IPv4Address.IPAddressToString -eq '{{ address }}' })) {
  Add-DnsServerResourceRecordA -ZoneName $update.Zone -Name $update.Name -IPv4Address '{{ address }}'
 }
}
nltest.exe /dsregdns
if ($LASTEXITCODE -ne 0) {throw 'DC locator registration failed'}
Register-DnsClient
New-NetFirewallRule -Name 'CNV-70031-domain-tcp' -DisplayName 'CNV-70031 domain TCP' `
 -Direction Inbound -Action Allow -Profile Any -InterfaceAlias '{{ network.name }}' `
 -RemoteAddress '{{ network.router.network }}' -Protocol TCP -LocalPort 53,88,135,389,445,464,636,3268,3269,'49152-65535' | Out-Null
New-NetFirewallRule -Name 'CNV-70031-domain-udp' -DisplayName 'CNV-70031 domain UDP' `
 -Direction Inbound -Action Allow -Profile Any -InterfaceAlias '{{ network.name }}' `
 -RemoteAddress '{{ network.router.network }}' -Protocol UDP -LocalPort 53,88,123,389,464 | Out-Null
