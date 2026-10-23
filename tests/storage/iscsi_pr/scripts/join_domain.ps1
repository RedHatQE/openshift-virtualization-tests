
$system=Get-CimInstance Win32_ComputerSystem
if ($system.PartOfDomain) {throw 'Expected a fresh workgroup member image'}
$payload=ConvertFrom-Json $InputData
$password=ConvertTo-SecureString $payload.password -AsPlainText -Force
$credential=[System.Management.Automation.PSCredential]::new('{{ domain.join_user }}@{{ domain.name }}',$password)
Rename-Computer -NewName '{{ domain.computer_names[index] }}' -Force
$result=Add-Computer -DomainName '{{ domain.name }}' -Server '{{ domain.computer_names[0] }}.{{ domain.name }}' `
 -Credential $credential -Options JoinWithNewName,AccountCreate -PassThru -Force
if (-not $result.HasSucceeded) {throw 'Domain join failed'}
shutdown.exe /r /t 5 /f /d p:2:4
if ($LASTEXITCODE -ne 0) {throw 'Reboot scheduling failed'}
