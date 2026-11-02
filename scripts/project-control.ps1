param(
    [ValidateSet('start','stop','status')]
    [string]$Action = 'status',
    [string]$Server = 'user@192.168.0.100'
)
$ErrorActionPreference = 'Stop'
# Windows operates the Ubuntu **user** systemd service remotely over SSH.
# No PowerShell process killing or sudo; stop does not terminate build units.
if (-not (Get-Command ssh.exe -ErrorAction SilentlyContinue)) {
    throw "Windows OpenSSH client (ssh.exe) is required."
}
if ($Server -notmatch '^[A-Za-z_][A-Za-z0-9_.-]*@[A-Za-z0-9.-]+$') {
    throw "Expected an SSH target such as user@192.168.0.100"
}
$remote = switch ($Action) {
    start  { 'systemctl --user start peginelab-factory.service && systemctl --user is-active peginelab-factory.service' }
    stop   { 'systemctl --user stop peginelab-factory.service && systemctl --user is-active peginelab-factory.service; test $? -ne 0' }
    status { 'systemctl --user status peginelab-factory.service --no-pager' }
}
Write-Host "YadroKreator: $Action on $Server (Ubuntu user service only)"
& ssh.exe -o BatchMode=yes -o ConnectTimeout=8 $Server $remote
if ($LASTEXITCODE -ne 0) {
    throw "SSH or systemd command failed (exit $LASTEXITCODE). Connect interactively first: ssh $Server"
}
