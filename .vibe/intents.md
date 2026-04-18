# 智能体工作流意图沉淀日志

### [2026-04-13] - 从 IDE 副驾驶向独立 Web 工作站的架构重构
- **驱动模型**: Gemini 3.1 Pro (High)
- **涉及文件**: `frontend/src/App.vue`, `backend/main.py`, `backend/scripts/universal_doc_gen.py`
- **变更逻辑摘要**: 
  - **初始实现思路/技术决策**: 将原有强依赖 IDE 侧边栏和 MCP 的软著生成工具，重构为前后端分离的独立平台。
  - **前端 (Vue 3 + Vite)**: 实现了左中右三栏式布局，左侧实现文件拖拽上传，中侧渲染生成的 Markdown（作为预览画布），右边显示 Agent 推演和执行日志，为用户提供友好的操作互动体验。
  - **后端 (FastAPI)**: 利用 FastAPI 提供 RESTful API (`/api/upload`, `/api/generate`)，完成从 ZIP 压缩包接收到提取源码、通过 Gemini 调用结构化 System Prompt（硬编码了文风与视角的“铁律”）的能力。
  - **引擎改造 (universal_doc_gen.py)**: 把原先 Python 代码迁移到 `backend/scripts` 下，适配后端参数调用，并且支持解析符合 DOT 格式规范的流程图节点，输出高标准的 Docx 文档格式。
