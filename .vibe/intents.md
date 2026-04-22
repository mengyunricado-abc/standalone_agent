# 智能体工作流意图沉淀日志

### [2026-04-13] - 从 IDE 副驾驶向独立 Web 工作站的架构重构
- **驱动模型**: Gemini 3.1 Pro (High)
- **涉及文件**: `frontend/src/App.vue`, `backend/main.py`, `backend/scripts/universal_doc_gen.py`
- **变更逻辑摘要**: 
  - **初始实现思路/技术决策**: 将原有强依赖 IDE 侧边栏和 MCP 的软著生成工具，重构为前后端分离的独立平台。
  - **前端 (Vue 3 + Vite)**: 实现了左中右三栏式布局，左侧实现文件拖拽上传，中侧渲染生成的 Markdown（作为预览画布），右边显示 Agent 推演和执行日志，为用户提供友好的操作互动体验。
  - **后端 (FastAPI)**: 利用 FastAPI 提供 RESTful API (`/api/upload`, `/api/generate`)，完成从 ZIP 压缩包接收到提取源码、通过 Gemini 调用结构化 System Prompt（硬编码了文风与视角的“铁律”）的能力。
  - **引擎改造 (universal_doc_gen.py)**: 把原先 Python 代码迁移到 `backend/scripts` 下，适配后端参数调用，并且支持解析符合 DOT 格式规范的流程图节点，输出高标准的 Docx 文档格式。
  - **追加：修复并增强后台 API 健壮性 (2026-04-21)**: 在调试 `POST /api/generate` 频繁抛出 500 Internal Server Error 问题时，发现原始代码在调用 `model.generate_content(prompt)` 时缺乏 `try...except` 拦截，导致当 Gemini API 因代理或超载（如 `ResourceExhausted` 限流）抛出异常时必定发生宕机。对此作了异常全捕获并规范化为包含 detail 的 `HTTPException`；同时修正了本地渲染脚步执行方法，使用 `sys.executable` 唤起虚拟环境解释器，并将 `python-docx` 丢失产生的系统底层 Traceback 进行编码转义通过 JSON detail 原样抛往前端，使得用户能在右侧调试面板实时洞察故障原因。
  - **追加：软著文档生成引擎架构重构 (2026-04-21)**: 彻底抛弃了 `universal_doc_gen.py` 中脆弱的正则匹配渲染方式，引入了 `mistletoe` 这一 Markdown AST 解析器。通过语法树遍历精确解析大模型输出的段落。同时实现了样式解耦与“模板继承”策略，将代码内硬编码的边距、字体等样式转为直接读取 `template.docx` 以继承其排版标准。对多级标题（>3级）执行了压平降级逻辑保护了生成文档的结构合规性，并成功将原有的 Graphviz 图表自动渲染节点回接至新的引擎逻辑中。
  - **追加：前端界面适配性与交互体验优化 (2026-04-22)**: 针对独立工作站的“三栏式”主交互界面进行了深度适配与排版升级。引入了基于 `nextTick` 和 `ref` 的日志自动滚动机制，强化了右侧 Agent 思考流的动态体验；增加了针对小屏幕（<1200px 及 <992px）的 CSS 响应式媒体查询，解决内容区挤压问题；并且为 `md-preview-container` 追加了更为精细的表格、引用块等元素的 Markdown 排版样式。同时更新了文案提示，强化了对 Gemini 3.1 Pro 旗舰模型的感知。
