#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
UNIT_NAME="deepseek-avx512.service"
UNIT_SOURCE="$SCRIPT_DIR/$UNIT_NAME"
ENV_SOURCE="$SCRIPT_DIR/deepseek-avx512.env.example"
USER_CONFIG_ROOT="$HOME/.config"
UNIT_TARGET="$USER_CONFIG_ROOT/systemd/user/$UNIT_NAME"
ENV_TARGET="$USER_CONFIG_ROOT/physics-assistant/deepseek-avx512.env"
NO_START=0
CHECK_ONLY=0

usage() {
  cat <<'EOF'
用法：bash install_deepseek_avx512_service.sh [--no-start | --check]

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
  local file="$1"
  local expected="$2"
  grep -Fq -- "$expected" "$file" || {
    echo "静态检查失败：$file 缺少 $expected" >&2
    exit 1
  }
}

[[ -f "$UNIT_SOURCE" ]] || { echo "缺少 unit：$UNIT_SOURCE" >&2; exit 1; }
[[ -f "$ENV_SOURCE" ]] || { echo "缺少环境示例：$ENV_SOURCE" >&2; exit 1; }
require_file_text "$UNIT_SOURCE" 'EnvironmentFile=%h/.config/physics-assistant/deepseek-avx512.env'
require_file_text "$UNIT_SOURCE" 'Restart=always'
require_file_text "$UNIT_SOURCE" '--physcpubind=${DEEPSEEK_AVX512_CPU_LIST}'
require_file_text "$UNIT_SOURCE" '--membind=${DEEPSEEK_AVX512_NUMA_NODE}'
require_file_text "$UNIT_SOURCE" '--load-mode dio'
if grep -Fq -- '--api-key' "$UNIT_SOURCE" || grep -Fq -- '--strict' "$UNIT_SOURCE"; then
  echo "静态检查失败：unit 不得把密钥放入 argv，也不得使用对进程无效的 numactl --strict。" >&2
  exit 1
fi
if grep -Fq -- '--numa numactl' "$UNIT_SOURCE"; then
  echo "静态检查失败：llama-server 内部 NUMA 调度会扩大 CPU 亲和性；只允许外层 numactl。" >&2
  exit 1
fi
require_file_text "$ENV_SOURCE" 'LLAMA_API_KEY=""'
require_file_text "$ENV_SOURCE" 'DEEPSEEK_AVX512_CTX_SIZE=1048576'
require_file_text "$ENV_SOURCE" 'DEEPSEEK_AVX512_PARALLEL=1'
require_file_text "$ENV_SOURCE" 'DEEPSEEK_AVX512_NUMA_NODE=1'
require_file_text "$ENV_SOURCE" 'DEEPSEEK_AVX512_CPU_LIST=128-255'

if ((CHECK_ONLY)); then
  echo "DeepSeek AVX-512 unit 与环境示例静态检查通过。"
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
[[ -x "$TRUE_BIN" ]] || {
  echo "找不到外部 true 命令，无法执行 NUMA dry-run。" >&2
  exit 1
}

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
  echo "请填写 llama-server、GGUF 分片首文件的绝对路径和独立 API key，然后重新运行本脚本。"
  exit 0
fi

if ((NO_START)); then
  echo "已安装用户级 unit：$UNIT_TARGET"
  echo "服务尚未启用；配置完成后不带 --no-start 重新运行本脚本。"
  exit 0
fi

required_variables=(
  DEEPSEEK_AVX512_SERVER_BIN
  DEEPSEEK_AVX512_MODEL_PATH
  LLAMA_API_KEY
  DEEPSEEK_AVX512_MODEL_ALIAS
  DEEPSEEK_AVX512_HOST
  DEEPSEEK_AVX512_PORT
  DEEPSEEK_AVX512_CTX_SIZE
  DEEPSEEK_AVX512_PARALLEL
  DEEPSEEK_AVX512_NUMA_NODE
  DEEPSEEK_AVX512_CPU_LIST
  DEEPSEEK_AVX512_THREADS
  DEEPSEEK_AVX512_THREADS_BATCH
  DEEPSEEK_AVX512_BATCH_SIZE
  DEEPSEEK_AVX512_UBATCH_SIZE
)
for variable_name in "${required_variables[@]}"; do
  unset "$variable_name"
done

is_allowed_variable() {
  local candidate="$1"
  local allowed
  for allowed in "${required_variables[@]}"; do
    [[ "$candidate" == "$allowed" ]] && return 0
  done
  return 1
}

# Parse the small dedicated EnvironmentFile without executing it as shell code.
# Accepted values are either unquoted tokens or one pair of double quotes.
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
  [[ -n "${!variable_name:-}" ]] || {
    echo "配置缺少必填项：$variable_name" >&2
    exit 1
  }
done

[[ "$LLAMA_API_KEY" =~ ^[A-Za-z0-9._~-]{32,256}$ ]] || {
  echo "LLAMA_API_KEY 必须是 32-256 位安全字符；建议使用 openssl rand -hex 32。" >&2
  exit 1
}

[[ "$DEEPSEEK_AVX512_SERVER_BIN" == /* ]] || {
  echo "DEEPSEEK_AVX512_SERVER_BIN 必须是绝对路径。" >&2
  exit 1
}
[[ -x "$DEEPSEEK_AVX512_SERVER_BIN" ]] || {
  echo "llama-server 不存在或不可执行：$DEEPSEEK_AVX512_SERVER_BIN" >&2
  exit 1
}
[[ "$DEEPSEEK_AVX512_MODEL_PATH" == /* ]] || {
  echo "DEEPSEEK_AVX512_MODEL_PATH 必须是绝对路径。" >&2
  exit 1
}
[[ -r "$DEEPSEEK_AVX512_MODEL_PATH" ]] || {
  echo "模型分片首文件不存在或不可读：$DEEPSEEK_AVX512_MODEL_PATH" >&2
  exit 1
}

server_help="$($DEEPSEEK_AVX512_SERVER_BIN --help 2>&1 || true)"
[[ "$server_help" == *"--load-mode MODE"* && "$server_help" == *"dio: use DirectIO"* ]] || {
  echo "当前 llama-server 不支持 Direct I/O 加载模式；请使用项目指定的 AVX-512 构建。" >&2
  exit 1
}

[[ "$DEEPSEEK_AVX512_HOST" == "127.0.0.1" ]] || {
  echo "为避免绕过访问控制，DEEPSEEK_AVX512_HOST 必须保持 127.0.0.1。" >&2
  exit 1
}
[[ "$DEEPSEEK_AVX512_CTX_SIZE" == "1048576" ]] || {
  echo "DEEPSEEK_AVX512_CTX_SIZE 必须保持 1048576。" >&2
  exit 1
}
[[ "$DEEPSEEK_AVX512_PARALLEL" == "1" ]] || {
  echo "DEEPSEEK_AVX512_PARALLEL 必须保持 1。" >&2
  exit 1
}
[[ "$DEEPSEEK_AVX512_NUMA_NODE" == "1" ]] || {
  echo "DEEPSEEK_AVX512_NUMA_NODE 必须保持 1。" >&2
  exit 1
}
[[ "$DEEPSEEK_AVX512_CPU_LIST" == "128-255" ]] || {
  echo "DEEPSEEK_AVX512_CPU_LIST 必须保持 128-255。" >&2
  exit 1
}
[[ -d /sys/devices/system/node/node1 ]] || {
  echo "当前机器没有 NUMA node 1，拒绝启动。" >&2
  exit 1
}
for cpu_number in $(seq 128 255); do
  [[ -e "/sys/devices/system/node/node1/cpu${cpu_number}" ]] || {
    echo "CPU ${cpu_number} 不属于 NUMA node 1，拒绝启动。" >&2
    exit 1
  }
  online_file="/sys/devices/system/cpu/cpu${cpu_number}/online"
  if [[ -f "$online_file" && "$(<"$online_file")" != "1" ]]; then
    echo "CPU ${cpu_number} 当前不在线，拒绝启动。" >&2
    exit 1
  fi
done
if ! numactl \
  --physcpubind="$DEEPSEEK_AVX512_CPU_LIST" \
  --membind="$DEEPSEEK_AVX512_NUMA_NODE" \
  "$TRUE_BIN"; then
  echo "当前用户的 cpuset 或 NUMA 内存策略不允许 node 1 / CPU 128-255，拒绝启动。" >&2
  exit 1
fi

systemctl --user enable "$UNIT_NAME"
if systemctl --user is-active --quiet "$UNIT_NAME"; then
  systemctl --user restart "$UNIT_NAME"
else
  systemctl --user start "$UNIT_NAME"
fi
echo "DeepSeek AVX-512 用户服务已启用并开始加载模型。"
echo "状态：systemctl --user status $UNIT_NAME"
echo "日志：journalctl --user -u $UNIT_NAME -f"

if command -v loginctl >/dev/null 2>&1; then
  linger="$(loginctl show-user "$(id -un)" -p Linger --value 2>/dev/null || true)"
  if [[ "$linger" != "yes" ]]; then
    echo "提示：当前用户未启用 linger；若需服务器重启后无人登录也自动启动，请让管理员执行："
    echo "sudo loginctl enable-linger $(id -un)"
  fi
fi
