<!--
/**
 * @vibe-intent 独立平台的前端主交互界面：实现三栏式布局及与后端的软著生成流通信
 * @vibe-model Gemini 3.1 Pro
 * @vibe-ref intents.md#2026-04-13
 */
-->
<template>
  <div class="layout-container">
    <!-- 左侧：资源导航区 -->
    <div class="sidebar-left">
      <div class="header">
        <h2>软著智能体平台</h2>
        <p class="subtitle">代码转文档神器</p>
      </div>
      
      <div class="upload-section">
        <label>选择代码包或文件 (.zip, .vue)</label>
        <el-upload
          class="upload-demo"
          drag
          action="/api/upload"
          :on-success="handleUploadSuccess"
          :on-error="handleUploadError"
          :before-upload="beforeUpload"
          name="file"
        >
          <i class="el-icon-upload"></i>
          <div class="el-upload__text">将源码包拖到此处，或 <em>点击上传</em></div>
          <template #tip>
            <div class="el-upload__tip">只能上传 zip 或 vue 文件，系统会自动剔除无关依赖</div>
          </template>
        </el-upload>
      </div>

      <div class="form-section">
        <el-input 
          v-model="softwareName" 
          placeholder="请输入待申请的软件全称" 
          style="margin-bottom: 15px;"
        />
        <el-button 
          type="primary" 
          @click="startGeneration" 
          :loading="processing"
          style="width: 100%;"
          :disabled="!taskId || !softwareName"
        >
          {{ processing ? 'AI 正在深度解析源码...' : '启动智能拆解与生成' }}
        </el-button>
      </div>
      
      <div class="status-summary" v-if="downloadUrl">
        <el-alert
          title="生成成功！"
          type="success"
          description="标准软著说明书已就绪。"
          show-icon
        >
        </el-alert>
        <el-button type="success" @click="downloadDocx" style="width: 100%; margin-top: 15px;">
          ⬇️ 下载最终 Word (.docx)
        </el-button>
      </div>
    </div>

    <!-- 中间：核心画布/文档预览区 -->
    <div class="main-content">
      <div class="editor-toolbar">
        <h3>Markdown 实时预览</h3>
        <el-tag type="info" v-if="!mdContent">等待生成...</el-tag>
        <el-tag type="success" v-else>渲染完成</el-tag>
      </div>
      <div class="md-preview-container" v-html="renderedHTML" v-if="mdContent"></div>
      <div class="empty-state" v-else>
        上传源码后，AI 会在这里呈现像素级的结构化分析...
      </div>
    </div>

    <!-- 右侧：侧边栏交互区 (日志) -->
    <div class="sidebar-right">
      <div class="header">
        <h3>Agent 思考与推演日志</h3>
      </div>
      <div class="log-container" ref="logContainerRef">
        <div class="log-item" v-for="(log, idx) in logs" :key="idx" :class="log.type">
          <span class="time">[{{ log.time }}]</span>
          <span class="msg">{{ log.message }}</span>
        </div>
        <div class="log-item info typing" v-if="processing">
          <span class="time">...</span>
          <span class="msg">Gemini 3.1 Pro 正在深度推演中，请勿刷新页面...</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, nextTick } from 'vue'
import { ElMessage } from 'element-plus'
import axios from 'axios'
import MarkdownIt from 'markdown-it'

const md = new MarkdownIt({ breaks: true, linkify: true })

const taskId = ref(null)
const softwareName = ref('示例系统')
const mdContent = ref('')
const processing = ref(false)
const downloadUrl = ref('')
const logs = ref([])
const logContainerRef = ref(null)

const renderedHTML = computed(() => {
  return mdContent.value ? md.render(mdContent.value) : ''
})

const addLog = (msg, type = 'info') => {
  const d = new Date()
  const pad = (n) => n.toString().padStart(2, '0')
  logs.value.push({
    time: `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`,
    message: msg,
    type
  })
  nextTick(() => {
    if (logContainerRef.value) {
      logContainerRef.value.scrollTop = logContainerRef.value.scrollHeight
    }
  })
}

const beforeUpload = (file) => {
  addLog(`准备上传文件: ${file.name}`)
  return true
}

const handleUploadSuccess = (res) => {
  taskId.value = res.task_id
  addLog(`文件上传成功，临时任务空间创建: ${res.task_id.slice(0, 8)}...`, 'success')
  ElMessage.success('源码包上传成功！')
}

const handleUploadError = () => {
  addLog(`文件上传失败，请检查网络或格式。`, 'error')
  ElMessage.error('上传失败')
}

const startGeneration = async () => {
  if (!taskId.value) return
  if (!softwareName.value) {
    ElMessage.warning('请输入软件名称')
    return
  }
  
  processing.value = true
  mdContent.value = ''
  downloadUrl.value = ''
  addLog('===========================', 'info')
  addLog(`[System] 触发 /ruanzhu 协议：开始解压并清洗源码包...`, 'info')
  addLog(`[System] 握手成功，已激活 Gemini 3.1 Pro 旗舰模型...`, 'info')
  addLog(`[Agent] 正在深度审视代码结构，提取核心业务流与交互逻辑...`, 'warning')
  addLog(`[Agent] 正在生成结构化 Markdown 及辅助理解的 Graphviz 流程图代码...`, 'warning')
  
  try {
    const response = await axios.post('/api/generate', {
      task_id: taskId.value,
      software_name: softwareName.value
    })
    
    if (response.data.status === 'success') {
       addLog('大模型返回解析结果，触发本地 Python 渲染层...', 'warning')
       mdContent.value = response.data.markdown_preview
       downloadUrl.value = response.data.download_url
       addLog('Word 文档渲染成功！✅', 'success')
       ElMessage.success('生成完毕！')
    }
  } catch (err) {
    console.error(err)
    addLog(`生成过程引发异常: ${err.response?.data?.detail || err.message}`, 'error')
    ElMessage.error(`生成失败：${err.response?.data?.detail || err.message}`)
  } finally {
    processing.value = false
  }
}

const downloadDocx = () => {
  if (downloadUrl.value) {
    addLog(`触发文件下载：${softwareName.value}_软著说明书.docx`, 'success')
    window.open(downloadUrl.value, '_blank')
  }
}
</script>

<style>
body {
  margin: 0;
  font-family: 'Helvetica Neue', Helvetica, 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', '微软雅黑', Arial, sans-serif;
  box-sizing: border-box;
  background-color: #f0f2f5;
}

.layout-container {
  display: flex;
  height: 100vh;
  overflow: hidden;
}

.sidebar-left {
  width: 320px;
  background: white;
  padding: 20px;
  box-shadow: 2px 0 8px rgba(0,0,0,0.05);
  display: flex;
  flex-direction: column;
  z-index: 10;
}

.header {
  border-bottom: 2px solid #ebeef5;
  padding-bottom: 15px;
  margin-bottom: 20px;
}

.header h2 { margin: 0 0 5px; color: #303133; }
.subtitle { margin: 0; font-size: 13px; color: #909399; }

.upload-section {
  margin-bottom: 25px;
}
.upload-section label {
  display: block;
  font-weight: bold;
  font-size: 14px;
  margin-bottom: 10px;
  color: #606266;
}

.form-section {
  padding: 15px;
  background: #fafafa;
  border-radius: 8px;
  border: 1px solid #ebeef5;
}

.status-summary {
  margin-top: auto;
  border-top: 1px solid #ebeef5;
  padding-top: 20px;
}

/* 中间区域 */
.main-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  background: #fff;
  margin: 15px;
  border-radius: 10px;
  box-shadow: 0 4px 12px rgba(0,0,0,0.05);
  overflow: hidden;
}

.editor-toolbar {
  height: 50px;
  display: flex;
  align-items: center;
  padding: 0 20px;
  background: #fafafa;
  border-bottom: 1px solid #ebeef5;
  justify-content: space-between;
}
.editor-toolbar h3 { margin: 0; font-size: 16px; color: #303133; }

.md-preview-container {
  flex: 1;
  overflow-y: auto;
  padding: 30px;
}
.md-preview-container h1, .md-preview-container h2, .md-preview-container h3 {
  border-bottom: 1px solid #ebeef5;
  padding-bottom: 8px;
}
.md-preview-container pre {
  background: #f4f4f5;
  padding: 12px;
  border-radius: 6px;
  overflow-x: auto;
}
.md-preview-container table {
  width: 100%;
  border-collapse: collapse;
  margin: 15px 0;
}
.md-preview-container th, .md-preview-container td {
  border: 1px solid #ebeef5;
  padding: 10px;
  text-align: left;
}
.md-preview-container th {
  background-color: #fafafa;
  font-weight: bold;
}
.md-preview-container tr:nth-child(even) {
  background-color: #fcfcfc;
}
.md-preview-container blockquote {
  border-left: 4px solid #409eff;
  margin: 15px 0;
  padding: 10px 15px;
  background-color: #ecf5ff;
  color: #606266;
}
.md-preview-container p {
  line-height: 1.6;
  color: #303133;
}
.empty-state {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #c0c4cc;
  font-size: 18px;
  letter-spacing: 1px;
}

/* 右侧：日志区 */
.sidebar-right {
  width: 320px;
  background: #1e1e1e;
  color: #d4d4d4;
  display: flex;
  flex-direction: column;
  z-index: 10;
}
.sidebar-right .header {
  padding: 20px;
  background: #252526;
  border-bottom: 1px solid #3c3c3c;
  margin-bottom: 0;
}
.sidebar-right h3 { margin: 0; font-size: 15px; color: #007acc; }

.log-container {
  flex: 1;
  padding: 15px;
  overflow-y: auto;
  font-family: 'Consolas', 'Courier New', monospace;
  font-size: 13px;
  line-height: 1.6;
}
.log-item {
  margin-bottom: 8px;
  word-wrap: break-word;
}
.log-item .time { color: #858585; margin-right: 8px; }
.log-item.info .msg { color: #d4d4d4; }
.log-item.success .msg { color: #89d185; font-weight: bold; }
.log-item.warning .msg { color: #d7ba7d; }
.log-item.error .msg { color: #f48771; font-weight: bold; }

.typing .msg {
  animation: blink 1.5s infinite;
}
@keyframes blink {
  0% { opacity: 1; }
  50% { opacity: 0.4; }
  100% { opacity: 1; }
}

/* 响应式适配 */
@media (max-width: 1200px) {
  .sidebar-left, .sidebar-right {
    width: 260px;
  }
}

@media (max-width: 992px) {
  .sidebar-right {
    display: none; /* 在较小屏幕下隐藏侧边栏日志以保证中间阅读体验 */
  }
  .sidebar-left {
    width: 240px;
  }
}
</style>

