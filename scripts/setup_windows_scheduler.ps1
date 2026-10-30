# ==============================================================================
# PowerShell script to register Windows Task Scheduler for Nightly 10:00 PM Scan
# ==============================================================================

$TaskName = "PersonalEmailAssistant_NightlyScan"
$ProjectDir = (Get-Item -Path "$PSScriptRoot\..").FullName
$PythonExe = Join-Path $ProjectDir ".venv\Scripts\python.exe"
$ScriptPath = Join-Path $ProjectDir "scripts\scheduled_scan.py"

Write-Host "======================================================================"
Write-Host "Setting up Windows Task Scheduler: Nightly 10:00 PM Email Analysis Scan"
Write-Host "======================================================================"
Write-Host "Project Directory : $ProjectDir"
Write-Host "Python Executable : $PythonExe"
Write-Host "Scheduled Script  : $ScriptPath"
Write-Host "Scheduled Time    : 10:00 PM Daily"
Write-Host "======================================================================"

# Verify Python executable exists
if (-not (Test-Path $PythonExe)) {
    Write-Error "Python executable not found at '$PythonExe'. Make sure virtual environment .venv is created."
    exit 1
}

# 1. Action: execute python.exe with scheduled_scan.py in project working directory
$Action = New-ScheduledTaskAction `
    -Execute $PythonExe `
    -Argument "`"$ScriptPath`"" `
    -WorkingDirectory $ProjectDir

# 2. Trigger: Daily at 10:00 PM (22:00)
$Trigger = New-ScheduledTaskTrigger -Daily -At "10:00PM"

# 3. Settings:
# - StartWhenAvailable: Runs missed scan immediately if machine was off/asleep at 10:00 PM
# - AllowStartIfOnBatteries: Allows running even if laptop is unplugged
# - ExecutionTimeLimit: 1 hour maximum
$Settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Hours 1)

# 4. Register Scheduled Task (replaces existing if already registered)
try {
    Register-ScheduledTask `
        -TaskName $TaskName `
        -Action $Action `
        -Trigger $Trigger `
        -Settings $Settings `
        -Description "Personal Gmail Analysis Assistant: Nightly email extraction scan for transactions and jobs at 10:00 PM." `
        -Force | Out-Null

    Write-Host "`n[OK] Task '$TaskName' registered successfully!" -ForegroundColor Green
    Write-Host "Triggered: Every night at 10:00 PM local time."
    Write-Host "Missed-Run Catch-up: Enabled (starts automatically if computer was asleep/off at 10:00 PM)."
    Write-Host "`nTo test the task immediately via Windows Task Scheduler, run:"
    Write-Host "  Start-ScheduledTask -TaskName '$TaskName'"
    Write-Host "To remove this scheduled task later, run:"
    Write-Host "  powershell -ExecutionPolicy Bypass -File scripts\remove_windows_scheduler.ps1"
} catch {
    Write-Error "Failed to register scheduled task: $_"
    exit 1
}
