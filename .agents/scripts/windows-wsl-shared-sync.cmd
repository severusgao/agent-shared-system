@echo off
setlocal

set "SYNC_SELF=%~f0"
set "WINDOWS_UNIFIED_ROOT=%USERPROFILE%\.agents"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop'; $lines=Get-Content -LiteralPath $env:SYNC_SELF; $idx=[Array]::IndexOf($lines,'### POWERSHELL ###'); if ($idx -lt 0) { throw 'Embedded PowerShell marker not found.' }; $script=($lines[($idx+1)..($lines.Count-1)] -join [Environment]::NewLine); Invoke-Expression $script"

if errorlevel 1 (
  echo.
  echo Windows WSL Shared Sync finished with errors. Review the output above.
  pause
  exit /b %errorlevel%
)

echo.
echo Windows WSL Shared Sync finished.
pause
exit /b 0

### POWERSHELL ###
function Remove-LocalLink {
    param([string]$Path)

    $item = Get-Item -LiteralPath $Path -Force
    if ($item.PSIsContainer) {
        [System.IO.Directory]::Delete($item.FullName)
    } else {
        [System.IO.File]::Delete($item.FullName)
    }
}

function Get-LinkPlan {
    param(
        [string]$LocalPath,
        [string]$TargetPath,
        [string]$Label
    )

    if (-not (Test-Path -LiteralPath $LocalPath)) {
        return [pscustomobject]@{ Label=$Label; Local=$LocalPath; Target=$TargetPath; Plan="create"; Reason="missing locally" }
    }

    $item = Get-Item -LiteralPath $LocalPath -Force
    if ($item.LinkType -in @("Junction", "SymbolicLink")) {
        if (@($item.Target) -contains $TargetPath) {
            return [pscustomobject]@{ Label=$Label; Local=$LocalPath; Target=$TargetPath; Plan="skip"; Reason="already linked" }
        }
        return [pscustomobject]@{ Label=$Label; Local=$LocalPath; Target=$TargetPath; Plan="relink"; Reason="existing link points elsewhere" }
    }

    return [pscustomobject]@{ Label=$Label; Local=$LocalPath; Target=$TargetPath; Plan="replace-local"; Reason="real directory or file exists" }
}

function Apply-LinkPlan {
    param(
        [pscustomobject]$Plan,
        [string]$BackupRoot
    )

    $localParent = Split-Path -Parent $Plan.Local
    if (-not (Test-Path -LiteralPath $localParent -PathType Container)) {
        New-Item -ItemType Directory -Path $localParent -Force | Out-Null
    }

    switch ($Plan.Plan) {
        "create" {
            New-Item -ItemType Junction -Path $Plan.Local -Target $Plan.Target | Out-Null
        }
        "relink" {
            Remove-LocalLink $Plan.Local
            New-Item -ItemType Junction -Path $Plan.Local -Target $Plan.Target | Out-Null
        }
        "replace-local" {
            $backupPath = Join-Path $BackupRoot $Plan.Label
            $backupParent = Split-Path -Parent $backupPath
            if (-not (Test-Path -LiteralPath $backupParent -PathType Container)) {
                New-Item -ItemType Directory -Path $backupParent -Force | Out-Null
            }
            Move-Item -LiteralPath $Plan.Local -Destination $backupPath
            New-Item -ItemType Junction -Path $Plan.Local -Target $Plan.Target | Out-Null
            Write-Host "Backed up $($Plan.Local) to $backupPath"
        }
    }
}

function Convert-ToWslPath {
    param(
        [string]$Distro,
        [string]$WindowsPath
    )

    $wslInput = $WindowsPath -replace '\\', '/'
    $linuxPath = & wsl.exe -d $Distro -- wslpath -u $wslInput
    if ($LASTEXITCODE -ne 0) {
        throw "wslpath failed for $WindowsPath"
    }
    return ($linuxPath -replace "`0", "").Trim()
}

function Get-WslIdentity {
    param([string]$Distro)

    $linuxUser = & wsl.exe -d $Distro -- sh -lc 'id -un'
    if ($LASTEXITCODE -ne 0) {
        throw "Unable to detect the default Linux user for $Distro"
    }
    $linuxHome = & wsl.exe -d $Distro -- sh -lc 'printf %s "$HOME"'
    if ($LASTEXITCODE -ne 0) {
        throw "Unable to detect the Linux home directory for $Distro"
    }

    $linuxUser = (($linuxUser -join "") -replace "`0", "").Trim()
    $linuxHome = (($linuxHome -join "") -replace "`0", "").Trim()
    if (-not $linuxUser -or -not $linuxHome -or -not $linuxHome.StartsWith("/")) {
        throw "WSL returned an invalid user or home directory for $Distro"
    }
    return [pscustomobject]@{ User=$linuxUser; Home=$linuxHome }
}

function Normalize-LinuxDirectoryInput {
    param([string]$Path)

    $value = $Path.Trim()
    if ($value.Length -ge 2 -and $value[0] -eq $value[$value.Length - 1] -and $value[0] -in @('"', "'")) {
        $value = $value.Substring(1, $value.Length - 2).Trim()
    }
    if (-not $value) {
        throw "Agent skills directory cannot be empty when Agent id is provided."
    }
    if ($value -match '^[A-Za-z]:[\\/]' -or $value.StartsWith('\\') -or $value.StartsWith('//')) {
        throw "Do not enter a Windows path or a \\wsl.localhost path. Enter a Linux absolute path inside WSL."
    }
    if (-not $value.StartsWith('/')) {
        throw "WSL Agent skills directory must be a Linux absolute path inside WSL, such as /home/name/.codex/skills."
    }
    if ($value.Length -gt 1) {
        $value = $value.TrimEnd('/')
    }
    return $value
}

$scriptDir = Split-Path -Parent $env:SYNC_SELF
$vaultAgentsRoot = (Resolve-Path -LiteralPath (Join-Path $scriptDir "..")).Path
$deployScript = Join-Path $scriptDir "deploy-cloud-skills-windows.cmd"
$windowsAgentsRoot = $env:WINDOWS_UNIFIED_ROOT
$localMcpRoot = Join-Path $windowsAgentsRoot "mcp"
$localMemoriesRoot = Join-Path $windowsAgentsRoot "memories"
$cloudMcpRoot = (Resolve-Path -LiteralPath (Join-Path $scriptDir "..\mcp")).Path
$cloudMemoriesRoot = (Resolve-Path -LiteralPath (Join-Path $scriptDir "..\memories")).Path
$cloudSkillsRoot = (Resolve-Path -LiteralPath (Join-Path $scriptDir "..\skills")).Path
$wslScriptWindowsPath = (Resolve-Path -LiteralPath (Join-Path $scriptDir "wsl-shared-system-sync.sh")).Path
$backupRoot = Join-Path $windowsAgentsRoot ("backups\windows-wsl-shared-sync\" + (Get-Date -Format "yyyyMMdd-HHmmss"))

Write-Host ""
Write-Host "Windows WSL Shared Sync"
Write-Host "Stage 1: vault shared skills -> Windows local unified root"
Write-Host "Stage 2: vault MCP/memories -> Windows local unified root"
Write-Host "Stage 3: Windows local unified root -> one WSL distribution"
Write-Host ""

if (-not (Test-Path -LiteralPath $deployScript -PathType Leaf)) {
    throw "Missing Windows skills deploy script: $deployScript"
}
if (-not (Get-Command wsl.exe -ErrorAction SilentlyContinue)) {
    Write-Host "WSL is not available on this machine. Host sync can still continue."
}

& cmd /c "`"$deployScript`""
if ($LASTEXITCODE -ne 0) {
    throw "Stage 1 skills deploy failed."
}

$plans = @(
    Get-LinkPlan -LocalPath $localMcpRoot -TargetPath $cloudMcpRoot -Label "mcp"
    Get-LinkPlan -LocalPath $localMemoriesRoot -TargetPath $cloudMemoriesRoot -Label "memories"
)

Write-Host ""
$plans | Format-Table Label,Plan,Reason,Local,Target -AutoSize

$pending = @($plans | Where-Object { $_.Plan -ne "skip" })
if ($pending.Count -gt 0) {
    $answer = Read-Host "Apply Windows MCP/memories changes? Type Y to continue"
    if ($answer.Trim() -match '^[Yy]$') {
        foreach ($plan in $pending) {
            Apply-LinkPlan -Plan $plan -BackupRoot $backupRoot
        }
        Write-Host "Windows local shared system updated."
    } else {
        Write-Host "Skipped Windows MCP/memories changes."
    }
} else {
    Write-Host "Windows MCP and memories roots are already linked."
}

$wslCommand = Get-Command wsl.exe -ErrorAction SilentlyContinue
if (-not $wslCommand) {
    Write-Host ""
    Write-Host "WSL launch skipped because wsl.exe is unavailable."
    return
}

$distros = @(
    & wsl.exe --list --quiet 2>$null |
        ForEach-Object { $_ -replace "`0", "" } |
        ForEach-Object { $_.Trim() } |
        Where-Object { $_ }
)

if ($distros.Count -eq 0) {
    Write-Host ""
    Write-Host "No WSL distributions were found. The wrapper will not install or start one for you."
    return
}

Write-Host ""
Write-Host "Installed WSL distributions:"
$distros | ForEach-Object { Write-Host "  $_" }

$selectedDistro = Read-Host "Exact WSL distribution name (Return to stop after Windows host stage)"
$selectedDistro = $selectedDistro.Trim()
if (-not $selectedDistro) {
    Write-Host "Stopped after Windows host stage."
    return
}
if ($selectedDistro -notin $distros) {
    throw "Distribution not found: $selectedDistro"
}

$wslIdentity = Get-WslIdentity -Distro $selectedDistro
Write-Host "Detected WSL user: $($wslIdentity.User)"
Write-Host "Detected WSL home: $($wslIdentity.Home)"

$agentId = Read-Host "WSL Agent id (optional; Return to skip Agent skills onboarding)"
$agentId = $agentId.Trim()
$agentSkillsDir = ""
if ($agentId) {
    Write-Host "Enter a Linux absolute path inside WSL, for example: $($wslIdentity.Home)/.codex/skills"
    Write-Host "Do not enter a Windows path or a \\wsl.localhost path."
    $agentSkillsDir = Read-Host "WSL Agent skills directory"
    $agentSkillsDir = Normalize-LinuxDirectoryInput -Path $agentSkillsDir
}

$linuxAgentsRoot = Convert-ToWslPath -Distro $selectedDistro -WindowsPath $windowsAgentsRoot
$linuxSharedSkillsRoot = Convert-ToWslPath -Distro $selectedDistro -WindowsPath $cloudSkillsRoot
$linuxScriptPath = Convert-ToWslPath -Distro $selectedDistro -WindowsPath $wslScriptWindowsPath

$wslArgs = @(
    "-d", $selectedDistro,
    "-u", $wslIdentity.User,
    "--",
    "bash", $linuxScriptPath,
    "--windows-agents-root", $linuxAgentsRoot,
    "--windows-shared-skills-root", $linuxSharedSkillsRoot,
    "--host-machine", $env:COMPUTERNAME
)
if ($agentId) {
    $wslArgs += @("--agent-id", $agentId, "--agent-skills-dir", $agentSkillsDir)
}

Write-Host ""
Write-Host "Previewing WSL onboarding..."
& wsl.exe @wslArgs
if ($LASTEXITCODE -ne 0) {
    throw "WSL onboarding preview failed."
}

$wslAnswer = Read-Host "Apply WSL onboarding changes? Type Y to continue"
if ($wslAnswer.Trim() -notmatch '^[Yy]$') {
    Write-Host "WSL onboarding preview only. No WSL links were changed."
    return
}

Write-Host ""
Write-Host "Applying WSL onboarding..."
& wsl.exe @($wslArgs + @("--yes"))
if ($LASTEXITCODE -ne 0) {
    throw "WSL onboarding apply failed."
}

Write-Host ""
Write-Host "Windows WSL Shared Sync complete."
