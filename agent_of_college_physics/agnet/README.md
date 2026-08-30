# 大学物理智能助教

应用源代码位于本目录。完整的功能介绍、安装配置、知识库构建和局域网部署说明请查看仓库根目录的 [README.md](../README.md)。

本地 `rag.py` 使用 BM25 倒排索引和预缓存词频，避免每次查询扫描全部知识块；首次加载建立索引，后续请求复用缓存。

当前 `knowledge_base/manifest.json` 记录 58,065 个可检索文本块：基础教学素材 35,967 个；李萨如 10,122 个、声速 4,047 个、电子荷质比 1,336 个、光电效应 301 个、双棱镜 517 个、牛顿环 113 个、杨氏模量 111 个、转动惯量 285 个、粘滞系数 954 个、固体比热容 347 个、弗兰克-赫兹 503 个、温度传感器 559 个、惠斯通电桥 30 个、霍尔效应 694 个、铁磁滞回线 284 个、薄透镜焦距 634 个、三棱镜折射率 202 个、固体热传导系数 1,059 个有效专题导入块。

固体比热容专题资料位于 `../教学素材/物理实验/固体比热容的测定/`。单独重建时执行 `build_specific_heat_import.py`，再执行 `build_kb.py --merge-imports-only`；当前有效专题文本块数为 347。

弗兰克-赫兹专题资料位于 `../教学素材/物理实验/弗兰克-赫兹实验/`，包含 10 篇核心文献、6 份 PDF、3 份 Markdown、合计 9 份导入文档和 503 个专题文本块。单独重建时依次执行 `build_franck_hertz_import.py` 和 `build_kb.py --merge-imports-only`。

薄透镜焦距、三棱镜折射率和固体热传导系数三个专题各整理约 10 篇经典或权威文献，资料分别位于 `../教学素材/物理实验/薄透镜焦距的测定/`、`../教学素材/物理实验/三棱镜折射率测定/` 和 `../教学素材/物理实验/固体热传导系数测定/`。单独重建时运行对应的 `build_thin_lens_focal_import.py`、`build_prism_refractive_index_import.py` 或 `build_thermal_conductivity_import.py`，再执行 `build_kb.py --merge-imports-only`。

回答策略以本地教材与 RAG 知识库为核心，并已配置 Tavily Search API 按需补充网络资料。普通教材题不联网；明确要求联网或涉及最新、近期、目前、进展、现行标准等时效信息时才搜索。应用只发送当前问题文本，搜索失败会自动回到本地知识库，答案末尾附实际采用的来源链接。

模型采用本地两阶段路由：普通问题直接由 Rocky 本机的 MiMo VL Miloco 7B 回答；上传图片时先由同一模型提取可见信息，再把识别文本、知识库结果和学生问题交给同一模型组织最终答案。第二阶段不会再次发送图片原始数据。Rocky 生产标识统一为 `mimo-vl-local-prod`；独立用户级 systemd 服务固定监听 `127.0.0.1:1237`，按 128K 上下文、4 个并行槽常驻，`manage.sh` 只验证 API 与模型别名，不再重复调用 LM Studio 加载。

Rocky Linux 10 独立版本位于仓库根目录的 [agent_of_college_physics/](../agent_of_college_physics/README.md)。`8501` 是服务器内部统一上游；学校当前公开入口为 [https://192.168.222.147:1234/agent/](https://192.168.222.147:1234/agent/)，备用 `8443` 未对校园网络开放。

快速启动：

```powershell
.\start.ps1
```

浏览器访问 `http://localhost:8501`。

首次启动会自动准备约 226.5 MiB 的 Paraformer-zh-streaming INT8 模型，并启动仅监听 `127.0.0.1:8604` 的语音服务。语音流量由 `gateway.py` 的 `/asr/...` 路径转发，局域网无需开放新端口。浏览器麦克风在 `localhost` 可使用 HTTP；通过其他主机名或 IP 访问时必须配置可信 HTTPS/WSS。

登录后可在首页选择“智能助教”或“可视化实验”。

名册中已核验的教师登录后会先选择“智能助教”或“教研考试”。教研考试复用公共知识库，并可叠加由 `build_teacher_exam_kb.py` 构建的教师私有索引，用于依据知识库组卷、专项出题、生成参考答案与评分标准；两个入口的对话历史彼此隔离。教师专用资料放在项目根目录 `教学素材/教师专用/教研考试/`，不会进入公共知识库或 Git。

## 教研考试试卷文件与 Rocky 编译环境

教研考试生成或修订整套试卷时，模型只负责输出 UTF-8 TeX 源文档，禁止在对话流中输出 PDF、ZIP、Base64、ASCII85 或其他二进制内容。应用在服务器端校验并编译 TeX，通常为教师提供四个可下载文件：试题 `main.tex`、试题 `main.pdf`、答案与评分标准 `answer.tex`、答案与评分标准 `answer.pdf`。若试卷引用标准模板目录中的可信图片，应用还会生成一个包含两份 TeX、两份 PDF 与全部所用图片的完整 ZIP，并保留 `fig/...` 相对路径。

整卷大题编号固定连续为“一、二、三、四、五、六、七”：单选题为一、填空题为二，五道计算题分别为三至七。每道计算题必须有独立知识主题标题和“共 10 分”标记，五个主题的先后次序可按课程蓝图调整。试卷固定为三张物理页，每页都有框外页眉、独立2pt黑色外框和双栏题面；页内显式换栏，三页之间显式分页，计算题之间保留足够答题空间。结构化回退在编译前检查题干和整栏文本预算，拒绝可能破坏三页版式或造成 TeX 拆页卡死的超长题面。题图优先使用安全白名单内的 TikZ；外部图件只能来自可信模板目录，拒绝 URL、绝对路径和目录穿越。

Rocky Linux 首次启用试卷编译前，在本目录执行：

```bash
bash ./install_tectonic.sh
```

脚本固定使用官方 Tectonic `0.16.9` Linux x86_64 GNU 发布包及其 SHA-256，严格校验后安装到项目父目录 `.runtime/tectonic/tectonic`。只有脚本内嵌的固定可信模板允许联网预热：它覆盖 `ctexart`、`geometry`、`amsmath`、TikZ 及其允许的常用绘图库、无编号章节、粗体、首段不缩进、`enumerate`，并显式编译 8/9/10/12pt Latin Modern 粗体以缓存 `lmroman8-bold` 等 TFM 资源。预热后同一模板必须在 `--untrusted --only-cached` 下再次编译成功；模型生成的 TeX 从不走联网阶段，应用运行时始终只使用现成缓存。脚本可重复执行；不要删除 `.runtime/tectonic-cache`，除非准备重新预热。

教研考试采用一次结构化 Blueprint 流式生成：DeepSeek 只生成题目、答案和评分标准，服务器再套用固定三页模板并编译 TeX/PDF，不再先生成整套 TeX、校验失败后又重做一遍。若整卷其余结构与课程政策均已通过、仅个别选择题存在重复选项，系统会锁定题干、正确答案、解析及其余选项，只把问题题目交给模型进行一次受限局部修复；修复后重新校验整卷，不重新生成其他题。局部修复默认最多等待 `PHYSICS_EXAM_REPAIR_TIMEOUT_SECONDS=180` 秒、接收 `PHYSICS_EXAM_REPAIR_MAX_OUTPUT_TOKENS=4096`。Rocky 独立 DeepSeek 路由使用 `PHYSICS_EXAM_BASE_URL=http://127.0.0.1:1236/v1`、模型别名、`PHYSICS_EXAM_CONTEXT_WINDOW=1048576`、`PHYSICS_EXAM_MAX_OUTPUT_TOKENS=32768`、`PHYSICS_EXAM_TIMEOUT_SECONDS=1800` 和 `PHYSICS_EXAM_GENERATION_ATTEMPTS=1`。专用模型只有一个生成槽位，“教研考试”入口的完整组卷与普通教研问答统一使用同一应用级队列；完整组卷会持续持锁直至其局部修复全部结束，普通教研问答不得插队。排队任务会在界面显示等待时间。`PHYSICS_EXAM_NO_THINK_SUFFIX` 默认留空，因为 DeepSeek 不接收 MiMo 专用的 `/no_think`；`PHYSICS_EXAM_API_KEY` 留空时回退主 `PHYSICS_API_KEY`。普通问答仍由 `PHYSICS_*` 配置单独限制。

教师入口只有明确“生成新整卷”的请求才进入 Blueprint 组卷流程；上传现有试卷后要求答案、解析、评分、审核或批改时按资料处理任务流式回答，不会重新命题。明确要求答案、解答、解析或评分标准时，回答完成后会额外生成独立的“参考答案.tex”和“参考答案.pdf”供下载。教师对话支持 20 MiB 以内 PDF：消息中显示原文件名与下载按钮，服务器提取文本并将前 8 页渲染为页面图交给本地视觉模型，历史记录也可按需重新加载附件。

## MiMo-VL Miloco 7B AVX2 用户服务

`mimo-vl-avx2.service`、`mimo-vl-avx2.env.example` 和 `install_mimo_vl_avx2_service.sh` 用于 Rocky 普通用户安装独立接口。服务监听 `127.0.0.1:1237`，模型别名为 `mimo-vl-local-prod`，使用现有 LM Studio AVX2 `llama-server` 二进制与配套 `mmproj`，严格绑定 NUMA node 0、CPU `0-127`。`--no-mmap` 让权重复制为受 `--membind=0` 约束的匿名页，避免复用另一节点的文件页缓存。路径和 API key 仅保存在权限为 `0600` 的专用环境文件中。

## DeepSeek V4 Flash AVX-512 用户服务

本目录同时提供 `deepseek-avx512.service`、`deepseek-avx512.env.example` 和 `install_deepseek_avx512_service.sh`，供 Rocky 普通用户安装独立的 OpenAI 兼容 API。默认服务监听 `127.0.0.1:1236`，使用一个 `1048576` token 槽，并通过 `numactl` 严格绑定 NUMA node 1、CPU `128-255`；Direct I/O 绕过共享文件页缓存，权重内存服从 node 1 策略，`Restart=always` 负责异常恢复。

首次执行安装脚本只创建 `~/.config/physics-assistant/deepseek-avx512.env` 并安装 unit。模型实际路径和独立 API key 必须在该文件中填写，配置权限为 `0600`，不得提交到 Git；密钥通过 llama-server 官方的 `LLAMA_API_KEY` 环境变量传递，不进入命令行参数。填写后再次运行脚本才会验证 node 1/CPU `128-255` 并启用服务。`--membind=1` 在 node 1 内存耗尽时直接失败。该后端与 MiMo-VL 1237 服务、应用模型路由和 Nginx 入口相互独立。

## 当前 Rocky 模型验收（2026-08-30）

- MiMo 使用 LM Studio AVX2 后端包 `llama.cpp-linux-x86_64-avx2@2.31.2`，其中 `llama-server` 自报 `0.3.0-dev`（build 1，commit `1844325`）；128000-token 上下文、4 槽、NUMA0/CPU `0-127`，中文问答、物理计算、`/no_think` 与识图均通过。
- DeepSeek 使用自编译 `llama.cpp 0.3.0`（build 1，commit `c1d0e7a`），已确认 AVX-512 指令；1048576-token 上下文、单槽、NUMA1/CPU `128-255`，中文问答、物理计算、严格 JSON、可编译 TeX 和并发串行均通过。
- 两个 unit 均为 `active/enabled`，测试后 PID 不变且 `NRestarts=0`；无效 API key 返回 HTTP 401。由于两者由用户级 systemd 直接启动，`lms ps` 不会列出它们，应检查 `systemctl --user status`、`/v1/models` 和 `/v1/slots`。
- 复杂图片定位建议把 MiMo 的 `--image-min-tokens` 设为至少 `1024`。新版 LM Studio 后端提示 `--no-mmap`、`--no-direct-io` 为兼容参数，迁移到 `--load-mode dio` 前需重新验证冷启动、NUMA 内存归属和识图。

可视化实验包含：

力学实验分组包含杨氏模量、转动惯量和粘滞系数测定。

热学实验分组包含固体比热容的测定、温度传感器特性的测定和固体热传导系数测定。

光学实验分组包含牛顿环、双棱镜干涉测波长、薄透镜焦距的测定和三棱镜折射率测定。

近代物理实验分组包含光电效应和弗兰克-赫兹实验。

- 李萨如图形：相位差、振幅比、有理频率比和频率失谐；
- 声速测量：回声法、双麦克风时差法、示波器相位差法和驻波法。
- 电子荷质比：电子束圆轨道、亥姆霍兹磁场标定、纵向磁聚焦和汤姆孙交叉电磁场。
- 光电效应：伏安特性与光强、普朗克常量拟合、红限与量子规律、遏止电压判读与系统误差。
- 双棱镜干涉测钠黄光波长：分波阵面与虚光源、钠黄光干涉条纹、凸透镜二次成像测间距、波长拟合与不确定度。
- 牛顿环等厚干涉：半波损失与环纹形成、读数显微镜单向扫描、15 级逐差法、直径平方线性拟合与不确定度。
- 杨氏模量测定：光杠杆微小伸长放大、加载与卸载读数、力—伸长线性拟合、杨氏模量与不确定度。
- 转动惯量测定：扭摆法、三线摆法、平行轴定理验证，以及摆动周期拟合与不确定度。
- 粘滞系数测定：斯托克斯落球、终端速度判据、有限圆筒修正、多直径拟合与不确定度。
- 固体比热容的测定：混合法热平衡、冷却散热修正、电加热法、多次数据拟合与不确定度。
- 弗兰克-赫兹实验：实验装置与能级跃迁、周期性峰谷曲线、激发电势分析、拟合与不确定度。
- 温度传感器特性的测定：Pt100 标定、阶跃响应、电桥与导线补偿、滞后与不确定度。
- 惠斯通电桥测电阻：零电流平衡、粗调细调、灵敏度与不确定度、多比率拟合。
- 霍尔效应测磁场分布：霍尔电压标定、沿轴扫描、线性拟合与残差、不确定度。
- 铁磁滞回线测定与观察：基本磁滞回线、积分器标定、交流退磁、损耗与不确定度。
- 薄透镜焦距的测定：物距—像距法、自准直法、贝塞尔位移法、拟合与不确定度。
- 三棱镜折射率测定：分光计调节、棱镜顶角测量、最小偏向角法、色散与不确定度。
- 固体热传导系数测定：稳态导热与温度梯度、冷却散热修正、多工况拟合与不确定度。

十八类实验均采用四个独立页面，只初始化当前选中的页面。最新三项路由为：薄透镜 `/direct`、`/autocollimation`、`/displacement`、`/uncertainty`；三棱镜 `/collimation`、`/apex`、`/minimum-deviation`、`/dispersion`；固体热传导 `/steady-state`、`/cooling`、`/fit`、`/uncertainty`。进入可视化模式时默认打开“力学实验 → 杨氏模量”。

实验依赖 Julia 1.10、Bonito 与 WGLMakie，并在首次打开对应实验时按需启动。若是首次安装 Julia 依赖，可分别执行：

```powershell
julia --project=experiments/lissajous -e "using Pkg; Pkg.instantiate(); Pkg.precompile()"
julia --project=experiments/sound_speed -e "using Pkg; Pkg.instantiate(); Pkg.precompile()"
julia --project=experiments/electron_em -e "using Pkg; Pkg.instantiate(); Pkg.precompile()"
julia --project=experiments/photoelectric -e "using Pkg; Pkg.instantiate(); Pkg.precompile()"
julia --project=experiments/biprism -e "using Pkg; Pkg.instantiate(); Pkg.precompile()"
julia --project=experiments/newton_rings -e "using Pkg; Pkg.instantiate(); Pkg.precompile()"
julia --project=experiments/young_modulus -e "using Pkg; Pkg.instantiate(); Pkg.precompile()"
julia --project=experiments/rotational_inertia -e "using Pkg; Pkg.instantiate(); Pkg.precompile()"
julia --project=experiments/viscosity -e "using Pkg; Pkg.instantiate(); Pkg.precompile()"
julia --project=experiments/specific_heat -e "using Pkg; Pkg.instantiate(); Pkg.precompile()"
julia --project=experiments/franck_hertz -e "using Pkg; Pkg.instantiate(); Pkg.precompile()"
julia --project=experiments/temperature_sensor -e "using Pkg; Pkg.instantiate(); Pkg.precompile()"
julia --project=experiments/wheatstone_bridge -e "using Pkg; Pkg.instantiate(); Pkg.precompile()"
julia --project=experiments/hall_effect -e "using Pkg; Pkg.instantiate(); Pkg.precompile()"
julia --project=experiments/magnetic_hysteresis -e "using Pkg; Pkg.instantiate(); Pkg.precompile()"
julia --project=experiments/thin_lens_focal -e "using Pkg; Pkg.instantiate(); Pkg.precompile()"
julia --project=experiments/prism_refractive_index -e "using Pkg; Pkg.instantiate(); Pkg.precompile()"
julia --project=experiments/thermal_conductivity -e "using Pkg; Pkg.instantiate(); Pkg.precompile()"
```

这些 Manifest 由 Julia 1.10.10 生成。若 Juliaup 当前默认版本较新，启动器会自动优先使用本机已安装的 `+1.10.10` 通道；`PHYSICS_JULIA_EXE` 和 `PHYSICS_JULIA_CHANNEL` 可用于显式覆盖。

十八套实验分别使用 `9384`–`9401` 回环端口，只监听本机，由 `gateway.py` 通过主站 `8501/experiments/...` 内嵌代理。最新三项使用 `9399`–`9401`。局域网使用前，以管理员身份运行 `enable_lan.ps1`，脚本只开放统一入口 `8501`。

同时启动学生端和管理员后台：

```powershell
.\start_all.ps1
```

管理员后台也由统一入口代理；管理员从主站登录后会跳转到 `/agent/analytics`（根路径部署时为 `/analytics`）。注册用户登录会通过同一网关换取签名的 HttpOnly Cookie，刷新页面可自动恢复账号，退出时由网关清除。完成名册身份核验的账号可使用原用户名或学号/工号登录，两种方式均进入同一账号并共享历史记录。管理页面支持名册批量导入，以及未绑定名册记录的逐条修改和删除；已绑定记录受保护。详细配置见仓库根目录说明。

Windows 联网搜索配置位于 `.streamlit/secrets.toml`。该文件使用 TOML 语法，字符串必须写在引号中，例如 `tavily_api_key = "..."`；不要直接复制 Linux 的 `KEY=value` 写法，也不要把密钥提交到 Git。
