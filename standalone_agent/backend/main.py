"""
/**
 * @vibe-intent 独立平台的后端入口：封装软著生成链路为API，处理上传及LLM调度 (安全修复 & 编码增强版)
 * @vibe-model Gemini 3.1 Pro (High)
 * @vibe-ref intents.md#2026-04-24
 */
"""
import os
import re
import uuid
import zipfile
import asyncio
import shutil
import sys
from urllib.parse import quote
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

# 全新的双任务 JSON 驱动 System Prompt
SYSTEM_PROMPT = """
# Role: 资深软件架构分析师与软著合规专家

## Objective
基于用户提供的源代码，进行“功能逻辑提炼”，并一次性生成包含《登记申请表》和《设计说明书》所需全部字段的 JSON 格式数据。

## 🚫 绝对红线（内容与文风约束）
1. **文风铁律（极度重要）**：
   - 必须站在“最终用户”的角度编写，严禁暴露底层代码实现。
   - **屏蔽代码词汇**：严禁出现“路由、Hook、DOM、接口、防抖(debounce)、生命周期、后端、API、Vue组件”等技术词汇。不要提具体的文件名或函数名。
   - **按用户行为描述**：描述以“用户点击...”、“界面展示...”、“系统校验...”为主体。
2. 必须输出纯 JSON，不含 Markdown 标记（如 ```json）。
3. 禁止虚构不存在的宏大业务模块，所有功能必须有源码支撑。

## 📥 JSON Schema 要求 (必须严格遵循)
{
  "application_form": {
    "software_name": "提取软件全称",
    "dev_purpose": "简述开发目的（限50字内）",
    "main_functions": "整体功能详述，限500-1300字（客观描述系统流转、状态控制与数据交互，严禁代码词汇）",
    "tech_features": "技术特点，限100字内"
  },
  "design_doc": {
    "full_name": "同上软件全称",
    "intro": "系统简介，限300字内",
    "modules": [
      {
        "name": "模块A名称（如：文件上传与校验模块）",
        "desc": "详细描述该模块的业务逻辑和预期交互，限100-300字（严禁代码词汇）"
      },
      {
        "name": "模块B名称",
        "desc": "详细描述..."
      }
    ]
  }
}
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
    try:
        await asyncio.sleep(delay)
        if os.path.exists(task_dir):
            shutil.rmtree(task_dir, ignore_errors=True) # ignore_errors 解决 Windows 下文件占用导致的崩溃
            print(f"后台清理：已销毁临时文件夹 {task_dir}")
    except asyncio.CancelledError:
        pass
    except Exception as e:
        print(f"清理临时目录失败: {e}")

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
#  * @vibe-intent 响应前端生成请求，调度LLM并渲染Word文档，修复URL编码与响应头
#  * @vibe-model Gemini 3.1 Pro (High)
#  * @vibe-ref intents.md#2026-04-24
#  */
@app.post("/api/generate")
async def generate_docs(req: GenerateRequest, background_tasks: BackgroundTasks):
    task_dir = os.path.join(TEMP_DIR, req.task_id)
    if not os.path.exists(task_dir):
        raise HTTPException(status_code=404, detail="Task ID not found")
        
    background_tasks.add_task(cleanup_task_dir, task_dir, 3600)
    code_content = extract_code(task_dir)
    if not code_content:
         raise HTTPException(status_code=400, detail="未找到可解析的代码文件")
         
    prompt = f"{SYSTEM_PROMPT}\n\n请针对以下代码源码生成软著要求：\n{code_content}"
    
    try:
        response = model.generate_content(prompt)
        raw_text = response.text
        # 清洗 JSON
        cleaned_json = re.sub(r'^```(json)?\s*', '', raw_text, flags=re.IGNORECASE)
        cleaned_json = re.sub(r'```\s*$', '', cleaned_json).strip()
    except Exception as e:
        err_msg = str(e)
        if "429" in err_msg or "Quota exceeded" in err_msg:
            raise HTTPException(status_code=429, detail="API频率达到免费层级上限，请冷静 30 秒后再试")
        if "503" in err_msg:
            raise HTTPException(status_code=503, detail="Google服务暂时繁忙（503），建议稍后重试")
        raise HTTPException(status_code=500, detail=f"AI 生成失败: {err_msg}")
    
    # 1. 保存 JSON (前端也可据此预览排错)
    json_path = os.path.join(task_dir, "data.json")
    with open(json_path, 'w', encoding='utf-8') as f:
        f.write(cleaned_json)
        
    # 2. 定义路径
    render_script = os.path.join(os.path.dirname(__file__), "scripts", "universal_doc_gen.py")
    template_app_path = os.path.join(os.path.dirname(__file__), "scripts", "template_app.docx")
    template_design_path = os.path.join(os.path.dirname(__file__), "scripts", "template_design.docx")
    
    # 清洗软件名称，防止特殊字符导致路径或 URL 异常
    safe_name = re.sub(r'[\\/:*?"<>|]', '', req.software_name).strip().replace(' ', '_')
    if not safe_name: safe_name = "software"

    out_app_path = os.path.join(task_dir, f"{safe_name}_申请表.docx")
    out_design_path = os.path.join(task_dir, f"{safe_name}_说明书.docx")
    zip_filename = f"{safe_name}_软著材料包.zip"
    zip_output_path = os.path.join(task_dir, zip_filename)
    
    try:
        import sys
        import subprocess
        
        # 调用基于 docxtpl 的新渲染引擎
        def run_subprocess():
            return subprocess.run(
                [sys.executable, render_script, json_path, template_app_path, template_design_path, out_app_path, out_design_path],
                capture_output=True
            )
            
        process = await asyncio.to_thread(run_subprocess)
        
        if process.returncode != 0:
             error_msg = process.stderr.decode('gbk', errors='ignore') or "渲染引擎未知错误"
             raise Exception(f"渲染失败: {error_msg}")
             
        # 【核心修复】：显式指定 ZIP 压缩标准，并确保 ZIP 文件流在响应前完全闭合
        with zipfile.ZipFile(zip_output_path, 'w', compression=zipfile.ZIP_DEFLATED) as z:
            if os.path.exists(out_app_path):
                # arcname 设为纯文件名，避免包含绝对路径
                z.write(out_app_path, os.path.basename(out_app_path))
            if os.path.exists(out_design_path):
                z.write(out_design_path, os.path.basename(out_design_path))
                
        # 防呆设计：检查 zip 文件是否真正生成且有效
        if not os.path.exists(zip_output_path) or os.path.getsize(zip_output_path) < 100:
            raise Exception("ZIP 文件生成为空或损坏，请检查 Word 渲染日志")
             
    except Exception as e:
        import traceback
        error_detail = f"打包或生成失败: {str(e)}\n{traceback.format_exc()}"
        print(error_detail)
        raise HTTPException(status_code=500, detail=error_detail)
        
    return {
         "status": "success",
         # 将清洗后的 JSON 返回前端预览，方便你核对文风是否恢复正常
         "markdown_preview": f"```json\n{cleaned_json}\n```", 
         "download_url": f"/api/download/{req.task_id}/{quote(zip_filename)}"
    }

@app.get("/api/download/{task_id}/{filename}")
async def download_doc(task_id: str, filename: str):
    file_path = os.path.join(TEMP_DIR, task_id, filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found or expired")
    
    # 【核心修复】：双重响应头策略，filename 用于常规下载，filename* 用于现代浏览器的 UTF-8 支持
    # 注意：filename 字段通常需要去除特殊字符或使用 quote
    safe_filename = quote(filename)
    content_disposition = f"attachment; filename=\"{safe_filename}\"; filename*=utf-8''{safe_filename}"
    
    return FileResponse(
        file_path, 
        media_type='application/zip',
        headers={
            "Content-Disposition": content_disposition,
            "Access-Control-Expose-Headers": "Content-Disposition" # 允许前端获取文件名
        }
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)