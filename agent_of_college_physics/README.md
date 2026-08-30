# Rocky Linux 10 用户目录版

本目录是一套与 Windows 版独立的、可直接复制的 Rocky Linux 10 版本，包含应用、整理后的教学资料、RAG 知识库和十八套可视化实验。用户、管理员、历史、数据库备份和签名密钥属于本机运行数据，可通过受控流程迁移，但不进入 Git。

回答以本地教材和 RAG 知识库为核心；遇到明确联网请求或时效性问题时，应用按需调用 Tavily 检索网络资料，再由本地模型统一组织答案。教材课程口径与网络资料不一致时以教材为准。

本版本已在学校服务器部署运行。校内访问地址：[https://192.168.222.147:1234/agent/](https://192.168.222.147:1234/agent/)

主应用安装不需要也不允许 `sudo`，不会写入 `/opt`、`/etc`、`/var`、`/usr/local`，不会创建系统用户，也不会修改 Nginx、系统级 systemd、firewalld 或 SELinux。Python、Julia、主应用配置、日志和 PID 文件都保存在复制后的当前目录。只有明确运行可选模型安装脚本时，才会在当前用户的 `~/.config/systemd/user/` 安装 MiMo 与 DeepSeek 用户级 unit，并在 `~/.config/physics-assistant/` 保存各自 `0600` 专用配置。

## 目录与数据

当前目录约 `1.77 GiB`，包含：

- 原始教学素材 702 个文件；
- RAG 主知识库 58,065 个文本块，其中基础教学素材 35,967 个；最新专题有效导入包括薄透镜焦距 634 个、三棱镜折射率 202 个、固体热传导系数 1,059 个文本块；
- 注册用户与匿名会话都支持逐条确认删除完整问答；只有问题而没有回答的孤立条目也可单独删除，注册用户的删除会同步写入数据库；
- 本机运行时可保存用户、管理员、对话、反馈、学情、身份名册、数据库备份和管理员签名密钥，这些内容均由 Git 忽略；
- 李萨如图形、声速测量、电子荷质比、光电效应、双棱镜干涉、牛顿环、杨氏模量、转动惯量、粘滞系数、固体比热容、弗兰克-赫兹、温度传感器、惠斯通电桥、霍尔效应、铁磁滞回线、薄透镜焦距、三棱镜折射率与固体热传导系数；十八类实验均包含四个按需加载的独立页面。
- Paraformer 中文流式语音输入服务及固定版本模型下载器。

`.streamlit/secrets.toml` 和 API Key 不会明文迁移。主应用模型连接写在安装后生成的 `config/physics-assistant.env` 中；MiMo 与 DeepSeek API 的独立密钥分别只写入当前用户的 `mimo-vl-avx2.env` 和 `deepseek-avx512.env`。

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
                 ├─ /experiments/photoelectric → 本机光电效应实验（127.0.0.1:9387）
                 ├─ /experiments/biprism → 本机双棱镜实验（127.0.0.1:9388）
                 ├─ /experiments/newton-rings → 本机牛顿环实验（127.0.0.1:9389）
                 ├─ /experiments/young-modulus → 本机杨氏模量实验（127.0.0.1:9390）
                 ├─ /experiments/rotational-inertia → 本机转动惯量实验（127.0.0.1:9391）
                 ├─ /experiments/viscosity → 本机粘滞系数实验（127.0.0.1:9392）
                 ├─ /experiments/specific-heat → 本机固体比热容实验（127.0.0.1:9393）
                 ├─ /experiments/franck-hertz → 本机弗兰克-赫兹实验（127.0.0.1:9394）
                 ├─ /experiments/temperature-sensor → 本机温度传感器实验（127.0.0.1:9395）
                 ├─ /experiments/wheatstone-bridge → 本机惠斯通电桥实验（127.0.0.1:9396）
                 ├─ /experiments/hall-effect → 本机霍尔效应实验（127.0.0.1:9397）
                 ├─ /experiments/magnetic-hysteresis → 本机铁磁滞回线实验（127.0.0.1:9398）
                 ├─ /experiments/thin-lens-focal → 本机薄透镜焦距实验（127.0.0.1:9399）
                 ├─ /experiments/prism-refractive-index → 本机三棱镜折射率实验（127.0.0.1:9400）
                 └─ /experiments/thermal-conductivity → 本机固体热传导系数实验（127.0.0.1:9401）
```

所有实际后端服务只监听本机或仅供服务器内部代理使用；校园网络只开放现有的 `1234` HTTPS 入口。`8501` 是反向代理内部上游，`8443` 是独立部署时的备用 HTTPS 网关，当前未对校园网络开放。实验图形由访问者浏览器的 WebGL2 渲染。

## 环境要求

- Rocky Linux 10，`x86_64` 或 `aarch64`；
- 普通 SSH 用户，不需要 sudo 权限；
- 至少 8 GB 内存，Julia 首次预编译建议 12 GB；
- 用户目录至少预留 8 GB 空间；
- 系统已有 `curl`、`tar`、`gzip`、`sha256sum`、`awk`；启用项目 HTTPS 时还需要 `openssl`；
- 安装阶段能访问 uv、Python 包源、Julia 官方下载站、GitHub 的 Noto CJK 字体源和 Hugging Face 模型仓库；
- 已确认现有 LM Studio AVX2 `llama-server` 二进制支持 `--mmproj`、`--no-mmap` 与本项目所列参数；生产运行不依赖 `lms load`。

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

`bash manage.sh status` 默认显示 `admin`、`asr`、`web`、`gateway` 四项运行中；配置 HTTPS 后还会显示 `gateway_https`。`bash manage.sh check` 会验证 ASR、统一入口，以及所有已按需启动实验的直接回环地址与 8501 代理路径。语音详细日志为 `.runtime/logs/asr.log`，HTTPS 网关日志为 `.runtime/logs/gateway_https.log`。`8604`、`9384`–`9401` 等内部端口固定只绑定 `127.0.0.1`，不得加入防火墙放行列表。

## 可视化实验

十八套 Julia/WGLMakie 实验分别使用 `9384`–`9401` 回环端口，均由主站按需启动。学生浏览器只访问统一入口，不直连实验内部端口；首次进入可视化模式默认加载“力学实验 → 杨氏模量”：

力学实验分组包含杨氏模量、转动惯量和粘滞系数测定。

热学实验分组包含固体比热容的测定、温度传感器特性的测定和固体热传导系数测定。

光学实验分组包含牛顿环、双棱镜干涉测波长、薄透镜焦距的测定和三棱镜折射率测定。

电磁实验分组包含电子荷质比、惠斯通电桥测电阻、霍尔效应测磁场分布和铁磁滞回线测定与观察。

近代物理实验分组包含光电效应和弗兰克-赫兹实验。

- 李萨如图形：相位差、振幅比、有理频率比和频率失谐；
- 声速测量：回声法、双麦克风时差法、示波器相位差法和驻波法；
- 电子荷质比：电子束圆轨道、亥姆霍兹线圈磁场标定、纵向磁聚焦和汤姆孙交叉电磁场。
- 光电效应：伏安特性与光强、普朗克常量拟合、红限与量子规律、遏止电压判读与系统误差。
- 双棱镜干涉测钠黄光波长：分波阵面与虚光源、钠黄光干涉条纹、凸透镜二次成像测间距、波长拟合与不确定度。
- 牛顿环测曲率半径：反射等厚干涉与半波损失、读数显微镜单向扫描、15 级逐差和直径平方线性拟合。
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

十八类实验均只构建和加载当前选中的页面。李萨如子页面为 `/phase`、`/amplitude`、`/ratio`、`/detune`；声速子页面为 `/echo`、`/dual`、`/phase`、`/standing`。

电子荷质比的公开基路径为 `/experiments/electron-em`，四个子页面分别是 `/circular`、`/helmholtz`、`/focus` 和 `/thomson`。它们共用一个只监听 `127.0.0.1:9386` 的内部服务，但分别构建和加载页面，避免打开一项实验时初始化其他三项。

光电效应的公开基路径为 `/experiments/photoelectric`，四个子页面分别是 `/iv`、`/planck`、`/threshold` 和 `/uncertainty`。它们共用一个只监听 `127.0.0.1:9387` 的内部服务，也只构建当前选中的图形。

双棱镜的公开基路径为 `/experiments/biprism`，四个子页面分别是 `/geometry`、`/fringes`、`/separation` 和 `/wavelength`。它们共用一个只监听 `127.0.0.1:9388` 的内部服务，固定测量空气中的钠黄光，标称参考波长为 `589.3 nm`。

牛顿环的公开基路径为 `/experiments/newton-rings`，四个子页面分别是 `/formation`、`/measurement`、`/difference` 和 `/fit`。它们共用一个只监听 `127.0.0.1:9389` 的内部服务，以 `589.3 nm` 钠黄光为已知量测量平凸透镜曲率半径。

杨氏模量的公开基路径为 `/experiments/young-modulus`，四个子页面分别是 `/principle`、`/loading`、`/fit` 和 `/uncertainty`。它们共用一个只监听 `127.0.0.1:9390` 的内部服务，以金属丝静态拉伸和光杠杆放大完成加载/卸载、线性拟合及不确定度分析。

转动惯量的公开基路径为 `/experiments/rotational-inertia`，四个子页面分别是 `/torsion`、`/trifilar`、`/parallel-axis` 和 `/pendulum-fit`。它们共用一个只监听 `127.0.0.1:9391` 的内部服务，分别演示扭摆法、三线摆法、平行轴定理验证和摆动周期拟合。

粘滞系数的公开基路径为 `/experiments/viscosity`，四个子页面分别是 `/stokes`、`/terminal`、`/correction` 和 `/fit`。它们共用一个只监听 `127.0.0.1:9392` 的内部服务，分别演示斯托克斯受力与落球过程、终端速度测量、有限圆筒修正和多直径线性拟合。

固体比热容的公开基路径为 `/experiments/specific-heat`，四个子页面分别是 `/mixing`、`/cooling`、`/electrical` 和 `/fit`。它们共用一个只监听 `127.0.0.1:9393` 的内部服务，分别演示混合法热平衡、冷却散热修正、电加热法和多次测量拟合与不确定度。健康端点 `/__physics_health__` 必须返回 `physics-experiment:specific-heat`；`manage.sh check` 同时核验 9393 直连与 8501 代理结果。

弗兰克-赫兹实验的公开基路径为 `/experiments/franck-hertz`，四个子页面分别是 `/apparatus`、`/curve`、`/analysis` 和 `/uncertainty`。它们共用一个只监听 `127.0.0.1:9394` 的内部服务，分别演示实验装置与能级跃迁、周期性峰谷曲线、激发电势分析、拟合与不确定度。健康端点 `/__physics_health__` 必须返回 `physics-experiment:franck-hertz`；`manage.sh check` 同时核验 9394 直连与 8501 代理结果。

最新三项依次使用 `9399`–`9401`：薄透镜 `/direct`、`/autocollimation`、`/displacement`、`/uncertainty`；三棱镜 `/collimation`、`/apex`、`/minimum-deviation`、`/dispersion`；固体热传导 `/steady-state`、`/cooling`、`/fit`、`/uncertainty`。`manage.sh check` 同时核验三项的直连和代理健康标识。

## 模型配置

```bash
vi config/physics-assistant.env
bash manage.sh restart
```

默认配置：

```ini
PHYSICS_BASE_URL=http://127.0.0.1:1237/v1
PHYSICS_MODEL=mimo-vl-local-prod
PHYSICS_VISION_MODEL=mimo-vl-local-prod
PHYSICS_EXAM_BASE_URL=http://127.0.0.1:1236/v1
PHYSICS_EXAM_MODEL=deepseek/deepseek-v4-flash-avx512
PHYSICS_EXAM_API_KEY=
PHYSICS_EXAM_NO_THINK_SUFFIX=
PHYSICS_EXAM_TIMEOUT_SECONDS=1800
PHYSICS_EXAM_CONTEXT_WINDOW=1048576
PHYSICS_EXAM_MAX_OUTPUT_TOKENS=32768
PHYSICS_CONTEXT_WINDOW=128000
PHYSICS_HISTORY_MAX_MESSAGES=4
PHYSICS_MAX_OUTPUT_TOKENS=4096
KB_CONTEXT_MAX_CHARS=2500
PHYSICS_VISION_MAX_OUTPUT_TOKENS=2048
PHYSICS_VISION_TIMEOUT_SECONDS=360
PHYSICS_CHAT_MODEL_KEY=xiaomi-mimo-vl-miloco-7b
PHYSICS_CHAT_MODEL_IDENTIFIER=mimo-vl-local-prod
PHYSICS_CHAT_MODEL_CONTEXT=128000
PHYSICS_CHAT_MODEL_PARALLEL=4
PHYSICS_VISION_MODEL_KEY=xiaomi-mimo-vl-miloco-7b
PHYSICS_VISION_MODEL_IDENTIFIER=mimo-vl-local-prod
PHYSICS_VISION_MODEL_CONTEXT=128000
PHYSICS_VISION_MODEL_PARALLEL=4
PHYSICS_CHAT_NO_THINK_SUFFIX=/no_think
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
PHYSICS_BIPRISM_PORT=9388
PHYSICS_BIPRISM_UPSTREAM=http://127.0.0.1:9388
PHYSICS_NEWTON_RINGS_PORT=9389
PHYSICS_NEWTON_RINGS_UPSTREAM=http://127.0.0.1:9389
PHYSICS_YOUNG_MODULUS_PORT=9390
PHYSICS_YOUNG_MODULUS_UPSTREAM=http://127.0.0.1:9390
PHYSICS_ROTATIONAL_INERTIA_PORT=9391
PHYSICS_ROTATIONAL_INERTIA_UPSTREAM=http://127.0.0.1:9391
PHYSICS_VISCOSITY_PORT=9392
PHYSICS_VISCOSITY_UPSTREAM=http://127.0.0.1:9392
PHYSICS_SPECIFIC_HEAT_PORT=9393
PHYSICS_SPECIFIC_HEAT_UPSTREAM=http://127.0.0.1:9393
PHYSICS_FRANCK_HERTZ_PORT=9394
PHYSICS_FRANCK_HERTZ_UPSTREAM=http://127.0.0.1:9394
PHYSICS_TEMPERATURE_SENSOR_PORT=9395
PHYSICS_TEMPERATURE_SENSOR_UPSTREAM=http://127.0.0.1:9395
PHYSICS_WHEATSTONE_BRIDGE_PORT=9396
PHYSICS_WHEATSTONE_BRIDGE_UPSTREAM=http://127.0.0.1:9396
PHYSICS_HALL_EFFECT_PORT=9397
PHYSICS_HALL_EFFECT_UPSTREAM=http://127.0.0.1:9397
PHYSICS_MAGNETIC_HYSTERESIS_PORT=9398
PHYSICS_MAGNETIC_HYSTERESIS_UPSTREAM=http://127.0.0.1:9398
PHYSICS_THIN_LENS_FOCAL_PORT=9399
PHYSICS_THIN_LENS_FOCAL_UPSTREAM=http://127.0.0.1:9399
PHYSICS_PRISM_REFRACTIVE_INDEX_PORT=9400
PHYSICS_PRISM_REFRACTIVE_INDEX_UPSTREAM=http://127.0.0.1:9400
PHYSICS_THERMAL_CONDUCTIVITY_PORT=9401
PHYSICS_THERMAL_CONDUCTIVITY_UPSTREAM=http://127.0.0.1:9401
```

当前对话、识图和最终答案统一使用学校 Rocky 服务器 `tjracphy` 本机的 MiMo VL Miloco 7B，生产 API 标识为 `mimo-vl-local-prod`。图片先由该模型识别，识别文本再交给同一模型结合知识库组织答案。MiMo 独立用户服务监听 `127.0.0.1:1237`，使用 128K 上下文与4个并行槽并严格绑定 NUMA0/CPU `0-127`；`manage.sh` 只启动用户 unit 并验证 API，不再通过 LM Studio CLI 重复加载。

### 独立 MiMo-VL Miloco 7B AVX2 服务

`agnet/mimo-vl-avx2.service` 使用现有 LM Studio AVX2 `llama-server` 二进制、模型 GGUF 和配套 mmproj。首次运行 `bash agnet/install_mimo_vl_avx2_service.sh` 创建 `0600` 配置；填写 `~/.config/physics-assistant/mimo-vl-avx2.env` 后再次运行即可启用。服务固定别名 `mimo-vl-local-prod`、端口 1237、NUMA node 0、CPU `0-127`，并通过 `--no-mmap` 避免权重复用其他节点的文件页缓存。

### 独立 DeepSeek V4 Flash AVX-512 服务

`agnet/deepseek-avx512.service` 提供独立 OpenAI 兼容 API，固定监听 `127.0.0.1:1236`。默认使用一个 `1048576` token 槽，并通过 `numactl` 严格绑定 NUMA node 1、CPU `128-255`。应用层对“教研考试”入口的全部 DeepSeek 请求使用同一把进程级锁：完整组卷从首次生成到所有局部修复结束前持续持锁，普通教研问答只能排队，不能插入组卷的修复调用之间；“智能助教”仍走 MiMo，不进入该队列。模型路径和独立 API key 只保存在当前用户的 `~/.config/physics-assistant/deepseek-avx512.env`，不会写入 unit 或 Git：

```bash
bash agnet/install_deepseek_avx512_service.sh
vi ~/.config/physics-assistant/deepseek-avx512.env
bash agnet/install_deepseek_avx512_service.sh
```

首次运行会安装用户级 unit、创建权限为 `0600` 的配置并停止，不会以空配置启动；填写后再次运行才启用并启动服务。API key 通过 llama-server 官方的 `LLAMA_API_KEY` 环境变量传递，不进入命令行参数。`--membind=1` 在 node 1 内存耗尽时直接失败，安装器还会验证全部 CPU 的节点归属并执行 NUMA dry-run。服务采用 `Restart=always`。若要求服务器重启后在无人登录时也自动启动，需让管理员为运行用户启用 linger。

应用的教研考试路由使用上方 `PHYSICS_EXAM_*` 配置：`1048576` 上下文、`32768` 输出上限、1800 秒单轮总耗时上限及 `PHYSICS_EXAM_GENERATION_ATTEMPTS=1`。整卷只生成一次结构化 Blueprint，随后由服务器固定模板生成 TeX/PDF；校验失败不会在后台静默重做整卷。专用 DeepSeek 为单槽位，并发命题会在页面明确显示排队时间。`PHYSICS_EXAM_NO_THINK_SUFFIX` 必须留空，DeepSeek 不接收 MiMo 专用的 `/no_think`；`PHYSICS_EXAM_API_KEY` 留空时回退 `PHYSICS_API_KEY`，其最终有效值必须与服务专用环境文件中的 `LLAMA_API_KEY` 相同。该路由不接管普通问答、识图或 Nginx。完整编译、校验、健康检查与停启方式见仓库根目录《AVX512后端部署与启动流程.md》。

### 当前模型后端验收（2026-08-30）

| 路由 | 当前后端与约束 | 生产验收结果 |
| --- | --- | --- |
| 普通问答与识图 | LM Studio AVX2 后端包 `llama.cpp-linux-x86_64-avx2@2.31.2`；其中 `llama-server` 自报 `0.3.0-dev`（build 1，commit `1844325`）；MiMo 为 128000-token 上下文、4 槽、NUMA0/CPU `0-127` | 中文问答、大学物理计算、`/no_think` 生产输出与图片识别通过；unit 为 `active/enabled`，测试后 PID 未变化、`NRestarts=0` |
| 教研考试 | 自编译 `llama.cpp 0.3.0`（build 1，commit `c1d0e7a`），已确认 AVX-512 指令；DeepSeek 为 1048576-token 上下文、单槽、NUMA1/CPU `128-255` | 中文问答、物理计算、严格 JSON 与可编译 TeX 输出通过；并发请求按单槽串行，组卷锁覆盖生成及局部修复；unit 为 `active/enabled`，`NRestarts=0` |

本轮热态烟测中，MiMo 的基础问答、物理计算和简单识图分别约为 5.87 秒、15.08 秒和 1.65 秒，短 `/no_think` 回答约为 0.30 秒；DeepSeek 的基础问答、物理计算、严格 JSON 和 TeX 测试分别约为 7.64 秒、20.93 秒、3.96 秒和 19.29 秒。各测试的提示和输出长度不同，数据只作为升级后的回归基线，不代表固定响应时延；测试过程中两个服务均未使用交换内存。

两条 API 都要求鉴权，无效密钥返回 HTTP 401。`lms ps` 不显示这两个服务是正常现象：它只列出 llmster 管理的实例，模型实际由用户级 systemd 常驻，应使用 `systemctl --user status mimo-vl-avx2.service deepseek-avx512.service`、`/v1/models` 和 `/v1/slots` 检查。复杂图片定位建议将 MiMo 的 `--image-min-tokens` 设为至少 `1024`。新版 LM Studio 后端已经提示 `--no-mmap`、`--no-direct-io` 为兼容参数；迁移到 `--load-mode dio` 前必须重新验证冷启动、NUMA 内存归属和识图结果。

当前 Rocky 与 Windows 版本均已配置并启用 Tavily Search API 联网补充。普通教材概念、公式推导和计算题不会联网；问题明确要求联网，或包含“最新、近期、目前、进展、现行标准”等时效性表达时才触发。应用只发送当前问题文本，不发送用户身份、历史记录或图片。结果经过清洗后作为不可信参考交给 MiMo-VL，并在答案末尾附真实来源链接；搜索失败会自动退回本地知识库，相同问题默认缓存 30 分钟。Rocky 密钥保存在 `config/physics-assistant.env`，Windows 密钥保存在 `.streamlit/secrets.toml`，两者都不得提交到 Git。

注册用户登录后由 `/session-login` 换取服务器签名的 HttpOnly Cookie；完成名册身份核验后，可使用原用户名或学号/工号登录，两种方式均解析为同一个账号。刷新页面会重新核验数据库中的账号状态并恢复登录，默认有效期为 7 天。HTTPS 入口会为 Cookie 自动增加 `Secure` 属性，退出登录通过 `/session-logout` 清除 Cookie；`PHYSICS_USER_SESSION_SECONDS` 可在 1 小时至 30 天范围内调整。

已通过名册核验的教师登录后先选择“智能助教”或“教研考试”。教研考试复用全部公共知识库，并可叠加 `教学素材/教师专用/教研考试/` 构建出的私有命题索引，用于组卷、专项出题、参考答案和评分标准；两个入口的历史记录按智能体隔离。新增教师资料后执行 `./agnet/.venv/bin/python ./agnet/build_teacher_exam_kb.py`，再重启服务即可刷新教师私有索引；教师资料和生成索引不会提交到 Git。

生成整套试卷前，系统必须取得学年、学期和考试名称；缺失时先提示教师补充，考试日期可以留空且不得自动猜测。只有教师明确指定补考时大标题才包含“补考”。大学物理1与大学物理A的试题、答案和评分点均排除相对论内容。大题编号按单选“一”、填空“二”、五道计算题“三”至“七”连续排列；每道计算题有独立主题标题和“共10分”，五题主题顺序可按蓝图调整。试卷严格生成三张物理页，每页采用框外页眉、独立2pt黑色外框和双栏题面，并按标准模板显式换栏、分页和保留计算题答题空间；结构化蓝图在编译前拒绝超长题干或超栏文本预算，避免 TeX 拆页卡死。题图优先使用安全 TikZ；引用可信模板图件时，服务器同时提供含 TeX、PDF 与图件的完整 ZIP。

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

浏览器统一通过 `https://192.168.222.147:1234/agent/` 访问；Rocky 应用在服务器内部通过 `http://127.0.0.1:1237/v1` 调用 MiMo，并通过 `http://127.0.0.1:1236/v1` 调用 DeepSeek，不受外部 HTTPS 入口影响。不要为当前生产环境配置 Edge 的 HTTP 安全来源例外，也不要把 `PHYSICS_PUBLIC_BASE_URL` 改回 HTTP。

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

杨氏模量专题的 10 份可追溯资料、111 个导入文本块及解析报告位于 `教学素材/物理实验/杨氏模量测定/` 和 `agnet/knowledge_base/imports/young_modulus.*`。需要单独重建并合并该专题时执行：

```bash
./agnet/.venv/bin/python ./agnet/build_young_modulus_import.py
./agnet/.venv/bin/python ./agnet/build_kb.py --merge-imports-only
```

转动惯量专题的约 10 篇核心参考资料、8 份本地核验 PDF、285 个导入文本块及解析报告位于 `教学素材/物理实验/转动惯量测定/` 和 `agnet/knowledge_base/imports/rotational_inertia.*`。需要单独重建并合并该专题时执行：

```bash
./agnet/.venv/bin/python ./agnet/build_rotational_inertia_import.py
./agnet/.venv/bin/python ./agnet/build_kb.py --merge-imports-only
```

粘滞系数专题的可视化方案、约 10 篇经典参考题录、可追溯本地资料及解析报告位于 `教学素材/物理实验/粘滞系数测定/` 和 `agnet/knowledge_base/imports/viscosity.*`。需要单独重建并合并该专题时执行：

```bash
./agnet/.venv/bin/python ./agnet/build_viscosity_import.py
./agnet/.venv/bin/python ./agnet/build_kb.py --merge-imports-only
```

固体比热容专题的可视化方案、约 10 篇经典参考题录、可追溯本地资料及解析报告位于 `教学素材/物理实验/固体比热容的测定/` 和 `agnet/knowledge_base/imports/specific_heat.*`。需要单独重建并合并该专题时执行；最终文本块数以 `agnet/knowledge_base/manifest.json` 为准：

```bash
./agnet/.venv/bin/python ./agnet/build_specific_heat_import.py
./agnet/.venv/bin/python ./agnet/build_kb.py --merge-imports-only
```

弗兰克-赫兹专题的 10 篇核心文献、6 份 PDF、3 份 Markdown、合计 9 份导入文档、503 个专题文本块及解析报告位于 `教学素材/物理实验/弗兰克-赫兹实验/` 和 `agnet/knowledge_base/imports/franck_hertz.*`。需要单独重建并合并该专题时执行：

```bash
./agnet/.venv/bin/python ./agnet/build_franck_hertz_import.py
./agnet/.venv/bin/python ./agnet/build_kb.py --merge-imports-only
```

薄透镜焦距、三棱镜折射率和固体热传导系数三个专题各整理约 10 篇经典或权威文献，资料分别位于 `教学素材/物理实验/薄透镜焦距的测定/`、`教学素材/物理实验/三棱镜折射率测定/` 和 `教学素材/物理实验/固体热传导系数测定/`。单独重建时运行对应的 `agnet/build_thin_lens_focal_import.py`、`agnet/build_prism_refractive_index_import.py` 或 `agnet/build_thermal_conductivity_import.py`，再执行 `agnet/build_kb.py --merge-imports-only`。

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
│  ├─ download_asr_model.py  # 固定版本模型下载与校验
│  ├─ deepseek-avx512.service             # DeepSeek 用户级 systemd unit
│  ├─ deepseek-avx512.env.example         # 无真实路径和密钥的专用环境示例
│  ├─ install_deepseek_avx512_service.sh  # DeepSeek unit 安装、校验与启用脚本
│  ├─ mimo-vl-avx2.service                 # MiMo-VL 用户级 systemd unit
│  ├─ mimo-vl-avx2.env.example             # MiMo 模型、mmproj 与密钥示例
│  └─ install_mimo_vl_avx2_service.sh      # MiMo unit 安装、校验与启用脚本
└─ 教学素材/                 # 全部原始教学资源
```
