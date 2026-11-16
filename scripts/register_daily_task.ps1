# Registriert den täglichen Lauf in der Windows-Aufgabenplanung (Standard 08:00).
# Ausführen in PowerShell im Projektordner:  .\scripts\register_daily_task.ps1 [-Time "08:00"]
# Entfernen:                                  .\scripts\unregister_daily_task.ps1
# Der Lauf tut nur etwas, wenn die Automatik in der Videooberfläche aktiviert ist.
param([string]$Time = "08:00")
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) { throw "Python der virtuellen Umgebung nicht gefunden: $python" }

$action = New-ScheduledTaskAction -Execute $python -Argument "-m workflows.daily_workflow" -WorkingDirectory $root
$trigger = New-ScheduledTaskTrigger -Daily -At $Time
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Hours 3)
Register-ScheduledTask -TaskName "BuergermeisterBob-Daily" -Action $action -Trigger $trigger -Settings $settings `
    -Description "BürgermeisterBob AI Video Factory – täglicher Lauf" -Force | Out-Null
Write-Host "Aufgabe 'BuergermeisterBob-Daily' registriert: täglich um $Time (läuft nach, falls der PC aus war)."
