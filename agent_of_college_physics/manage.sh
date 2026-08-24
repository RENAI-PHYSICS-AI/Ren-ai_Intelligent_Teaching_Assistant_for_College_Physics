#!/usr/bin/env bash
set -Eeuo pipefail

APP_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
RUNTIME_ROOT="$APP_ROOT/.runtime"
CONFIG_FILE="$APP_ROOT/config/physics-assistant.env"
PID_DIR="$RUNTIME_ROOT/pids"
LOG_DIR="$RUNTIME_ROOT/logs"
PYTHON="$APP_ROOT/agnet/.venv/bin/python"

mkdir -p "$PID_DIR" "$LOG_DIR"
if [[ -f "$CONFIG_FILE" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$CONFIG_FILE"
  set +a
fi
export HOME="${HOME:?HOME 未设置}"
export PATH="$RUNTIME_ROOT/bin:$PATH"
export PYTHONPATH="$APP_ROOT/agnet"
export PHYSICS_JULIA_EXE="${PHYSICS_JULIA_EXE:-$RUNTIME_ROOT/bin/julia}"
export JULIA_DEPOT_PATH="${JULIA_DEPOT_PATH:-$RUNTIME_ROOT/julia-depot}"
export PHYSICS_SOUND_SPEED_OUTPUT_DIR="${PHYSICS_SOUND_SPEED_OUTPUT_DIR:-$RUNTIME_ROOT/experiment-output/sound-speed}"
export PHYSICS_ELECTRON_EM_PORT="${PHYSICS_ELECTRON_EM_PORT:-9386}"
export PHYSICS_ELECTRON_EM_UPSTREAM="${PHYSICS_ELECTRON_EM_UPSTREAM:-http://127.0.0.1:$PHYSICS_ELECTRON_EM_PORT}"
export PHYSICS_PHOTOELECTRIC_PORT="${PHYSICS_PHOTOELECTRIC_PORT:-9387}"
export PHYSICS_PHOTOELECTRIC_UPSTREAM="${PHYSICS_PHOTOELECTRIC_UPSTREAM:-http://127.0.0.1:$PHYSICS_PHOTOELECTRIC_PORT}"
export PHYSICS_BIPRISM_PORT="${PHYSICS_BIPRISM_PORT:-9388}"
export PHYSICS_BIPRISM_UPSTREAM="${PHYSICS_BIPRISM_UPSTREAM:-http://127.0.0.1:$PHYSICS_BIPRISM_PORT}"
export PHYSICS_NEWTON_RINGS_PORT="${PHYSICS_NEWTON_RINGS_PORT:-9389}"
export PHYSICS_NEWTON_RINGS_UPSTREAM="${PHYSICS_NEWTON_RINGS_UPSTREAM:-http://127.0.0.1:$PHYSICS_NEWTON_RINGS_PORT}"
export PHYSICS_YOUNG_MODULUS_PORT="${PHYSICS_YOUNG_MODULUS_PORT:-9390}"
export PHYSICS_YOUNG_MODULUS_UPSTREAM="${PHYSICS_YOUNG_MODULUS_UPSTREAM:-http://127.0.0.1:$PHYSICS_YOUNG_MODULUS_PORT}"
export PHYSICS_ROTATIONAL_INERTIA_PORT="${PHYSICS_ROTATIONAL_INERTIA_PORT:-9391}"
export PHYSICS_ROTATIONAL_INERTIA_UPSTREAM="${PHYSICS_ROTATIONAL_INERTIA_UPSTREAM:-http://127.0.0.1:$PHYSICS_ROTATIONAL_INERTIA_PORT}"
export PHYSICS_CJK_FONT="${PHYSICS_CJK_FONT:-$RUNTIME_ROOT/fonts/NotoSansCJKsc-Regular.otf}"
export PHYSICS_ASR_MODEL_DIR="${PHYSICS_ASR_MODEL_DIR:-$RUNTIME_ROOT/models/paraformer-zh-streaming}"
if [[ "$PHYSICS_ASR_MODEL_DIR" != /* ]]; then
  export PHYSICS_ASR_MODEL_DIR="$APP_ROOT/${PHYSICS_ASR_MODEL_DIR#./}"
fi
export PHYSICS_ASR_PORT="${PHYSICS_ASR_PORT:-8604}"
export PHYSICS_ASR_UPSTREAM="http://127.0.0.1:$PHYSICS_ASR_PORT"
export PHYSICS_CHAT_MODEL_KEY="${PHYSICS_CHAT_MODEL_KEY:-zai-org/glm-4.7-flash}"
export PHYSICS_CHAT_MODEL_IDENTIFIER="${PHYSICS_CHAT_MODEL_IDENTIFIER:-glm47-local-prod}"
export PHYSICS_CHAT_MODEL_CONTEXT="${PHYSICS_CHAT_MODEL_CONTEXT:-8192}"
export PHYSICS_CHAT_MODEL_PARALLEL="${PHYSICS_CHAT_MODEL_PARALLEL:-4}"
export PHYSICS_VISION_MODEL_KEY="${PHYSICS_VISION_MODEL_KEY:-qwen/qwen3-vl-30b}"
export PHYSICS_VISION_MODEL_IDENTIFIER="${PHYSICS_VISION_MODEL_IDENTIFIER:-qwen-vl30-local-prod}"
export PHYSICS_VISION_MODEL_CONTEXT="${PHYSICS_VISION_MODEL_CONTEXT:-8192}"
export PHYSICS_VISION_MODEL_PARALLEL="${PHYSICS_VISION_MODEL_PARALLEL:-4}"
export PHYSICS_MODEL="${PHYSICS_MODEL:-$PHYSICS_CHAT_MODEL_IDENTIFIER}"
export PHYSICS_VISION_MODEL="${PHYSICS_VISION_MODEL:-$PHYSICS_VISION_MODEL_IDENTIFIER}"
export PHYSICS_GATEWAY_HTTPS_PORT="${PHYSICS_GATEWAY_HTTPS_PORT:-}"
export PHYSICS_GATEWAY_TLS_CERT="${PHYSICS_GATEWAY_TLS_CERT:-$APP_ROOT/config/tls/server.crt}"
export PHYSICS_GATEWAY_TLS_KEY="${PHYSICS_GATEWAY_TLS_KEY:-$APP_ROOT/config/tls/server.key}"
export PHYSICS_GATEWAY_PUBLIC_PREFIX="${PHYSICS_GATEWAY_PUBLIC_PREFIX:-/agent}"
if [[ "$PHYSICS_GATEWAY_TLS_CERT" != /* ]]; then
  export PHYSICS_GATEWAY_TLS_CERT="$APP_ROOT/${PHYSICS_GATEWAY_TLS_CERT#./}"
fi
if [[ "$PHYSICS_GATEWAY_TLS_KEY" != /* ]]; then
  export PHYSICS_GATEWAY_TLS_KEY="$APP_ROOT/${PHYSICS_GATEWAY_TLS_KEY#./}"
fi

pid_alive() {
  local name="$1" pid_file="$PID_DIR/$1.pid" pid
  [[ -s "$pid_file" ]] || return 1
  pid="$(cat "$pid_file")"
  [[ "$pid" =~ ^[0-9]+$ ]] && kill -0 "$pid" 2>/dev/null
}

start_one() {
  local name="$1"
  shift
  if pid_alive "$name"; then
    echo "$name 已运行（PID $(cat "$PID_DIR/$name.pid")）"
    return 0
  fi
  (
    cd "$APP_ROOT/agnet"
    nohup "$@" >"$LOG_DIR/$name.log" 2>&1 </dev/null &
    echo "$!" >"$PID_DIR/$name.pid"
  )
  sleep 1
  if ! pid_alive "$name"; then
    echo "$name 启动失败，日志如下：" >&2
    tail -n 30 "$LOG_DIR/$name.log" >&2 || true
    return 1
  fi
  echo "$name 已启动（PID $(cat "$PID_DIR/$name.pid")）"
}

wait_url() {
  local url="$1" label="$2"
  for _ in {1..60}; do
    curl --fail --silent "$url" >/dev/null 2>&1 && return 0
    sleep 1
  done
  echo "$label 健康检查超时：$url" >&2
  return 1
}

wait_https_url() {
  local url="$1" label="$2"
  for _ in {1..60}; do
    curl --insecure --fail --silent "$url" >/dev/null 2>&1 && return 0
    sleep 1
  done
  echo "$label 健康检查超时：$url" >&2
  return 1
}

local_llm_loaded() {
  local lms_bin="$1" identifier="$2" model_key="$3" context="$4" parallel="$5" models_json
  models_json="$("$lms_bin" ps --json 2>/dev/null)" || return 1
  MODELS_JSON="$models_json" "$PYTHON" -c '
import json
import os
import sys

models = json.loads(os.environ.get("MODELS_JSON", "[]"))
identifier, model_key, context, parallel = sys.argv[1:]
matched = any(
    item.get("identifier") == identifier
    and item.get("modelKey") == model_key
    and item.get("deviceIdentifier") is None
    and int(item.get("contextLength") or 0) == int(context)
    and int(item.get("parallel") or 0) == int(parallel)
    for item in models
)
raise SystemExit(0 if matched else 1)
' "$identifier" "$model_key" "$context" "$parallel"
}

ensure_one_local_llm() {
  local lms_bin="$1" label="$2" model_key="$3" identifier="$4" context="$5" parallel="$6"
  if ! local_llm_loaded "$lms_bin" "$identifier" "$model_key" "$context" "$parallel"; then
    "$lms_bin" unload "$identifier" >/dev/null 2>&1 || true
    "$lms_bin" unload "$model_key" >/dev/null 2>&1 || true
    "$lms_bin" load "$model_key" \
      --identifier "$identifier" \
      --gpu off \
      --context-length "$context" \
      --parallel "$parallel" \
      --no-speculative-draft-mtp \
      --yes
  fi
  local_llm_loaded "$lms_bin" "$identifier" "$model_key" "$context" "$parallel" || {
    "$lms_bin" unload "$identifier" >/dev/null 2>&1 || true
    echo "$label 校验失败：模型未按指定配置加载在 tjracphy。" >&2
    return 1
  }
  echo "$label 已常驻（$identifier，无 TTL）"
}

ensure_local_llms() {
  local lms_bin="${PHYSICS_LMS_BIN:-}"
  [[ "$PHYSICS_MODEL" == "$PHYSICS_CHAT_MODEL_IDENTIFIER" ]] || {
    echo "PHYSICS_MODEL 必须等于 $PHYSICS_CHAT_MODEL_IDENTIFIER" >&2
    return 1
  }
  [[ "$PHYSICS_VISION_MODEL" == "$PHYSICS_VISION_MODEL_IDENTIFIER" ]] || {
    echo "PHYSICS_VISION_MODEL 必须等于 $PHYSICS_VISION_MODEL_IDENTIFIER" >&2
    return 1
  }
  [[ "${PHYSICS_BASE_URL:-}" == "http://127.0.0.1:1235/v1" ]] || {
    echo "本机模型必须使用 PHYSICS_BASE_URL=http://127.0.0.1:1235/v1" >&2
    return 1
  }
  if [[ -z "$lms_bin" ]]; then
    if [[ -x "$HOME/.lmstudio/bin/lms" ]]; then
      lms_bin="$HOME/.lmstudio/bin/lms"
    elif command -v lms >/dev/null 2>&1; then
      lms_bin="$(command -v lms)"
    else
      echo "未找到 lms，无法加载本机对话与图片模型。" >&2
      return 1
    fi
  fi

  "$lms_bin" daemon up >/dev/null 2>&1 || true
  if ! curl --fail --silent http://127.0.0.1:1235/v1/models >/dev/null 2>&1; then
    "$lms_bin" server start --port 1235 --bind 127.0.0.1 >/dev/null
    wait_url http://127.0.0.1:1235/v1/models "LM Studio 本机接口"
  fi
  ensure_one_local_llm "$lms_bin" "本机 GLM-4.7-Flash 对话模型" \
    "$PHYSICS_CHAT_MODEL_KEY" "$PHYSICS_CHAT_MODEL_IDENTIFIER" \
    "$PHYSICS_CHAT_MODEL_CONTEXT" "$PHYSICS_CHAT_MODEL_PARALLEL"
  ensure_one_local_llm "$lms_bin" "本机 Qwen3-VL-30B 图片模型" \
    "$PHYSICS_VISION_MODEL_KEY" "$PHYSICS_VISION_MODEL_IDENTIFIER" \
    "$PHYSICS_VISION_MODEL_CONTEXT" "$PHYSICS_VISION_MODEL_PARALLEL"
}

start_all() {
  [[ -x "$PYTHON" ]] || { echo "尚未安装，请先执行 bash install.sh" >&2; return 1; }
  ensure_local_llms
  start_one admin "$PYTHON" -m uvicorn admin_api:app \
    --host 127.0.0.1 --port 8603 --proxy-headers --forwarded-allow-ips=127.0.0.1
  start_one asr "$PYTHON" -m uvicorn asr_service:app \
    --host 127.0.0.1 --port "$PHYSICS_ASR_PORT" \
    --proxy-headers --forwarded-allow-ips=127.0.0.1
  start_one web "$APP_ROOT/agnet/.venv/bin/streamlit" run app.py \
    --server.address=127.0.0.1 --server.port=8502 --server.headless=true \
    --server.fileWatcherType=none --browser.gatherUsageStats=false
  wait_url http://127.0.0.1:8603/health "管理员服务"
  wait_url http://127.0.0.1:"$PHYSICS_ASR_PORT"/health "Paraformer 语音服务"
  wait_url http://127.0.0.1:8502/_stcore/health "智能助教"
  start_one gateway env PHYSICS_GATEWAY_TLS_CERT= PHYSICS_GATEWAY_TLS_KEY= \
    "$PYTHON" gateway.py
  wait_url http://127.0.0.1:8501/_stcore/health "8501 统一入口"
  if [[ -n "$PHYSICS_GATEWAY_HTTPS_PORT" ]]; then
    [[ -r "$PHYSICS_GATEWAY_TLS_CERT" ]] || {
      echo "HTTPS 证书不可读：$PHYSICS_GATEWAY_TLS_CERT" >&2
      return 1
    }
    [[ -r "$PHYSICS_GATEWAY_TLS_KEY" ]] || {
      echo "HTTPS 私钥不可读：$PHYSICS_GATEWAY_TLS_KEY" >&2
      return 1
    }
    start_one gateway_https env \
      PHYSICS_GATEWAY_PORT="$PHYSICS_GATEWAY_HTTPS_PORT" \
      "$PYTHON" gateway.py
    wait_https_url \
      "https://127.0.0.1:$PHYSICS_GATEWAY_HTTPS_PORT$PHYSICS_GATEWAY_PUBLIC_PREFIX/_stcore/health" \
      "$PHYSICS_GATEWAY_HTTPS_PORT HTTPS 统一入口"
  fi
}

stop_one() {
  local name="$1" pid_file="$PID_DIR/$1.pid" pid
  if ! pid_alive "$name"; then
    rm -f -- "$pid_file"
    echo "$name 未运行"
    return 0
  fi
  pid="$(cat "$pid_file")"
  kill -TERM "$pid"
  for _ in {1..20}; do
    kill -0 "$pid" 2>/dev/null || break
    sleep 0.5
  done
  if kill -0 "$pid" 2>/dev/null; then
    kill -KILL "$pid"
  fi
  rm -f -- "$pid_file"
  echo "$name 已停止"
}

experiment_pids() {
  local proc_dir pid command
  for proc_dir in /proc/[0-9]*; do
    [[ -r "$proc_dir/cmdline" ]] || continue
    pid="${proc_dir##*/}"
    command="$(tr '\0' ' ' <"$proc_dir/cmdline" 2>/dev/null || true)"
    case "$command" in
      *"$APP_ROOT/agnet/experiments/lissajous/web.jl"*|*"$APP_ROOT/agnet/experiments/sound_speed/web.jl"*|*"$APP_ROOT/agnet/experiments/electron_em/web.jl"*|*"$APP_ROOT/agnet/experiments/photoelectric/web.jl"*|*"$APP_ROOT/agnet/experiments/biprism/web.jl"*|*"$APP_ROOT/agnet/experiments/newton_rings/web.jl"*|*"$APP_ROOT/agnet/experiments/young_modulus/web.jl"*|*"$APP_ROOT/agnet/experiments/rotational_inertia/web.jl"*)
        printf '%s\n' "$pid"
        ;;
    esac
  done
}

stop_experiments() {
  local -a pids=()
  local pid
  mapfile -t pids < <(experiment_pids)
  if (( ${#pids[@]} == 0 )); then
    echo "可视化实验未运行"
    return 0
  fi
  kill -TERM "${pids[@]}" 2>/dev/null || true
  for _ in {1..20}; do
    local any_alive=0
    for pid in "${pids[@]}"; do
      kill -0 "$pid" 2>/dev/null && any_alive=1
    done
    (( any_alive == 0 )) && break
    sleep 0.5
  done
  for pid in "${pids[@]}"; do
    kill -0 "$pid" 2>/dev/null && kill -KILL "$pid" 2>/dev/null || true
  done
  echo "可视化实验已停止"
}

status_all() {
  local name
  for name in admin asr web gateway gateway_https; do
    if pid_alive "$name"; then
      echo "$name: 运行中（PID $(cat "$PID_DIR/$name.pid")）"
    else
      echo "$name: 未运行"
    fi
  done
}

check_all() {
  curl --fail --silent --show-error http://127.0.0.1:8502/_stcore/health; printf '\n'
  curl --fail --silent --show-error http://127.0.0.1:8603/health; printf '\n'
  curl --fail --silent --show-error http://127.0.0.1:"$PHYSICS_ASR_PORT"/health; printf '\n'
  curl --fail --silent --show-error http://127.0.0.1:8501/agent-health/admin; printf '\n'
  curl --fail --silent --show-error http://127.0.0.1:8501/asr/health; printf '\n'
  curl --fail --silent --show-error http://127.0.0.1:8501/_stcore/health; printf '\n'
  local electron_health
  if electron_health="$(curl --fail --silent --max-time 2 \
      "http://127.0.0.1:$PHYSICS_ELECTRON_EM_PORT/__physics_health__")"; then
    [[ "$electron_health" == *"physics-experiment:electron-em"* ]] || {
      echo "电子荷质比实验健康标识不匹配。" >&2
      return 1
    }
    electron_health="$(curl --fail --silent --show-error \
      http://127.0.0.1:8501/experiments/electron-em/__physics_health__)"
    [[ "$electron_health" == *"physics-experiment:electron-em"* ]] || {
      echo "电子荷质比实验的 8501 代理健康标识不匹配。" >&2
      return 1
    }
    echo "electron_em: 直接与 8501 代理健康检查通过"
  else
    echo "electron_em: 按需服务尚未启动（首次打开电子荷质比页面后再检查）"
  fi
  local photoelectric_health
  if photoelectric_health="$(curl --fail --silent --max-time 2 \
      "http://127.0.0.1:$PHYSICS_PHOTOELECTRIC_PORT/__physics_health__")"; then
    [[ "$photoelectric_health" == *"physics-experiment:photoelectric"* ]] || {
      echo "光电效应实验健康标识不匹配。" >&2
      return 1
    }
    photoelectric_health="$(curl --fail --silent --show-error \
      http://127.0.0.1:8501/experiments/photoelectric/__physics_health__)"
    [[ "$photoelectric_health" == *"physics-experiment:photoelectric"* ]] || {
      echo "光电效应实验的 8501 代理健康标识不匹配。" >&2
      return 1
    }
    echo "photoelectric: 直接与 8501 代理健康检查通过"
  else
    echo "photoelectric: 按需服务尚未启动（首次打开光电效应页面后再检查）"
  fi
  local biprism_health
  if biprism_health="$(curl --fail --silent --max-time 2 \
      "http://127.0.0.1:$PHYSICS_BIPRISM_PORT/__physics_health__")"; then
    [[ "$biprism_health" == *"physics-experiment:biprism"* ]] || {
      echo "双棱镜实验健康标识不匹配。" >&2
      return 1
    }
    biprism_health="$(curl --fail --silent --show-error \
      http://127.0.0.1:8501/experiments/biprism/__physics_health__)"
    [[ "$biprism_health" == *"physics-experiment:biprism"* ]] || {
      echo "双棱镜实验的 8501 代理健康标识不匹配。" >&2
      return 1
    }
    echo "biprism: 直接与 8501 代理健康检查通过"
  else
    echo "biprism: 按需服务尚未启动（首次打开双棱镜页面后再检查）"
  fi
  local newton_rings_health
  if newton_rings_health="$(curl --fail --silent --max-time 2 \
      "http://127.0.0.1:$PHYSICS_NEWTON_RINGS_PORT/__physics_health__")"; then
    [[ "$newton_rings_health" == *"physics-experiment:newton-rings"* ]] || {
      echo "牛顿环实验健康标识不匹配。" >&2
      return 1
    }
    newton_rings_health="$(curl --fail --silent --show-error \
      http://127.0.0.1:8501/experiments/newton-rings/__physics_health__)"
    [[ "$newton_rings_health" == *"physics-experiment:newton-rings"* ]] || {
      echo "牛顿环实验的 8501 代理健康标识不匹配。" >&2
      return 1
    }
    echo "newton_rings: 直接与 8501 代理健康检查通过"
  else
    echo "newton_rings: 按需服务尚未启动（首次打开牛顿环页面后再检查）"
  fi
  local young_modulus_health
  if young_modulus_health="$(curl --fail --silent --max-time 2 \
      "http://127.0.0.1:$PHYSICS_YOUNG_MODULUS_PORT/__physics_health__")"; then
    [[ "$young_modulus_health" == *"physics-experiment:young-modulus"* ]] || {
      echo "杨氏模量实验健康标识不匹配。" >&2
      return 1
    }
    young_modulus_health="$(curl --fail --silent --show-error \
      http://127.0.0.1:8501/experiments/young-modulus/__physics_health__)"
    [[ "$young_modulus_health" == *"physics-experiment:young-modulus"* ]] || {
      echo "杨氏模量实验的 8501 代理健康标识不匹配。" >&2
      return 1
    }
    echo "young_modulus: 直接与 8501 代理健康检查通过"
  else
    echo "young_modulus: 按需服务尚未启动（首次打开杨氏模量页面后再检查）"
  fi
  local rotational_inertia_health
  if rotational_inertia_health="$(curl --fail --silent --max-time 2 \
      "http://127.0.0.1:$PHYSICS_ROTATIONAL_INERTIA_PORT/__physics_health__")"; then
    [[ "$rotational_inertia_health" == *"physics-experiment:rotational-inertia"* ]] || {
      echo "转动惯量实验健康标识不匹配。" >&2
      return 1
    }
    rotational_inertia_health="$(curl --fail --silent --show-error \
      http://127.0.0.1:8501/experiments/rotational-inertia/__physics_health__)"
    [[ "$rotational_inertia_health" == *"physics-experiment:rotational-inertia"* ]] || {
      echo "转动惯量实验的 8501 代理健康标识不匹配。" >&2
      return 1
    }
    echo "rotational_inertia: 直接与 8501 代理健康检查通过"
  else
    echo "rotational_inertia: 按需服务尚未启动（首次打开转动惯量页面后再检查）"
  fi
  if [[ -n "$PHYSICS_GATEWAY_HTTPS_PORT" ]]; then
    curl --insecure --fail --silent --show-error \
      "https://127.0.0.1:$PHYSICS_GATEWAY_HTTPS_PORT$PHYSICS_GATEWAY_PUBLIC_PREFIX/asr/health"
    printf '\n'
  fi
}

case "${1:-status}" in
  start) start_all ;;
  stop) stop_one gateway_https; stop_one gateway; stop_one web; stop_experiments; stop_one asr; stop_one admin ;;
  restart) bash "$APP_ROOT/manage.sh" stop; bash "$APP_ROOT/manage.sh" start ;;
  status) status_all ;;
  logs) tail -n 100 -F "$LOG_DIR"/admin.log "$LOG_DIR"/asr.log "$LOG_DIR"/web.log "$LOG_DIR"/gateway.log "$LOG_DIR"/gateway_https.log ;;
  check) check_all ;;
  *) echo "用法：$0 {start|stop|restart|status|logs|check}" >&2; exit 2 ;;
esac
