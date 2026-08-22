#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

if [[ ${EUID:-$(id -u)} -eq 0 ]]; then
  echo "请使用运行智能助教的普通用户执行，不要使用 sudo。" >&2
  exit 1
fi

APP_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_FILE="$APP_ROOT/config/physics-assistant.env"
TLS_ROOT="$APP_ROOT/config/tls"
SERVER_IP="${PHYSICS_HTTPS_HOST:-$(hostname -I 2>/dev/null | awk '{print $1}')}"
HTTPS_PORT="${PHYSICS_GATEWAY_HTTPS_PORT:-8443}"
PUBLIC_PREFIX="/${PHYSICS_GATEWAY_PUBLIC_PREFIX:-agent}"
PUBLIC_PREFIX="/${PUBLIC_PREFIX#/}"
PUBLIC_PREFIX="${PUBLIC_PREFIX%/}"

[[ -n "$SERVER_IP" ]] || { echo "无法确定服务器 IP，请设置 PHYSICS_HTTPS_HOST。" >&2; exit 1; }
[[ "$HTTPS_PORT" =~ ^[0-9]+$ ]] || { echo "HTTPS 端口无效：$HTTPS_PORT" >&2; exit 1; }
command -v openssl >/dev/null 2>&1 || { echo "缺少 openssl。" >&2; exit 1; }
[[ -f "$CONFIG_FILE" ]] || { echo "请先执行 bash install.sh。" >&2; exit 1; }

mkdir -p "$TLS_ROOT" "$APP_ROOT/.runtime/tmp"
chmod 700 "$TLS_ROOT"

CA_KEY="$TLS_ROOT/physics-assistant-ca.key"
CA_CERT="$TLS_ROOT/physics-assistant-ca.crt"
SERVER_KEY="$TLS_ROOT/server.key"
SERVER_CERT="$TLS_ROOT/server.crt"

if [[ ! -s "$CA_KEY" || ! -s "$CA_CERT" || ! -s "$SERVER_KEY" || ! -s "$SERVER_CERT" ]]; then
  temporary="$(mktemp -d "$APP_ROOT/.runtime/tmp/physics-tls.XXXXXX")"
  cleanup() {
    [[ -d "${temporary:-}" && "$temporary" == "$APP_ROOT/.runtime/tmp/physics-tls."* ]] && \
      rm -rf -- "$temporary"
  }
  trap cleanup EXIT

  openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:3072 -out "$temporary/ca.key"
  openssl req -x509 -new -sha256 -days 3650 \
    -key "$temporary/ca.key" \
    -subj "/CN=Renai Physics Assistant Local CA" \
    -addext "basicConstraints=critical,CA:TRUE,pathlen:0" \
    -addext "keyUsage=critical,keyCertSign,cRLSign" \
    -out "$temporary/ca.crt"

  openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:3072 -out "$temporary/server.key"
  openssl req -new -sha256 -key "$temporary/server.key" \
    -subj "/CN=$SERVER_IP" -out "$temporary/server.csr"
  cat >"$temporary/server.ext" <<EOF
basicConstraints=critical,CA:FALSE
keyUsage=critical,digitalSignature,keyEncipherment
extendedKeyUsage=serverAuth
subjectAltName=IP:$SERVER_IP
subjectKeyIdentifier=hash
authorityKeyIdentifier=keyid,issuer
EOF
  openssl x509 -req -sha256 -days 825 \
    -in "$temporary/server.csr" \
    -CA "$temporary/ca.crt" -CAkey "$temporary/ca.key" -CAcreateserial \
    -extfile "$temporary/server.ext" -out "$temporary/server.crt"
  openssl verify -CAfile "$temporary/ca.crt" "$temporary/server.crt"

  install -m 600 "$temporary/ca.key" "$CA_KEY"
  install -m 644 "$temporary/ca.crt" "$CA_CERT"
  install -m 600 "$temporary/server.key" "$SERVER_KEY"
  install -m 644 "$temporary/server.crt" "$SERVER_CERT"
  cleanup
  trap - EXIT
fi

openssl verify -CAfile "$CA_CERT" "$SERVER_CERT"
openssl x509 -in "$SERVER_CERT" -noout -checkend 86400 >/dev/null || {
  echo "现有服务器证书即将过期，请移走 config/tls 后重新运行。" >&2
  exit 1
}
openssl x509 -in "$SERVER_CERT" -noout -ext subjectAltName | grep -F "IP Address:$SERVER_IP" >/dev/null || {
  echo "现有证书不包含当前 IP：$SERVER_IP。请移走 config/tls 后重新运行。" >&2
  exit 1
}

set_env_value() {
  local key="$1" value="$2" output
  output="$(mktemp "$APP_ROOT/.runtime/tmp/physics-env.XXXXXX")"
  awk -v key="$key" -v value="$value" '
    BEGIN { found = 0 }
    $0 ~ "^" key "=" { print key "=" value; found = 1; next }
    { print }
    END { if (!found) print key "=" value }
  ' "$CONFIG_FILE" >"$output"
  mv -- "$output" "$CONFIG_FILE"
}

set_env_value PHYSICS_GATEWAY_HTTPS_PORT "$HTTPS_PORT"
set_env_value PHYSICS_GATEWAY_TLS_CERT "config/tls/server.crt"
set_env_value PHYSICS_GATEWAY_TLS_KEY "config/tls/server.key"
set_env_value PHYSICS_GATEWAY_PUBLIC_PREFIX "$PUBLIC_PREFIX"
set_env_value PHYSICS_PUBLIC_BASE_URL "https://$SERVER_IP:$HTTPS_PORT$PUBLIC_PREFIX"
chmod 600 "$CONFIG_FILE"

"$APP_ROOT/manage.sh" restart

echo
echo "HTTPS/WSS 已启动：https://$SERVER_IP:$HTTPS_PORT$PUBLIC_PREFIX/"
echo "客户端必须信任此 CA 公钥：$CA_CERT"
echo "CA 私钥仅保存在服务器：$CA_KEY（权限 0600，请勿分发）"
