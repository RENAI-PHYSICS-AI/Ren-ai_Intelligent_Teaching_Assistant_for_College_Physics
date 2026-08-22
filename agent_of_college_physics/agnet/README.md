# 大学物理智能助教（Rocky 应用目录）

本目录是 Rocky Linux 独立版的应用代码与运行数据目录。完整部署说明见上一级 [README.md](../README.md)。

请勿单独执行本目录中的 Windows 启动方式。把完整 `agent_of_college_physics` 文件夹复制到服务器后，在上一级目录运行：

```bash
bash install.sh
```

请使用普通用户，不要使用 sudo。安装器只在当前 `agent_of_college_physics` 目录中创建 Python、Julia、配置和运行文件，并通过用户级 Python 网关统一提供内部上游 `8501`；不会修改任何系统目录。学校当前只通过 [https://192.168.222.147:1234/agent/](https://192.168.222.147:1234/agent/) 对外访问，备用 `8443` 未向校园网络开放。四套可视化实验只作为本机内部服务运行，由主站 `/experiments/...` 路径内嵌，不单独对外提供端口。

安装器还会准备 Paraformer-zh-streaming INT8 模型。语音服务仅监听 `127.0.0.1:8604`，由主站 `/asr/...` 同源代理，不新增外部端口。学校浏览器应统一使用当前 `1234` HTTPS/WSS 入口；普通 HTTP IP 地址不属于生产入口，也不能取得远程麦克风权限。

本机模型采用固定两段式分工：GLM-4.7-Flash（`glm47-local-prod`）负责普通对话与最终答案，Qwen3-VL-30B（`qwen-vl30-local-prod`）只提取图片中的可见信息，再把识别文本交给 GLM 结合知识库组织答案。`manage.sh` 会按 8K 上下文、4 个并行槽检查并加载两个模型，不设置 TTL，因而保持常驻。

联网补充由应用按需调用 Tavily API：普通教材题不联网，明确要求搜索或涉及最新、近期、目前等时效信息时才发送当前问题文本；不会发送用户身份、历史记录或图片。检索失败会自动退回本地知识库，采用的来源链接会附在答案末尾。

本目录中的关键数据：

- `data/assistant.db`：迁移的用户、管理员、会话、消息、反馈和学情数据；
- 注册用户通过签名的 HttpOnly Cookie 保持登录，刷新页面会从数据库核验账号后恢复会话，退出登录会清除 Cookie；
- `data/backups/`：Windows 端已有数据库备份；
- `knowledge_base/`：完整 RAG 知识库及竞赛专题扩展；
- `experiments/`：李萨如、声速测量、电子荷质比与光电效应 Julia/WGLMakie 实验；四类均各有四个独立页面，只初始化当前选中项。李萨如页面为 `/phase`、`/amplitude`、`/ratio`、`/detune`；声速为 `/echo`、`/dual`、`/phase`、`/standing`；电子荷质比使用 `/experiments/electron-em` 和 `9386`，页面为 `/circular`、`/helmholtz`、`/focus`、`/thomson`；光电效应使用 `/experiments/photoelectric` 和 `9387`，页面为 `/iv`、`/planck`、`/threshold`、`/uncertainty`。

原始教材、课件与课程资料位于上一级 `教学素材/`。
