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
RUNTIME_ROOT="$APP_ROOT/.runtime"
CONFIG_ROOT="$APP_ROOT/config"
JULIA_VERSION="${JULIA_VERSION:-1.10.10}"
PYTHON_VERSION="${PYTHON_VERSION:-3.13}"
PRECOMPILE_EXPERIMENTS="${PRECOMPILE_EXPERIMENTS:-1}"
CJK_FONT_URL="https://raw.githubusercontent.com/notofonts/noto-cjk/Sans2.004/Sans/OTF/SimplifiedChinese/NotoSansCJKsc-Regular.otf"
CJK_FONT_SHA256="2c76254f6fc379fddfce0a7e84fb5385bb135d3e399294f6eeb6680d0365b74b"
CJK_FONT_PATH="$RUNTIME_ROOT/fonts/NotoSansCJKsc-Regular.otf"

for required in \
  "$APP_ROOT/agnet/app.py" \
  "$APP_ROOT/agnet/gateway.py" \
  "$APP_ROOT/agnet/data/assistant.db" \
  "$APP_ROOT/agnet/knowledge_base/chunks.jsonl" \
  "$APP_ROOT/教学素材" \
  "$APP_ROOT/requirements.lock"; do
  [[ -e "$required" ]] || { echo "独立目录缺少：$required" >&2; exit 1; }
done

for command in curl tar gzip sha256sum awk; do
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
  "$RUNTIME_ROOT/julia-depot" \
  "$RUNTIME_ROOT/experiment-output/sound-speed" \
  "$CONFIG_ROOT" \
  "$APP_ROOT/agnet/runtime" \
  "$APP_ROOT/agnet/experiments/sound_speed/output"

echo "[1/7] 在项目目录准备中文字体……"
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

echo "[2/7] 在用户目录安装 uv 与 Python ${PYTHON_VERSION}……"
UV_BIN="$RUNTIME_ROOT/bin/uv"
if [[ ! -x "$UV_BIN" ]]; then
  curl -LsSf https://astral.sh/uv/install.sh | env UV_UNMANAGED_INSTALL="$RUNTIME_ROOT/bin" sh
fi
if [[ ! -x "$APP_ROOT/agnet/.venv/bin/python" ]]; then
  env UV_CACHE_DIR="$RUNTIME_ROOT/uv-cache" UV_PYTHON_INSTALL_DIR="$RUNTIME_ROOT/python" \
    "$UV_BIN" venv --python "$PYTHON_VERSION" "$APP_ROOT/agnet/.venv"
fi
env UV_CACHE_DIR="$RUNTIME_ROOT/uv-cache" UV_PYTHON_INSTALL_DIR="$RUNTIME_ROOT/python" \
  "$UV_BIN" pip sync --python "$APP_ROOT/agnet/.venv/bin/python" "$APP_ROOT/requirements.lock"

echo "[3/7] 在用户目录安装 Julia ${JULIA_VERSION}……"
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
ln -sfn "$JULIA_BIN" "$RUNTIME_ROOT/bin/julia"

echo "[4/7] 创建用户级运行配置……"
CONFIG_FILE="$CONFIG_ROOT/physics-assistant.env"
if [[ ! -f "$CONFIG_FILE" ]]; then
  cp "$APP_ROOT/physics-assistant.env.example" "$CONFIG_FILE"
fi
chmod 600 "$CONFIG_FILE" "$APP_ROOT/agnet/data/assistant.db" 2>/dev/null || true
[[ -f "$APP_ROOT/agnet/data/admin_signing_secret" ]] && \
  chmod 600 "$APP_ROOT/agnet/data/admin_signing_secret"

echo "[5/7] 检查迁移管理员……"
database="$APP_ROOT/agnet/data/assistant.db"
has_admin="$($APP_ROOT/agnet/.venv/bin/python -c '
import sqlite3, sys
try:
    with sqlite3.connect(sys.argv[1]) as db:
        found = db.execute("SELECT 1 FROM users WHERE role=\"admin\" AND COALESCE(is_active,1)=1 LIMIT 1").fetchone()
    print(1 if found else 0)
except sqlite3.Error:
    print(0)
' "$database")"
if [[ "$has_admin" != "1" ]]; then
  username="${BOOTSTRAP_ADMIN_USERNAME:-tjracphy}"
  password="${BOOTSTRAP_ADMIN_PASSWORD:-}"
  display_name="${BOOTSTRAP_ADMIN_DISPLAY_NAME:-课程管理员}"
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

echo "[6/7] 初始化可视化实验……"
if [[ "$PRECOMPILE_EXPERIMENTS" == "1" ]]; then
  for experiment in lissajous sound_speed; do
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

echo "[7/7] 启动用户级服务……"
chmod 700 "$APP_ROOT/install.sh" "$APP_ROOT/manage.sh"
"$APP_ROOT/manage.sh" restart

lan_ip="$(hostname -I 2>/dev/null | awk '{print $1}')"
echo
echo "安装完成。所有文件均位于：$APP_ROOT"
echo "访问地址：http://${lan_ip:-服务器IP}:8501"
echo "管理命令：bash $APP_ROOT/manage.sh {start|stop|restart|status|logs|check}"
echo "本安装器未修改系统目录、防火墙、SELinux、Nginx 或系统级 systemd。"
echo "若其他电脑无法访问，请联系服务器管理员只放行 TCP 8501。"
