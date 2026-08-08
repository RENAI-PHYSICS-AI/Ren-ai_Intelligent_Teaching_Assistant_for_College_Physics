# 已吸收的实验专题知识索引

本目录只保存可供 RAG 检索的 JSONL 文本索引，不包含原项目的智能体代码、页面、脚本、Julia 实验或原始文献文件：

- `lissajous.jsonl`：李萨如图形、机械振动、示波器测量及相关经典资料。
- `sound_speed.jsonl`：声速、声波、驻波、相位法、时差法和回声法等实验资料。
- `*.manifest.json`：原知识库的构建时间、文献数、文本块数和检索配置。
- `*.extraction_report.json`：原始文献的逐文件解析与 OCR 建议记录。

运行 `python build_kb.py` 会在完整重建时自动合并这些索引；运行
`python build_kb.py --merge-imports-only` 可以只刷新扩展知识索引，不重新解析全部教学素材。

整合规则：祝之光《物理学》第 5 版仍保持最高优先级，竞赛专题资料以较低权重用于补充实验背景、经典文献和测量方法。
