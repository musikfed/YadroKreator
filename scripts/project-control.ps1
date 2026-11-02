param(
    [ValidateSet('start','stop','status','stop-panel','start-panel')]
    [string]$Action = 'status',
    [string]$Server = 'user@192.168.0.100'
)
$ErrorActionPreference = 'Stop'
# Run the SAME strict project-scoped Linux lifecycle via SSH. No
# Stop-Process, taskkill, sudo, service-wide Docker stop or blind kills.
if (-not (Get-Command ssh.exe -ErrorAction SilentlyContinue)) {
    throw 'Windows OpenSSH client (ssh.exe) is required.'
}
if ($Server -notmatch '^[A-Za-z_][A-Za-z0-9_.-]*@[A-Za-z0-9.-]+$') {
    throw 'Expected an SSH target such as user@192.168.0.100'
}
$remote = "/bin/bash /1tbdisk/PegineLab/projects/YadroKreator/scripts/project-control.sh $Action"
Write-Host "YadroKreator: $Action on $Server"
& ssh.exe -o ConnectTimeout=8 $Server $remote
if ($LASTEXITCODE -ne 0) {
    throw "SSH or YadroKreator lifecycle failed (exit $LASTEXITCODE). Connect interactively first: ssh $Server"
}
