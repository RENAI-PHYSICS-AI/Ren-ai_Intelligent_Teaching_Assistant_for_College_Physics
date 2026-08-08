# 大学物理智能助教

一个面向大学物理课程的本地知识库智能助教。项目以祝之光《物理学》第5版为课程基准，结合配套习题解答及课程教学资料构建 RAG 知识库，可完成教材检索、概念讲解、公式推导、习题分析、图片识题和交互式物理可视化。

> 项目默认不进行互联网搜索。回答依据本地教学资料及模型已有的通用物理知识生成，适合校内教学、课程答疑和局域网部署。

## 主要功能

- **本地教材增强**：检索 PDF、PPT/PPTX、DOC/DOCX、Markdown、文本及资源目录。
<<<<<<< HEAD
- **实验专题增强**：知识库补充李萨如图形与声速测量相关内容，不引入外部智能体功能。
=======
>>>>>>> 811be50a933ea7003594d04f0ce6288969310e2a
- **教材优先级控制**：祝之光教材正文优先，配套习题解答次之，其他课程资料作为补充。
- **大学物理答疑**：覆盖力学、热学、电磁学、振动与波、波动光学和近代物理。
- **图片识题**：可在聊天输入框直接粘贴或上传题目图片，支持多图分析。
- **LaTeX 公式**：流式回答过程中实时渲染行内公式和独立公式。
- **交互式可视化**：支持函数曲线、参数轨迹、多曲线比较和离散实验数据。
<<<<<<< HEAD
- **双模式首页**：登录后可在“智能助教”和“可视化实验”之间直接切换。
- **经典实验复用**：内置李萨如图形与声速测量两套 Julia/WGLMakie 交互实验。
- **安全绘图执行**：仅执行经过语法校验的数学表达式，不运行任意 Python、Shell、文件或网络代码。
- **对话式界面**：随机快速提问、亮色/暗色/跟随系统主题、流式输出及回答位置跟随。
- **用户与历史**：支持匿名使用、注册登录、历史恢复、Markdown 导出和身份名册绑定。
- **反馈与学情分析**：记录回答评价、意见、问答请求错误、章节分布和注册用户学习活动。
- **管理员后台**：提供受令牌和管理员账号保护的独立分析页面，支持 Excel 名册导入。
- **局域网部署**：默认监听 `0.0.0.0:8501`，同一网络中的师生可通过浏览器访问。
=======
- **安全绘图执行**：仅执行经过语法校验的数学表达式，不运行任意 Python、Shell、文件或网络代码。
- **对话式界面**：随机快速提问、亮色/暗色/跟随系统主题、流式输出及回答位置跟随。
- **局域网部署**：默认监听 `0.0.0.0:8503`，同一网络中的师生可通过浏览器访问。
>>>>>>> 811be50a933ea7003594d04f0ce6288969310e2a
- **无模型降级**：未配置生成模型时，仍可返回本地知识库检索结果。

## 知识库规模

<<<<<<< HEAD
当前知识库由整个 `教学素材` 目录和两套实验专题文本索引共同生成：
=======
当前知识库由整个 `教学素材` 目录生成：
>>>>>>> 811be50a933ea7003594d04f0ce6288969310e2a

| 指标 | 数量 |
| --- | ---: |
| 扫描文件 | 668 |
<<<<<<< HEAD
| 教学素材文本块 | 35,973 |
| 李萨如专题文本块 | 10,122 |
| 声速专题文本块 | 4,047 |
| 合计文本块 | 50,142 |
=======
| 文本块 | 35,973 |
>>>>>>> 811be50a933ea7003594d04f0ce6288969310e2a
| PDF | 114 |
| PPT/PPTX/PPTM/POT | 145 |
| DOC/DOCX | 389 |
| 其他资源 | Markdown、文本、压缩包和视频目录索引 |

检索采用轻量级本地 BM25，并针对中文加入相邻双字切分。知识库记录来源文件、章节、PDF 页码或课件页码，方便回答时标注依据。

## 系统架构

```mermaid
flowchart LR
    A[教材与教学素材] --> B[多格式解析与分块]
<<<<<<< HEAD
    K[李萨如与声速专题知识] --> B
    B --> C[本地 BM25 知识库]
    D[文字或图片提问] --> E[Streamlit 对话界面]
    E --> N[首页模式选择]
    N --> O[李萨如与声速可视化实验]
    E --> C
    C --> F[相关教材上下文]
    E --> G[OpenAI-compatible 视觉语言模型]
    E --> L[(SQLite 用户与学习记录)]
    M[管理员后台] --> L
=======
    B --> C[本地 BM25 知识库]
    D[文字或图片提问] --> E[Streamlit 对话界面]
    E --> C
    C --> F[相关教材上下文]
    E --> G[OpenAI-compatible 视觉语言模型]
>>>>>>> 811be50a933ea7003594d04f0ce6288969310e2a
    F --> G
    G --> H[流式讲解与 LaTeX]
    G --> I[受限可视化规范]
    I --> J[Plotly 交互图表]
```

## 目录结构

```text
仁爱大学物理智能助教/
├─ README.md                 # GitHub 项目说明
<<<<<<< HEAD
├─ rocky/                    # Rocky Linux 10 完整独立目录版（普通用户安装）
│  ├─ install.sh            # 首次安装脚本，不需要 sudo
│  ├─ manage.sh             # 启动、停止、检查和查看日志
│  ├─ config/               # 安装时生成的私密配置（不提交 Git）
│  ├─ .runtime/             # 用户级 Python、Julia、日志与 PID（安装时生成）
│  └─ agnet/                # Rocky 独立应用、数据、知识库与实验
=======
>>>>>>> 811be50a933ea7003594d04f0ce6288969310e2a
├─ 教学素材/                # 教材、课件及补充教学资源
└─ agnet/                   # 应用目录（保留项目原始命名）
   ├─ app.py                # Streamlit 页面与对话流程
   ├─ llm.py                # OpenAI-compatible 模型调用与流式解析
   ├─ rag.py                # 本地 BM25 检索
   ├─ build_kb.py           # 多格式资料解析与知识库构建
   ├─ visualization.py      # 安全表达式校验与 Plotly 绘图
<<<<<<< HEAD
   ├─ experiment_hub.py     # 实验选择、Julia 服务管理与网页嵌入
   ├─ experiments/          # 李萨如与声速 Julia/WGLMakie 网页实验
   ├─ storage.py            # 用户消息、历史恢复与 Markdown 导出
   ├─ analytics_db.py       # 会话、问答、反馈、错误与学情统计
   ├─ admin_api.py          # FastAPI 管理员分析后台
   ├─ admin_auth.py         # 管理员短期签名令牌
   ├─ config.py             # 路径和运行配置
   ├─ knowledge_base/       # JSONL 知识库、实验专题扩展索引与构建清单
   ├─ .streamlit/           # Streamlit 配置与密钥示例
   ├─ start.bat             # Windows 双击启动
   ├─ start.ps1             # PowerShell 启动脚本
   ├─ start_admin.ps1       # 管理员后台启动脚本（127.0.0.1:8603）
   ├─ start_all.ps1         # 同时启动学生端和管理员后台
=======
   ├─ config.py             # 路径和运行配置
   ├─ knowledge_base/       # JSONL 知识库与构建清单
   ├─ .streamlit/           # Streamlit 配置与密钥示例
   ├─ start.bat             # Windows 双击启动
   ├─ start.ps1             # PowerShell 启动脚本
>>>>>>> 811be50a933ea7003594d04f0ce6288969310e2a
   ├─ enable_lan.ps1        # 局域网防火墙配置脚本
   └─ requirements.txt      # Python 依赖
```

## 环境要求

<<<<<<< HEAD
- Windows 10/11，或 Rocky Linux 10（纯 CPU 服务器可用）
- Python 3.13（启动脚本通过 `uv` 自动创建虚拟环境）
- Julia 1.10（使用“可视化实验”模式时需要）
- 支持 WebGL2 的现代 Edge、Chrome 或 Firefox 浏览器
=======
- Windows 10/11
- Python 3.13（启动脚本通过 `uv` 自动创建虚拟环境）
>>>>>>> 811be50a933ea7003594d04f0ce6288969310e2a
- [uv](https://docs.astral.sh/uv/)
- Poppler 的 `pdftotext`，用于提取 PDF 文字
- WPS Office（可选），用于读取旧式 `.doc`、`.ppt`、`.pot` 文件
- 一个支持 OpenAI Chat Completions 格式的文本或视觉语言模型服务

<<<<<<< HEAD
Rocky Linux 版不使用 Windows `.venv`、PowerShell 或 WPS COM。`rocky` 文件夹自身已包含应用、全部原始教学素材、RAG 知识库、现有用户/管理员/历史记录及两套实验；把整个目录复制到服务器后只需执行其中的 `install.sh`。数据库通过 SQLite 在线快照安全迁移；API Key 不以明文复制。

Rocky 版是与 Windows 版相互独立的完整副本，安装和运行都限制在复制后的用户目录中：

- 不需要、也不允许使用 `sudo` 运行安装脚本；
- 不写入 `/opt`、`/etc`、`/var`、`/usr/local` 等系统目录；
- 不安装 systemd 服务，不修改 SELinux、firewalld 或 Nginx；
- Python、Julia、虚拟环境、配置、日志和实验输出均位于 `rocky/.runtime`、`rocky/config` 或 `rocky/agnet`；
- 用户级 Python 网关对外监听 `8501`，学生端与管理员页面使用同一入口；内部的 `8502` 和 `8603` 只监听 `127.0.0.1`。

完整说明见 [rocky/README.md](rocky/README.md)。

=======
>>>>>>> 811be50a933ea7003594d04f0ce6288969310e2a
## 快速启动

进入应用目录：

```powershell
cd .\agnet
```

<<<<<<< HEAD
只启动学生端可双击 `start.bat`，或在 PowerShell 中运行：
=======
双击 `start.bat`，或在 PowerShell 中运行：
>>>>>>> 811be50a933ea7003594d04f0ce6288969310e2a

```powershell
.\start.ps1
```

脚本会自动创建 `.venv` 并安装依赖。启动后访问：

```text
<<<<<<< HEAD
http://localhost:8501
```

同时启用用户统计和管理员后台，推荐运行：

```powershell
.\start_all.ps1
```

把完整 Rocky 独立目录复制到服务器：

```powershell
scp -r .\rocky user@rocky-host:~/
```

登录 Rocky Linux 10 后只执行安装脚本：

```bash
cd ~/rocky
bash install.sh
```

不要使用 `sudo bash install.sh`。安装完成后访问：

```text
http://Rocky服务器局域网IP:8501
```

Rocky 版的日常管理命令：

```bash
cd ~/rocky
bash manage.sh status    # 查看状态
bash manage.sh start     # 启动
bash manage.sh stop      # 停止
bash manage.sh restart   # 重启
bash manage.sh logs      # 查看日志
bash manage.sh check     # 检查内部及外部入口
```

当前用户级部署不会注册开机服务，服务器重启后需要再次执行 `bash manage.sh start`。若其他电脑无法访问，请让服务器管理员放行 TCP `8501`、`9384` 和 `9385`；安装脚本本身不会修改防火墙。

=======
http://localhost:8503
```

>>>>>>> 811be50a933ea7003594d04f0ce6288969310e2a
## 模型配置

复制配置示例：

```powershell
Copy-Item .\.streamlit\secrets.toml.example .\.streamlit\secrets.toml
```

编辑 `.streamlit/secrets.toml`：

```toml
physics_api_key = "你的 API Key；无鉴权的本地服务可留空"
physics_base_url = "http://你的模型服务地址/v1"
physics_model = "模型 ID"
<<<<<<< HEAD

admin_username = "admin"
admin_display_name = "课程管理员"
admin_password = "至少12位的独立强密码"
admin_token = "足够长的随机访问令牌"
admin_login_url = "http://127.0.0.1:8603/admin-login"
=======
>>>>>>> 811be50a933ea7003594d04f0ce6288969310e2a
```

也可以使用环境变量：

- `PHYSICS_API_KEY`
- `PHYSICS_BASE_URL`
- `PHYSICS_MODEL`
- `DASHSCOPE_API_KEY`（兼容回退项）
<<<<<<< HEAD
- `PHYSICS_JULIA_EXE`（可选，指定 Julia 可执行文件）
- `PHYSICS_LISSAJOUS_PORT`、`PHYSICS_SOUND_SPEED_PORT`（可选，默认 `9384`、`9385`）
- `PHYSICS_EXPERIMENT_BIND`（可选，默认 `0.0.0.0`）

> 请勿将 `.streamlit/secrets.toml`、API Key 或内网服务凭据提交到 GitHub。项目的 `.gitignore` 已忽略本地密钥文件。

## 用户系统与管理员后台

- 注册用户的账号、历史消息、身份信息和学习活动保存在 `agnet/data/assistant.db`。
- 匿名用户无需注册；匿名对话不写入个人历史，但问答请求可计入匿名总体统计。
- 注册用户可以恢复历史、导出 Markdown、评价回答并提交意见。
- 管理员可以导入学生/教师名册，查看用户活动、章节分布、反馈和系统错误。
- 管理员接口默认只监听本机 `127.0.0.1:8603`，不会直接向局域网公开。

启动全部服务后，管理员可先登录学生端账号，再点击侧栏中的“打开管理员后台”；也可以直接访问：

```text
http://127.0.0.1:8603/analytics
```

首次配置 `admin_username` 和 `admin_password` 后会自动创建管理员账号。数据库迁移会保留已有账号与历史消息。

## 教学资料与知识库

项目会扫描仓库根目录下的 `教学素材`，并自动吸收 `knowledge_base/imports` 中的实验专题文本索引。如需使用自己的资料，请在合法授权范围内放入该目录，然后执行：
=======

> 请勿将 `.streamlit/secrets.toml`、API Key 或内网服务凭据提交到 GitHub。项目的 `.gitignore` 已忽略本地密钥文件。

## 教学资料与知识库

项目会扫描仓库根目录下的 `教学素材`。如需使用自己的资料，请在合法授权范围内放入该目录，然后执行：
>>>>>>> 811be50a933ea7003594d04f0ce6288969310e2a

```powershell
cd .\agnet
.\.venv\Scripts\python.exe .\build_kb.py
```

构建结果：

- `knowledge_base/chunks.jsonl`：可检索文本块
- `knowledge_base/manifest.json`：文件数量、文本块数量、失败记录和资料优先级
<<<<<<< HEAD
- `knowledge_base/imports/lissajous.jsonl`：李萨如图形与机械振动专题索引
- `knowledge_base/imports/sound_speed.jsonl`：声速、驻波、相位法及时差法专题索引

如果仅更新了实验专题索引，可以跳过全部教学素材的重新解析：

```powershell
.\.venv\Scripts\python.exe .\build_kb.py --merge-imports-only
```

专题索引的整合仍然只作为 RAG 知识，不会加载竞赛项目的智能体、问答提示词或用户数据。另行迁移的两套网页实验位于 `agnet/experiments`，只复用 Julia/WGLMakie 实验核心。检索优先级仍以祝之光教材为最高，专题知识只补充实验原理、测量方法、历史文献和深入应用。
=======
>>>>>>> 811be50a933ea7003594d04f0ce6288969310e2a

对于没有文字层的扫描版 PDF，应先进行 OCR；未提取到正文的文件仍会以文件名和相对路径进入资源目录索引。

## 可视化使用示例

可以直接在对话中提出：

- “绘制简谐振动的位移—时间曲线。”
- “画出平抛运动轨迹，并说明初速度变化的影响。”
- “比较两种阻尼系数下的振幅变化。”
- “将这组实验数据绘制成图并分析趋势。”

模型只生成结构化绘图规范，`visualization.py` 会对表达式、变量、函数、指数范围和数据规模进行校验，再交给 Plotly 渲染。

<<<<<<< HEAD
首页切换到“可视化实验”后，还可以运行两套参数化实验：

- **李萨如图形**：相位差、振幅比、有理频率比、频率失谐；
- **声速测量**：回声法、双麦克风时差法、示波器相位差法、驻波法。

两个实验按需启动，不会在首页同时占用资源。首次部署可在 `agnet` 目录中执行：

```powershell
julia --project=experiments/lissajous -e "using Pkg; Pkg.instantiate(); Pkg.precompile()"
julia --project=experiments/sound_speed -e "using Pkg; Pkg.instantiate(); Pkg.precompile()"
```

=======
>>>>>>> 811be50a933ea7003594d04f0ce6288969310e2a
## 局域网访问

应用默认监听所有本机网卡。首次使用时，以管理员 PowerShell 运行：

```powershell
.\agnet\enable_lan.ps1
```

<<<<<<< HEAD
脚本只对 Windows 的“专用网络”开放主应用端口 `8501` 和实验端口 `9384-9385`。其他设备随后可访问：

```text
http://本机局域网IP:8501
=======
脚本只对 Windows 的“专用网络”开放 TCP 8503。其他设备随后可访问：

```text
http://本机局域网IP:8503
>>>>>>> 811be50a933ea7003594d04f0ce6288969310e2a
```

如果局域网地址发生变化，可运行 `ipconfig` 查看新的 IPv4 地址。

<<<<<<< HEAD
Rocky Linux 版无需运行上述 PowerShell 脚本。它通过目录内的 Python 网关公开 `8501`，两套实验按需使用 `9384` 和 `9385`。端口若被系统防火墙拦截，应由服务器管理员按实际校园网网段配置放行规则。

## 常见问题

### 8501 端口被占用

```powershell
Get-NetTCPConnection -LocalPort 8501 -State Listen
=======
## 常见问题

### 8503 端口被占用

```powershell
Get-NetTCPConnection -LocalPort 8503 -State Listen
>>>>>>> 811be50a933ea7003594d04f0ce6288969310e2a
Stop-Process -Id <OwningProcess>
```

停止进程前请确认它确实是本项目的 Streamlit 服务。

### PDF 没有检索结果

扫描版 PDF 通常没有文字层，请先进行 OCR；也可利用配套习题解答、课件和补充资料完善检索结果。

### 旧版 PPT/DOC 无法解析

<<<<<<< HEAD
Windows 可安装 WPS Office；Rocky/Linux 可安装 LibreOffice 并使用 headless 转换。两者均不可用时，构建器会尝试保守恢复部分文本。已有知识库可以直接使用，不受影响。
=======
安装 WPS Office 后重新生成知识库。没有 WPS 时，构建器会尝试保守恢复部分文本。
>>>>>>> 811be50a933ea7003594d04f0ce6288969310e2a

### 模型服务不可用

检查 `physics_base_url`、模型 ID、API Key 和局域网连通性。模型不可用不会破坏知识库文件。

<<<<<<< HEAD
### Rocky 安装脚本是否需要管理员权限

不需要。请用普通 SSH 登录用户执行 `bash install.sh`，所有文件都安装在当前 `rocky` 目录内。脚本检测到以 root 身份运行时会主动退出，以免占用系统目录或造成文件归属混乱。

### Rocky 重启后网页无法访问

用户目录版不会创建系统级自启动服务。登录服务器后运行：

```bash
cd ~/rocky
bash manage.sh start
```

## 数据与版权

迁移或发布前可以运行便携路径检查，确认源码、配置、知识库路径字段和 SQLite 数据中没有写死 Windows 盘符：

```powershell
python .\check_portable_paths.py
```

程序资源路径均从脚本位置计算；Rocky 版只安装到复制后的用户目录，不写入 `/opt`、`/etc`、`/var` 或 `/usr/local`。

=======
## 数据与版权

>>>>>>> 811be50a933ea7003594d04f0ce6288969310e2a
- 请仅使用自己拥有或已获授权的教材、课件和教学资料。
- 公开仓库时建议只提交程序代码和可公开的数据，不要上传受版权保护的教材全文。
- 本项目用于教学辅助，模型回答可能存在错误，关键结论、公式条件和数值结果应由教师或学习者复核。

## 技术栈

- Streamlit
- Python
- OpenAI-compatible Chat Completions
- 本地 BM25 检索
- Plotly
<<<<<<< HEAD
- Poppler / WPS COM / LibreOffice headless（资料解析）
=======
- Poppler / WPS COM（资料解析）

>>>>>>> 811be50a933ea7003594d04f0ce6288969310e2a
