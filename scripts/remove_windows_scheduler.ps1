# ==============================================================================
# PowerShell script to unregister Windows Task Scheduler Nightly Scan Task
# ==============================================================================

$TaskName = "PersonalEmailAssistant_NightlyScan"

Write-Host "Unregistering Windows Scheduled Task: $TaskName..."

try {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction Stop
    Write-Host "[OK] Scheduled task '$TaskName' removed successfully." -ForegroundColor Green
} catch {
    Write-Warning "Task '$TaskName' was not found or already removed."
}
