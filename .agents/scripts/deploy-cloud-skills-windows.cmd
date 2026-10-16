@echo off
setlocal

set "DEPLOY_SELF=%~f0"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop'; $lines=Get-Content -LiteralPath $env:DEPLOY_SELF; $idx=[Array]::IndexOf($lines,'### POWERSHELL ###'); if ($idx -lt 0) { throw 'Embedded PowerShell marker not found.' }; $script=($lines[($idx+1)..($lines.Count-1)] -join [Environment]::NewLine); Invoke-Expression $script"

if errorlevel 1 (
  echo.
  echo Deployment finished with errors. Review the output above.
  pause
  exit /b %errorlevel%
)

echo.
echo Cloud skills deployment finished.
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

$scriptDir = Split-Path -Parent $env:DEPLOY_SELF
$cloud = if ($env:DEPLOY_CLOUD_SKILLS_ROOT) { $env:DEPLOY_CLOUD_SKILLS_ROOT } else { Join-Path $scriptDir '..\skills' }
$cloud = (Resolve-Path -LiteralPath $cloud).Path
$local = if ($env:DEPLOY_LOCAL_SKILLS_ROOT) { $env:DEPLOY_LOCAL_SKILLS_ROOT } else { Join-Path $env:USERPROFILE '.agents\skills' }
$helper = Join-Path $scriptDir '..\skills\agent-shared-skills\scripts\sync_agent_skill_links.py'
$arguments = @($helper, '--shared-root', $cloud, '--local-root', $cloud, '--target-dir', $local, '--target-id', 'unified', '--create-roots', '--no-record', '--format', 'markdown')
if ($env:DEPLOY_BACKUP_ROOT) { $arguments += @('--backup-root', $env:DEPLOY_BACKUP_ROOT) }
Invoke-Python -Arguments $arguments
$answer = Read-Host 'Apply Layer 1 links? Type Y to continue'
if ($answer.Trim() -match '^[Yy]$') { Invoke-Python -Arguments ($arguments + @('--apply', '--yes')) }
else { throw 'Cancelled. Layer 1 was not applied; onboarding stopped.' }
