# 大学物理智能助教

以祝之光《物理学》第5版及配套习题解答为基准，并以整个 `教学素材` 目录为补充的本地 RAG 教学应用。

## 功能

- PDF、PPT/PPTX、DOC/DOCX等教学资料的页级/幻灯片级检索和来源标注
- 按章节限定检索范围
- 概念解释、公式推导、物理直觉、易错点和自检问题
- 未配置模型时仍可使用本地教材检索
- OpenAI-compatible 生成引擎；当前配置为局域网 `xiaomi-mimo-vl-miloco-7b`（MiMo VL）

## 启动

双击 `start.bat`，或在 PowerShell 中运行：

```powershell
.\start.ps1
```

浏览器访问 `http://localhost:8503`。

## 模型配置

设置普通百炼按量计费环境变量 `DASHSCOPE_API_KEY`，也可设置 `PHYSICS_API_KEY`、`PHYSICS_BASE_URL`、`PHYSICS_MODEL`；或者复制
`.streamlit/secrets.toml.example` 为 `.streamlit/secrets.toml` 后填写。

默认端点为 `https://dashscope.aliyuncs.com/compatible-mode/v1`，默认模型为 `qwen-plus`。
Token Plan/Coding Plan 专用密钥不能用于本自定义应用后端。

## 知识库说明

运行 `uv run --python 3.13 --with-requirements requirements.txt python build_kb.py` 可重新生成知识库。
祝之光教材正文 PDF 是扫描版，目前没有有效文字层；构建器会优先提取正文已有文字，并完整索引配套习题解答和 `教学素材` 中的补充资料。
旧式二进制 DOC/PPT 在 Office COM 不可用时采用保守文本恢复；未能提取正文的文件仍会进入资源目录索引。
知识库只保存检索文本、来源名称和 PDF 页码，不复制原始 PDF。
