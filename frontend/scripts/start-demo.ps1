<#
  ScamGuard — Demo Mode Launcher
  ------------------------------
  Launches the Electron app with much shorter polling intervals and alert
  cooldowns so the detection pipeline reacts in seconds rather than minutes.
  This only sets environment variables for THIS process — production defaults
  (60-120s cooldowns, 8-15s polling) are completely unaffected.

  Pair this with simulate-scam.ps1 in another terminal to run a full live demo
  where every alert appears within a comfortable, narratable window.

  USAGE (from the frontend/ directory):
    .\scripts\start-demo.ps1
#>

# Detector polling — how often each pillar re-checks the system.
$env:SCAMGUARD_BROWSER_TITLE_INTERVAL = "4000"   # default 8000
$env:SCAMGUARD_PROCESS_INTERVAL       = "5000"   # default 10000
$env:SCAMGUARD_CONNECTION_INTERVAL    = "6000"   # default 15000

# Alert cooldowns — how long before the same alert can re-fire.
# Shortened so a presenter doesn't have to stall for 60-120s mid-demo.
$env:SCAMGUARD_BANKING_COOLDOWN         = "15000"  # default 60000
$env:SCAMGUARD_PROCESS_COOLDOWN         = "15000"  # default 60000
$env:SCAMGUARD_CONNECTION_COOLDOWN      = "15000"  # default 120000
$env:SCAMGUARD_BANKING_CONTEXT_COOLDOWN = "20000"  # default 90000

Write-Host ""
Write-Host "===================================================================" -ForegroundColor Cyan
Write-Host " ScamGuard — DEMO MODE" -ForegroundColor Cyan
Write-Host "===================================================================" -ForegroundColor Cyan
Write-Host " Detector polling : titles=4s   processes=5s   connections=6s"
Write-Host " Alert cooldowns  : 15-20s (vs. 60-120s in production)"
Write-Host ""
Write-Host " In another terminal, run scripts\simulate-scam.ps1 to trigger"
Write-Host " each alert type on a timed, narratable schedule."
Write-Host "===================================================================" -ForegroundColor Cyan
Write-Host ""

npm run dev
