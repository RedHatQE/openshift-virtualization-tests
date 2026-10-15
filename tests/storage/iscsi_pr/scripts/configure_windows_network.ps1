$ErrorActionPreference='Stop';
{% for network in networks %}{% set ip = network.members[index] %}
$nics=@(Get-NetAdapter | Where-Object MacAddress -eq '{{ macs[network.name].replace(":", "-").upper() }}');
if ($nics.Count -ne 1) {throw 'Guest NIC MAC is missing or duplicated'};
$nic=$nics[0];
$nic | Rename-NetAdapter -NewName '{{ network.name }}';
Set-NetIPInterface -InterfaceIndex $nic.ifIndex -AddressFamily IPv4 -Dhcp Disabled -AutomaticMetric Disabled -InterfaceMetric 100;
Get-NetIPAddress -AddressFamily IPv4 | Where-Object InterfaceIndex -eq $nic.ifIndex | Remove-NetIPAddress -Confirm:$false;
New-NetIPAddress -InterfaceIndex $nic.ifIndex -IPAddress '{{ ip.ip }}' -PrefixLength {{ ip.network.prefixlen }}{% if loop.first %} -DefaultGateway '{{ network.router.ip }}'{% endif %} | Out-Null;
Set-DnsClientServerAddress -InterfaceIndex $nic.ifIndex -ResetServerAddresses;
{% endfor %}
Set-DnsClient -InterfaceAlias '{{ networks[0].name }}' -RegisterThisConnectionsAddress $true;
Get-NetAdapter | Where-Object Name -ne '{{ networks[0].name }}' | ForEach-Object {Set-DnsClient -InterfaceIndex $_.ifIndex -RegisterThisConnectionsAddress $false};
New-NetRoute -DestinationPrefix '{{ egress.address }}/32' -InterfaceAlias '{{ networks[0].name }}' -NextHop '{{ networks[0].router.ip }}' -RouteMetric 1 | Out-Null;
New-NetFirewallRule -Name 'CNV-70031-guest-icmp' -DisplayName 'CNV-70031 guest ICMPv4' -Direction Inbound -Protocol ICMPv4 -IcmpType 8 -Action Allow -Profile Any -InterfaceAlias {% for network in networks %}'{{ network.name }}'{% if not loop.last %},{% endif %}{% endfor %} -RemoteAddress {% for network in networks %}'{{ network.router.network }}'{% if not loop.last %},{% endif %}{% endfor %} | Out-Null
