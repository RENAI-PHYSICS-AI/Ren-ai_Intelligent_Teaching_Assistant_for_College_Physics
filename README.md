# 大学物理智能助教

一个面向大学物理课程的本地知识库智能助教。项目以祝之光《物理学》第5版为课程基准，结合配套习题解答及课程教学资料构建 RAG 知识库，可完成教材检索、概念讲解、公式推导、习题分析、图片识题和交互式物理可视化。

> 项目默认不进行互联网搜索。回答依据本地教学资料及模型已有的通用物理知识生成，适合校内教学、课程答疑和局域网部署。

## 主要功能

- **本地教材增强**：检索 PDF、PPT/PPTX、DOC/DOCX、Markdown、文本及资源目录。
- **教材优先级控制**：祝之光教材正文优先，配套习题解答次之，其他课程资料作为补充。
- **大学物理答疑**：覆盖力学、热学、电磁学、振动与波、波动光学和近代物理。
- **图片识题**：可在聊天输入框直接粘贴或上传题目图片，支持多图分析。
- **LaTeX 公式**：流式回答过程中实时渲染行内公式和独立公式。
- **交互式可视化**：支持函数曲线、参数轨迹、多曲线比较和离散实验数据。
- **安全绘图执行**：仅执行经过语法校验的数学表达式，不运行任意 Python、Shell、文件或网络代码。
- **对话式界面**：随机快速提问、亮色/暗色/跟随系统主题、流式输出及回答位置跟随。
- **局域网部署**：默认监听 `0.0.0.0:8503`，同一网络中的师生可通过浏览器访问。
- **无模型降级**：未配置生成模型时，仍可返回本地知识库检索结果。

## 知识库规模

当前知识库由整个 `教学素材` 目录生成：

| 指标 | 数量 |
| --- | ---: |
| 扫描文件 | 668 |
| 文本块 | 35,973 |
| PDF | 114 |
| PPT/PPTX/PPTM/POT | 145 |
| DOC/DOCX | 389 |
| 其他资源 | Markdown、文本、压缩包和视频目录索引 |

检索采用轻量级本地 BM25，并针对中文加入相邻双字切分。知识库记录来源文件、章节、PDF 页码或课件页码，方便回答时标注依据。

## 系统架构

```mermaid
flowchart LR
    A[教材与教学素材] --> B[多格式解析与分块]
    B --> C[本地 BM25 知识库]
    D[文字或图片提问] --> E[Streamlit 对话界面]
    E --> C
    C --> F[相关教材上下文]
    E --> G[OpenAI-compatible 视觉语言模型]
    F --> G
    G --> H[流式讲解与 LaTeX]
    G --> I[受限可视化规范]
    I --> J[Plotly 交互图表]
```

## 目录结构

```text
仁爱大学物理智能助教/
├─ README.md                 # GitHub 项目说明
├─ 教学素材/                # 教材、课件及补充教学资源
└─ agnet/                   # 应用目录（保留项目原始命名）
   ├─ app.py                # Streamlit 页面与对话流程
   ├─ llm.py                # OpenAI-compatible 模型调用与流式解析
   ├─ rag.py                # 本地 BM25 检索
   ├─ build_kb.py           # 多格式资料解析与知识库构建
   ├─ visualization.py      # 安全表达式校验与 Plotly 绘图
   ├─ config.py             # 路径和运行配置
   ├─ knowledge_base/       # JSONL 知识库与构建清单
   ├─ .streamlit/           # Streamlit 配置与密钥示例
   ├─ start.bat             # Windows 双击启动
   ├─ start.ps1             # PowerShell 启动脚本
   ├─ enable_lan.ps1        # 局域网防火墙配置脚本
   └─ requirements.txt      # Python 依赖
```

## 环境要求

- Windows 10/11
- Python 3.13（启动脚本通过 `uv` 自动创建虚拟环境）
- [uv](https://docs.astral.sh/uv/)
- Poppler 的 `pdftotext`，用于提取 PDF 文字
- WPS Office（可选），用于读取旧式 `.doc`、`.ppt`、`.pot` 文件
- 一个支持 OpenAI Chat Completions 格式的文本或视觉语言模型服务

## 快速启动

进入应用目录：

```powershell
cd .\agnet
```

双击 `start.bat`，或在 PowerShell 中运行：

```powershell
.\start.ps1
```

脚本会自动创建 `.venv` 并安装依赖。启动后访问：

```text
http://localhost:8503
```

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
```

也可以使用环境变量：

- `PHYSICS_API_KEY`
- `PHYSICS_BASE_URL`
- `PHYSICS_MODEL`
- `DASHSCOPE_API_KEY`（兼容回退项）

> 请勿将 `.streamlit/secrets.toml`、API Key 或内网服务凭据提交到 GitHub。项目的 `.gitignore` 已忽略本地密钥文件。

## 教学资料与知识库

项目会扫描仓库根目录下的 `教学素材`。如需使用自己的资料，请在合法授权范围内放入该目录，然后执行：

```powershell
cd .\agnet
.\.venv\Scripts\python.exe .\build_kb.py
```

构建结果：

- `knowledge_base/chunks.jsonl`：可检索文本块
- `knowledge_base/manifest.json`：文件数量、文本块数量、失败记录和资料优先级

对于没有文字层的扫描版 PDF，应先进行 OCR；未提取到正文的文件仍会以文件名和相对路径进入资源目录索引。

## 可视化使用示例

可以直接在对话中提出：

- “绘制简谐振动的位移—时间曲线。”
- “画出平抛运动轨迹，并说明初速度变化的影响。”
- “比较两种阻尼系数下的振幅变化。”
- “将这组实验数据绘制成图并分析趋势。”

模型只生成结构化绘图规范，`visualization.py` 会对表达式、变量、函数、指数范围和数据规模进行校验，再交给 Plotly 渲染。

## 局域网访问

应用默认监听所有本机网卡。首次使用时，以管理员 PowerShell 运行：

```powershell
.\agnet\enable_lan.ps1
```

脚本只对 Windows 的“专用网络”开放 TCP 8503。其他设备随后可访问：

```text
http://本机局域网IP:8503
```

如果局域网地址发生变化，可运行 `ipconfig` 查看新的 IPv4 地址。

## 常见问题

### 8503 端口被占用

```powershell
Get-NetTCPConnection -LocalPort 8503 -State Listen
Stop-Process -Id <OwningProcess>
```

停止进程前请确认它确实是本项目的 Streamlit 服务。

### PDF 没有检索结果

扫描版 PDF 通常没有文字层，请先进行 OCR；也可利用配套习题解答、课件和补充资料完善检索结果。

### 旧版 PPT/DOC 无法解析

安装 WPS Office 后重新生成知识库。没有 WPS 时，构建器会尝试保守恢复部分文本。

### 模型服务不可用

检查 `physics_base_url`、模型 ID、API Key 和局域网连通性。模型不可用不会破坏知识库文件。

## 数据与版权

- 请仅使用自己拥有或已获授权的教材、课件和教学资料。
- 公开仓库时建议只提交程序代码和可公开的数据，不要上传受版权保护的教材全文。
- 本项目用于教学辅助，模型回答可能存在错误，关键结论、公式条件和数值结果应由教师或学习者复核。

## 技术栈

- Streamlit
- Python
- OpenAI-compatible Chat Completions
- 本地 BM25 检索
- Plotly
- Poppler / WPS COM（资料解析）

