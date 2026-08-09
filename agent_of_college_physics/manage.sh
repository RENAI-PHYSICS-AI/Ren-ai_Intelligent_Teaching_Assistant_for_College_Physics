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
export PHYSICS_CJK_FONT="${PHYSICS_CJK_FONT:-$RUNTIME_ROOT/fonts/NotoSansCJKsc-Regular.otf}"

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

start_all() {
  [[ -x "$PYTHON" ]] || { echo "尚未安装，请先执行 bash install.sh" >&2; return 1; }
  start_one admin "$PYTHON" -m uvicorn admin_api:app \
    --host 127.0.0.1 --port 8603 --proxy-headers --forwarded-allow-ips=127.0.0.1
  start_one web "$APP_ROOT/agnet/.venv/bin/streamlit" run app.py \
    --server.address=127.0.0.1 --server.port=8502 --server.headless=true \
    --server.fileWatcherType=none --browser.gatherUsageStats=false
  wait_url http://127.0.0.1:8603/health "管理员服务"
  wait_url http://127.0.0.1:8502/_stcore/health "智能助教"
  start_one gateway "$PYTHON" gateway.py
  wait_url http://127.0.0.1:8501/_stcore/health "8501 统一入口"
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
      *"$APP_ROOT/agnet/experiments/lissajous/web.jl"*|*"$APP_ROOT/agnet/experiments/sound_speed/web.jl"*)
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
  for name in admin web gateway; do
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
  curl --fail --silent --show-error http://127.0.0.1:8501/agent-health/admin; printf '\n'
  curl --fail --silent --show-error http://127.0.0.1:8501/_stcore/health; printf '\n'
}

case "${1:-status}" in
  start) start_all ;;
  stop) stop_one gateway; stop_one web; stop_experiments; stop_one admin ;;
  restart) bash "$APP_ROOT/manage.sh" stop; bash "$APP_ROOT/manage.sh" start ;;
  status) status_all ;;
  logs) tail -n 100 -F "$LOG_DIR"/admin.log "$LOG_DIR"/web.log "$LOG_DIR"/gateway.log ;;
  check) check_all ;;
  *) echo "用法：$0 {start|stop|restart|status|logs|check}" >&2; exit 2 ;;
esac
