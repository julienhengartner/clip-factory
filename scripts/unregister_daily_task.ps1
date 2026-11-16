# Entfernt den täglichen Lauf aus der Windows-Aufgabenplanung.
$ErrorActionPreference = "Stop"
Unregister-ScheduledTask -TaskName "BuergermeisterBob-Daily" -Confirm:$false
Write-Host "Aufgabe 'BuergermeisterBob-Daily' entfernt."
