<#
  ScamGuard Demo Simulator
  ------------------------
  Spins up SAFE, harmless, fully-reversible simulations of the scam patterns
  ScamGuard is built to catch, on a timed schedule, so you can watch its
  overlay alerts fire in real time on your own machine.

  WHAT THIS DOES *NOT* DO:
    - It never visits a real bank, real malware, or real remote-access software.
    - "Fake remote access tool"  = a COPY of curl.exe, renamed to AnyDesk.exe,
       making one ordinary HTTPS download from a public speed-test server
       (speed.hetzner.de — a legitimate hosting company's bandwidth-test file).
       ScamGuard's process/connection scanners match on NAME ONLY, so a
       renamed copy of a harmless binary trips the same detector a real
       remote-access tool would.
    - "Fake screen recorder"     = a COPY of notepad.exe, renamed to obs64.exe.
    - "Fake banking site"        = a local HTML file titled like a bank login
       page, opened in your default browser.

  Everything lives in %TEMP%\scamguard-sim and is removed by -Cleanup.

  USAGE (run ScamGuard FIRST, ideally via scripts\start-demo.ps1, then):
    .\scripts\simulate-scam.ps1            Run the full sequence
    .\scripts\simulate-scam.ps1 -Cleanup   Stop everything & delete temp files
#>

param([switch]$Cleanup)

$simDir       = "$env:TEMP\scamguard-sim"
$bankHtml     = "$simDir\fake-bank.html"
$fakeRAT      = "$simDir\AnyDesk.exe"     # renamed curl.exe   -> real outbound connection
$fakeRecorder = "$simDir\obs64.exe"       # renamed notepad.exe -> just needs to "be running"

function Banner($text) {
  Write-Host ""
  Write-Host "===================================================================" -ForegroundColor Magenta
  Write-Host " $text" -ForegroundColor Magenta
  Write-Host "===================================================================" -ForegroundColor Magenta
}
function Step($n, $msg)  { Write-Host ""; Write-Host "[$n] $msg" -ForegroundColor Cyan }
function Watch($msg)     { Write-Host "    -> $msg" -ForegroundColor Yellow }

# -------------------------------------------------------------------------
# Cleanup mode
# -------------------------------------------------------------------------
if ($Cleanup) {
  Banner "Cleaning up simulation artifacts"
  Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
    Where-Object { $_.ExecutablePath -like "$simDir*" } |
    ForEach-Object {
      Write-Host "  stopping $($_.Name) (pid $($_.ProcessId))"
      Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
    }
  Start-Sleep -Seconds 1
  Remove-Item -Recurse -Force $simDir -ErrorAction SilentlyContinue
  Write-Host ""
  Write-Host "Done — simulated processes closed, temp files removed." -ForegroundColor Green
  return
}

New-Item -ItemType Directory -Force -Path $simDir | Out-Null

Banner "ScamGuard Demo Simulator — safe, reversible scam-pattern replay"
Write-Host "Make sure ScamGuard is already running and its overlay is visible."
Write-Host "(Recommended: launch it with scripts\start-demo.ps1 for fast alerts.)"
Read-Host "Press Enter to begin"

# -------------------------------------------------------------------------
# Step 1 — Fake banking site (browser-title detection)
# -------------------------------------------------------------------------
Step 1 "Opening a fake banking page titled 'Chase Online Banking - Sign In'"
Watch "Detector : browser title scan (Pillar 2b)"
Watch "Expect   : BANKING_SITE  -- info, auto-dismisses  (~4-15s in demo mode)"

@"
<!DOCTYPE html>
<html><head><title>Chase Online Banking - Sign In</title></head>
<body style="font-family:sans-serif;padding:40px">
<h1>ScamGuard Demo -- Fake Banking Page</h1>
<p>This is a local test page used only to trigger ScamGuard's banking-site
detector. No real bank, no real credentials, no real data.</p>
</body></html>
"@ | Out-File -FilePath $bankHtml -Encoding utf8

Start-Process $bankHtml
Start-Sleep -Seconds 18

# -------------------------------------------------------------------------
# Step 2 — Fake remote-access tool WITH a live external connection
# -------------------------------------------------------------------------
Step 2 "Launching a renamed copy of curl.exe as 'AnyDesk.exe' (downloads a public test file)"
Watch "Detector : process scan, then active-connection scan (Pillars 2 & 2c)"
Watch "Expect 1 : REMOTE_ACCESS_TOOL       -- critical, just from the process name"
Watch "Expect 2 : REMOTE_ACCESS_CONNECTED  -- critical, names the live external IP"
Watch "Note     : requires internet access (downloads from speed.hetzner.de)"

Copy-Item "$env:WINDIR\System32\curl.exe" $fakeRAT -Force
Start-Process -FilePath $fakeRAT -ArgumentList "-s -o NUL https://speed.hetzner.de/100MB.bin" -WindowStyle Minimized
Start-Sleep -Seconds 40

# -------------------------------------------------------------------------
# Step 3 — The correlation: banking + "remote access" active at the same time
# -------------------------------------------------------------------------
Step 3 "Banking site is still open AND 'AnyDesk' is still connected -- the scam pattern"
Watch "Detector : banking + remote-access correlation (the headline feature)"
Watch "Expect   : BANKING_WITH_REMOTE_ACCESS"
Watch "           -- ScamGuard's MOST SEVERE alert: critical, non-dismissable,"
Watch "              names the exact process AND notes it's actively connected"
Watch "(Narrate while you wait -- this is the 'someone is watching you bank' moment.)"
Start-Sleep -Seconds 35

# -------------------------------------------------------------------------
# Step 4 — Fake screen recorder
# -------------------------------------------------------------------------
Step 4 "Launching a renamed copy of notepad.exe as 'obs64.exe'"
Watch "Detector : process scan, screen_capture category (Pillar 2)"
Watch "Expect   : SCREEN_RECORDING_ACTIVE -- warning, dismissable, auto-dismisses"

Copy-Item "$env:WINDIR\System32\notepad.exe" $fakeRecorder -Force
Start-Process $fakeRecorder
Start-Sleep -Seconds 15

Banner "Simulation complete"
Write-Host "Alerts you should have seen, in order:"
Write-Host "  1. BANKING_SITE              (info)"
Write-Host "  2. REMOTE_ACCESS_TOOL        (critical)"
Write-Host "  3. REMOTE_ACCESS_CONNECTED   (critical)"
Write-Host "  4. BANKING_WITH_REMOTE_ACCESS (critical, non-dismissable -- the headline)"
Write-Host "  5. SCREEN_RECORDING_ACTIVE   (warning)"
Write-Host ""
Write-Host "To stop everything and remove all temp files:" -ForegroundColor Yellow
Write-Host "  .\scripts\simulate-scam.ps1 -Cleanup" -ForegroundColor Yellow
