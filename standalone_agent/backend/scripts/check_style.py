from docx import Document

def inspect_styles(docx_path):
    try:
        doc = Document(docx_path)
        print(f"\n✅ 成功读取模板: {docx_path}")
        print("-" * 30)
        print("以下是您的模板中真实可用的【段落样式名称】：")
        
        # 提取所有段落类型的样式
        styles = [s.name for s in doc.styles if s.type == 1]
        
        # 排序并打印，方便查看
        for name in sorted(styles):
            print(f"  - {name}")
            
        print("-" * 30)
        print("请将上面的列表复制发给我！")
        
    except Exception as e:
        print(f"❌ 读取失败，请检查路径是否正确: {e}")

if __name__ == "__main__":
    # 这里的路径请确保指向您正在使用的那个 template.docx
    # 如果 check_style.py 和 template.docx 在同一个目录下，直接填文件名即可
    TARGET_TEMPLATE = "template.docx" 
    
    inspect_styles(TARGET_TEMPLATE)