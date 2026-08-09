# Rocky Linux 10 用户目录版

本目录是一套与 Windows 版独立的、可直接复制的 Rocky Linux 10 版本。应用、原始教学素材、RAG 知识库、迁移的用户/管理员/历史数据和两套可视化实验都在这里。

回答以本地教材和 RAG 知识库为核心，同时由配置的模型服务检索网络内容进行补充。应用自身不运行独立网页爬虫；教材课程口径与网络资料不一致时以教材为准。该策略固定启用，不提供用户开关。

安装不需要也不允许 `sudo`，不会写入 `/opt`、`/etc`、`/var`、`/usr/local`，不会创建系统用户，也不会修改 Nginx、systemd、firewalld 或 SELinux。Python、Julia、配置、日志和 PID 文件都保存在复制后的当前目录。

## 目录与数据

当前目录约 `1.72 GiB`，包含：

- 原始教学素材 668 个文件；
- RAG 主知识库 50,142 个文本块；
- Windows 端现有用户、管理员、对话、反馈、学情与身份名册；
- 注册用户与匿名会话都支持逐条确认删除回答，注册用户的删除会同步写入数据库；
- 数据库备份和管理员签名密钥；
- 李萨如图形与声速测量实验。

`.streamlit/secrets.toml` 和 API Key 不会明文迁移。模型连接写在安装后生成的 `config/physics-assistant.env` 中。

## 运行结构

```text
局域网浏览器
  └─ http://服务器IP:8501  用户级 Python 网关
       ├─ 智能助教与 WebSocket → 127.0.0.1:8502
       ├─ 管理员页面           → 127.0.0.1:8603
       ├─ /experiments/lissajous   → 本机李萨如实验
       └─ /experiments/sound-speed → 本机声速实验
```

所有后端服务只监听本机；浏览器统一使用 8501。服务器纯 CPU 可用，实验图形由访问者浏览器的 WebGL2 渲染。

## 环境要求

- Rocky Linux 10，`x86_64` 或 `aarch64`；
- 普通 SSH 用户，不需要 sudo 权限；
- 至少 8 GB 内存，Julia 首次预编译建议 12 GB；
- 用户目录至少预留 8 GB 空间；
- 系统已有 `curl`、`tar`、`gzip`、`sha256sum`、`awk`；
- 安装阶段能访问 uv、Python 包源、Julia 官方下载站和 GitHub 的 Noto CJK 字体源；
- 能访问模型服务 `http://192.168.222.147:1234/v1`。

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
agnet/.venv/                  # Python 环境
config/physics-assistant.env  # 权限 0600 的运行配置
```

安装器会把经过 SHA-256 校验的 Noto Sans CJK SC 下载到
`.runtime/fonts/NotoSansCJKsc-Regular.otf`。字体只供本项目使用，不写入系统字体目录，
也不需要 `sudo` 或 `fc-cache`。如需使用已有字体，可在配置中设置
`PHYSICS_CJK_FONT` 为支持简体中文的字体文件绝对路径。

已有管理员已随数据库迁移，不会再次询问密码。只有数据库确实没有管理员时才交互创建。

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

## 模型配置

```bash
vi config/physics-assistant.env
bash manage.sh restart
```

默认配置：

```ini
PHYSICS_BASE_URL=http://192.168.222.147:1234/v1
PHYSICS_MODEL=qwen/qwen3-vl-30b
PHYSICS_API_KEY=
ADMIN_LOGIN_URL=/admin-login
PHYSICS_PUBLIC_BASE_URL=http://192.168.222.147:1234/agent
```

Python 网关使管理员与学生端继续共用 8501。直接访问 8501 时可将
`PHYSICS_PUBLIC_BASE_URL` 留空；若通过子路径反向代理，必须填写浏览器实际看到的
公开基址，否则可视化实验的 WebSocket 会丢失子路径并一直停在加载界面。当前反向代理入口为：

```text
http://192.168.222.147:1234/agent/
```

修改配置后执行 `bash manage.sh restart`。实验仍以内嵌网页运行，不额外向局域网开放端口。

## 知识库

完整 `教学素材` 与现成知识库都已包含。需要在 Rocky 重新构建时：

```bash
./agnet/.venv/bin/python ./agnet/build_kb.py
```

PDF 解析需要系统提供 `pdftotext`；DOCX/PPTX 原生解析。旧 `.doc/.ppt/.pot` 若需重建，建议由服务器管理员提供 LibreOffice headless。已有知识库不依赖这些工具。

## 局域网访问

应用在服务器本机只通过 8501 对外提供服务，管理员和实验网页均由同源路径内嵌代理。若上层反向代理提供统一入口，访问者只需使用该入口，无需直接访问 8501。安装器不会修改系统防火墙；任何内部服务端口都不应对外开放。

## 便携性检查

Windows 外层项目提供 `check_portable_paths.py`，已确认源码、配置、知识库字段和所有 SQLite 数据库中没有写死 `C:`、`D:`、`E:` 等盘符路径。

## 文件结构

```text
agent_of_college_physics/
├─ install.sh                 # 唯一安装入口，普通用户执行
├─ manage.sh                  # 用户级服务管理
├─ requirements.in
├─ requirements.lock
├─ physics-assistant.env.example
├─ agnet/                     # 应用、知识库、迁移数据与 Python 网关
└─ 教学素材/                 # 全部原始教学资源
```
