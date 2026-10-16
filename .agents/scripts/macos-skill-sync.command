#!/usr/bin/env bash
set -euo pipefail

export PYTHONDONTWRITEBYTECODE=1

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
deploy_script="${script_dir}/deploy-cloud-skills-macos.command"
sync_script="${script_dir}/../skills/agent-shared-skills/scripts/sync_agent_skill_links.py"
cloud_skills_root="$(cd "${script_dir}/../skills" && pwd)"
local_skills_root="${HOME}/.agents/skills"

echo
echo "macOS Skill Sync"
echo "Stage 1: shared-source skills -> local unified root"
echo "Stage 2: local unified root -> one Agent skills directory"
echo

if [[ ! -f "$deploy_script" ]]; then
  echo "Missing Stage 1 deploy script: $deploy_script" >&2
  exit 1
fi

if [[ ! -f "$sync_script" ]]; then
  echo "Missing Stage 2 sync script: $sync_script" >&2
  exit 1
fi

bash "$deploy_script"

echo
echo "Stage 2 needs the Agent skills directory, not a specific skill folder."
echo "Examples:"
echo "  /Users/name/.workbuddy/skills"
echo "  /Users/name/.workbuddy/skills/"
echo
read -r -p "Agent name/id (optional; Return to infer from path): " agent_name
read -r -p "Agent skills directory: " agent_dir

agent_dir="$(printf '%s' "$agent_dir" | sed -E 's/^[[:space:]]+|[[:space:]]+$//g')"
if [[ -z "$agent_dir" ]]; then
  echo "Cancelled. Agent skills directory was empty."
  echo
  read -r -p "Press Return to close..."
  exit 0
fi

sync_args=("$sync_script" "--shared-root" "$cloud_skills_root" "--local-root" "$local_skills_root" "--target-dir" "$agent_dir" "--create-roots" "--format" "markdown")
if [[ -n "$(printf '%s' "$agent_name" | tr -d '[:space:]')" ]]; then
  sync_args+=("--target-id" "$agent_name" "--target-label" "$agent_name")
fi

echo
echo "Previewing Agent skill link plan..."
python3 "${sync_args[@]}"

echo
read -r -p "Apply Stage 2 link changes? Type Y to continue: " answer
answer="$(printf '%s' "$answer" | tr -d '[:space:]')"
if [[ ! "$answer" =~ ^[Yy]$ ]]; then
  echo "Cancelled. Stage 2 links were not changed."
  echo
  read -r -p "Press Return to close..."
  exit 0
fi

python3 "${sync_args[@]}" "--apply" "--yes"

echo
echo "macOS Skill Sync complete."
echo
read -r -p "Press Return to close..."
