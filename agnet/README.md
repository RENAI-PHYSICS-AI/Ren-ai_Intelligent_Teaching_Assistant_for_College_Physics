# 大学物理智能助教

应用源代码位于本目录。完整的功能介绍、安装配置、知识库构建和局域网部署说明请查看仓库根目录的 [README.md](../README.md)。

回答策略以本地教材与 RAG 知识库为核心，同时由模型服务检索可靠网络内容进行补充；应用自身不运行独立网页爬虫。该策略固定启用，不提供用户开关。

Rocky Linux 10（纯 CPU）版本位于仓库根目录的 [rocky/](../rocky/README.md)，对外端口仍为 `8501`。

快速启动：

```powershell
.\start.ps1
```

浏览器访问 `http://localhost:8501`。

登录后可在首页选择“智能助教”或“可视化实验”。可视化实验包含：

- 李萨如图形：相位差、振幅比、有理频率比和频率失谐；
- 声速测量：回声法、双麦克风时差法、示波器相位差法和驻波法。

实验依赖 Julia 1.10、Bonito 与 WGLMakie，并在首次打开对应实验时按需启动。若是首次安装 Julia 依赖，可分别执行：

```powershell
julia --project=experiments/lissajous -e "using Pkg; Pkg.instantiate(); Pkg.precompile()"
julia --project=experiments/sound_speed -e "using Pkg; Pkg.instantiate(); Pkg.precompile()"
```

本机实验端口为 `9384` 和 `9385`。局域网使用前，以管理员身份运行 `enable_lan.ps1`，脚本会同时开放 `8501`、`9384` 和 `9385`。

同时启动学生端和管理员后台：

```powershell
.\start_all.ps1
```

管理员后台默认地址为 `http://127.0.0.1:8603/analytics`，详细配置见仓库根目录说明。
