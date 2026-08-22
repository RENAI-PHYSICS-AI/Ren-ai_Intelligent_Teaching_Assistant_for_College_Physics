# 大学物理智能助教

应用源代码位于本目录。完整的功能介绍、安装配置、知识库构建和局域网部署说明请查看仓库根目录的 [README.md](../README.md)。

本地 `rag.py` 使用 BM25 倒排索引和预缓存词频，避免每次查询扫描全部知识块；首次加载建立索引，后续请求复用缓存。

回答策略以本地教材与 RAG 知识库为核心，并已配置 Tavily Search API 按需补充网络资料。普通教材题不联网；明确要求联网或涉及最新、近期、目前、进展、现行标准等时效信息时才搜索。应用只发送当前问题文本，搜索失败会自动回到本地知识库，答案末尾附实际采用的来源链接。

模型采用本地两段式路由：普通问题直接由 GLM-4.7-Flash 回答；上传图片时先由 Qwen3-VL-30B 提取可见信息，再把识别文本、知识库结果和学生问题交给 GLM 组织最终答案。图片原始数据不会再次发送给 GLM。

Rocky Linux 10 独立版本位于仓库根目录的 [agent_of_college_physics/](../agent_of_college_physics/README.md)，对外端口仍为 `8501`。

快速启动：

```powershell
.\start.ps1
```

浏览器访问 `http://localhost:8501`。

首次启动会自动准备约 226.5 MiB 的 Paraformer-zh-streaming INT8 模型，并启动仅监听 `127.0.0.1:8604` 的语音服务。语音流量由 `gateway.py` 的 `/asr/...` 路径转发，局域网无需开放新端口。浏览器麦克风在 `localhost` 可使用 HTTP；通过其他主机名或 IP 访问时必须配置可信 HTTPS/WSS。

登录后可在首页选择“智能助教”或“可视化实验”。可视化实验包含：

- 李萨如图形：相位差、振幅比、有理频率比和频率失谐；
- 声速测量：回声法、双麦克风时差法、示波器相位差法和驻波法。

实验依赖 Julia 1.10、Bonito 与 WGLMakie，并在首次打开对应实验时按需启动。若是首次安装 Julia 依赖，可分别执行：

```powershell
julia --project=experiments/lissajous -e "using Pkg; Pkg.instantiate(); Pkg.precompile()"
julia --project=experiments/sound_speed -e "using Pkg; Pkg.instantiate(); Pkg.precompile()"
```

两套实验只监听本机，由 `gateway.py` 通过主站 `8501/experiments/...` 内嵌代理。局域网使用前，以管理员身份运行 `enable_lan.ps1`，脚本只开放统一入口 `8501`。

同时启动学生端和管理员后台：

```powershell
.\start_all.ps1
```

管理员后台也由统一入口代理；管理员从主站登录后会跳转到 `/agent/analytics`（根路径部署时为 `/analytics`）。管理页面支持名册批量导入，以及未绑定名册记录的逐条修改和删除；已绑定记录受保护。详细配置见仓库根目录说明。

Windows 联网搜索配置位于 `.streamlit/secrets.toml`。该文件使用 TOML 语法，字符串必须写在引号中，例如 `tavily_api_key = "..."`；不要直接复制 Linux 的 `KEY=value` 写法，也不要把密钥提交到 Git。
