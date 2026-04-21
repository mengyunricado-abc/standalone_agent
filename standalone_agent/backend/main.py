"""
/**
 * @vibe-intent 独立平台的后端入口：封装软著生成链路为API，处理上传及LLM调度 (安全修复版)
 * @vibe-model Gemini 3.1 Pro
 */
"""
import os
import re
import uuid
import zipfile
import asyncio
import shutil
import sys
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, BackgroundTasks

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
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

genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))
model = genai.GenerativeModel('gemini-2.5-flash')

# 保持你原有的系统提示词不变
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

def is_safe_path(basedir, path, follow_symlinks=True):
    """【修复 1】安全路径校验，防止 Zip Slip 漏洞跨目录写入系统文件"""
    if follow_symlinks:
        matchpath = os.path.realpath(path)
    else:
        matchpath = os.path.abspath(path)
    return basedir == os.path.commonpath((basedir, matchpath))

def extract_code(directory: str) -> str:
    """提取目录下的核心源码文本以便于大模型分析。增加了防爆和多编码支持"""
    core_content = []
    for root, dirs, files in os.walk(directory):
        # 过滤无关目录，节约大模型 Token
        dirs[:] = [d for d in dirs if d not in ['.git', 'node_modules', 'dist', '__pycache__', '.idea', '.vscode']]
        
        for file in files:
            # 过滤掉压缩后的前端资源文件
            if file.endswith(('.min.js', '.min.css')):
                continue
                
            if file.endswith(('.vue', '.js', '.ts', '.py', '.java', '.go')):
                filepath = os.path.join(root, file)
                # 【修复 2】加入多编码回退策略和日志，避免 `except: pass` 吞掉报错导致代码遗失
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        content = f.read()
                        core_content.append(f"==== {file} ====\n{content}")
                except UnicodeDecodeError:
                    try:
                        with open(filepath, 'r', encoding='gbk') as f:
                            content = f.read()
                            core_content.append(f"==== {file} ====\n{content}")
                    except Exception as e:
                        print(f"警告：无法读取文件 {filepath}: {str(e)}")
                except Exception as e:
                    print(f"读取异常 {filepath}: {str(e)}")
                    
    # 如果代码过长，进行安全截断（可按需调大限制，目前预估 10万字符）
    full_content = "\n\n".join(core_content)
    if len(full_content) > 100000:
        print("警告：代码量超出限制，已进行截断处理")
        return full_content[:100000]
    return full_content

async def cleanup_task_dir(task_dir: str, delay: int = 3600):
    """【修复 3】后台延时清理任务：文件保留 1 小时后自动销毁，防止磁盘爆炸"""
    await asyncio.sleep(delay)
    if os.path.exists(task_dir):
        shutil.rmtree(task_dir)
        print(f"后台清理：已销毁临时文件夹 {task_dir}")

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
            # 【应用修复 1】解压前执行安全校验
            for member in zip_ref.namelist():
                member_path = os.path.join(task_dir, member)
                if not is_safe_path(task_dir, member_path):
                    shutil.rmtree(task_dir) # 发现恶意包，立刻销毁
                    raise HTTPException(status_code=400, detail="检测到不安全的ZIP路径 (Zip Slip漏洞)")
            zip_ref.extractall(task_dir)
            
    return {"task_id": task_id, "status": "Uploaded"}

# /**
#  * @vibe-intent 响应前端生成请求，调度LLM并渲染Word文档，增加异常穿透
#  * @vibe-model Gemini 3.1 Pro (High)
#  * @vibe-ref intents.md#2026-04-21
#  */
@app.post("/api/generate")
async def generate_docs(req: GenerateRequest, background_tasks: BackgroundTasks):
    task_dir = os.path.join(TEMP_DIR, req.task_id)
    if not os.path.exists(task_dir):
        raise HTTPException(status_code=404, detail="Task ID not found")
        
    # 【应用修复 3】注册后台任务，接口返回后自动开始倒计时清理
    background_tasks.add_task(cleanup_task_dir, task_dir, 3600)
        
    code_content = extract_code(task_dir)
    if not code_content:
         raise HTTPException(status_code=400, detail="No readable code found")
         
    prompt = f"{SYSTEM_PROMPT}\n\n请针对以下代码源码生成软著文件要求：\n{code_content}"
    
    # 注意：如果此处并发量大，Gemini调用也建议改用 async 版本，这里先保持同步或走异步包装
    try:
        response = model.generate_content(prompt)
        md_content = response.text
    except Exception as e:
        print(f"DEBUG Error during generation: {e}")
        raise HTTPException(status_code=500, detail=f"LLM Generation failed: {repr(e)}")
    
    md_path = os.path.join(task_dir, "temp_manual.md")
    with open(md_path, 'w', encoding='utf-8') as f:
        f.write(md_content)
        
    docx_path = os.path.join(task_dir, f"{req.software_name}_软著说明书.docx")
    render_script = os.path.join(os.path.dirname(__file__), "scripts", "universal_doc_gen.py")
    template_docx_path = os.path.join(os.path.dirname(__file__), "scripts", "template.docx")
    
    # 【修复 4】在 Windows 上为了彻底避免 EventLoop 兼容性导致的 NotImplementedError，
    # 改用线程池包裹同步的 subprocess.run 来实现非阻塞运行
    try:
        import sys
        import subprocess
        
        def run_subprocess():
            return subprocess.run(
                [sys.executable, render_script, md_path, docx_path, req.software_name, template_docx_path],
                capture_output=True
            )
            
        process = await asyncio.to_thread(run_subprocess)
        stdout, stderr = process.stdout, process.stderr
        
        if process.returncode != 0:
             error_msg = stderr.decode('gbk', errors='ignore') or stderr.decode('utf-8', errors='ignore') or "Unknown error"
             raise Exception(f"Return code {process.returncode}, stderr: {error_msg}, stdout: {stdout.decode('gbk', errors='ignore')}")
             
    except Exception as e:
        import traceback
        tb_str = traceback.format_exc()
        raise HTTPException(status_code=500, detail=f"Word generation failed: e={repr(e)}, traceback={tb_str}")
        
    return {
         "status": "success",
         "markdown_preview": md_content,
         "download_url": f"/api/download/{req.task_id}/{req.software_name}_软著说明书.docx"
    }

@app.get("/api/download/{task_id}/{filename}")
async def download_doc(task_id: str, filename: str):
    file_path = os.path.join(TEMP_DIR, task_id, filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found or expired")
    return FileResponse(file_path, filename=filename)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)