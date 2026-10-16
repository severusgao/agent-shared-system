#!/usr/bin/env bash
set -euo pipefail
export PYTHONDONTWRITEBYTECODE=1
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cloud_skills_root="${DEPLOY_CLOUD_SKILLS_ROOT:-${script_dir}/../skills}"
cloud_skills_root="$(cd "$cloud_skills_root" && pwd)"
local_skills_root="${DEPLOY_LOCAL_SKILLS_ROOT:-${HOME}/.agents/skills}"
helper="${script_dir}/../skills/agent-shared-skills/scripts/sync_agent_skill_links.py"
python3 -B -c 'import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)' || { echo 'Python 3.12+ is required locally.' >&2; exit 1; }
args=("$helper" --shared-root "$cloud_skills_root" --local-root "$cloud_skills_root" --target-dir "$local_skills_root" --target-id unified --create-roots --no-record --format markdown)
if [[ -n "${DEPLOY_BACKUP_ROOT:-}" ]]; then args+=(--backup-root "$DEPLOY_BACKUP_ROOT"); fi
python3 -B "${args[@]}"
read -r -p 'Apply Layer 1 links? Type Y to continue: ' answer
if [[ "$answer" =~ ^[Yy]$ ]]; then
  python3 -B "${args[@]}" --apply --yes
else
  echo 'Cancelled. Layer 1 was not applied; onboarding stopped.' >&2
  exit 1
fi
