param([string]$Server = 'user@192.168.0.100')
& "$PSScriptRoot/scripts/project-control.ps1" -Action stop -Server $Server
if (-not $?) { exit 1 }
