<template>
  <div class="script-editor-demo">
    <div class="demo-header">
      <h1>Script Editor 演示</h1>
      <p>基于 CodeMirror 的 Python 脚本编辑器，支持 ScriptContext API 智能提示</p>
    </div>

    <div class="demo-content">
      <div class="editor-section">
        <ScriptEditor
          v-model="scriptCode"
          @save="handleSave"
        />
      </div>

      <div class="output-section">
        <div class="output-header">
          <h3>输出预览</h3>
          <button class="run-btn" @click="runScript">
            <span class="run-icon">&#9654;</span> 运行脚本
          </button>
        </div>
        <div class="output-content">
          <pre v-if="output">{{ output }}</pre>
          <div v-else class="output-placeholder">点击"运行脚本"查看输出</div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import ScriptEditor from '../components/editor/ScriptEditor.vue'

const scriptCode = ref(`# Python 脚本示例
# 使用 ScriptContext API 访问执行上下文

# 访问告警数据
chain_id = ctx.alert_data.get('chain_id', 1)
tx_hash = ctx.alert_data.get('tx_hash', '')

# 访问交易上下文
if 'tx' in dir():
    from_addr = tx.from_address
    to_addr = tx.to_address
    value_wei = tx.value

    # 检查大额转账
    if value_wei > 1000000000000000000:  # > 1 ETH
        print(f"检测到大额转账: {value_wei / 1e18} ETH")

# 访问节点输出
for node_id, output in ctx.node_outputs.items():
    print(f"节点 {node_id}: score={output.score}, passed={output.passed}")

# 检查严重级别
if ctx.final_severity in ['CRITICAL', 'HIGH']:
    print(f"警告: 检测到 {ctx.final_severity} 级别威胁")
    print(f"最终评分: {ctx.final_score}")
    print(f"标签: {', '.join(ctx.collected_labels)}")

# 返回结果
result = ctx.final_score >= 60
score = ctx.final_score
labels = ctx.collected_labels + ["SCRIPT_PROCESSED"]
`)

const output = ref('')

function handleSave(code) {
  console.log('保存脚本:', code)
  output.value = '✓ 脚本已保存\n\n' + code
}

function runScript() {
  output.value = '执行脚本...\n\n'

  // 模拟脚本执行
  setTimeout(() => {
    output.value += '检测到大额转账: 5.5 ETH\n'
    output.value += '节点 detector_1: score=75.0, passed=True\n'
    output.value += '节点 detector_2: score=60.0, passed=True\n'
    output.value += '警告: 检测到 HIGH 级别威胁\n'
    output.value += '最终评分: 75.0\n'
    output.value += '标签: LARGE_TRANSFER, SUSPICIOUS_PATTERN, SCRIPT_PROCESSED\n'
    output.value += '\n✓ 脚本执行完成'
  }, 500)
}
</script>

<style scoped>
.script-editor-demo {
  height: 100vh;
  display: flex;
  flex-direction: column;
  background: #0f0f1e;
  color: #e2e8f0;
}

.demo-header {
  padding: 24px 32px;
  background: #16162a;
  border-bottom: 1px solid #2d2d50;
}

.demo-header h1 {
  font-size: 24px;
  font-weight: 700;
  color: #e2e8f0;
  margin: 0 0 8px 0;
}

.demo-header p {
  font-size: 14px;
  color: #94a3b8;
  margin: 0;
}

.demo-content {
  flex: 1;
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
  padding: 16px;
  overflow: hidden;
}

.editor-section,
.output-section {
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.output-section {
  background: #1a1a2e;
  border: 1px solid #2d2d50;
  border-radius: 12px;
  overflow: hidden;
}

.output-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  background: #16162a;
  border-bottom: 1px solid #2d2d50;
}

.output-header h3 {
  font-size: 14px;
  font-weight: 600;
  color: #e2e8f0;
  margin: 0;
}

.run-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  background: #10b981;
  color: white;
  border: none;
  padding: 6px 14px;
  border-radius: 6px;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.15s;
}

.run-btn:hover {
  background: #059669;
  transform: translateY(-1px);
  box-shadow: 0 4px 8px rgba(16, 185, 129, 0.2);
}

.run-icon {
  font-size: 10px;
}

.output-content {
  flex: 1;
  overflow: auto;
  padding: 16px;
}

.output-content pre {
  margin: 0;
  font-family: 'JetBrains Mono', 'Fira Code', monospace;
  font-size: 13px;
  line-height: 1.6;
  color: #94a3b8;
  white-space: pre-wrap;
  word-wrap: break-word;
}

.output-placeholder {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: #4b5563;
  font-size: 14px;
  font-style: italic;
}

.output-content::-webkit-scrollbar {
  width: 8px;
}

.output-content::-webkit-scrollbar-track {
  background: #1a1a2e;
}

.output-content::-webkit-scrollbar-thumb {
  background: #2d2d50;
  border-radius: 4px;
}

.output-content::-webkit-scrollbar-thumb:hover {
  background: #3d3d60;
}

@media (max-width: 1200px) {
  .demo-content {
    grid-template-columns: 1fr;
    grid-template-rows: 1fr 1fr;
  }
}
</style>
