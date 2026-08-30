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
export PHYSICS_VISCOSITY_PORT="${PHYSICS_VISCOSITY_PORT:-9392}"
export PHYSICS_VISCOSITY_UPSTREAM="${PHYSICS_VISCOSITY_UPSTREAM:-http://127.0.0.1:$PHYSICS_VISCOSITY_PORT}"
export PHYSICS_SPECIFIC_HEAT_PORT="${PHYSICS_SPECIFIC_HEAT_PORT:-9393}"
export PHYSICS_SPECIFIC_HEAT_UPSTREAM="${PHYSICS_SPECIFIC_HEAT_UPSTREAM:-http://127.0.0.1:$PHYSICS_SPECIFIC_HEAT_PORT}"
export PHYSICS_FRANCK_HERTZ_PORT="${PHYSICS_FRANCK_HERTZ_PORT:-9394}"
export PHYSICS_FRANCK_HERTZ_UPSTREAM="${PHYSICS_FRANCK_HERTZ_UPSTREAM:-http://127.0.0.1:$PHYSICS_FRANCK_HERTZ_PORT}"
export PHYSICS_TEMPERATURE_SENSOR_PORT="${PHYSICS_TEMPERATURE_SENSOR_PORT:-9395}"
export PHYSICS_TEMPERATURE_SENSOR_UPSTREAM="${PHYSICS_TEMPERATURE_SENSOR_UPSTREAM:-http://127.0.0.1:$PHYSICS_TEMPERATURE_SENSOR_PORT}"
export PHYSICS_WHEATSTONE_BRIDGE_PORT="${PHYSICS_WHEATSTONE_BRIDGE_PORT:-9396}"
export PHYSICS_WHEATSTONE_BRIDGE_UPSTREAM="${PHYSICS_WHEATSTONE_BRIDGE_UPSTREAM:-http://127.0.0.1:$PHYSICS_WHEATSTONE_BRIDGE_PORT}"
export PHYSICS_HALL_EFFECT_PORT="${PHYSICS_HALL_EFFECT_PORT:-9397}"
export PHYSICS_HALL_EFFECT_UPSTREAM="${PHYSICS_HALL_EFFECT_UPSTREAM:-http://127.0.0.1:$PHYSICS_HALL_EFFECT_PORT}"
export PHYSICS_MAGNETIC_HYSTERESIS_PORT="${PHYSICS_MAGNETIC_HYSTERESIS_PORT:-9398}"
export PHYSICS_MAGNETIC_HYSTERESIS_UPSTREAM="${PHYSICS_MAGNETIC_HYSTERESIS_UPSTREAM:-http://127.0.0.1:$PHYSICS_MAGNETIC_HYSTERESIS_PORT}"
export PHYSICS_THIN_LENS_FOCAL_PORT="${PHYSICS_THIN_LENS_FOCAL_PORT:-9399}"
export PHYSICS_THIN_LENS_FOCAL_UPSTREAM="${PHYSICS_THIN_LENS_FOCAL_UPSTREAM:-http://127.0.0.1:$PHYSICS_THIN_LENS_FOCAL_PORT}"
export PHYSICS_PRISM_REFRACTIVE_INDEX_PORT="${PHYSICS_PRISM_REFRACTIVE_INDEX_PORT:-9400}"
export PHYSICS_PRISM_REFRACTIVE_INDEX_UPSTREAM="${PHYSICS_PRISM_REFRACTIVE_INDEX_UPSTREAM:-http://127.0.0.1:$PHYSICS_PRISM_REFRACTIVE_INDEX_PORT}"
export PHYSICS_THERMAL_CONDUCTIVITY_PORT="${PHYSICS_THERMAL_CONDUCTIVITY_PORT:-9401}"
export PHYSICS_THERMAL_CONDUCTIVITY_UPSTREAM="${PHYSICS_THERMAL_CONDUCTIVITY_UPSTREAM:-http://127.0.0.1:$PHYSICS_THERMAL_CONDUCTIVITY_PORT}"
export PHYSICS_CJK_FONT="${PHYSICS_CJK_FONT:-$RUNTIME_ROOT/fonts/NotoSansCJKsc-Regular.otf}"
export PHYSICS_ASR_MODEL_DIR="${PHYSICS_ASR_MODEL_DIR:-$RUNTIME_ROOT/models/paraformer-zh-streaming}"
if [[ "$PHYSICS_ASR_MODEL_DIR" != /* ]]; then
  export PHYSICS_ASR_MODEL_DIR="$APP_ROOT/${PHYSICS_ASR_MODEL_DIR#./}"
fi
export PHYSICS_ASR_PORT="${PHYSICS_ASR_PORT:-8604}"
export PHYSICS_ASR_UPSTREAM="http://127.0.0.1:$PHYSICS_ASR_PORT"
export PHYSICS_CHAT_MODEL_KEY="${PHYSICS_CHAT_MODEL_KEY:-xiaomi-mimo-vl-miloco-7b}"
export PHYSICS_CHAT_MODEL_IDENTIFIER="${PHYSICS_CHAT_MODEL_IDENTIFIER:-mimo-vl-local-prod}"
export PHYSICS_CHAT_MODEL_CONTEXT="${PHYSICS_CHAT_MODEL_CONTEXT:-128000}"
export PHYSICS_CHAT_MODEL_PARALLEL="${PHYSICS_CHAT_MODEL_PARALLEL:-4}"
export PHYSICS_VISION_MODEL_KEY="${PHYSICS_VISION_MODEL_KEY:-xiaomi-mimo-vl-miloco-7b}"
export PHYSICS_VISION_MODEL_IDENTIFIER="${PHYSICS_VISION_MODEL_IDENTIFIER:-mimo-vl-local-prod}"
export PHYSICS_VISION_MODEL_CONTEXT="${PHYSICS_VISION_MODEL_CONTEXT:-128000}"
export PHYSICS_VISION_MODEL_PARALLEL="${PHYSICS_VISION_MODEL_PARALLEL:-4}"
export PHYSICS_MODEL="${PHYSICS_MODEL:-$PHYSICS_CHAT_MODEL_IDENTIFIER}"
export PHYSICS_VISION_MODEL="${PHYSICS_VISION_MODEL:-$PHYSICS_VISION_MODEL_IDENTIFIER}"
export PHYSICS_BASE_URL="${PHYSICS_BASE_URL:-http://127.0.0.1:1237/v1}"
export PHYSICS_EXAM_BASE_URL="${PHYSICS_EXAM_BASE_URL:-http://127.0.0.1:1236/v1}"
export PHYSICS_EXAM_MODEL="${PHYSICS_EXAM_MODEL:-deepseek/deepseek-v4-flash-avx512}"
export PHYSICS_MODEL_STARTUP_TIMEOUT_SECONDS="${PHYSICS_MODEL_STARTUP_TIMEOUT_SECONDS:-1800}"
export PHYSICS_USE_LEGACY_LM_STUDIO="${PHYSICS_USE_LEGACY_LM_STUDIO:-0}"
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

model_api_ready() {
  local base_url="$1" expected_model="$2" api_key="$3"
  MODEL_API_BASE_URL="$base_url" \
  MODEL_API_EXPECTED_MODEL="$expected_model" \
  MODEL_API_KEY="$api_key" \
  "$PYTHON" - <<'PY'
import json
import os
import urllib.request

base_url = os.environ["MODEL_API_BASE_URL"].rstrip("/")
expected = os.environ["MODEL_API_EXPECTED_MODEL"]
headers = {"Accept": "application/json"}
api_key = os.environ.get("MODEL_API_KEY", "")
if api_key:
    headers["Authorization"] = f"Bearer {api_key}"
request = urllib.request.Request(f"{base_url}/models", headers=headers)
try:
    with urllib.request.urlopen(request, timeout=5) as response:
        payload = json.load(response)
except Exception:
    raise SystemExit(1)
models = payload.get("data", []) if isinstance(payload, dict) else []
model_ids = {
    str(item.get("id", ""))
    for item in models
    if isinstance(item, dict) and item.get("id")
}
raise SystemExit(0 if expected in model_ids else 1)
PY
}

validate_dedicated_model_routes() {
  [[ "$PHYSICS_MODEL" == "$PHYSICS_CHAT_MODEL_IDENTIFIER" ]] || {
    echo "PHYSICS_MODEL 必须等于 $PHYSICS_CHAT_MODEL_IDENTIFIER" >&2
    return 1
  }
  [[ "$PHYSICS_VISION_MODEL" == "$PHYSICS_VISION_MODEL_IDENTIFIER" ]] || {
    echo "PHYSICS_VISION_MODEL 必须等于 $PHYSICS_VISION_MODEL_IDENTIFIER" >&2
    return 1
  }
  [[ "${PHYSICS_BASE_URL%/}" == "http://127.0.0.1:1237/v1" ]] || {
    echo "生产 MiMo-VL 必须使用 PHYSICS_BASE_URL=http://127.0.0.1:1237/v1" >&2
    return 1
  }
  [[ "${PHYSICS_EXAM_BASE_URL%/}" == "http://127.0.0.1:1236/v1" ]] || {
    echo "教研考试必须使用 PHYSICS_EXAM_BASE_URL=http://127.0.0.1:1236/v1" >&2
    return 1
  }
  [[ "$PHYSICS_EXAM_MODEL" == "deepseek/deepseek-v4-flash-avx512" ]] || {
    echo "PHYSICS_EXAM_MODEL 必须等于 deepseek/deepseek-v4-flash-avx512" >&2
    return 1
  }
}

check_dedicated_model_apis() {
  validate_dedicated_model_routes
  local exam_api_key="${PHYSICS_EXAM_API_KEY:-${PHYSICS_API_KEY:-}}"
  model_api_ready "$PHYSICS_BASE_URL" "$PHYSICS_MODEL" "${PHYSICS_API_KEY:-}" || {
    echo "MiMo-VL 常驻接口未就绪或模型别名不匹配：$PHYSICS_BASE_URL" >&2
    return 1
  }
  model_api_ready "$PHYSICS_EXAM_BASE_URL" "$PHYSICS_EXAM_MODEL" "$exam_api_key" || {
    echo "DeepSeek 常驻接口未就绪或模型别名不匹配：$PHYSICS_EXAM_BASE_URL" >&2
    return 1
  }
  echo "模型接口正常：MiMo-VL 1237（NUMA0）与 DeepSeek 1236（NUMA1）"
}

wait_dedicated_model_apis() {
  validate_dedicated_model_routes
  [[ "$PHYSICS_MODEL_STARTUP_TIMEOUT_SECONDS" =~ ^[0-9]+$ ]] \
    && (( PHYSICS_MODEL_STARTUP_TIMEOUT_SECONDS >= 1 )) \
    && (( PHYSICS_MODEL_STARTUP_TIMEOUT_SECONDS <= 7200 )) || {
      echo "PHYSICS_MODEL_STARTUP_TIMEOUT_SECONDS 必须是 1-7200 秒。" >&2
      return 1
    }
  local deadline=$((SECONDS + PHYSICS_MODEL_STARTUP_TIMEOUT_SECONDS))
  echo "等待常驻模型接口完成冷加载（最长 ${PHYSICS_MODEL_STARTUP_TIMEOUT_SECONDS} 秒）……"
  while (( SECONDS < deadline )); do
    if check_dedicated_model_apis >/dev/null 2>&1; then
      check_dedicated_model_apis
      return 0
    fi
    sleep 5
  done
  echo "常驻模型接口等待超时；请检查 mimo-vl-avx2.service 与 deepseek-avx512.service 日志。" >&2
  return 1
}

local_llm_loaded() {
  local lms_bin="$1" identifier="$2" model_key="$3" context="$4" parallel="$5"
  local models_json attempt parse_status
  for attempt in {1..5}; do
    if models_json="$("$lms_bin" ps --json 2>/dev/null)"; then
      if MODELS_JSON="$models_json" "$PYTHON" -c '
import json
import os
import sys

try:
    models = json.loads(os.environ.get("MODELS_JSON", "[]"))
except (json.JSONDecodeError, TypeError):
    raise SystemExit(2)
if not isinstance(models, list) or not all(isinstance(item, dict) for item in models):
    raise SystemExit(2)
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
' "$identifier" "$model_key" "$context" "$parallel"; then
        return 0
      else
        parse_status="$?"
        [[ "$parse_status" -eq 1 ]] && return 1
      fi
    fi
    (( attempt < 5 )) && sleep 1
  done
  return 1
}

ensure_one_local_llm() {
  local lms_bin="$1" label="$2" model_key="$3" identifier="$4" context="$5" parallel="$6"
  if ! local_llm_loaded "$lms_bin" "$identifier" "$model_key" "$context" "$parallel"; then
    "$lms_bin" unload "$identifier" >/dev/null 2>&1 || true
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
  if [[ "$PHYSICS_CHAT_MODEL_KEY" == "$PHYSICS_VISION_MODEL_KEY" \
        && "$PHYSICS_CHAT_MODEL_IDENTIFIER" == "$PHYSICS_VISION_MODEL_IDENTIFIER" \
        && "$PHYSICS_CHAT_MODEL_CONTEXT" == "$PHYSICS_VISION_MODEL_CONTEXT" \
        && "$PHYSICS_CHAT_MODEL_PARALLEL" == "$PHYSICS_VISION_MODEL_PARALLEL" ]]; then
    ensure_one_local_llm "$lms_bin" "本机 MiMo-VL 对话与图片模型" \
      "$PHYSICS_CHAT_MODEL_KEY" "$PHYSICS_CHAT_MODEL_IDENTIFIER" \
      "$PHYSICS_CHAT_MODEL_CONTEXT" "$PHYSICS_CHAT_MODEL_PARALLEL"
  else
    ensure_one_local_llm "$lms_bin" "本机对话模型" \
      "$PHYSICS_CHAT_MODEL_KEY" "$PHYSICS_CHAT_MODEL_IDENTIFIER" \
      "$PHYSICS_CHAT_MODEL_CONTEXT" "$PHYSICS_CHAT_MODEL_PARALLEL"
    ensure_one_local_llm "$lms_bin" "本机图片模型" \
      "$PHYSICS_VISION_MODEL_KEY" "$PHYSICS_VISION_MODEL_IDENTIFIER" \
      "$PHYSICS_VISION_MODEL_CONTEXT" "$PHYSICS_VISION_MODEL_PARALLEL"
  fi
}

ensure_model_apis() {
  if [[ "$PHYSICS_USE_LEGACY_LM_STUDIO" == "1" ]]; then
    echo "警告：正在使用兼容模式，由 manage.sh 管理旧 LM Studio 1235 服务。" >&2
    ensure_local_llms
    return
  fi
  [[ "$PHYSICS_USE_LEGACY_LM_STUDIO" == "0" ]] || {
    echo "PHYSICS_USE_LEGACY_LM_STUDIO 只能设为 0 或 1。" >&2
    return 1
  }
  command -v systemctl >/dev/null 2>&1 || {
    echo "未找到 systemctl，无法启动两个用户级常驻模型服务。" >&2
    return 1
  }
  local unit
  for unit in mimo-vl-avx2.service deepseek-avx512.service; do
    systemctl --user cat "$unit" >/dev/null 2>&1 || {
      echo "缺少用户级 unit：$unit；请先运行对应安装脚本。" >&2
      return 1
    }
  done
  # start 对已运行的 unit 是幂等操作，不会重启或重复加载模型。
  systemctl --user start mimo-vl-avx2.service deepseek-avx512.service
  wait_dedicated_model_apis
}

start_all() {
  [[ -x "$PYTHON" ]] || { echo "尚未安装，请先执行 bash install.sh" >&2; return 1; }
  ensure_model_apis
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
      *"$APP_ROOT/agnet/experiments/lissajous/web.jl"*|*"$APP_ROOT/agnet/experiments/sound_speed/web.jl"*|*"$APP_ROOT/agnet/experiments/electron_em/web.jl"*|*"$APP_ROOT/agnet/experiments/photoelectric/web.jl"*|*"$APP_ROOT/agnet/experiments/biprism/web.jl"*|*"$APP_ROOT/agnet/experiments/newton_rings/web.jl"*|*"$APP_ROOT/agnet/experiments/young_modulus/web.jl"*|*"$APP_ROOT/agnet/experiments/rotational_inertia/web.jl"*|*"$APP_ROOT/agnet/experiments/viscosity/web.jl"*|*"$APP_ROOT/agnet/experiments/specific_heat/web.jl"*|*"$APP_ROOT/agnet/experiments/franck_hertz/web.jl"*|*"$APP_ROOT/agnet/experiments/temperature_sensor/web.jl"*|*"$APP_ROOT/agnet/experiments/wheatstone_bridge/web.jl"*|*"$APP_ROOT/agnet/experiments/hall_effect/web.jl"*|*"$APP_ROOT/agnet/experiments/magnetic_hysteresis/web.jl"*|*"$APP_ROOT/agnet/experiments/thin_lens_focal/web.jl"*|*"$APP_ROOT/agnet/experiments/prism_refractive_index/web.jl"*|*"$APP_ROOT/agnet/experiments/thermal_conductivity/web.jl"*)
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
  if command -v systemctl >/dev/null 2>&1; then
    local unit
    for unit in mimo-vl-avx2.service deepseek-avx512.service; do
      if systemctl --user is-active --quiet "$unit"; then
        echo "$unit: 运行中"
      else
        echo "$unit: 未运行"
      fi
    done
  fi
}

check_experiment_if_running() {
  local name="$1" port="$2" slug="$3" marker="$4" health
  if health="$(curl --fail --silent --max-time 2 \
      "http://127.0.0.1:$port/__physics_health__")"; then
    [[ "$health" == *"$marker"* ]] || {
      echo "$name 实验健康标识不匹配。" >&2
      return 1
    }
    health="$(curl --fail --silent --show-error \
      "http://127.0.0.1:8501/experiments/$slug/__physics_health__")"
    [[ "$health" == *"$marker"* ]] || {
      echo "$name 实验的 8501 代理健康标识不匹配。" >&2
      return 1
    }
    echo "$slug: 直接与 8501 代理健康检查通过"
  else
    echo "$slug: 按需服务尚未启动（首次打开$name 页面后再检查）"
  fi
}

check_all() {
  if [[ "$PHYSICS_USE_LEGACY_LM_STUDIO" == "1" ]]; then
    curl --fail --silent --show-error http://127.0.0.1:1235/v1/models >/dev/null
    echo "旧 LM Studio 1235 接口正常"
  else
    check_dedicated_model_apis
  fi
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
  local viscosity_health
  if viscosity_health="$(curl --fail --silent --max-time 2 \
      "http://127.0.0.1:$PHYSICS_VISCOSITY_PORT/__physics_health__")"; then
    [[ "$viscosity_health" == *"physics-experiment:viscosity"* ]] || {
      echo "粘滞系数实验健康标识不匹配。" >&2
      return 1
    }
    viscosity_health="$(curl --fail --silent --show-error \
      http://127.0.0.1:8501/experiments/viscosity/__physics_health__)"
    [[ "$viscosity_health" == *"physics-experiment:viscosity"* ]] || {
      echo "粘滞系数实验的 8501 代理健康标识不匹配。" >&2
      return 1
    }
    echo "viscosity: 直接与 8501 代理健康检查通过"
  else
    echo "viscosity: 按需服务尚未启动（首次打开粘滞系数页面后再检查）"
  fi
  local specific_heat_health
  if specific_heat_health="$(curl --fail --silent --max-time 2 \
      "http://127.0.0.1:$PHYSICS_SPECIFIC_HEAT_PORT/__physics_health__")"; then
    [[ "$specific_heat_health" == *"physics-experiment:specific-heat"* ]] || {
      echo "固体比热容实验健康标识不匹配。" >&2
      return 1
    }
    specific_heat_health="$(curl --fail --silent --show-error \
      http://127.0.0.1:8501/experiments/specific-heat/__physics_health__)"
    [[ "$specific_heat_health" == *"physics-experiment:specific-heat"* ]] || {
      echo "固体比热容实验的 8501 代理健康标识不匹配。" >&2
      return 1
    }
    echo "specific_heat: 直接与 8501 代理健康检查通过"
  else
    echo "specific_heat: 按需服务尚未启动（首次打开固体比热容页面后再检查）"
  fi
  local franck_hertz_health
  if franck_hertz_health="$(curl --fail --silent --max-time 2 \
      "http://127.0.0.1:$PHYSICS_FRANCK_HERTZ_PORT/__physics_health__")"; then
    [[ "$franck_hertz_health" == *"physics-experiment:franck-hertz"* ]] || {
      echo "弗兰克-赫兹实验健康标识不匹配。" >&2
      return 1
    }
    franck_hertz_health="$(curl --fail --silent --show-error \
      http://127.0.0.1:8501/experiments/franck-hertz/__physics_health__)"
    [[ "$franck_hertz_health" == *"physics-experiment:franck-hertz"* ]] || {
      echo "弗兰克-赫兹实验的 8501 代理健康标识不匹配。" >&2
      return 1
    }
    echo "franck_hertz: 直接与 8501 代理健康检查通过"
  else
    echo "franck_hertz: 按需服务尚未启动（首次打开弗兰克-赫兹页面后再检查）"
  fi
  check_experiment_if_running \
    "温度传感器" "$PHYSICS_TEMPERATURE_SENSOR_PORT" \
    "temperature-sensor" "physics-experiment:temperature-sensor"
  check_experiment_if_running \
    "惠斯通电桥" "$PHYSICS_WHEATSTONE_BRIDGE_PORT" \
    "wheatstone-bridge" "physics-experiment:wheatstone-bridge"
  check_experiment_if_running \
    "霍尔效应" "$PHYSICS_HALL_EFFECT_PORT" \
    "hall-effect" "physics-experiment:hall-effect"
  check_experiment_if_running \
    "铁磁滞回线" "$PHYSICS_MAGNETIC_HYSTERESIS_PORT" \
    "magnetic-hysteresis" "physics-experiment:magnetic-hysteresis"
  check_experiment_if_running \
    "薄透镜焦距" "$PHYSICS_THIN_LENS_FOCAL_PORT" \
    "thin-lens-focal" "physics-experiment:thin-lens-focal"
  check_experiment_if_running \
    "三棱镜折射率" "$PHYSICS_PRISM_REFRACTIVE_INDEX_PORT" \
    "prism-refractive-index" "physics-experiment:prism-refractive-index"
  check_experiment_if_running \
    "固体热传导系数" "$PHYSICS_THERMAL_CONDUCTIVITY_PORT" \
    "thermal-conductivity" "physics-experiment:thermal-conductivity"
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
