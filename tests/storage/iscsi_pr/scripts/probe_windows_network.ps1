$ErrorActionPreference='Stop'
& {
{% for network in networks %}{% set ip = network.members[index] %}
$nics=@(Get-NetAdapter -Name '{{ network.name }}')
if ($nics.Count -ne 1 -or $nics[0].MacAddress -ne '{{ macs[network.name].replace(':', '-') }}') {
 return @{Ready=$false; Failure="{{ network.name }}: expected one NIC with MAC {{ macs[network.name].replace(':', '-') }}; observed $($nics | Select-Object Name,MacAddress | ConvertTo-Json -Compress)"}
}
$nic=$nics[0]
$addresses=@(Get-NetIPAddress -InterfaceIndex $nic.ifIndex -AddressFamily IPv4)
if ($addresses.Count -ne 1 -or $addresses[0].IPAddress -ne '{{ ip.ip }}' -or
 $addresses[0].PrefixLength -ne {{ ip.network.prefixlen }} -or $addresses[0].AddressState -ne 'Preferred') {
 return @{Ready=$false; Failure="{{ network.name }}: expected {{ ip }} Preferred; observed $($addresses | Select-Object IPAddress,PrefixLength,AddressState | ConvertTo-Json -Compress)"}
}
$defaults=@(Get-NetRoute -InterfaceIndex $nic.ifIndex -AddressFamily IPv4 | Where-Object DestinationPrefix -eq '0.0.0.0/0')
if ({% if loop.first %}$defaults.Count -ne 1 -or $defaults[0].NextHop -ne '{{ network.router.ip }}'{% else %}$defaults.Count -ne 0{% endif %}) {return @{Ready=$false; Failure="{{ network.name }}: expected {% if loop.first %}one default via {{ network.router.ip }}{% else %}no default route{% endif %}; observed $($defaults | Select-Object NextHop,InterfaceIndex,RouteMetric | ConvertTo-Json -Compress)"}}
$dnsRegistration=(Get-DnsClient -InterfaceIndex $nic.ifIndex).RegisterThisConnectionsAddress
if ($dnsRegistration -ne ${{ 'true' if loop.first else 'false' }}) {
 return @{Ready=$false; Failure="{{ network.name }}: expected DNS registration {{ loop.first }}; observed $dnsRegistration"}
}
{% if loop.first %}$primaryIndex=$nic.ifIndex
{% endif %}{% for destination in destinations[network.name] %}
$reply=@(ping.exe -4 -n 1 -w 1000 -S '{{ ip.ip }}' '{{ destination }}')
if ($LASTEXITCODE -ne 0 -or -not ($reply -match 'TTL=[0-9]+')) {
 return @{Ready=$false; Failure="{{ network.name }}: ping from {{ ip.ip }} to {{ destination }} failed; exit=$LASTEXITCODE; reply=$($reply -join ' ')"}
}
{% endfor %}{% endfor %}{% set primary = networks[0] %}
$otherDns=@(Get-NetAdapter | Where-Object Name -ne '{{ primary.name }}' |
 ForEach-Object {Get-DnsClient -InterfaceIndex $_.ifIndex} | Where-Object RegisterThisConnectionsAddress)
if ($otherDns.Count) {return @{Ready=$false; Failure="Expected only {{ primary.name }} to register in DNS; observed other NICs $($otherDns.InterfaceAlias -join ',')"}}
$route=@(Find-NetRoute -LocalIPAddress '{{ primary.members[index].ip }}' -RemoteIPAddress '{{ egress.address }}' |
 Where-Object {$null -ne $_.NextHop})
if ($route.Count -ne 1 -or $route[0].InterfaceIndex -ne $primaryIndex -or $route[0].NextHop -ne '{{ primary.router.ip }}') {
 return @{Ready=$false; Failure="Expected egress to {{ egress.address }} via {{ primary.name }}/{{ primary.router.ip }}; observed $($route | Select-Object InterfaceIndex,NextHop | ConvertTo-Json -Compress)"}
}
$local=[System.Net.IPEndPoint]::new([System.Net.IPAddress]::Parse('{{ primary.members[index].ip }}'),0)
$tcp=[System.Net.Sockets.TcpClient]::new($local); $connected=$false
try {
 $task=$tcp.ConnectAsync('{{ egress.address }}',{{ egress.port }})
 if ($task.Wait(5000)) {$connected=$tcp.Connected}
} catch [System.AggregateException] {$connected=$false} finally {$tcp.Dispose()}
if (-not $connected) {return @{Ready=$false; Failure='TCP from {{ primary.members[index].ip }} to {{ egress.address }}:{{ egress.port }} via {{ primary.router.ip }} failed (5s connect wait)'}}
@{Ready=$true; Failure=''}
} | ConvertTo-Json -Compress
