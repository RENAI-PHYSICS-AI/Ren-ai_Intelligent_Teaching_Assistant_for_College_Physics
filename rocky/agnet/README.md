# 大学物理智能助教（Rocky 应用目录）

本目录是 Rocky Linux 独立版的应用代码与运行数据目录。完整部署说明见上一级 [README.md](../README.md)。

请勿单独执行本目录中的 Windows 启动方式。把完整 `rocky` 文件夹复制到服务器后，在上一级目录运行：

```bash
bash install.sh
```

请使用普通用户，不要使用 sudo。安装器只在当前 `rocky` 目录中创建 Python、Julia、配置和运行文件，并通过用户级 Python 网关统一提供 `8501`；不会修改任何系统目录。可视化实验使用 `9384` 和 `9385`。

本目录中的关键数据：

- `data/assistant.db`：迁移的用户、管理员、会话、消息、反馈和学情数据；
- `data/backups/`：Windows 端已有数据库备份；
- `knowledge_base/`：完整 RAG 知识库及竞赛专题扩展；
- `experiments/`：李萨如与声速测量 Julia/WGLMakie 实验。

原始教材、课件与课程资料位于上一级 `教学素材/`。
