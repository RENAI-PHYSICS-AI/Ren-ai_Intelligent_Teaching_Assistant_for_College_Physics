# Paraformer-zh-streaming 语音引擎部署流程

本文记录大学物理智能助教中 Paraformer-zh-streaming 流式语音输入的部署方式。目标是 Rocky Linux 用户目录，不修改系统目录、systemd、Nginx、防火墙或模型服务。

## 1. 部署结构

```text
浏览器麦克风
  │ 16 kHz Float32 PCM WebSocket
  ▼
8501 用户级 Python 网关
  │ /asr/*
  ▼
127.0.0.1:8604 FastAPI + sherpa-onnx
  ▼
Paraformer-zh-streaming INT8
```

麦克风按钮位于聊天输入框内、发送按钮左侧。录音期间显示中间结果，停止录音后才把最终文字填入输入框，不会自动发送。

## 2. 环境要求

- Rocky Linux 10，普通 SSH 用户；
- Python 3.13 项目虚拟环境；
- CPU 即可，不需要 GPU、PyTorch、FFmpeg 或系统级音频设备；
- `curl`、`tar`、`gzip`、`sha256sum`、`awk`；启用 HTTPS 时还需要 `openssl`；
- 可访问 Python 包源和 Hugging Face 模型仓库；
- 项目目录至少预留约 1 GiB 模型空间。

## 3. 复制项目并安装

Windows 项目根目录执行：

```powershell
scp -r ".\agent_of_college_physics" 用户名@Rocky服务器IP:~/
```

登录 Rocky 后执行：

```bash
cd ~/agent_of_college_physics
bash install.sh
```

不要使用 `sudo`。安装器会在当前目录内创建 `.runtime/`、`.runtime/models/`、`agnet/.venv/` 和 `config/physics-assistant.env`。

## 4. 安装依赖与下载模型

项目固定使用 `sherpa-onnx==1.13.4`：

```bash
./.runtime/bin/uv pip sync -p agnet/.venv/bin/python requirements.lock
```

下载并校验三个 Sherpa 成品 INT8 文件：

```bash
agnet/.venv/bin/python agnet/download_asr_model.py
agnet/.venv/bin/python agnet/download_asr_model.py --check
```

模型目录为：

```text
.runtime/models/paraformer-zh-streaming/
├─ encoder.int8.onnx
├─ decoder.int8.onnx
└─ tokens.txt
```

下载器会校验大小和 SHA-256，并使用临时文件原子替换。不要保留约 1 GiB 的完整压缩归档或 FP32 文件。

## 5. 配置语音服务

编辑配置：

```bash
vi config/physics-assistant.env
```

关键配置：

```ini
PHYSICS_ASR_PORT=8604
PHYSICS_ASR_MODEL_DIR=.runtime/models/paraformer-zh-streaming
PHYSICS_ASR_THREADS=4
PHYSICS_ASR_BATCH_SIZE=4
PHYSICS_ASR_BATCH_WAIT_MS=8
PHYSICS_ASR_MAX_CONNECTIONS=4
PHYSICS_ASR_MAX_AUDIO_SECONDS=180
PHYSICS_ASR_IDLE_TIMEOUT_SECONDS=20
PHYSICS_ASR_ALLOW_MISSING_ORIGIN=0
PHYSICS_PUBLIC_BASE_URL=http://192.168.222.147:1234/agent
```

`8604` 必须只监听 `127.0.0.1`，不能直接暴露到局域网。对外访问统一经过 8501 网关。

## 6. 启动与健康检查

```bash
bash manage.sh start
bash manage.sh status
bash manage.sh check
bash manage.sh logs
```

停止或重启：

```bash
bash manage.sh stop
bash manage.sh restart
```

直接检查：

```bash
curl http://127.0.0.1:8604/health
curl http://127.0.0.1:8501/asr/health
ss -lnt | grep -E '8501|8604'
tail -n 100 .runtime/logs/asr.log
```

健康响应应包含：

```json
{"ok":true,"engine":"sherpa-onnx","model":"Paraformer-zh-streaming INT8","sample_rate":16000}
```

## 7. 流式 WebSocket 协议

HTTP 子路径入口：

```text
ws://服务器:1234/agent/asr/ws
```

项目 8501 直连入口：

```text
ws://服务器:8501/asr/ws
```

正式 HTTPS 入口：

```text
wss://服务器:8443/agent/asr/ws
```

开始录音：

```json
{"type":"start","sample_rate":16000,"format":"pcm_f32le"}
```

随后发送二进制 Float32 PCM 音频块，结束时发送：

```json
{"type":"finish"}
```

服务端返回 `ready`、`partial`、`final` 或 `error`。每个连接拥有独立识别流，共享同一个识别模型。

## 8. 浏览器麦克风权限

### 正式方案：HTTPS/WSS

非 `localhost` 页面通常需要受信任 HTTPS。项目提供不需要 sudo 的用户级 HTTPS 网关：

```bash
cd ~/agent_of_college_physics
PHYSICS_HTTPS_HOST=192.168.222.147 bash setup_https.sh
```

默认入口为 `https://192.168.222.147:8443/agent/`。脚本只写项目内的 `config/tls/`，不会修改 Nginx 或系统防火墙；网络管理员仍需放行 TCP 8443。

客户端只导入 CA 公钥 `config/tls/physics-assistant-ca.crt`，不要分发 `physics-assistant-ca.key` 或 `server.key`：

```powershell
Import-Certificate `
  -FilePath .\physics-assistant-ca.crt `
  -CertStoreLocation Cert:\CurrentUser\Root
```

导入后完全关闭并重新打开 Edge/Chrome。当前证书只包含服务器 IP 的 SAN，访问地址必须使用同一 IP。

### 临时方案：受控内网 Edge 安全来源例外

如果网络暂时只放行 HTTP 1234，先确保配置仍是：

```ini
PHYSICS_PUBLIC_BASE_URL=http://192.168.222.147:1234/agent
```

然后重启服务，并在 Windows 当前用户执行：

```powershell
$p = 'HKCU:\Software\Policies\Microsoft\Edge\OverrideSecurityRestrictionsOnInsecureOrigin'
New-Item -Path $p -Force | Out-Null
New-ItemProperty -Path $p -Name 1 -PropertyType String `
  -Value 'http://192.168.222.147:1234/' -Force | Out-Null
```

完全退出并重开 Edge 后生效。该方式只放宽浏览器安全来源判定，音频仍通过未加密 HTTP/WS 传输，只适用于受控局域网。恢复默认策略：

```powershell
Remove-Item 'HKCU:\Software\Policies\Microsoft\Edge\OverrideSecurityRestrictionsOnInsecureOrigin' -Recurse
```

## 9. 真实音频验证

应观察到：

- 收到 `ready`；
- 录音期间持续收到多个 `partial`；
- `finish` 后收到 `final`；
- 没有 `error`、超时或连接泄漏；
- `/health` 中 `active_connections` 在结束后回到 0。

项目已用官方测试音频验证，收到 12 个中间结果并正确完成最终转写。

## 10. 常见故障

### `asr/health` 返回 503

```bash
agnet/.venv/bin/python agnet/download_asr_model.py --check
tail -n 100 .runtime/logs/asr.log
```

### 浏览器提示需要 HTTPS

这是浏览器安全策略，不是模型故障。优先使用 8443 HTTPS/WSS；若 8443 未放行，只能使用受控 Edge 临时策略或 localhost/SSH 隧道。

### WebSocket 无最终结果

反向代理必须保留：

```nginx
proxy_http_version 1.1;
proxy_set_header Host $http_host;
proxy_set_header X-Forwarded-Host $http_host;
proxy_set_header X-Forwarded-Proto $scheme;
proxy_set_header Upgrade $http_upgrade;
proxy_set_header Connection "upgrade";
proxy_read_timeout 3600s;
```

并确认公开路径为 `/agent/asr/ws`，不要直接访问 8604。

### 并发连接被拒绝

默认最多 4 个活动连接。先查看：

```bash
curl http://127.0.0.1:8604/health
```

不要直接开放 8604；调整 `PHYSICS_ASR_MAX_CONNECTIONS` 前应先进行 CPU 和延迟压测。

## 11. 安全与更新注意事项

- 不要提交 API Key、CA 私钥、服务器私钥；
- 不要放行 8502、8603、8604 或实验内部端口；
- HTTP Edge 例外会降低传输安全，只能用于受控网络；
- 原位更新时保留 `config/`、`.runtime/` 和 `agnet/data/assistant.db`，不要用 Windows 快照覆盖远端数据库；
- 语音数据使用应遵守学校隐私和数据管理规定。
