"""
基于 docxtpl 的数据驱动渲染引擎 (打平增强版)
"""
import sys
import json
import os
from docxtpl import DocxTemplate

def flatten_context(data):
    """
    将嵌套的 JSON 结构打平，方便 Word 模板直接通过 {{ key }} 访问。
    例如 {"application_form": {"name": "X"}} -> {"name": "X", "application_form": {...}}
    """
    flat = {}
    if not isinstance(data, dict):
        return flat
        
    for k, v in data.items():
        if isinstance(v, dict):
            # 将子字典的内容合并到顶层
            flat.update(v)
            # 同时保留原有的嵌套结构，兼容性更强
            flat[k] = v
        else:
            flat[k] = v
    return flat

def render_docs(json_data_str, template_app_path, template_design_path, out_app_path, out_design_path):
    try:
        # 解析 LLM 传来的 JSON 字符串
        raw_context = json.loads(json_data_str)
        
        # 【核心修复】打平上下文，确保 {{ software_name }} 等字段能被直接识别
        context = flatten_context(raw_context)
        
        # 调试日志：输出当前可用的顶层 Key
        print(f"DEBUG: 渲染上下文打平完成，可用字段: {list(context.keys())}")

        # 1. 渲染《申请表》
        if os.path.exists(template_app_path):
            app_doc = DocxTemplate(template_app_path)
            app_doc.render(context)
            app_doc.save(out_app_path)
            print(f"申请表生成成功: {out_app_path}")
        else:
            print(f"错误: 找不到申请表模板 {template_app_path}", file=sys.stderr)
            sys.exit(1)
        
        # 2. 渲染《说明书》
        if os.path.exists(template_design_path):
            design_doc = DocxTemplate(template_design_path)
            design_doc.render(context)
            design_doc.save(out_design_path)
            print(f"说明书生成成功: {out_design_path}")
        else:
            print(f"错误: 找不到说明书模板 {template_design_path}", file=sys.stderr)
            sys.exit(1)
            
    except json.JSONDecodeError as e:
        print(f"JSON解析失败，LLM返回的格式不合法: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        import traceback
        print(f"渲染过程发生异常: {str(e)}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    if len(sys.argv) < 6:
        print("Usage: python universal_doc_gen.py <json_path> <tpl_app> <tpl_design> <out_app> <out_design>")
        sys.exit(1)
        
    json_path = sys.argv[1]
    tpl_app = sys.argv[2]
    tpl_design = sys.argv[3]
    out_app = sys.argv[4]
    out_design = sys.argv[5]
    
    # 读取保存在临时文件中的 JSON 数据
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            json_data = f.read()
        render_docs(json_data, tpl_app, tpl_design, out_app, out_design)
    except Exception as e:
        print(f"无法读取 JSON 文件: {e}", file=sys.stderr)
        sys.exit(1)