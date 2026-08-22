# Rocky Linux 10 用户目录版

本目录是一套与 Windows 版独立的、可直接复制的 Rocky Linux 10 版本，包含应用、整理后的教学资料、RAG 知识库和四套可视化实验。用户、管理员、历史、数据库备份和签名密钥属于本机运行数据，可通过受控流程迁移，但不进入 Git。

回答以本地教材和 RAG 知识库为核心；遇到明确联网请求或时效性问题时，应用按需调用 Tavily 检索网络资料，再由本地模型统一组织答案。教材课程口径与网络资料不一致时以教材为准。

本版本已在学校服务器部署运行。校内访问地址：[https://192.168.222.147:1234/agent/](https://192.168.222.147:1234/agent/)

安装不需要也不允许 `sudo`，不会写入 `/opt`、`/etc`、`/var`、`/usr/local`，不会创建系统用户，也不会修改 Nginx、systemd、firewalld 或 SELinux。Python、Julia、配置、日志和 PID 文件都保存在复制后的当前目录。

## 目录与数据

当前目录约 `1.72 GiB`，包含：

- 原始教学素材 668 个文件；
- RAG 主知识库 51,779 个文本块，其中电子荷质比专题文献 1,336 个、光电效应专题文献 301 个文本块；
- 注册用户与匿名会话都支持逐条确认删除完整问答；只有问题而没有回答的孤立条目也可单独删除，注册用户的删除会同步写入数据库；
- 本机运行时可保存用户、管理员、对话、反馈、学情、身份名册、数据库备份和管理员签名密钥，这些内容均由 Git 忽略；
- 李萨如图形、声速测量、电子荷质比与光电效应实验；四类实验均包含四个按需加载的独立页面。
- Paraformer 中文流式语音输入服务及固定版本模型下载器。

`.streamlit/secrets.toml` 和 API Key 不会明文迁移。模型连接写在安装后生成的 `config/physics-assistant.env` 中。

## 运行结构

```text
校园网浏览器
  └─ https://192.168.222.147:1234/agent/   当前唯一生产入口
       └─ 现有 HTTPS 反向代理
            └─ 8501 用户级 Python 网关（服务器内部上游）
                 ├─ 智能助教与 WebSocket → 127.0.0.1:8502
                 ├─ 管理员页面           → 127.0.0.1:8603
                 ├─ /asr/*               → 127.0.0.1:8604 Paraformer
                 ├─ /experiments/lissajous   → 本机李萨如实验
                 ├─ /experiments/sound-speed → 本机声速实验
                 ├─ /experiments/electron-em → 本机电子荷质比实验（127.0.0.1:9386）
                 └─ /experiments/photoelectric → 本机光电效应实验（127.0.0.1:9387）
```

所有实际后端服务只监听本机或仅供服务器内部代理使用；校园网络只开放现有的 `1234` HTTPS 入口。`8501` 是反向代理内部上游，`8443` 是独立部署时的备用 HTTPS 网关，当前未对校园网络开放。实验图形由访问者浏览器的 WebGL2 渲染。

## 环境要求

- Rocky Linux 10，`x86_64` 或 `aarch64`；
- 普通 SSH 用户，不需要 sudo 权限；
- 至少 8 GB 内存，Julia 首次预编译建议 12 GB；
- 用户目录至少预留 8 GB 空间；
- 系统已有 `curl`、`tar`、`gzip`、`sha256sum`、`awk`；启用项目 HTTPS 时还需要 `openssl`；
- 安装阶段能访问 uv、Python 包源、Julia 官方下载站、GitHub 的 Noto CJK 字体源和 Hugging Face 模型仓库；
- 本机已安装 LM Studio CLI；`manage.sh` 会自动检查并常驻加载 `glm47-local-prod` 与 `qwen-vl30-local-prod`。

系统缺少基础命令时，安装器只报告缺项，不会自行调用 dnf 或修改系统。

## 复制与安装

在 Windows 项目根目录执行：

```powershell
scp -r ".\agent_of_college_physics" 用户名@Rocky服务器IP:~/
```

登录 Rocky 后，以普通用户执行：

```bash
cd ~/agent_of_college_physics
bash install.sh
```

不要运行 `sudo bash install.sh`；安装器会拒绝 root，以免文件落入系统目录或 `/root`。

默认直接以复制后的 `~/agent_of_college_physics` 作为安装目录，不再复制到别处。安装器会在本目录建立：

```text
.runtime/                     # uv、Julia、Julia depot、中文字体、日志和 PID
.runtime/models/              # Paraformer 流式 INT8 模型（约 226.5 MiB）
agnet/.venv/                  # Python 环境
config/physics-assistant.env  # 权限 0600 的运行配置
```

安装器会把经过 SHA-256 校验的 Noto Sans CJK SC 下载到
`.runtime/fonts/NotoSansCJKsc-Regular.otf`。字体只供本项目使用，不写入系统字体目录，
也不需要 `sudo` 或 `fc-cache`。如需使用已有字体，可在配置中设置
`PHYSICS_CJK_FONT` 为支持简体中文的字体文件绝对路径。

安装器还会下载 Sherpa-ONNX 成品模型 `encoder.int8.onnx`、`decoder.int8.onnx` 和 `tokens.txt`，逐个校验固定大小及 SHA-256 后原子替换。只传输并保存约 226.5 MiB 的 INT8 文件，不下载或保留约 1 GiB 的 FP32 完整归档。下载中断会从已有分块继续。

已有管理员已随数据库迁移，不会再次询问密码。只有数据库确实没有管理员时才交互创建。

管理员页面支持身份名册批量导入，以及未绑定记录的逐条修改和删除；已绑定账号的记录不能直接删除或修改，避免破坏身份关联。

若暂时跳过 Julia 预编译：

```bash
PRECOMPILE_EXPERIMENTS=0 bash install.sh
```

## 服务管理

安装结束会自动启动服务。以后均以普通用户执行：

```bash
bash manage.sh start
bash manage.sh stop
bash manage.sh restart
bash manage.sh status
bash manage.sh check
bash manage.sh logs
```

服务由 `nohup` 在后台运行，日志位于 `.runtime/logs/`。本版本不会注册系统开机服务；服务器重启后进入目录执行 `bash manage.sh start` 即可。

`bash manage.sh status` 默认显示 `admin`、`asr`、`web`、`gateway` 四项运行中；配置 HTTPS 后还会显示 `gateway_https`。`bash manage.sh check` 会验证 ASR 的直接回环地址、8501 代理地址以及已配置的 HTTPS 地址；电子荷质比或光电效应实验已按需启动时，还会分别校验 `9386`、`9387` 回环地址和 8501 代理路径。语音详细日志为 `.runtime/logs/asr.log`，HTTPS 网关日志为 `.runtime/logs/gateway_https.log`。`8604`、`9386`、`9387` 及其他实验内部端口固定只绑定 `127.0.0.1`，不得加入防火墙放行列表。

## 可视化实验

四套 Julia/WGLMakie 实验均由主站按需启动，学生浏览器只访问统一入口，不直连实验内部端口：

- 李萨如图形：相位差、振幅比、有理频率比和频率失谐；
- 声速测量：回声法、双麦克风时差法、示波器相位差法和驻波法；
- 电子荷质比：电子束圆轨道、亥姆霍兹线圈磁场标定、纵向磁聚焦和汤姆孙交叉电磁场。
- 光电效应：伏安特性与光强、普朗克常量拟合、红限与量子规律、遏止电压判读与系统误差。

四类实验均只构建和加载当前选中的页面。李萨如子页面为 `/phase`、`/amplitude`、`/ratio`、`/detune`；声速子页面为 `/echo`、`/dual`、`/phase`、`/standing`。

电子荷质比的公开基路径为 `/experiments/electron-em`，四个子页面分别是 `/circular`、`/helmholtz`、`/focus` 和 `/thomson`。它们共用一个只监听 `127.0.0.1:9386` 的内部服务，但分别构建和加载页面，避免打开一项实验时初始化其他三项。

光电效应的公开基路径为 `/experiments/photoelectric`，四个子页面分别是 `/iv`、`/planck`、`/threshold` 和 `/uncertainty`。它们共用一个只监听 `127.0.0.1:9387` 的内部服务，也只构建当前选中的图形。

## 模型配置

```bash
vi config/physics-assistant.env
bash manage.sh restart
```

默认配置：

```ini
PHYSICS_BASE_URL=http://127.0.0.1:1235/v1
PHYSICS_MODEL=glm47-local-prod
PHYSICS_VISION_MODEL=qwen-vl30-local-prod
PHYSICS_CONTEXT_WINDOW=8192
PHYSICS_HISTORY_MAX_MESSAGES=4
PHYSICS_MAX_OUTPUT_TOKENS=1024
KB_CONTEXT_MAX_CHARS=2500
PHYSICS_VISION_MAX_OUTPUT_TOKENS=1024
PHYSICS_CHAT_MODEL_KEY=zai-org/glm-4.7-flash
PHYSICS_CHAT_MODEL_IDENTIFIER=glm47-local-prod
PHYSICS_VISION_MODEL_KEY=qwen/qwen3-vl-30b
PHYSICS_VISION_MODEL_IDENTIFIER=qwen-vl30-local-prod
PHYSICS_CHAT_NO_THINK_SUFFIX=/nothink
PHYSICS_VISION_NO_THINK_SUFFIX=/no_think
PHYSICS_API_KEY=
ADMIN_LOGIN_URL=/admin-login
USER_SESSION_LOGIN_URL=/session-login
USER_SESSION_LOGOUT_URL=/session-logout
PHYSICS_USER_SESSION_SECONDS=604800
PHYSICS_PUBLIC_BASE_URL=https://192.168.222.147:1234/agent
PHYSICS_ASR_PORT=8604
PHYSICS_ASR_THREADS=4
PHYSICS_ASR_BATCH_SIZE=4
PHYSICS_ASR_BATCH_WAIT_MS=8
PHYSICS_ASR_MAX_CONNECTIONS=4
PHYSICS_ASR_MAX_AUDIO_SECONDS=180
PHYSICS_ASR_IDLE_TIMEOUT_SECONDS=20
PHYSICS_ASR_ALLOW_MISSING_ORIGIN=0
PHYSICS_ELECTRON_EM_PORT=9386
PHYSICS_ELECTRON_EM_UPSTREAM=http://127.0.0.1:9386
PHYSICS_PHOTOELECTRIC_PORT=9387
PHYSICS_PHOTOELECTRIC_UPSTREAM=http://127.0.0.1:9387
```

当前对话和最终答案使用学校 Rocky 服务器 `tjracphy` 本机的 GLM-4.7-Flash，生产 API 标识为 `glm47-local-prod`；图片先由本机 Qwen3-VL-30B-A3B-Instruct 识别，生产 API 标识为 `qwen-vl30-local-prod`，识别文本再交给 GLM 结合知识库组织答案。`manage.sh start/restart` 会检查两个模型的本机设备标识、8K 上下文和4个并行槽；缺少时自动加载，加载命令不设置 TTL，因此空闲时不会自动卸载。服务器或 LM Studio 重启后再次执行 `bash manage.sh start` 即可恢复双模型常驻。

当前 Rocky 与 Windows 版本均已配置并启用 Tavily Search API 联网补充。普通教材概念、公式推导和计算题不会联网；问题明确要求联网，或包含“最新、近期、目前、进展、现行标准”等时效性表达时才触发。应用只发送当前问题文本，不发送用户身份、历史记录或图片。结果经过清洗后作为不可信参考交给 GLM，并在答案末尾附真实来源链接；搜索失败会自动退回本地知识库，相同问题默认缓存 30 分钟。Rocky 密钥保存在 `config/physics-assistant.env`，Windows 密钥保存在 `.streamlit/secrets.toml`，两者都不得提交到 Git。

注册用户登录后由 `/session-login` 换取服务器签名的 HttpOnly Cookie；刷新页面会重新核验数据库中的账号状态并恢复登录，默认有效期为 7 天。HTTPS 入口会为 Cookie 自动增加 `Secure` 属性，退出登录通过 `/session-logout` 清除 Cookie；`PHYSICS_USER_SESSION_SECONDS` 可在 1 小时至 30 天范围内调整。

Python 网关使管理员与学生端在服务器内部共用 `8501` 上游。仅在独立本机调试、直接访问 8501 时可将
`PHYSICS_PUBLIC_BASE_URL` 留空；当前生产环境通过子路径反向代理，必须填写浏览器实际看到的
公开基址，否则可视化实验与语音 WebSocket 会丢失子路径，或因公开端口不一致而被同源校验拒绝。当前反向代理入口为：

```text
https://192.168.222.147:1234/agent/
```

修改配置后执行 `bash manage.sh restart`。实验仍以内嵌网页运行，不额外向局域网开放端口。

## Paraformer 流式语音输入

语音后端使用 `sherpa-onnx 1.13.4` 与中英双语 `Paraformer-zh-streaming` INT8，并作为本地独立服务运行。麦克风按钮位于输入框内部、发送按钮左侧。浏览器通过 AudioWorklet 采集麦克风，将音频连续重采样为 16 kHz Float32 PCM；中间结果显示在输入框上方浮层中，再次点按麦克风后把最终文字写入草稿，不会自动发送。模型不提供词级时间戳，Sherpa 的在线 Paraformer API 也没有真正的热词偏置。

浏览器安全策略要求非 `localhost` 麦克风页面使用可信 HTTPS。当前生产入口已经统一为 `https://192.168.222.147:1234/agent/`，语音通过同源 WSS 工作；校园用户不应再访问 HTTP 入口，也不需要开放其他端口。

### 备用 8443 HTTPS/WSS 入口

仅在没有现有 HTTPS 反向代理的独立部署中，才需要使用项目自带的用户级 HTTPS/WSS 网关：

```bash
cd ~/agent_of_college_physics
PHYSICS_HTTPS_HOST=192.168.222.147 bash setup_https.sh
```

脚本只写当前项目的 `config/tls/` 和运行配置，并启动备用 `https://192.168.222.147:8443/agent/`；不会修改 Nginx、系统证书、firewalld 或模型 API。当前校园网络没有开放 `8443`，生产访问仍只使用 `1234`。`manage.sh check` 使用 `--insecure` 只验证备用服务存活，不代表客户端已经信任证书。

### 备用 8443 入口的 Windows 证书信任

以下步骤只适用于测试备用 `8443` 入口；当前 `1234` 生产入口使用现有 HTTPS 反向代理，不需要为了本项目导入这套备用 CA。启用备用入口时，只复制 CA **公钥证书**；不要复制 `physics-assistant-ca.key`、`server.key` 或整个 `config/tls` 目录：

```powershell
$certDir = Join-Path $env:LOCALAPPDATA 'RenaiPhysicsAssistant\certs'
New-Item -ItemType Directory -Force $certDir | Out-Null
scp renai_server:~/agent_of_college_physics/config/tls/physics-assistant-ca.crt $certDir
Import-Certificate `
  -FilePath (Join-Path $certDir 'physics-assistant-ca.crt') `
  -CertStoreLocation Cert:\CurrentUser\Root
```

应先通过独立渠道核对证书 SHA-256 指纹，再关闭并重新打开浏览器。备用服务器证书只包含 `192.168.222.147` 的 IP SAN，必须使用完全相同的 IP；服务器 IP 或备用根 CA 变化后需要重新签发并重新信任。CA 私钥权限为 0600，只用于签发，绝不能分发到客户端。移除当前用户信任可执行：

```powershell
Get-ChildItem Cert:\CurrentUser\Root |
  Where-Object Subject -eq 'CN=Renai Physics Assistant Local CA' |
  Remove-Item
```

浏览器统一通过 `https://192.168.222.147:1234/agent/` 访问；Rocky 应用在服务器内部通过 `http://127.0.0.1:1235/v1` 调用本机模型，不受外部 HTTPS 入口影响。不要为当前生产环境配置 Edge 的 HTTP 安全来源例外，也不要把 `PHYSICS_PUBLIC_BASE_URL` 改回 HTTP。

### 当前生产 HTTPS 反向代理

当前生产环境由现有反向代理在 `1234` 提供 HTTPS，并把 `/agent/` 转发给内部 `8501` 网关，不使用备用 `8443`。反向代理必须允许 `/agent/asr/ws` WebSocket Upgrade，并保留浏览器看到的完整主机、端口和协议；否则 WebSocket 的同源校验无法判断真实来源：

```nginx
proxy_http_version 1.1;
proxy_set_header Host $http_host;
proxy_set_header X-Forwarded-Host $http_host;
proxy_set_header X-Forwarded-Proto $scheme;
proxy_set_header Upgrade $http_upgrade;
proxy_set_header Connection "upgrade";
proxy_read_timeout 3600s;
```

若统一入口设置了 `Permissions-Policy`，不要使用 `microphone=()` 禁止当前来源。

外层反代方式的服务链路为：

```text
https://192.168.222.147:1234/agent/asr/ws
  → 现有反向代理去掉 /agent
  → 8501 用户级网关去掉 /asr
  → ws://127.0.0.1:8604/ws
```

后端检查：

```bash
curl http://127.0.0.1:8604/health
curl http://127.0.0.1:8501/asr/health
curl --insecure https://192.168.222.147:1234/agent/asr/health
ss -lnt | grep 8604                 # 必须只看到 127.0.0.1
tail -n 100 .runtime/logs/asr.log
```

## 知识库

每次新问答的分阶段响应耗时仅在管理员页面显示，学生界面不展示开发联调数据；管理员可查看最近 30 次问答的知识检索、上下文拼装、历史加载、首段答案、模型生成和端到端耗时。

### 检索性能

本地 BM25 检索使用倒排索引和预缓存词频。查询时只计算包含查询词的候选文本块，并使用 Top-K 堆排序，避免每次扫描全部知识块。首次加载会读取 JSONL 并建立索引，之后由服务进程缓存复用；知识库更新后重启应用即可刷新索引。

完整 `教学素材` 与现成知识库都已包含。需要在 Rocky 重新构建时：

```bash
./agnet/.venv/bin/python ./agnet/build_kb.py
```

PDF 解析需要系统提供 `pdftotext`；DOCX/PPTX 原生解析。旧 `.doc/.ppt/.pot` 若需重建，建议由服务器管理员提供 LibreOffice headless。已有知识库不依赖这些工具。

## 局域网访问

当前校园访问只使用 `https://192.168.222.147:1234/agent/`。`8501` 是服务器内部反向代理上游，`8443` 是未向校园网络开放的备用入口；管理员、ASR 和实验网页均由 `/agent/...` 同源路径代理。安装器不会修改系统防火墙或网络 ACL，不要向校园网络开放 8501、8443、8502、8603、8604 或实验内部端口。

## 便携性检查

Windows 外层项目提供 `check_portable_paths.py`，已确认源码、配置、知识库字段和所有 SQLite 数据库中没有写死 `C:`、`D:`、`E:` 等盘符路径。

本目录可整体复制到任意普通用户目录并改名。安装、管理和 HTTPS 脚本均按自身位置确定项目根目录；证书配置写为 `config/tls/...` 相对路径，搬迁后由 `manage.sh` 解析为当前项目中的实际位置。

## 文件结构

```text
agent_of_college_physics/
├─ install.sh                 # 唯一安装入口，普通用户执行
├─ manage.sh                  # 用户级服务管理
├─ setup_https.sh             # 备用 8443 HTTPS/WSS 与项目 CA（当前校园网络未开放）
├─ requirements.in
├─ requirements.lock
├─ physics-assistant.env.example
├─ config/tls/                # 运行后生成的 CA、服务器证书与私钥
├─ agnet/                     # 应用、知识库、迁移数据与 Python 网关
│  ├─ voice_input.py         # Streamlit V2 录音组件
│  ├─ asr_service.py         # 回环 WebSocket 识别服务
│  └─ download_asr_model.py  # 固定版本模型下载与校验
└─ 教学素材/                 # 全部原始教学资源
```
