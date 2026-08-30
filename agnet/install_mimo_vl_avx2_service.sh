#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
UNIT_NAME="mimo-vl-avx2.service"
UNIT_SOURCE="$SCRIPT_DIR/$UNIT_NAME"
ENV_SOURCE="$SCRIPT_DIR/mimo-vl-avx2.env.example"
USER_CONFIG_ROOT="$HOME/.config"
UNIT_TARGET="$USER_CONFIG_ROOT/systemd/user/$UNIT_NAME"
ENV_TARGET="$USER_CONFIG_ROOT/physics-assistant/mimo-vl-avx2.env"
NO_START=0
CHECK_ONLY=0

usage() {
  cat <<'EOF'
用法：bash install_mimo_vl_avx2_service.sh [--no-start | --check]

  --no-start  安装 unit 和示例配置，但不启用或启动服务
  --check     只静态检查仓库中的 unit 和示例配置
EOF
}

while (($#)); do
  case "$1" in
    --no-start) NO_START=1 ;;
    --check) CHECK_ONLY=1 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "未知参数：$1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

require_file_text() {
  local file="$1" expected="$2"
  grep -Fq -- "$expected" "$file" || {
    echo "静态检查失败：$file 缺少 $expected" >&2
    exit 1
  }
}

[[ -f "$UNIT_SOURCE" ]] || { echo "缺少 unit：$UNIT_SOURCE" >&2; exit 1; }
[[ -f "$ENV_SOURCE" ]] || { echo "缺少环境示例：$ENV_SOURCE" >&2; exit 1; }
require_file_text "$UNIT_SOURCE" 'EnvironmentFile=%h/.config/physics-assistant/mimo-vl-avx2.env'
require_file_text "$UNIT_SOURCE" 'Restart=always'
require_file_text "$UNIT_SOURCE" '--physcpubind=${MIMO_VL_CPU_LIST}'
require_file_text "$UNIT_SOURCE" '--membind=${MIMO_VL_NUMA_NODE}'
require_file_text "$UNIT_SOURCE" '--no-mmap'
require_file_text "$UNIT_SOURCE" '--no-direct-io'
require_file_text "$UNIT_SOURCE" '--mmproj ${MIMO_VL_MMPROJ_PATH}'
require_file_text "$UNIT_SOURCE" '--ctx-checkpoints 32'
require_file_text "$UNIT_SOURCE" '--cache-type-k f16'
require_file_text "$UNIT_SOURCE" '--cache-type-v f16'
require_file_text "$UNIT_SOURCE" '--flash-attn off'
require_file_text "$UNIT_SOURCE" '--kv-offload'
require_file_text "$UNIT_SOURCE" '--n-gpu-layers 0'
if grep -Fq -- '--api-key' "$UNIT_SOURCE" || grep -Fq -- '--strict' "$UNIT_SOURCE"; then
  echo "静态检查失败：unit 不得把密钥放入 argv，也不得使用对进程无效的 numactl --strict。" >&2
  exit 1
fi
if grep -Fq -- '--numa numactl' "$UNIT_SOURCE"; then
  echo "静态检查失败：llama-server 内部 NUMA 调度会扩大 CPU 亲和性；只允许外层 numactl。" >&2
  exit 1
fi
require_file_text "$ENV_SOURCE" 'LLAMA_API_KEY=""'
require_file_text "$ENV_SOURCE" 'MIMO_VL_MODEL_ALIAS=mimo-vl-local-prod'
require_file_text "$ENV_SOURCE" 'MIMO_VL_PORT=1237'
require_file_text "$ENV_SOURCE" 'MIMO_VL_CTX_SIZE=128000'
require_file_text "$ENV_SOURCE" 'MIMO_VL_PARALLEL=4'
require_file_text "$ENV_SOURCE" 'MIMO_VL_NUMA_NODE=0'
require_file_text "$ENV_SOURCE" 'MIMO_VL_CPU_LIST=0-127'

if ((CHECK_ONLY)); then
  echo "MiMo-VL AVX2 unit 与环境示例静态检查通过。"
  exit 0
fi

[[ "$(uname -s)" == "Linux" ]] || {
  echo "此安装器只用于 Rocky Linux，不会在当前系统安装服务。" >&2
  exit 1
}
if [[ ${EUID:-$(id -u)} -eq 0 ]]; then
  echo "请使用运行模型的普通用户执行，不要使用 sudo。" >&2
  exit 1
fi
for command in install numactl seq systemctl; do
  command -v "$command" >/dev/null 2>&1 || {
    echo "系统缺少命令：$command；请让管理员预先安装。" >&2
    exit 1
  }
done

TRUE_BIN="$(type -P true)"
[[ -x "$TRUE_BIN" ]] || { echo "找不到外部 true 命令，无法执行 NUMA dry-run。" >&2; exit 1; }

mkdir -p -- "$(dirname -- "$UNIT_TARGET")" "$(dirname -- "$ENV_TARGET")"
config_created=0
if [[ ! -f "$ENV_TARGET" ]]; then
  install -m 0600 "$ENV_SOURCE" "$ENV_TARGET"
  config_created=1
else
  chmod 0600 "$ENV_TARGET"
fi
install -m 0644 "$UNIT_SOURCE" "$UNIT_TARGET"
systemctl --user daemon-reload

if ((config_created)); then
  echo "已创建配置：$ENV_TARGET"
  echo "请填写 llama-server、GGUF、mmproj 的绝对路径和独立 API key，然后重新运行本脚本。"
  exit 0
fi
if ((NO_START)); then
  echo "已安装用户级 unit：$UNIT_TARGET"
  echo "服务尚未启用；配置完成后不带 --no-start 重新运行本脚本。"
  exit 0
fi

required_variables=(
  MIMO_VL_SERVER_BIN MIMO_VL_MODEL_PATH MIMO_VL_MMPROJ_PATH LLAMA_API_KEY
  MIMO_VL_MODEL_ALIAS MIMO_VL_HOST MIMO_VL_PORT MIMO_VL_CTX_SIZE MIMO_VL_PARALLEL
  MIMO_VL_NUMA_NODE MIMO_VL_CPU_LIST MIMO_VL_THREADS MIMO_VL_THREADS_BATCH
  MIMO_VL_BATCH_SIZE MIMO_VL_UBATCH_SIZE
)
for variable_name in "${required_variables[@]}"; do unset "$variable_name"; done

is_allowed_variable() {
  local candidate="$1" allowed
  for allowed in "${required_variables[@]}"; do
    [[ "$candidate" == "$allowed" ]] && return 0
  done
  return 1
}

# 解析专用 EnvironmentFile，但绝不把它作为 shell 代码执行。
while IFS= read -r config_line || [[ -n "$config_line" ]]; do
  config_line="${config_line%$'\r'}"
  [[ "$config_line" =~ ^[[:space:]]*$ ]] && continue
  [[ "$config_line" =~ ^[[:space:]]*# ]] && continue
  if [[ ! "$config_line" =~ ^([A-Z][A-Z0-9_]*)=(.*)$ ]]; then
    echo "环境文件含无效行，必须使用 NAME=value：$config_line" >&2
    exit 1
  fi
  variable_name="${BASH_REMATCH[1]}"
  raw_value="${BASH_REMATCH[2]}"
  is_allowed_variable "$variable_name" || {
    echo "环境文件含未知配置项：$variable_name" >&2
    exit 1
  }
  if [[ "$raw_value" =~ ^\"([^\"]*)\"$ ]]; then
    parsed_value="${BASH_REMATCH[1]}"
  elif [[ "$raw_value" =~ ^[A-Za-z0-9_./:@,+~-]*$ ]]; then
    parsed_value="$raw_value"
  else
    echo "配置 $variable_name 必须是简单值或一对双引号包围的值。" >&2
    exit 1
  fi
  printf -v "$variable_name" '%s' "$parsed_value"
done < "$ENV_TARGET"

for variable_name in "${required_variables[@]}"; do
  [[ -n "${!variable_name:-}" ]] || { echo "配置缺少必填项：$variable_name" >&2; exit 1; }
done
[[ "$LLAMA_API_KEY" =~ ^[A-Za-z0-9._~-]{32,256}$ ]] || {
  echo "LLAMA_API_KEY 必须是 32-256 位安全字符；建议使用 openssl rand -hex 32。" >&2
  exit 1
}
for path_variable in MIMO_VL_SERVER_BIN MIMO_VL_MODEL_PATH MIMO_VL_MMPROJ_PATH; do
  [[ "${!path_variable}" == /* ]] || { echo "$path_variable 必须是绝对路径。" >&2; exit 1; }
done
[[ -x "$MIMO_VL_SERVER_BIN" ]] || { echo "llama-server 不存在或不可执行：$MIMO_VL_SERVER_BIN" >&2; exit 1; }
[[ -r "$MIMO_VL_MODEL_PATH" ]] || { echo "模型文件不存在或不可读：$MIMO_VL_MODEL_PATH" >&2; exit 1; }
[[ -r "$MIMO_VL_MMPROJ_PATH" ]] || { echo "mmproj 文件不存在或不可读：$MIMO_VL_MMPROJ_PATH" >&2; exit 1; }

[[ "$MIMO_VL_MODEL_ALIAS" == "mimo-vl-local-prod" ]] || { echo "MIMO_VL_MODEL_ALIAS 必须保持 mimo-vl-local-prod。" >&2; exit 1; }
[[ "$MIMO_VL_HOST" == "127.0.0.1" ]] || { echo "MIMO_VL_HOST 必须保持 127.0.0.1。" >&2; exit 1; }
[[ "$MIMO_VL_PORT" == "1237" ]] || { echo "MIMO_VL_PORT 必须保持 1237。" >&2; exit 1; }
[[ "$MIMO_VL_CTX_SIZE" == "128000" ]] || { echo "MIMO_VL_CTX_SIZE 必须保持 128000。" >&2; exit 1; }
[[ "$MIMO_VL_PARALLEL" == "4" ]] || { echo "MIMO_VL_PARALLEL 必须保持 4。" >&2; exit 1; }
[[ "$MIMO_VL_NUMA_NODE" == "0" ]] || { echo "MIMO_VL_NUMA_NODE 必须保持 0。" >&2; exit 1; }
[[ "$MIMO_VL_CPU_LIST" == "0-127" ]] || { echo "MIMO_VL_CPU_LIST 必须保持 0-127。" >&2; exit 1; }
[[ -d /sys/devices/system/node/node0 ]] || { echo "当前机器没有 NUMA node 0，拒绝启动。" >&2; exit 1; }
for cpu_number in $(seq 0 127); do
  [[ -e "/sys/devices/system/node/node0/cpu${cpu_number}" ]] || {
    echo "CPU ${cpu_number} 不属于 NUMA node 0，拒绝启动。" >&2
    exit 1
  }
  online_file="/sys/devices/system/cpu/cpu${cpu_number}/online"
  if [[ -f "$online_file" && "$(<"$online_file")" != "1" ]]; then
    echo "CPU ${cpu_number} 当前不在线，拒绝启动。" >&2
    exit 1
  fi
done
if ! numactl --physcpubind="$MIMO_VL_CPU_LIST" --membind="$MIMO_VL_NUMA_NODE" "$TRUE_BIN"; then
  echo "当前用户的 cpuset 或 NUMA 内存策略不允许 node 0 / CPU 0-127，拒绝启动。" >&2
  exit 1
fi

server_help="$("$MIMO_VL_SERVER_BIN" --help 2>&1 || true)"
for required_option in --no-mmap --no-direct-io --mmproj --ctx-checkpoints --cache-type-k --cache-type-v --flash-attn --kv-offload --n-gpu-layers; do
  [[ "$server_help" == *"$required_option"* ]] || {
    echo "当前 llama-server 不支持 $required_option；请使用支持该参数的固定版本。" >&2
    exit 1
  }
done

systemctl --user enable "$UNIT_NAME"
if systemctl --user is-active --quiet "$UNIT_NAME"; then
  systemctl --user restart "$UNIT_NAME"
else
  systemctl --user start "$UNIT_NAME"
fi
echo "MiMo-VL AVX2 用户服务已启用并开始加载模型。"
echo "状态：systemctl --user status $UNIT_NAME"
echo "日志：journalctl --user -u $UNIT_NAME -f"
echo "NUMA 验收：numastat -p \$(systemctl --user show -p MainPID --value $UNIT_NAME)"
echo "匿名权重页验收：grep -E 'anon|heap' /proc/\$(systemctl --user show -p MainPID --value $UNIT_NAME)/numa_maps"

if command -v loginctl >/dev/null 2>&1; then
  linger="$(loginctl show-user "$(id -un)" -p Linger --value 2>/dev/null || true)"
  if [[ "$linger" != "yes" ]]; then
    echo "提示：若需无人登录也自动启动，请让管理员执行：sudo loginctl enable-linger $(id -un)"
  fi
fi
