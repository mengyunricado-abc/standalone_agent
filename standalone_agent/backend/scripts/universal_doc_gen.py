"""
/**
 * @vibe-intent 底层文档渲染引擎：将标准MD结构及Graphviz配置转换为软著验收标准的Word文档
 * @vibe-model Gemini 3.1 Pro
 * @vibe-ref intents.md#2026-04-13
 */
"""
import os
import re
import sys
from docx import Document
from docx.shared import Pt, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
from PIL import Image, ImageDraw, ImageFont

try:
    import graphviz
    from graphviz import Digraph
    HAS_GRAPHVIZ = True
except ImportError:
    HAS_GRAPHVIZ = False

# --- 辅助函数：强制设置中西文字体 (消灭 MS Gothic) ---
def set_font_style(run, font_name='SimSun', western_font='Times New Roman', size_pt=12, bold=False):
    run.font.name = western_font
    run.font.size = Pt(size_pt)
    run.font.bold = bold
    run._element.rPr.rFonts.set(qn('w:eastAsia'), font_name)

# --- 核心逻辑：配置全局 Word 样式 ---
def configure_doc_styles(doc):
    section = doc.sections[0]
    section.page_width = Cm(21); section.page_height = Cm(29.7)
    section.top_margin = Cm(2.54); section.bottom_margin = Cm(2.54)
    section.left_margin = Cm(2.54); section.right_margin = Cm(2.54)

    style_normal = doc.styles['Normal']
    style_normal.font.name = 'Times New Roman'
    style_normal.font.size = Pt(12)
    style_normal.element.rPr.rFonts.set(qn('w:eastAsia'), 'SimSun')
    style_normal.paragraph_format.line_spacing = 1.5

# --- 核心逻辑：封面与目录 ---
def add_cover_page(doc, software_name):
    for _ in range(8): doc.add_paragraph()
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run(f"{software_name}\n操作说明书")
    set_font_style(run, size_pt=24, bold=True) # 小一
    doc.add_page_break()

def add_toc_page(doc):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run("目  录")
    set_font_style(run, size_pt=16, bold=True) # 三号
    doc.add_paragraph()

    p_toc = doc.add_paragraph()
    run = p_toc.add_run()
    fldChar1 = OxmlElement('w:fldChar'); fldChar1.set(qn('w:fldCharType'), 'begin')
    instrText = OxmlElement('w:instrText'); instrText.set(qn('xml:space'), 'preserve'); instrText.text = 'TOC \\o "1-3" \\h \\z \\u'
    fldChar2 = OxmlElement('w:fldChar'); fldChar2.set(qn('w:fldCharType'), 'separate')
    fldChar3 = OxmlElement('w:fldChar'); fldChar3.set(qn('w:fldCharType'), 'end')
    for el in [fldChar1, instrText, fldChar2, fldChar3]: run._element.append(el)
    doc.add_page_break()

def parse_flow_config(md_text):
    # Try finding modern DOT config block
    pattern_dot = re.compile(r'\[FLOW-CONFIG-START\](.*?)\[FLOW-CONFIG-END\]', re.DOTALL)
    match = pattern_dot.search(md_text)
    if not match: 
        return None, None
        
    content = match.group(1).strip()
    # Check if it is the old pseudo-syntax or standard DOT syntax
    if 'digraph' in content:
        # Standard graphviz syntax, just return the content
        return 'dot', content
    
    # Old syntax
    nodes, edges = {}, []
    lines = content.split('\n')
    current_section = None
    
    for line in lines:
        line = line.strip()
        if not line: continue
        if '[Nodes]' in line: current_section = 'nodes'; continue
        elif '[Edges]' in line: current_section = 'edges'; continue
        
        if current_section == 'nodes':
            parts = line.split(':', 1)
            if len(parts) >= 2:
                n_id = parts[0].strip()
                attrs = parts[1].split('|')
                label = attrs[0].strip()
                shape = 'box'
                if len(attrs) > 1 and 'shape=' in attrs[1]: shape = attrs[1].split('=')[1].strip()
                nodes[n_id] = {'label': label, 'shape': shape}
        elif current_section == 'edges' and '->' in line:
            s, d = line.split('->')
            edges.append((s.strip(), d.strip()))
    return nodes, edges

def draw_dynamic_flowchart(nodes, edges, filename='temp_flowchart.png', dot_code=None):
    if not HAS_GRAPHVIZ: return False
    try:
        from graphviz import Source
        if dot_code:
            src = Source(dot_code)
            src.render(outfile=filename, format='png', cleanup=True)
            return True
            
        dot = Digraph(comment='Auto Flow', format='png')
        dot.attr(rankdir='TB', size='6,8')
        dot.attr('node', fontname='SimHei', fontsize='12', style='filled', fillcolor='aliceblue')
        dot.attr('edge', fontname='SimHei')
        for n_id, props in nodes.items():
            fill = 'lightgrey' if props['shape'] == 'oval' else 'aliceblue'
            if props['shape'] == 'diamond': fill = 'lightyellow'
            dot.node(n_id, props['label'], shape=props['shape'], fillcolor=fill)
        for src, dst in edges: dot.edge(src, dst)
        dot.render(filename.replace('.png', ''), cleanup=True)
        return True
    except Exception as e: 
        print(f"Graphviz draw failed: {e}")
        return False

def create_dummy_image(path):
    img = Image.new('RGB', (600, 350), (240, 240, 240))
    d = ImageDraw.Draw(img); d.rectangle([0,0,599,349], outline="gray")
    img.save(path)

# --- 主程序 ---
def generate_docx(md_path, docx_path, software_name):
    with open(md_path, 'r', encoding='utf-8') as f: content = f.read()

    # 画图
    nodes, edges = parse_flow_config(content)
    flow_ready = False
    
    if nodes == 'dot':
        flow_ready = draw_dynamic_flowchart(None, None, dot_code=edges)
    elif nodes and edges:
        flow_ready = draw_dynamic_flowchart(nodes, edges)
    
    # 抹除流程图代码块
    content = re.sub(r'\[FLOW-CONFIG-START\][\s\S]*?\[FLOW-CONFIG-END\]', '', content)

    doc = Document()
    configure_doc_styles(doc)
    add_cover_page(doc, software_name)
    add_toc_page(doc)

    dummy_img_path = "temp_placeholder.png"
    flow_img_path = "temp_flowchart.png"
    if not os.path.exists(dummy_img_path): create_dummy_image(dummy_img_path)

    # 逐行解析 (暴力锁死字体)
    for line in content.split('\n'):
        line = line.strip()
        if not line: continue

        if line.startswith('# '):
            p = doc.add_paragraph(line.replace('# ', ''), style='Heading 1')
            for run in p.runs: set_font_style(run, size_pt=14, bold=True)
        elif line.startswith('## '):
            p = doc.add_paragraph(line.replace('## ', ''), style='Heading 2')
            for run in p.runs: set_font_style(run, size_pt=12, bold=True)
        elif line.startswith('### '):
            p = doc.add_paragraph(line.replace('### ', ''), style='Heading 3')
            for run in p.runs: set_font_style(run, size_pt=12, bold=False)
        elif re.match(r'^\[图\d+[：:].*\]$', line):
            p_img = doc.add_paragraph()
            p_img.alignment = WD_ALIGN_PARAGRAPH.CENTER
            target_img = flow_img_path if ("图1" in line and flow_ready) else dummy_img_path
            p_img.add_run().add_picture(target_img, width=Cm(14))
            
            p_cap = doc.add_paragraph()
            p_cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
            set_font_style(p_cap.add_run(line.strip('[]')), size_pt=10.5)
        else:
            p = doc.add_paragraph(line, style='Normal')
            p.paragraph_format.first_line_indent = Cm(0.85)
            for run in p.runs: set_font_style(run, size_pt=12)

    doc.save(docx_path)
    for f in [dummy_img_path, flow_img_path]: 
        if os.path.exists(f): os.remove(f)
    print(f"✅ Word 文档已生成: {docx_path}")

if __name__ == "__main__":
    if len(sys.argv) < 4: sys.exit(1)
    generate_docx(sys.argv[1], sys.argv[2], sys.argv[3])
