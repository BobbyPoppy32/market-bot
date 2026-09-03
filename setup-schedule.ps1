<#
.SYNOPSIS
  Registers (or updates) a Windows Scheduled Task that runs the market bot daily.

.EXAMPLE
  .\setup-schedule.ps1
  .\setup-schedule.ps1 -Time "16:35" -Days "Mon,Tue,Wed,Thu,Fri"
  .\setup-schedule.ps1 -Remove
#>

[CmdletBinding()]
param(
  # Local time for the closing digest, 24h HH:mm. Default 16:35 -- just after
  # the 4pm ET close.
  [string]$Time = "16:35",

  # Local time for the pre-market morning brief, before the 9:30 ET open.
  [string]$MorningTime = "08:00",

  # Weekdays only by default; markets are closed on weekends.
  [string]$Days = "Mon,Tue,Wed,Thu,Fri",

  [string]$TaskName = "MarketBot Daily Digest",

  [string]$MorningTaskName = "MarketBot Morning Brief",

  # Skip the morning brief and register only the closing digest.
  [switch]$NoMorning,

  [switch]$Remove
)

$ErrorActionPreference = "Stop"

$here    = Split-Path -Parent $MyInvocation.MyCommand.Path
$runner  = Join-Path $here "run-bot.cmd"

if ($Remove) {
  foreach ($name in @($TaskName, $MorningTaskName)) {
    if (Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue) {
      Unregister-ScheduledTask -TaskName $name -Confirm:$false
      Write-Host "Removed scheduled task '$name'." -ForegroundColor Yellow
    } else {
      Write-Host "No scheduled task named '$name' found." -ForegroundColor Yellow
    }
  }
  return
}

if (-not (Test-Path $runner)) { throw "Cannot find run-bot.cmd at $runner" }

# Validate times up front so a typo fails here rather than silently never firing.
function Parse-RunTime([string]$value, [string]$label) {
  $parsed = [datetime]::MinValue
  if (-not [datetime]::TryParseExact($value, "HH:mm", $null,
        [Globalization.DateTimeStyles]::None, [ref]$parsed)) {
    throw "$label '$value' is not in 24-hour HH:mm format (e.g. 16:35)."
  }
  return $parsed
}

$closeAt   = Parse-RunTime $Time        "Time"
$morningAt = Parse-RunTime $MorningTime "MorningTime"

$dayList = $Days.Split(",") | ForEach-Object { $_.Trim() } | Where-Object { $_ }

# Wake/retry behaviour: if the machine is off at trigger time, run once it is
# back; retry a few times in case the network isn't up yet at login.
$settings = New-ScheduledTaskSettingsSet `
  -StartWhenAvailable `
  -DontStopIfGoingOnBatteries `
  -AllowStartIfOnBatteries `
  -RestartCount 3 `
  -RestartInterval (New-TimeSpan -Minutes 5) `
  -ExecutionTimeLimit (New-TimeSpan -Minutes 10)

function Register-BotTask($name, $at, $botArgs, $description) {
  $action = if ($botArgs) {
    New-ScheduledTaskAction -Execute $runner -Argument $botArgs -WorkingDirectory $here
  } else {
    New-ScheduledTaskAction -Execute $runner -WorkingDirectory $here
  }
  $trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek $dayList -At $at

  if (Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $name -Confirm:$false
  }
  Register-ScheduledTask -TaskName $name -Action $action -Trigger $trigger `
    -Settings $settings -Description $description | Out-Null
}

Register-BotTask $TaskName $closeAt "" `
  "Posts the daily stock market and AI news closing digest to Discord."

Write-Host ""
Write-Host "Scheduled tasks registered." -ForegroundColor Green
Write-Host "  $TaskName"
Write-Host "     $($dayList -join ', ') at $Time  (closing digest)"

if (-not $NoMorning) {
  Register-BotTask $MorningTaskName $morningAt "--morning" `
    "Posts the pre-market morning brief to Discord."
  Write-Host "  $MorningTaskName"
  Write-Host "     $($dayList -join ', ') at $MorningTime  (pre-market brief)"
}

Write-Host ""
Write-Host "  Cmd  : $runner"
Write-Host "  Log  : $(Join-Path $here 'logs\market-bot.log')"
Write-Host ""
Write-Host "Run either right now to test:" -ForegroundColor Cyan
Write-Host "  Start-ScheduledTask -TaskName `"$TaskName`""
if (-not $NoMorning) {
  Write-Host "  Start-ScheduledTask -TaskName `"$MorningTaskName`""
}
Write-Host ""
