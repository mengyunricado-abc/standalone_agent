"""
/**
 * @vibe-intent 独立平台的后端入口：封装软著生成链路为API，处理上传及LLM调度
 * @vibe-model Gemini 3.1 Pro
 * @vibe-ref intents.md#2026-04-13
 */
"""
import os
import re
import uuid
import zipfile
import subprocess
import shutil
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="Soft Copyright Gen API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

TEMP_DIR = os.path.join(os.path.dirname(__file__), "temp")
os.makedirs(TEMP_DIR, exist_ok=True)

# 请在 .env 文件中设置 GEMINI_API_KEY
genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))
model = genai.GenerativeModel('gemini-2.5-flash')

SYSTEM_PROMPT = """
# [GLOBAL SKILL] Soft Copyright Automation (软著生成专家)

你是一个“企业级高级技术文档工程师”，严格按顺序执行以下工作流：

1. **绝对遵守文风与视角铁律**：
   - **屏蔽代码词汇**：严禁出现“路由、Hook、DOM、接口、防抖、异步、后端、组件库”等技术词汇。
   - **按用户行为**：描述以“用户点击...”、“界面展示...”、“系统校验...”为主体。
   - **平实克制**：严禁夸张修辞，使用客观中立的操作说明书语言。

2. **绝对遵守结构铁律（严禁增减标题）**：
   - `# 1. 编写目的` 
   - `# 2. 功能设计`
     - `## 2.1 软件介绍`
     - `## 2.2 界面设计`
   - `# 3. 系统操作说明`
     - `## 3.1 运行环境配置` (操作系统/浏览器等)
     - `## 3.2 [核心业务模块1]`
       - `### 3.2.1 [子操作1]` (包含前提条件、详细按步操作、预期反馈)
   - `# 4. 异常处理`

3. **图表占位硬指标（必须 ≥ 5张）**：
   - **独立成行，且上下空行**。
   - `[图1：系统主流程图]` (放在2.1末尾)
   - `[图2：主界面全局布局截图]` (放在2.2末尾)
   - 其余至少3张截图分布在3.2及第4章。

4. **流程图语法铁律**：
   - 必须在 Markdown 末尾生成标准 Graphviz DOT 代码。
   - 严禁使用 Mermaid。结构必须如下：
   [FLOW-CONFIG-START]
   digraph G {
       node [shape=box, fontname="SimHei"];
       Start [label="打开系统", shape=oval];
       Node1 [label="执行操作"];
       Start -> Node1;
   }
   [FLOW-CONFIG-END]
"""

class GenerateRequest(BaseModel):
    task_id: str
    software_name: str

def extract_code(directory: str) -> str:
    """提取目录下的核心源码文本以便于大模型分析。可以过滤掉无用的内容"""
    core_content = []
    for root, dirs, files in os.walk(directory):
        if 'node_modules' in dirs:
            dirs.remove('node_modules')
        if '.git' in dirs:
            dirs.remove('.git')
        for file in files:
            if file.endswith(('.vue', '.js', '.ts', '.py')):
                filepath = os.path.join(root, file)
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        core_content.append(f"==== {file} ====\n{f.read()}")
                except:
                    pass
    return "\n\n".join(core_content)[:100000] # 尽量不超太多token

@app.post("/api/upload")
async def upload_code(file: UploadFile = File(...)):
    if not file.filename.endswith('.zip') and not file.filename.endswith('.vue'):
        raise HTTPException(status_code=400, detail="Only .zip or .vue files are allowed")

    task_id = str(uuid.uuid4())
    task_dir = os.path.join(TEMP_DIR, task_id)
    os.makedirs(task_dir, exist_ok=True)
    
    file_path = os.path.join(task_dir, file.filename)
    with open(file_path, "wb") as buffer:
        buffer.write(await file.read())
        
    if file.filename.endswith('.zip'):
        with zipfile.ZipFile(file_path, 'r') as zip_ref:
            zip_ref.extractall(task_dir)
            
    return {"task_id": task_id, "status": "Uploaded"}

@app.post("/api/generate")
async def generate_docs(req: GenerateRequest):
    task_dir = os.path.join(TEMP_DIR, req.task_id)
    if not os.path.exists(task_dir):
        raise HTTPException(status_code=404, detail="Task ID not found")
        
    code_content = extract_code(task_dir)
    if not code_content:
         raise HTTPException(status_code=400, detail="No readable code found")
         
    prompt = f"{SYSTEM_PROMPT}\n\n请针对以下代码源码生成软著文件要求：\n{code_content}"
    
    response = model.generate_content(prompt)
    md_content = response.text
    
    md_path = os.path.join(task_dir, "temp_manual.md")
    with open(md_path, 'w', encoding='utf-8') as f:
        f.write(md_content)
        
    # 调用渲染引擎
    docx_path = os.path.join(task_dir, f"{req.software_name}_软著说明书.docx")
    render_script = os.path.join(os.path.dirname(__file__), "scripts", "universal_doc_gen.py")
    
    try:
        subprocess.run(
            ["python", render_script, md_path, docx_path, req.software_name],
            check=True
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Word generation failed: {str(e)}")
        
    return {
         "status": "success",
         "markdown_preview": md_content,
         "download_url": f"/api/download/{req.task_id}/{req.software_name}_软著说明书.docx"
    }

@app.get("/api/download/{task_id}/{filename}")
async def download_doc(task_id: str, filename: str):
    file_path = os.path.join(TEMP_DIR, task_id, filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(file_path, filename=filename)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
