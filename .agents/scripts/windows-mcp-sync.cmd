@echo off
setlocal

set "SYNC_SELF=%~f0"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop'; $lines=Get-Content -LiteralPath $env:SYNC_SELF; $idx=[Array]::IndexOf($lines,'### POWERSHELL ###'); if ($idx -lt 0) { throw 'Embedded PowerShell marker not found.' }; $script=($lines[($idx+1)..($lines.Count-1)] -join [Environment]::NewLine); Invoke-Expression $script"

if errorlevel 1 (
  echo.
  echo Windows MCP Sync finished with errors. Review the output above.
  pause
  exit /b %errorlevel%
)

echo.
echo Windows MCP Sync finished.
pause
exit /b 0

### POWERSHELL ###
function Invoke-Python {
    param([string[]]$Arguments)

    $failures = @()
    $py = Get-Command py -ErrorAction SilentlyContinue
    $python = Get-Command python -ErrorAction SilentlyContinue
    $python3 = Get-Command python3 -ErrorAction SilentlyContinue

    if ($py) {
        & py -3 @Arguments
        $code = $LASTEXITCODE
        if ($code -eq 0) { return }
        $failures += "py exited with code $code"
    }

    if ($python) {
        & python @Arguments
        $code = $LASTEXITCODE
        if ($code -eq 0) { return }
        $failures += "python exited with code $code"
    }

    if ($python3) {
        & python3 @Arguments
        $code = $LASTEXITCODE
        if ($code -eq 0) { return }
        $failures += "python3 exited with code $code"
    }

    $detail = if ($failures) { $failures -join "; " } else { "no command was found" }
    throw "No usable Python interpreter found or all candidates failed: $detail"
}

$scriptDir = Split-Path -Parent $env:SYNC_SELF
$cloudMcpRoot = (Resolve-Path -LiteralPath (Join-Path $scriptDir "..\mcp")).Path
$localMcpRoot = Join-Path $env:USERPROFILE ".agents\mcp"
$backupBase = Join-Path (Join-Path $env:USERPROFILE ".agents\backups") "cloud-mcp-deploy"
$syncScript = Join-Path $scriptDir "..\skills\agent-shared-mcps\scripts\sync_agent_mcp.py"

Write-Host ""
Write-Host "Windows MCP Sync"
Write-Host "Stage 1: vault shared MCP registry -> local unified MCP root"
Write-Host "Stage 2: shared MCP registry -> one Agent MCP configuration"
Write-Host ""

if (-not (Test-Path -LiteralPath $cloudMcpRoot -PathType Container)) {
    throw "Cloud MCP root not found: $cloudMcpRoot"
}
if (-not (Test-Path -LiteralPath $syncScript -PathType Leaf)) {
    throw "MCP sync script not found: $syncScript"
}

Write-Host "Cloud MCP root: $cloudMcpRoot"
Write-Host "Local MCP root: $localMcpRoot"
Write-Host ""

$stage1Plan = "skip"
$stage1Reason = "already linked"
if (Test-Path -LiteralPath $localMcpRoot) {
    $item = Get-Item -LiteralPath $localMcpRoot -Force
    if ($item.LinkType -in @("Junction", "SymbolicLink")) {
        if (-not (@($item.Target) -contains $cloudMcpRoot)) {
            $stage1Plan = "relink"
            $stage1Reason = "existing link points elsewhere: $($item.Target)"
        }
    } else {
        $stage1Plan = "replace-local"
        $stage1Reason = "local real directory or file exists"
    }
} else {
    $stage1Plan = "create"
    $stage1Reason = "missing locally"
}

Write-Host "Stage 1 plan: $stage1Plan ($stage1Reason)"
if ($stage1Plan -ne "skip") {
    $stage1Answer = Read-Host "Apply Stage 1 Junction change? Type Y to continue"
    if ($stage1Answer.Trim() -notmatch '^[Yy]$') {
        Write-Host "Cancelled. Stage 1 link was not changed."
        return
    }

    $localParent = Split-Path -Parent $localMcpRoot
    if (-not (Test-Path -LiteralPath $localParent -PathType Container)) {
        New-Item -ItemType Directory -Path $localParent | Out-Null
    }

    if ($stage1Plan -eq "create") {
        New-Item -ItemType Junction -Path $localMcpRoot -Target $cloudMcpRoot | Out-Null
    } elseif ($stage1Plan -eq "relink") {
        [System.IO.Directory]::Delete($localMcpRoot)
        New-Item -ItemType Junction -Path $localMcpRoot -Target $cloudMcpRoot | Out-Null
    } elseif ($stage1Plan -eq "replace-local") {
        $timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
        $backupDir = Join-Path $backupBase $timestamp
        New-Item -ItemType Directory -Path $backupDir -Force | Out-Null
        $backupPath = Join-Path $backupDir "mcp"
        Move-Item -LiteralPath $localMcpRoot -Destination $backupPath
        New-Item -ItemType Junction -Path $localMcpRoot -Target $cloudMcpRoot | Out-Null
        Write-Host "Backed up existing local MCP root to $backupPath"
    }
    Write-Host "Stage 1 complete."
}

Write-Host ""
$mcpId = Read-Host "MCP id (default: open-design)"
if (-not $mcpId.Trim()) { $mcpId = "open-design" }
$agentId = Read-Host "Agent id (examples: codex, claude, cursor, opencode, hermes)"
if (-not $agentId.Trim()) {
    Write-Host "Cancelled. Agent id was empty."
    return
}

$syncArgs = @($syncScript, "--mcp", $mcpId.Trim(), "--agent", $agentId.Trim(), "--format", "markdown")

Write-Host ""
Write-Host "Previewing MCP install plan..."
Invoke-Python -Arguments $syncArgs

Write-Host ""
$answer = Read-Host "Apply MCP install changes? Type Y to continue"
if ($answer.Trim() -notmatch '^[Yy]$') {
    Write-Host "Cancelled. MCP config was not changed."
    return
}

Invoke-Python -Arguments ($syncArgs + @("--apply", "--yes"))

Write-Host ""
Write-Host "Windows MCP Sync complete."
