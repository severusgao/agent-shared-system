@echo off
setlocal

set "SYNC_SELF=%~f0"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop'; $lines=Get-Content -LiteralPath $env:SYNC_SELF; $idx=[Array]::IndexOf($lines,'### POWERSHELL ###'); if ($idx -lt 0) { throw 'Embedded PowerShell marker not found.' }; $script=($lines[($idx+1)..($lines.Count-1)] -join [Environment]::NewLine); Invoke-Expression $script"

if errorlevel 1 (
  echo.
  echo macOS/Windows Skill Sync finished with errors. Review the output above.
  pause
  exit /b %errorlevel%
)

echo.
echo Windows Skill Sync finished.
pause
exit /b 0

### POWERSHELL ###
$env:PYTHONDONTWRITEBYTECODE = "1"
$script:SkillPython = $null
function Invoke-Python {
    param([string[]]$Arguments)
    if (-not $script:SkillPython) {
        $py = Get-Command py -ErrorAction SilentlyContinue
        $python = Get-Command python -ErrorAction SilentlyContinue
        $python3 = Get-Command python3 -ErrorAction SilentlyContinue
        foreach ($candidate in @($py, $python, $python3)) {
            if (-not $candidate) { continue }
            $prefix = @()
            if ($candidate.Name -match '^py(\.exe)?$') { $prefix = @('-3') }
            & $candidate.Source @prefix -B -c "import sys; sys.exit(0 if sys.version_info >= (3,12) else 1)" 2>$null
            if ($LASTEXITCODE -eq 0) {
                $script:SkillPython = @{ Path=$candidate.Source; Prefix=$prefix }
                break
            }
        }
        if (-not $script:SkillPython) { throw "No usable Python interpreter found; install Python 3.12 or newer locally." }
    }
    $prefix = $script:SkillPython.Prefix
    & $script:SkillPython.Path @prefix -X utf8 -B @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Skill operation failed (exit $LASTEXITCODE); it was not retried." }
}

$scriptDir = Split-Path -Parent $env:SYNC_SELF
$deployScript = Join-Path $scriptDir "deploy-cloud-skills-windows.cmd"
$syncScript = Join-Path $scriptDir "..\skills\agent-shared-skills\scripts\sync_agent_skill_links.py"
$cloudSkillsRoot = (Resolve-Path -LiteralPath (Join-Path $scriptDir "..\skills")).Path
$localSkillsRoot = Join-Path $env:USERPROFILE ".agents\skills"

Write-Host ""
Write-Host "Windows Skill Sync"
Write-Host "Stage 1: shared-source skills -> local unified root"
Write-Host "Stage 2: local unified root -> one Agent skills directory"
Write-Host ""

if (-not (Test-Path -LiteralPath $deployScript -PathType Leaf)) {
    throw "Missing Stage 1 deploy script: $deployScript"
}
if (-not (Test-Path -LiteralPath $syncScript -PathType Leaf)) {
    throw "Missing Stage 2 sync script: $syncScript"
}

& cmd /c "`"$deployScript`""
if ($LASTEXITCODE -ne 0) {
    throw "Stage 1 deploy script failed."
}

Write-Host ""
Write-Host "Stage 2 needs the Agent skills directory, not a specific skill folder."
Write-Host "Examples:"
Write-Host "  C:\Users\name\.workbuddy\skills"
Write-Host "  C:\Users\name\.workbuddy\skills\"
Write-Host ""

$agentName = Read-Host "Agent name/id (optional; Return to infer from path)"
$agentDir = Read-Host "Agent skills directory"
$agentDir = $agentDir.Trim()
if (-not $agentDir) {
    Write-Host "Cancelled. Agent skills directory was empty."
    return
}

$syncArgs = @(
    $syncScript,
    "--shared-root", $cloudSkillsRoot,
    "--local-root", $localSkillsRoot,
    "--target-dir", $agentDir,
    "--create-roots",
    "--format", "markdown"
)

if ($agentName.Trim()) {
    $syncArgs += @("--target-id", $agentName, "--target-label", $agentName)
}

Write-Host ""
Write-Host "Previewing Agent skill link plan..."
Invoke-Python -Arguments $syncArgs

Write-Host ""
$answer = Read-Host "Apply Stage 2 link changes? Type Y to continue"
if ($answer.Trim() -notmatch '^[Yy]$') {
    Write-Host "Cancelled. Stage 2 links were not changed."
    return
}

Invoke-Python -Arguments ($syncArgs + @("--apply", "--yes"))

Write-Host ""
Write-Host "Windows Skill Sync complete."
