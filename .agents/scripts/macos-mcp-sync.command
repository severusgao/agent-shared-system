#!/usr/bin/env bash
set -euo pipefail

export PYTHONDONTWRITEBYTECODE=1

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cloud_mcp_root="$(cd "${script_dir}/../mcp" && pwd)"
local_mcp_root="${HOME}/.agents/mcp"
backup_base="${HOME}/.agents/backups/cloud-mcp-deploy"
sync_script="${script_dir}/../skills/agent-shared-mcps/scripts/sync_agent_mcp.py"

echo
echo "macOS MCP Sync"
echo "Stage 1: vault shared MCP registry -> local unified MCP root"
echo "Stage 2: shared MCP registry -> one Agent MCP configuration"
echo

if [[ ! -d "$cloud_mcp_root" ]]; then
  echo "Cloud MCP root not found: $cloud_mcp_root" >&2
  exit 1
fi
if [[ ! -f "$sync_script" ]]; then
  echo "MCP sync script not found: $sync_script" >&2
  exit 1
fi

echo "Cloud MCP root: $cloud_mcp_root"
echo "Local MCP root: $local_mcp_root"
echo

stage1_plan="skip"
stage1_reason="already linked"
if [[ -e "$local_mcp_root" || -L "$local_mcp_root" ]]; then
  if [[ -L "$local_mcp_root" ]]; then
    current_target="$(readlink "$local_mcp_root")"
    if [[ "$current_target" != "$cloud_mcp_root" ]]; then
      stage1_plan="relink"
      stage1_reason="existing link points elsewhere: $current_target"
    fi
  else
    stage1_plan="replace-local"
    stage1_reason="local real directory or file exists"
  fi
else
  stage1_plan="create"
  stage1_reason="missing locally"
fi

echo "Stage 1 plan: $stage1_plan ($stage1_reason)"
if [[ "$stage1_plan" != "skip" ]]; then
  read -r -p "Apply Stage 1 link change? Type Y to continue: " stage1_answer
  stage1_answer="$(printf '%s' "$stage1_answer" | tr -d '[:space:]')"
  if [[ ! "$stage1_answer" =~ ^[Yy]$ ]]; then
    echo "Cancelled. Stage 1 link was not changed."
    echo
    read -r -p "Press Return to close..."
    exit 0
  fi

  mkdir -p "$(dirname "$local_mcp_root")"
  case "$stage1_plan" in
    create)
      ln -s "$cloud_mcp_root" "$local_mcp_root"
      ;;
    relink)
      rm "$local_mcp_root"
      ln -s "$cloud_mcp_root" "$local_mcp_root"
      ;;
    replace-local)
      timestamp="$(date +%Y%m%d-%H%M%S)"
      backup_dir="${backup_base}/${timestamp}"
      mkdir -p "$backup_dir"
      mv "$local_mcp_root" "${backup_dir}/mcp"
      ln -s "$cloud_mcp_root" "$local_mcp_root"
      echo "Backed up existing local MCP root to ${backup_dir}/mcp"
      ;;
  esac
  echo "Stage 1 complete."
fi

echo
read -r -p "MCP id (default: open-design): " mcp_id
mcp_id="$(printf '%s' "${mcp_id:-open-design}" | sed -E 's/^[[:space:]]+|[[:space:]]+$//g')"
read -r -p "Agent id (examples: codex, claude, cursor, opencode, hermes): " agent_id
agent_id="$(printf '%s' "$agent_id" | sed -E 's/^[[:space:]]+|[[:space:]]+$//g')"
if [[ -z "$agent_id" ]]; then
  echo "Cancelled. Agent id was empty."
  echo
  read -r -p "Press Return to close..."
  exit 0
fi

sync_args=("$sync_script" "--mcp" "$mcp_id" "--agent" "$agent_id" "--format" "markdown")

echo
echo "Previewing MCP install plan..."
python3 "${sync_args[@]}"

echo
read -r -p "Apply MCP install changes? Type Y to continue: " answer
answer="$(printf '%s' "$answer" | tr -d '[:space:]')"
if [[ ! "$answer" =~ ^[Yy]$ ]]; then
  echo "Cancelled. MCP config was not changed."
  echo
  read -r -p "Press Return to close..."
  exit 0
fi

python3 "${sync_args[@]}" "--apply" "--yes"

echo
echo "macOS MCP Sync complete."
echo
read -r -p "Press Return to close..."
