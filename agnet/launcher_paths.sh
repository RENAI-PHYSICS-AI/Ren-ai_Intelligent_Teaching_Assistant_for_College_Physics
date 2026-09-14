#!/usr/bin/env bash
# Sourced by the Rocky launchers. Configured paths are relative to the release
# directory, never to the caller's working directory or a child process's cwd.

physics_anchor_path() {
  local base="$1" value="$2" kind="${3:-file}"
  case "$value" in
    "") printf '%s' "" ;;
    /*) printf '%s' "$value" ;;
    '~') printf '%s' "$HOME" ;;
    '~/'*) printf '%s/%s' "$HOME" "${value#\~/}" ;;
    *)
      if [[ "$kind" == executable && "$value" != */* ]]; then
        # Commands such as julia or tectonic intentionally use PATH discovery.
        printf '%s' "$value"
      else
        printf '%s/%s' "$base" "${value#./}"
      fi
      ;;
  esac
}

physics_anchor_variable() {
  local variable="$1" base="$2" kind="${3:-file}" value
  [[ -v "$variable" ]] || return 0
  value="${!variable}"
  printf -v "$variable" '%s' "$(physics_anchor_path "$base" "$value" "$kind")"
  export "$variable"
}

physics_resolve_launcher_paths() {
  local base="$1" variable depot_remaining depot_item depot_joined="" depot_separator=""
  for variable in \
    PHYSICS_EXAM_MATERIALS_DIR PHYSICS_ASR_MODEL_DIR PHYSICS_TEX_CACHE_DIR \
    PHYSICS_CJK_FONT PHYSICS_GATEWAY_TLS_CERT PHYSICS_GATEWAY_TLS_KEY \
    PHYSICS_CA_BUNDLE PHYSICS_SOUND_SPEED_OUTPUT_DIR; do
    physics_anchor_variable "$variable" "$base"
  done
  for variable in PHYSICS_JULIA_EXE PHYSICS_TEX_COMPILER PHYSICS_LMS_BIN; do
    physics_anchor_variable "$variable" "$base" executable
  done
  # Julia's colon-separated depot list gives empty entries special meaning;
  # preserve leading/trailing empties instead of treating the list as one path.
  if [[ -n "${JULIA_DEPOT_PATH:-}" ]]; then
    depot_remaining="$JULIA_DEPOT_PATH"
    while :; do
      depot_item="${depot_remaining%%:*}"
      depot_joined+="$depot_separator$(physics_anchor_path "$base" "$depot_item")"
      [[ "$depot_remaining" == *:* ]] || break
      depot_remaining="${depot_remaining#*:}"
      depot_separator=:
    done
    export JULIA_DEPOT_PATH="$depot_joined"
  fi
}
