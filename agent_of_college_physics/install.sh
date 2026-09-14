#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

# Rocky Linux 10 用户目录安装器：不写 /opt、/etc、/var、/usr/local，
# 不修改 systemd、firewalld、SELinux 或 Nginx。

if [[ ${EUID:-$(id -u)} -eq 0 ]]; then
  echo "请使用普通登录用户执行，不要使用 sudo：bash install.sh" >&2
  exit 1
fi

APP_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=agnet/launcher_paths.sh
source "$APP_ROOT/agnet/launcher_paths.sh"
RUNTIME_ROOT="$APP_ROOT/.runtime"
CONFIG_ROOT="$APP_ROOT/config"
CONFIG_FILE="$CONFIG_ROOT/physics-assistant.env"
if [[ -f "$CONFIG_FILE" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$CONFIG_FILE"
  set +a
fi
physics_resolve_launcher_paths "$APP_ROOT"
JULIA_VERSION="${JULIA_VERSION:-1.10.10}"
PYTHON_VERSION="${PYTHON_VERSION:-3.13}"
UV_VERSION="0.12.5"
PRECOMPILE_EXPERIMENTS="${PRECOMPILE_EXPERIMENTS:-1}"
CJK_FONT_URL="https://raw.githubusercontent.com/notofonts/noto-cjk/Sans2.004/Sans/OTF/SimplifiedChinese/NotoSansCJKsc-Regular.otf"
CJK_FONT_SHA256="2c76254f6fc379fddfce0a7e84fb5385bb135d3e399294f6eeb6680d0365b74b"
CJK_FONT_PATH="$RUNTIME_ROOT/fonts/NotoSansCJKsc-Regular.otf"
ASR_MODEL_DIR="${PHYSICS_ASR_MODEL_DIR:-$RUNTIME_ROOT/models/paraformer-zh-streaming}"
if [[ "$ASR_MODEL_DIR" != /* ]]; then
  ASR_MODEL_DIR="$APP_ROOT/${ASR_MODEL_DIR#./}"
fi

set_config_value() {
  local key="$1" value="$2" output
  output="$(mktemp "$RUNTIME_ROOT/tmp/physics-env.XXXXXX")"
  awk -v key="$key" -v value="$value" '
    BEGIN { found = 0 }
    $0 ~ "^" key "=" { print key "=" value; found = 1; next }
    { print }
    END { if (!found) print key "=" value }
  ' "$CONFIG_FILE" >"$output"
  mv -- "$output" "$CONFIG_FILE"
}

for required in \
  "$APP_ROOT/agnet/app.py" \
  "$APP_ROOT/agnet/asr_service.py" \
  "$APP_ROOT/agnet/download_asr_model.py" \
  "$APP_ROOT/agnet/gateway.py" \
  "$APP_ROOT/agnet/migrate_db.py" \
  "$APP_ROOT/agnet/install_tectonic.sh" \
  "$APP_ROOT/agnet/knowledge_base/chunks.jsonl" \
  "$APP_ROOT/教学素材" \
  "$APP_ROOT/requirements.lock"; do
  [[ -e "$required" ]] || { echo "独立目录缺少：$required" >&2; exit 1; }
done

for command in curl tar gzip sha256sum awk mktemp install mkdir mv rm; do
  command -v "$command" >/dev/null 2>&1 || {
    echo "系统缺少基础命令 $command；请让服务器管理员预先安装。" >&2
    exit 1
  }
done

mkdir -p \
  "$RUNTIME_ROOT/bin" \
  "$RUNTIME_ROOT/logs" \
  "$RUNTIME_ROOT/pids" \
  "$RUNTIME_ROOT/tmp" \
  "$RUNTIME_ROOT/uv-cache" \
  "$RUNTIME_ROOT/python" \
  "$RUNTIME_ROOT/fonts" \
  "$ASR_MODEL_DIR" \
  "$RUNTIME_ROOT/julia-depot" \
  "$RUNTIME_ROOT/experiment-output/sound-speed" \
  "$CONFIG_ROOT" \
  "$APP_ROOT/agnet/data" \
  "$APP_ROOT/agnet/runtime" \
  "$APP_ROOT/agnet/runtime/experiments" \
  "$APP_ROOT/agnet/experiments/sound_speed/output"
chmod u+rwx \
  "$APP_ROOT/agnet/data" \
  "$APP_ROOT/agnet/runtime" \
  "$APP_ROOT/agnet/runtime/experiments"
touch \
  "$APP_ROOT/agnet/runtime/experiments/photoelectric.log" \
  "$APP_ROOT/agnet/runtime/experiments/biprism.log" \
  "$APP_ROOT/agnet/runtime/experiments/newton_rings.log" \
  "$APP_ROOT/agnet/runtime/experiments/young_modulus.log" \
  "$APP_ROOT/agnet/runtime/experiments/rotational_inertia.log" \
  "$APP_ROOT/agnet/runtime/experiments/viscosity.log" \
  "$APP_ROOT/agnet/runtime/experiments/specific_heat.log" \
  "$APP_ROOT/agnet/runtime/experiments/franck_hertz.log" \
  "$APP_ROOT/agnet/runtime/experiments/temperature_sensor.log" \
  "$APP_ROOT/agnet/runtime/experiments/wheatstone_bridge.log" \
  "$APP_ROOT/agnet/runtime/experiments/hall_effect.log" \
  "$APP_ROOT/agnet/runtime/experiments/magnetic_hysteresis.log" \
  "$APP_ROOT/agnet/runtime/experiments/thin_lens_focal.log" \
  "$APP_ROOT/agnet/runtime/experiments/prism_refractive_index.log" \
  "$APP_ROOT/agnet/runtime/experiments/thermal_conductivity.log"

echo "[1/9] 在项目目录准备中文字体……"
if ! printf '%s  %s\n' "$CJK_FONT_SHA256" "$CJK_FONT_PATH" | \
    sha256sum --check --status 2>/dev/null; then
  font_tmp="$(mktemp "$RUNTIME_ROOT/tmp/physics-font.XXXXXX")"
  if ! curl --fail --location --retry 3 "$CJK_FONT_URL" -o "$font_tmp"; then
    rm -f -- "$font_tmp"
    echo "Noto Sans CJK 字体下载失败。" >&2
    exit 1
  fi
  printf '%s  %s\n' "$CJK_FONT_SHA256" "$font_tmp" | sha256sum --check --strict
  mv -- "$font_tmp" "$CJK_FONT_PATH"
fi
export PHYSICS_CJK_FONT="${PHYSICS_CJK_FONT:-$CJK_FONT_PATH}"

echo "[2/9] 在用户目录安装 uv ${UV_VERSION} 与 Python ${PYTHON_VERSION}……"
UV_BIN="$RUNTIME_ROOT/bin/uv"
installed_uv_version="$("$UV_BIN" --version 2>/dev/null | awk '{print $2}' || true)"
if [[ ! -x "$UV_BIN" || "$installed_uv_version" != "$UV_VERSION" ]]; then
  rm -f -- "$UV_BIN" "$RUNTIME_ROOT/bin/uvx"
  uv_installer="$(mktemp "$RUNTIME_ROOT/tmp/uv-installer.XXXXXX.sh")"
  if ! curl --proto '=https' --tlsv1.2 --fail --location --retry 3 \
      "https://astral.sh/uv/${UV_VERSION}/install.sh" -o "$uv_installer"; then
    rm -f -- "$uv_installer"
    echo "uv ${UV_VERSION} 安装器下载失败。" >&2
    exit 1
  fi
  env UV_UNMANAGED_INSTALL="$RUNTIME_ROOT/bin" sh "$uv_installer"
  rm -f -- "$uv_installer"
fi
[[ "$("$UV_BIN" --version | awk '{print $2}')" == "$UV_VERSION" ]] || {
  echo "uv 版本校验失败，期望 ${UV_VERSION}。" >&2
  exit 1
}
if [[ ! -x "$APP_ROOT/agnet/.venv/bin/python" ]]; then
  env UV_CACHE_DIR="$RUNTIME_ROOT/uv-cache" UV_PYTHON_INSTALL_DIR="$RUNTIME_ROOT/python" \
    "$UV_BIN" venv --python "$PYTHON_VERSION" "$APP_ROOT/agnet/.venv"
fi
env UV_CACHE_DIR="$RUNTIME_ROOT/uv-cache" UV_PYTHON_INSTALL_DIR="$RUNTIME_ROOT/python" \
  "$UV_BIN" pip sync --python "$APP_ROOT/agnet/.venv/bin/python" "$APP_ROOT/requirements.lock"

echo "[3/9] 安装并离线验证固定版本 Tectonic……"
bash "$APP_ROOT/agnet/install_tectonic.sh"

echo "[4/9] 下载并校验 Paraformer 中文流式 INT8 模型……"
env PHYSICS_ASR_MODEL_DIR="$ASR_MODEL_DIR" \
  "$APP_ROOT/agnet/.venv/bin/python" "$APP_ROOT/agnet/download_asr_model.py"

echo "[5/9] 在用户目录安装 Julia ${JULIA_VERSION}……"
JULIA_HOME="$RUNTIME_ROOT/julia-${JULIA_VERSION}"
JULIA_BIN="$JULIA_HOME/bin/julia"
if [[ ! -x "$JULIA_BIN" ]]; then
  case "$(uname -m)" in
    x86_64) julia_url_arch="x64"; julia_file_arch="x86_64" ;;
    aarch64) julia_url_arch="aarch64"; julia_file_arch="aarch64" ;;
    *) echo "暂不支持的 CPU 架构：$(uname -m)" >&2; exit 1 ;;
  esac
  julia_series="${JULIA_VERSION%.*}"
  julia_archive="julia-${JULIA_VERSION}-linux-${julia_file_arch}.tar.gz"
  julia_url="https://julialang-s3.julialang.org/bin/linux/${julia_url_arch}/${julia_series}/${julia_archive}"
  checksums_url="https://julialang-s3.julialang.org/bin/checksums/julia-${JULIA_VERSION}.sha256"
  julia_tmp="$(mktemp -d "$RUNTIME_ROOT/tmp/physics-julia.XXXXXX")"
  cleanup() {
    if [[ -n "${julia_tmp:-}" && -d "${julia_tmp:-}" \
          && "$julia_tmp" == "$RUNTIME_ROOT/tmp/physics-julia."* ]]; then
      rm -rf -- "$julia_tmp"
    fi
  }
  trap cleanup EXIT
  curl --fail --location --retry 3 "$julia_url" -o "$julia_tmp/$julia_archive"
  curl --fail --location --retry 3 "$checksums_url" -o "$julia_tmp/julia.sha256"
  expected="$(awk -v archive="$julia_archive" '$2 == archive {print $1}' "$julia_tmp/julia.sha256")"
  [[ "$expected" =~ ^[0-9a-fA-F]{64}$ ]] || { echo "找不到 Julia 官方校验值。" >&2; exit 1; }
  printf '%s  %s\n' "$expected" "$julia_tmp/$julia_archive" | sha256sum --check --strict
  tar -xzf "$julia_tmp/$julia_archive" -C "$julia_tmp"
  mv "$julia_tmp/julia-${JULIA_VERSION}" "$JULIA_HOME"
  cleanup
  trap - EXIT
fi
# Keep the bundled runtime usable when the complete release directory moves.
ln -sfn "../julia-${JULIA_VERSION}/bin/julia" "$RUNTIME_ROOT/bin/julia"

echo "[6/9] 创建用户级运行配置……"
if [[ ! -f "$CONFIG_FILE" ]]; then
  cp "$APP_ROOT/physics-assistant.env.example" "$CONFIG_FILE"
fi
# Migrate legacy wildcard HTTP configurations to the mandatory loopback
# upstream.  External HTTPS uses PHYSICS_GATEWAY_HTTPS_HOST independently.
if [[ -n "${PHYSICS_GATEWAY_HTTPS_PORT:-}" && -z "${PHYSICS_GATEWAY_HTTPS_HOST:-}" ]]; then
  legacy_gateway_host="${PHYSICS_GATEWAY_HOST:-0.0.0.0}"
  set_config_value PHYSICS_GATEWAY_HTTPS_HOST "$legacy_gateway_host"
  export PHYSICS_GATEWAY_HTTPS_HOST="$legacy_gateway_host"
  echo "警告：检测到旧版 HTTPS 配置，已将原监听地址 $legacy_gateway_host 迁移到 PHYSICS_GATEWAY_HTTPS_HOST。" >&2
fi
set_config_value PHYSICS_GATEWAY_HOST "127.0.0.1"
chmod 600 "$CONFIG_FILE" "$APP_ROOT/agnet/data/assistant.db" 2>/dev/null || true
set -a
# shellcheck disable=SC1090
source "$CONFIG_FILE"
set +a
physics_resolve_launcher_paths "$APP_ROOT"
[[ -f "$APP_ROOT/agnet/data/admin_signing_secret" ]] && \
  chmod 600 "$APP_ROOT/agnet/data/admin_signing_secret"

echo "[7/9] 初始化空库并检查迁移管理员……"
database="$APP_ROOT/agnet/data/assistant.db"
env PYTHONPATH="$APP_ROOT/agnet" \
  "$APP_ROOT/agnet/.venv/bin/python" "$APP_ROOT/agnet/migrate_db.py"
chmod 600 "$database"
has_admin="$("$APP_ROOT/agnet/.venv/bin/python" -c '
import sqlite3, sys
try:
    with sqlite3.connect(sys.argv[1]) as db:
        found = db.execute("SELECT 1 FROM users WHERE role=\"admin\" AND COALESCE(is_active,1)=1 LIMIT 1").fetchone()
    print(1 if found else 0)
except sqlite3.Error:
    print(0)
' "$database")"
if [[ "$has_admin" != "1" ]]; then
  username="${BOOTSTRAP_ADMIN_USERNAME:-${ADMIN_USERNAME:-tjracphy}}"
  password="${BOOTSTRAP_ADMIN_PASSWORD:-${ADMIN_PASSWORD:-}}"
  display_name="${BOOTSTRAP_ADMIN_DISPLAY_NAME:-${ADMIN_DISPLAY_NAME:-课程管理员}}"
  if [[ -z "$password" ]]; then
    [[ -t 0 ]] || { echo "需要交互创建管理员，或设置 BOOTSTRAP_ADMIN_PASSWORD。" >&2; exit 1; }
    read -r -p "管理员用户名 [$username]：" entered
    username="${entered:-$username}"
    read -r -s -p "管理员密码（至少 12 位）：" password; echo
    read -r -s -p "再次输入管理员密码：" confirmation; echo
    [[ "$password" == "$confirmation" ]] || { echo "两次密码不一致。" >&2; exit 1; }
  fi
  [[ "$username" =~ ^[A-Za-z0-9_-]{3,32}$ ]] || { echo "管理员用户名格式无效。" >&2; exit 1; }
  (( ${#password} >= 12 )) || { echo "管理员密码至少需要 12 位。" >&2; exit 1; }
  printf '%s' "$password" | env PYTHONPATH="$APP_ROOT/agnet" \
    PHYSICS_BOOTSTRAP_ADMIN_USERNAME="$username" \
    PHYSICS_BOOTSTRAP_ADMIN_DISPLAY_NAME="$display_name" \
    "$APP_ROOT/agnet/.venv/bin/python" -c '
import os, sys, analytics_db
from storage import init_db
password = sys.stdin.read()
init_db(); analytics_db.init_db()
analytics_db.ensure_admin_user(os.environ["PHYSICS_BOOTSTRAP_ADMIN_USERNAME"], password,
                               os.environ["PHYSICS_BOOTSTRAP_ADMIN_DISPLAY_NAME"], update_password=True)
'
  unset password confirmation BOOTSTRAP_ADMIN_PASSWORD
fi

echo "[8/9] 初始化可视化实验……"
if [[ "$PRECOMPILE_EXPERIMENTS" == "1" ]]; then
  for experiment in lissajous sound_speed electron_em photoelectric biprism newton_rings young_modulus rotational_inertia viscosity specific_heat franck_hertz temperature_sensor wheatstone_bridge hall_effect magnetic_hysteresis thin_lens_focal prism_refractive_index thermal_conductivity gas_gamma grating_interference light_polarization michelson_wavelength; do
    env HOME="$HOME" JULIA_DEPOT_PATH="$RUNTIME_ROOT/julia-depot" \
      JULIA_NUM_THREADS="${JULIA_NUM_THREADS:-2}" \
      "$JULIA_BIN" --startup-file=no --project="$APP_ROOT/agnet/experiments/$experiment" \
      -e 'using Pkg; Pkg.instantiate(); Pkg.precompile()'
    env HOME="$HOME" JULIA_DEPOT_PATH="$RUNTIME_ROOT/julia-depot" \
      "$JULIA_BIN" --startup-file=no --project="$APP_ROOT/agnet/experiments/$experiment" \
      "$APP_ROOT/agnet/experiments/$experiment/web.jl" --no-instantiate --self-test
  done
else
  echo "已按 PRECOMPILE_EXPERIMENTS=0 跳过 Julia 预编译。"
fi

echo "[9/9] 启动用户级服务……"
chmod 700 "$APP_ROOT/install.sh" "$APP_ROOT/manage.sh"
"$APP_ROOT/manage.sh" restart

echo
echo "安装完成。所有文件均位于：$APP_ROOT"
echo "本机诊断地址：http://127.0.0.1:8501"
echo "管理命令：bash $APP_ROOT/manage.sh {start|stop|restart|status|logs|check}"
echo "本安装器未修改系统目录、防火墙、SELinux、Nginx 或系统级 systemd。"
echo "8501 默认仅监听回环地址，请勿直接对外放行；远程访问请配置可信 HTTPS/WSS 反向代理。"
