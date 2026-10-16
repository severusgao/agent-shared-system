#!/usr/bin/env bash
set -euo pipefail

export PYTHONDONTWRITEBYTECODE=1

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
default_state_file="${script_dir}/../state/shared_system_instances.json"

windows_agents_root=""
windows_shared_skills_root=""
host_machine=""
agent_id=""
agent_skills_dir=""
state_file="${default_state_file}"
agent_state_file="${script_dir}/../skills/agent-shared-skills/state/agent_skill_instances.json"
assume_yes=0
prune=0
replace_conflicts=0
format="text"
backup_root=""

applied_count=0
conflict_count=0
stale_count=0
scan_incomplete_count=0
skills_audit="ok"
mcp_audit="ok"
memories_audit="ok"
VALID_SKILLS_RESULT=""
SCAN_COMPLETE_RESULT=1

normalize_dir_input() {
  local value="${1:-}"
  value="${value%/}"
  value="${value%\\}"
  if [[ "$value" == \"*\" && "$value" == *\" ]]; then
    value="${value:1:${#value}-2}"
  fi
  if [[ "$value" == \'*\' && "$value" == *\' ]]; then
    value="${value:1:${#value}-2}"
  fi
  printf '%s' "$value"
}

resolve_dir() {
  local target="$1"
  (
    cd "$target" >/dev/null 2>&1
    pwd -P
  )
}

python3_is_usable() {
  command -v python3 >/dev/null 2>&1 && python3 -V >/dev/null 2>&1
}

same_link_target() {
  local path="$1"
  local target="$2"
  [[ -L "$path" ]] || return 1
  [[ "$(readlink "$path")" == "$target" ]]
}

classify_link() {
  local path="$1"
  local target="$2"
  if [[ -L "$path" ]]; then
    if same_link_target "$path" "$target"; then
      printf 'ok'
    else
      printf 'relink'
    fi
    return
  fi

  if [[ -e "$path" ]]; then
    printf 'conflict'
    return
  fi

  printf 'create'
}

backup_conflict() {
  local path="$1"
  local name="$2"
  local parent
  local backup_base

  if [[ -z "$backup_root" ]]; then
    backup_base="${HOME}/.agents/backups"
    if [[ "$path" == "${HOME}/.agents" ]] && [[ -L "${HOME}/.agents" || ( -e "${HOME}/.agents" && ! -d "${HOME}/.agents" ) ]]; then
      backup_base="${HOME}/.agents-backups"
    fi
    backup_root="${backup_base}/windows-wsl-shared-sync/$(date +%Y%m%d-%H%M%S)"
  fi

  mkdir -p "$backup_root"
  parent="$(dirname "$name")"
  if [[ "$parent" != "." ]]; then
    mkdir -p "$backup_root/$parent"
  fi
  mv "$path" "$backup_root/$name"
  echo "backed up conflict: $path -> $backup_root/$name"
}

ensure_real_directory() {
  local path="$1"
  local label="$2"

  if [[ -d "$path" && ! -L "$path" ]]; then
    echo "ok real directory: $label"
    return 0
  fi

  if [[ ! -e "$path" && ! -L "$path" ]]; then
    if (( assume_yes )); then
      mkdir -p "$path"
      echo "created real directory: $label"
    else
      echo "preview create real directory: $label"
    fi
    return 0
  fi

  conflict_count=$((conflict_count + 1))
  if (( assume_yes && replace_conflicts )); then
    backup_conflict "$path" "$label"
    mkdir -p "$path"
    applied_count=$((applied_count + 1))
    echo "replaced conflict with real directory: $label"
    return 0
  fi

  echo "conflict: $label must be a real directory; rerun with --yes --replace-conflicts to back up and replace." >&2
  return 1
}

apply_link() {
  local path="$1"
  local target="$2"
  local label="$3"
  local action

  action="$(classify_link "$path" "$target")"
  case "$action" in
    ok)
      echo "ok: $label -> $target"
      ;;
    create)
      if (( assume_yes )); then
        mkdir -p "$(dirname "$path")"
        ln -s "$target" "$path"
        applied_count=$((applied_count + 1))
        echo "created: $label -> $target"
      else
        echo "preview create: $label -> $target"
      fi
      ;;
    relink)
      if (( assume_yes )); then
        rm "$path"
        mkdir -p "$(dirname "$path")"
        ln -s "$target" "$path"
        applied_count=$((applied_count + 1))
        echo "relinked: $label -> $target"
      else
        echo "preview relink: $label -> $target"
      fi
      ;;
    conflict)
      conflict_count=$((conflict_count + 1))
      if [[ "$label" == */skills/* ]]; then
        echo "conflict: $label (native skill preserved; use targeted --replace-local --skills through the skill helper)" >&2
      elif (( assume_yes && replace_conflicts )); then
        backup_conflict "$path" "$label"
        mkdir -p "$(dirname "$path")"
        ln -s "$target" "$path"
        applied_count=$((applied_count + 1))
        echo "replaced conflict: $label -> $target"
      else
        echo "conflict: $label (real file or directory left unchanged)"
      fi
      ;;
  esac
}

skill_entry_usable() {
  local entry="$1"
  [[ -d "$entry" ]] || return 1
  [[ -r "$entry/SKILL.md" ]] || return 1
  [[ -s "$entry/SKILL.md" ]] || return 1
}

same_real_directory() {
  local left="$1"
  local right="$2"
  local left_real
  local right_real

  left_real="$(resolve_dir "$left")" || return 1
  right_real="$(resolve_dir "$right")" || return 1
  [[ "$left_real" == "$right_real" ]]
}

build_valid_skill_set() {
  local source_root="$1"
  local canonical_root="$2"
  local label_prefix="$3"
  local name
  local entry
  local source_entry

  VALID_SKILLS_RESULT=""
  SCAN_COMPLETE_RESULT=1

  shopt -s nullglob
  for entry in "$canonical_root"/*; do
    [[ -e "$entry" || -L "$entry" ]] || continue
    name="$(basename "$entry")"

    if ! skill_entry_usable "$entry"; then
      SCAN_COMPLETE_RESULT=0
      echo "scan incomplete: ${label_prefix}/${name} has unusable canonical SKILL.md; skipping prune for ${label_prefix}"
      continue
    fi

    source_entry="${source_root}/${name}"
    if ! skill_entry_usable "$source_entry"; then
      SCAN_COMPLETE_RESULT=0
      echo "scan incomplete: ${label_prefix}/${name} is missing or unreadable in source root; skipping prune for ${label_prefix}"
      continue
    fi

    if ! same_real_directory "$source_entry" "$entry"; then
      SCAN_COMPLETE_RESULT=0
      echo "scan incomplete: ${label_prefix}/${name} does not resolve to canonical source; skipping prune for ${label_prefix}"
      continue
    fi

    if [[ -n "$VALID_SKILLS_RESULT" ]]; then
      VALID_SKILLS_RESULT+=$'\n'
    fi
    VALID_SKILLS_RESULT+="$name"
  done
  shopt -u nullglob
}

sync_skill_layer() {
  local source_root="$1"
  local destination_root="$2"
  local managed_root="$3"
  local label_prefix="$4"
  local canonical_root="$5"
  local scan_complete
  local entry
  local name
  local target
  local existing
  local current_target
  local valid_skill_index=$'\n'

  build_valid_skill_set "$source_root" "$canonical_root" "$label_prefix"
  if (( assume_yes )) && [[ -n "$VALID_SKILLS_RESULT" ]]; then
    while IFS= read -r name; do
      existing="${destination_root}/${name}"
      if [[ -e "$existing" && ! -L "$existing" ]]; then
        echo "conflict: ${label_prefix}/${name} (native skill preserved; use a targeted helper takeover)" >&2
        return 1
      fi
    done <<< "$VALID_SKILLS_RESULT"
  fi
  if [[ -n "$VALID_SKILLS_RESULT" ]]; then
    while IFS= read -r name; do
      valid_skill_index+="${name}"$'\n'
      entry="${canonical_root}/${name}"
      target="${source_root}/${name}"
      apply_link "${destination_root}/${name}" "$target" "${label_prefix}/${name}"
    done <<< "$VALID_SKILLS_RESULT"
  fi
  scan_complete="$SCAN_COMPLETE_RESULT"

  if (( ! scan_complete )); then
    scan_incomplete_count=$((scan_incomplete_count + 1))
    if (( prune )); then
      echo "prune skipped: source scan incomplete for ${label_prefix}"
    fi
    return
  fi

  shopt -s nullglob
  for existing in "$destination_root"/*; do
    [[ -L "$existing" ]] || continue
    name="$(basename "$existing")"
    if [[ "$valid_skill_index" == *$'\n'"${name}"$'\n'* ]]; then
      continue
    fi

    current_target="$(readlink "$existing")"
    case "$current_target" in
      "${managed_root}/"*)
        stale_count=$((stale_count + 1))
        if (( assume_yes && prune )); then
          rm "$existing"
          applied_count=$((applied_count + 1))
          echo "pruned stale managed link: ${label_prefix}/${name}"
        else
          echo "stale managed link: ${label_prefix}/${name}"
        fi
        ;;
    esac
  done
  shopt -u nullglob
}

sync_whole_directory_link() {
  local source_path="$1"
  local destination_path="$2"
  local label="$3"
  apply_link "$destination_path" "$source_path" "$label"
}

verify_skill_layer() {
  local source_root="$1"
  local destination_root="$2"
  local canonical_root="$3"
  local label="$4"
  local expected=0
  local readable=0
  local failed=0
  local entry
  local name
  local destination
  local expected_target

  shopt -s nullglob
  for entry in "$canonical_root"/*; do
    [[ -e "$entry" || -L "$entry" ]] || continue
    if ! skill_entry_usable "$entry"; then
      echo "verification failed: ${label}/$(basename "$entry") has no readable SKILL.md" >&2
      failed=1
      continue
    fi
    expected=$((expected + 1))
    name="$(basename "$entry")"
    destination="${destination_root}/${name}"
    expected_target="${source_root}/${name}"
    if [[ ! -L "$destination" ]]; then
      echo "verification failed: ${label}/${name} is not a symlink" >&2
      failed=1
    elif ! same_link_target "$destination" "$expected_target"; then
      echo "verification failed: ${label}/${name} points to $(readlink "$destination") instead of $expected_target" >&2
      failed=1
    elif ! skill_entry_usable "$destination"; then
      echo "verification failed: ${label}/${name}/SKILL.md is unreadable" >&2
      failed=1
    else
      readable=$((readable + 1))
    fi
  done
  shopt -u nullglob

  echo "verification: ${label} ${readable}/${expected} readable"
  (( expected > 0 && readable == expected && failed == 0 ))
}

verify_whole_directory_link() {
  local path="$1"
  local target="$2"
  local label="$3"

  if [[ -L "$path" ]] && same_link_target "$path" "$target" && [[ -d "$path" ]]; then
    echo "verification: ${label} readable"
    return 0
  fi
  echo "verification failed: ${label} is not a readable symlink to $target" >&2
  return 1
}

discover_windows_agents_root() {
  if [[ -n "$windows_agents_root" ]]; then
    windows_agents_root="$(normalize_dir_input "$windows_agents_root")"
    return
  fi

  if [[ -n "${WINDOWS_AGENTS_ROOT:-}" ]]; then
    windows_agents_root="$(normalize_dir_input "$WINDOWS_AGENTS_ROOT")"
    return
  fi

  if command -v cmd.exe >/dev/null 2>&1 && command -v wslpath >/dev/null 2>&1; then
    local windows_profile
    windows_profile="$(cmd.exe /c echo %USERPROFILE% 2>/dev/null | tr -d '\r\000')"
    windows_profile="$(normalize_dir_input "$windows_profile")"
    if [[ -n "$windows_profile" ]]; then
      windows_agents_root="$(wslpath -u "${windows_profile}\\.agents")"
    fi
  fi

  if [[ -z "$windows_agents_root" ]]; then
    echo "Unable to discover Windows unified .agents root. Pass --windows-agents-root." >&2
    exit 1
  fi
}

discover_host_machine() {
  if [[ -n "$host_machine" ]]; then
    host_machine="$(normalize_dir_input "$host_machine")"
    return
  fi

  if [[ -n "${WINDOWS_HOST_MACHINE:-}" ]]; then
    host_machine="$(normalize_dir_input "$WINDOWS_HOST_MACHINE")"
    return
  fi

  if command -v cmd.exe >/dev/null 2>&1; then
    host_machine="$(cmd.exe /c echo %COMPUTERNAME% 2>/dev/null | tr -d '\r\000')"
    host_machine="$(normalize_dir_input "$host_machine")"
  fi

  if [[ -z "$host_machine" ]]; then
    host_machine="unknown-host"
  fi
}

record_states_if_possible() {
  local unified_root="$1"
  local wsl_distro="$2"
  local linux_user="$3"
  local home_dir="$4"

  if ! python3_is_usable; then
    echo "state_pending: python3 unavailable; verified links were applied but environment and Agent state were not recorded."
    return 0
  fi

  python3 "${script_dir}/shared_environment.py" \
    --state-file "$state_file" \
    --platform wsl \
    --machine "$host_machine" \
    --user "$linux_user" \
    --home "$home_dir" \
    --wsl-distro "$wsl_distro" \
    --unified-root "$unified_root" \
    --windows-agents-root "$windows_agents_root" \
    --audit-skills "$skills_audit" \
    --audit-mcp "$mcp_audit" \
    --audit-memories "$memories_audit" \
    --apply \
    --yes \
    --format json >/dev/null
  echo "state_recorded: ${state_file}"

  if [[ -z "$agent_skills_dir" ]]; then
    return 0
  fi

  local agent_sync_script="${script_dir}/../skills/agent-shared-skills/scripts/sync_agent_skill_links.py"
  if [[ ! -f "$agent_sync_script" ]]; then
    echo "state_pending: Agent sync helper is missing; WSL Agent instance was not recorded."
    return 0
  fi

  if ! COMPUTERNAME="$host_machine" python3 "$agent_sync_script" \
    --shared-root "$windows_shared_skills_root" \
    --local-root "$unified_skills_root" \
    --target-id "${agent_id:-custom-agent}" \
    --target-label "${agent_id:-custom-agent}" \
    --target-dir "$agent_skills_dir" \
    --state-file "$agent_state_file" \
    --apply \
    --yes \
    --format json >/dev/null; then
    echo "state_pending: WSL Agent links are readable but the Agent instance state was not recorded."
    return 0
  fi
  echo "agent_state_recorded: ${agent_state_file}"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --windows-agents-root)
      windows_agents_root="${2:-}"
      shift 2
      ;;
    --windows-shared-skills-root)
      windows_shared_skills_root="${2:-}"
      shift 2
      ;;
    --host-machine)
      host_machine="${2:-}"
      shift 2
      ;;
    --agent-id)
      agent_id="${2:-}"
      shift 2
      ;;
    --agent-skills-dir)
      agent_skills_dir="${2:-}"
      shift 2
      ;;
    --state-file)
      state_file="${2:-}"
      shift 2
      ;;
    --agent-state-file)
      agent_state_file="${2:-}"
      shift 2
      ;;
    --yes)
      assume_yes=1
      shift
      ;;
    --prune)
      prune=1
      shift
      ;;
    --replace-conflicts)
      replace_conflicts=1
      shift
      ;;
    --format)
      format="${2:-text}"
      shift 2
      ;;
    --help|-h)
      cat <<'EOF'
Usage: wsl-shared-system-sync.sh [options]
  --windows-agents-root PATH
  --windows-shared-skills-root PATH
  --host-machine NAME
  --agent-id ID
  --agent-skills-dir PATH
  --state-file PATH
  --agent-state-file PATH
  --yes
  --prune
  --replace-conflicts
  --format text
EOF
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 1
      ;;
  esac
done

if [[ "$format" != "text" ]]; then
  echo "Unsupported format: $format" >&2
  exit 1
fi

discover_windows_agents_root
discover_host_machine

windows_agents_root="$(normalize_dir_input "$windows_agents_root")"
windows_shared_skills_root="$(normalize_dir_input "$windows_shared_skills_root")"
state_file="$(normalize_dir_input "$state_file")"
agent_state_file="$(normalize_dir_input "$agent_state_file")"
agent_skills_dir="$(normalize_dir_input "$agent_skills_dir")"

wsl_distro="${WSL_DISTRO_NAME:-}"
if [[ -z "$wsl_distro" ]]; then
  echo "WSL_DISTRO_NAME is required. Run inside WSL or set it explicitly for testing." >&2
  exit 1
fi

linux_user="${USER:-$(id -un)}"
home_dir="${HOME:-$(cd ~ && pwd)}"
unified_root="${home_dir}/.agents"
unified_skills_root="${unified_root}/skills"
windows_skills_root="${windows_agents_root}/skills"
windows_mcp_root="${windows_agents_root}/mcp"
windows_memories_root="${windows_agents_root}/memories"

if [[ ! -d "$windows_skills_root" ]]; then
  echo "Windows shared skills root not found: $windows_skills_root" >&2
  exit 1
fi
if [[ -z "$windows_shared_skills_root" ]]; then
  echo "Safe standalone discovery requires --windows-shared-skills-root; this explicit canonical root is required because Windows links alone are not trustworthy here." >&2
  exit 1
fi
if [[ ! -d "$windows_shared_skills_root" ]]; then
  echo "Windows canonical shared skills root not found: $windows_shared_skills_root" >&2
  exit 1
fi
if [[ ! -d "$windows_mcp_root" ]]; then
  echo "Windows MCP registry root not found: $windows_mcp_root" >&2
  exit 1
fi
if [[ ! -d "$windows_memories_root" ]]; then
  echo "Windows memories root not found: $windows_memories_root" >&2
  exit 1
fi

echo "mode: $([[ $assume_yes -eq 1 ]] && printf 'apply' || printf 'preview')"
echo "windows_agents_root: $windows_agents_root"
if [[ -n "$windows_shared_skills_root" ]]; then
  echo "windows_shared_skills_root: $windows_shared_skills_root"
fi
echo "host_machine: $host_machine"
echo "wsl_distro: $wsl_distro"
echo "linux_user: $linux_user"
echo "unified_root: $unified_root"

ensure_real_directory "$unified_root" ".agents" || exit 1
ensure_real_directory "$unified_skills_root" ".agents/skills" || exit 1

sync_skill_layer "$windows_skills_root" "$unified_skills_root" "$windows_skills_root" ".agents/skills" "$windows_shared_skills_root"
sync_whole_directory_link "$windows_mcp_root" "${unified_root}/mcp" ".agents/mcp"
sync_whole_directory_link "$windows_memories_root" "${unified_root}/memories" ".agents/memories"

if [[ -n "$agent_skills_dir" ]]; then
  sync_skill_layer "$unified_skills_root" "$agent_skills_dir" "$unified_skills_root" "${agent_id:-agent}/skills" "$unified_skills_root"
fi

if (( conflict_count > 0 || stale_count > 0 || scan_incomplete_count > 0 )); then
  skills_audit="attention"
  mcp_audit="attention"
  memories_audit="attention"
fi

if (( assume_yes )); then
  if (( scan_incomplete_count > 0 )); then
    echo "verification: deferred because the canonical skill scan is incomplete; state was not recorded."
    echo "state_pending: repair the canonical skill scan and rerun WSL synchronization."
  else
  verification_failed=0
  verify_skill_layer "$windows_skills_root" "$unified_skills_root" "$windows_shared_skills_root" ".agents/skills" || verification_failed=1
  verify_whole_directory_link "${unified_root}/mcp" "$windows_mcp_root" ".agents/mcp" || verification_failed=1
  verify_whole_directory_link "${unified_root}/memories" "$windows_memories_root" ".agents/memories" || verification_failed=1
  if [[ -n "$agent_skills_dir" ]]; then
    verify_skill_layer "$unified_skills_root" "$agent_skills_dir" "$unified_skills_root" "${agent_id:-agent}/skills" || verification_failed=1
  fi
  if (( verification_failed )); then
    echo "WSL shared-system verification failed; state was not recorded." >&2
    exit 1
  fi
  record_states_if_possible "$unified_root" "$wsl_distro" "$linux_user" "$home_dir"
  fi
fi

echo "summary: applied=${applied_count} conflicts=${conflict_count} stale=${stale_count} scan_incomplete=${scan_incomplete_count}"

if (( conflict_count > 0 )); then exit 1; fi
