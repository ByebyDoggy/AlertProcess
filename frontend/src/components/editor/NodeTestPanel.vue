<template>
  <div class="modal-overlay" @click.self="$emit('close')">
    <div class="test-panel" :class="{ 'panel-wide': showFullOutput }">
      <!-- Header -->
      <div class="panel-header">
        <div class="header-left">
          <span class="header-icon">&#9889;</span>
          <h3>节点测试 — {{ nodeLabel }}</h3>
          <span class="node-type-tag">{{ nodeType }}</span>
        </div>
        <div class="header-actions">
          <button v-if="testResult && !showFullOutput" class="action-btn" @click="showFullOutput = true" title="展开完整输出">详情</button>
          <button v-if="showFullOutput" class="action-btn" @click="showFullOutput = false" title="收起">收起</button>
          <button class="action-btn close-btn" @click="$emit('close')">&times;</button>
        </div>
      </div>

      <div class="panel-body">
        <!-- Upstream info -->
        <div v-if="upstreamNodes.length > 0" class="section upstream-section">
          <span class="section-title">&#8593; 上游输入（{{ upstreamNodes.length }} 个）</span>
          <div class="upstream-list">
            <div v-for="u in upstreamNodes" :key="u.nodeId" class="upstream-item" :class="{ 'has-data': !!u.result }">
              <span class="upstream-label">{{ u.label || u.nodeType }}</span>
              <span v-if="u.result" class="upstream-status status-ok">&#10003; {{ u.resultText }}</span>
              <span v-else class="upstream-status status-none">&mdash; 无输出</span>
            </div>
          </div>
        </div>

        <!-- Manual input -->
        <div class="section input-section">
          <div class="section-header">
            <span class="section-title">{{ isTrigger ? '&#128269; 测试数据' : '&#9999; 自定义输入数据' }}<span v-if="!isTrigger" class="optional-hint">（可选，覆盖上游输出）</span></span>
            <button v-if="!showInputEditor" class="mini-btn" @click="showInputEditor = true">编辑</button>
            <button v-else class="mini-btn" @click="showInputEditor = false">收起</button>
          </div>
          <div v-if="showInputEditor || isTrigger" class="input-editor">
            <!-- 数据来源标签 -->
            <div v-if="dataSource !== 'none'" class="data-source-tag" :class="'src-' + dataSource">
              <span v-if="dataSource === 'kb'">&#128270; 来自知识库: {{ kbSampleDetail?.title?.substring(0, 30) }}{{ kbSampleDetail?.title && kbSampleDetail.title.length > 30 ? '...' : '' }}</span>
              <span v-else-if="dataSource === 'sample'">&#128202; 示例数据</span>
              <span v-else-if="dataSource === 'manual'">&#9999; 用户自定义数据</span>
              <button class="mini-btn tag-clear-btn" @click="clearDataSource" title="清除来源标记">&times;</button>
            </div>
            <textarea
              ref="inputTextarea"
              v-model="inputJson"
              class="json-textarea"
              :placeholder="inputPlaceholder"
              rows="8"
              spellcheck="false"
            ></textarea>
            <div v-if="inputError" class="input-error">{{ inputError }}</div>
            <div class="input-actions">
              <button class="btn btn-sm btn-secondary" @click="loadFromKB" title="从知识库加载样本数据">&#128270; 从知识库加载</button>
              <button class="btn btn-sm btn-secondary" @click="fillSampleData">填入示例</button>
              <button class="btn btn-sm btn-ghost-danger" :disabled="!inputJson.trim()" @click="clearInputData" title="清空已填写的数据">清除</button>
              <button class="btn btn-sm btn-primary" :disabled="!!inputError || !inputJson.trim()" @click="saveInputData">保存输入</button>
            </div>

            <!-- 知识库选择器 -->
            <div v-if="showKBPicker" class="kb-picker">
              <div class="kb-picker-header">
                <span class="kb-picker-title">选择知识库样本</span>
                <button class="mini-btn" @click="showKBPicker = false">&times;</button>
              </div>
              <div v-if="kbLoading" class="kb-picker-loading">加载中...</div>
              <select v-else v-model="selectedKBSampleId" class="kb-select">
                <option value="">-- 选择样本 --</option>
                <option v-for="s in kbSamples" :key="s.id" :value="s.id">
                  {{ s.title }} | chain={{ s.chain_id }} | {{ s.category }}
                </option>
              </select>
              <div v-if="selectedKBSampleId && kbSampleDetail" class="kb-preview">
                <div class="kb-preview-header">{{ kbSampleDetail.title }}</div>
                <pre class="kb-preview-data">{{ JSON.stringify(kbSampleDetail.alert_data, null, 2).substring(0, 600) }}{{ JSON.stringify(kbSampleDetail.alert_data).length > 600 ? '\n...' : '' }}</pre>
                <button class="btn btn-sm btn-primary" style="margin-top:8px" @click="applyKBSample">使用此数据</button>
              </div>
            </div>
          </div>
        </div>

        <!-- Run button area -->
        <div class="section run-section">
          <div class="run-bar">
            <span class="run-hint">
              <template v-if="canRunNow">
                <span class="dot-green"></span> 就绪：{{ runHint }}
              </template>
              <template v-else>
                <span class="dot-red"></span> {{ runHint }}
              </template>
            </span>
            <button
              class="btn btn-run"
              :disabled="!canRunNow || running"
              @click="runTest"
            >
              {{ running ? '执行中...' : (testResult ? '重新执行' : '执行测试') }}
            </button>
          </div>
        </div>

        <!-- Result -->
        <div v-if="testResult" class="section result-section" :class="{ 'result-error': isTestFailed }">
          <div class="result-header">
            <span class="result-badge" :class="isTestFailed ? 'badge-error' : 'badge-success'">
              {{ isTestFailed ? '&#10007; 执行异常' : '&#10003; 执行成功' }}
            </span>
            <span class="result-meta">
              耗时: {{ testResult.duration_ms }}ms
              <span v-if="outputSummary"> | {{ outputSummary }}</span>
            </span>
            <button class="mini-btn danger-btn" @click="clearResult" title="清除结果">清除</button>
          </div>

          <!-- Error detail -->
          <div v-if="contextErrorMessage" class="result-error-detail">
            {{ contextErrorMessage }}
          </div>

          <!-- Output preview -->
          <template v-if="testResult.output">
            <div v-if="!showFullOutput" class="result-preview" @click="showFullOutput = true">
              <pre>{{ outputPreview }}</pre>
            </div>
            <div v-else class="result-full">
              <div class="output-tabs">
                <button
                  v-for="tab in outputTabs"
                  :key="tab.key"
                  :class="['tab', { active: activeTab === tab.key }]"
                  @click="activeTab = tab.key"
                >{{ tab.label }}</button>
              </div>
              <pre class="output-content">{{ currentTabContent }}</pre>
            </div>
          </template>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { useChainDataStore } from '../../stores/chainData.js'
import { useNodeTypesStore } from '../../stores/nodeTypes.js'
import { useKnowledgeBaseStore } from '../../stores/knowledgeBase.js'
import * as chainApi from '../../api/ruleChain.js'
import { getSamples } from '../../api/knowledgeBase.js'

const props = defineProps({
  nodeId: { type: String, required: true },
})
defineEmits(['close'])

const chainDataStore = useChainDataStore()
const nodeTypesStore = useNodeTypesStore()
const kbStore = useKnowledgeBaseStore()

// ── 知识库加载状态 ──
const showKBPicker = ref(false)
const kbLoading = ref(false)
const selectedKBSampleId = ref('')
const kbSampleDetail = ref(null)
const kbSamples = computed(() => kbStore.samples)

// ── State ──
const running = ref(false)
const showInputEditor = ref(false)
const showFullOutput = ref(false)
const inputJson = ref('')
const inputError = ref('')
const inputTextarea = ref(null)
const activeTab = ref('output')

// ── 数据来源标记 ──
/** 'none' | 'kb' | 'sample' | 'manual' */
const dataSource = ref('none')

// ── Computed ──
const currentNode = computed(() =>
  chainDataStore.nodes.find(n => n.id === props.nodeId) || {}
)

const nodeTypeObj = computed(() =>
  nodeTypesStore.getByName(currentNode.value?.type)
)

const nodeLabel = computed(() => currentNode.value?.label || '未知节点')
const nodeType = computed(() => nodeTypeObj.value?.label || currentNode.value?.type || '?')
const isTrigger = computed(() => nodeTypeObj.value?.category === 'input')

/** 上游节点及其测试结果 */
const upstreamNodes = computed(() => {
  const edges = chainDataStore.edges.filter(e => e.target === props.nodeId)
  return edges.map(e => {
    const srcNode = chainDataStore.nodes.find(n => n.id === e.source)
    const result = chainDataStore.nodeTestResults[e.source]
    return {
      nodeId: e.source,
      label: srcNode?.label || '',
      nodeType: srcNode?.type || '',
      result: result || null,
      resultText: result
        ? result.error
          ? result.error.substring(0, 25)
          : `score=${result.output?.score ?? '-'}`
        : '',
    }
  })
})

/** 当前节点的测试结果 */
const testResult = computed(() => chainDataStore.nodeTestResults[props.nodeId] || null)

/** 是否失败 — 后端已将所有异常归一化到 error 字段 */
const isTestFailed = computed(() => !!testResult.value?.error)

/** 输出摘要 */
const outputSummary = computed(() => {
  if (!testResult.value?.output) return ''
  const o = testResult.value.output
  // error 已由后端统一提取，此处只展示正常指标
  if (isTestFailed.value) return ''
  const parts = []
  if (o.score != null) parts.push(`score ${o.score}`)
  if (o.passed !== undefined) parts.push(o.passed ? 'passed' : 'not passed')
  if (o.severity) parts.push(o.severity)
  if (o.labels?.length) parts.push(`labels: ${o.labels.join(', ')}`)
  return parts.join(' · ')
})

/** 错误信息（直接取后端归一化的 error 字段） */
const contextErrorMessage = computed(() => {
  return testResult.value?.error || null
})

/** 输出预览文本 */
const outputPreview = computed(() => {
  if (!testResult.value?.output) return ''
  try {
    return JSON.stringify(testResult.value.output, null, 2).substring(0, 800)
    + (JSON.stringify(testResult.value.output).length > 800 ? '\n...' : '')
  } catch { return String(testResult.value.output) }
})

/** 是否可以运行 */
const canRunNow = computed(() => {
  // Trigger 始终可以运行
  if (isTrigger.value) return true
  // 有上游输出
  if (upstreamNodes.value.some(u => u.result)) return true
  // 有手动设置的输入数据
  if (chainDataStore.getNodeTestInput(props.nodeId)) return true
  return false
})

/** 运行提示文字 */
const runHint = computed(() => {
  if (isTrigger.value) {
    if (dataSource.value === 'kb') return '使用知识库数据运行'
    if (dataSource.value === 'sample') return '使用示例空数据运行'
    if (dataSource.value === 'manual') return chainDataStore.getNodeTestInput(props.nodeId) ? '使用自定义测试数据运行' : '使用默认空数据运行'
    return '使用默认空数据运行'
  }
  const hasUpstream = upstreamNodes.value.some(u => u.result)
  const hasManual = !!chainDataStore.getNodeTestInput(props.nodeId)
  if (hasUpstream && hasManual) return '使用手动输入 + 上游输出'
  if (hasUpstream) return `使用 ${upstreamNodes.value.filter(u => u.result).length} 个上游输出`
  if (hasManual || dataSource.value !== 'none') {
    const srcLabel = { kb: '来自知识库', sample: '示例', manual: '自定义' }[dataSource.value] || ''
    return `使用${srcLabel}${hasManual ? '+ 上游输出' : ''}数据`
  }
  return '需要先运行上游节点或设置输入数据'
})

/** 输入占位符 */
const inputPlaceholder = computed(() => {
  if (isTrigger.value) {
    return JSON.stringify({
      "chain_id": 1,
      "tx_hash": "0x...",
      "gas_price": 50000000000,
      "gas_used": 210000,
      "to_address": "0x...",
      "from_address": "0x...",
      "value": "1000000000000000000",
      "input_data": "0x...",
    }, null, 2)
  }
  return '{"key": "value"}'
})

/** 输出 Tab 定义 */
const outputTabs = computed(() => {
  const tabs = [
    { key: 'output', label: '完整输出' },
    { key: 'context', label: 'Context' },
  ]
  const out = testResult.value?.output
  if (!out) return tabs.slice(0, 1)
  if (out.labels?.length) tabs.push({ key: 'labels', label: `Labels(${out.labels.length})` })
  return tabs
})

/** 当前 Tab 的内容 */
const currentTabContent = computed(() => {
  const out = testResult.value?.output
  if (!out) return '(无输出)'
  switch (activeTab.value) {
    case 'output':
      return JSON.stringify(out, null, 2)
    case 'context':
      return JSON.stringify(out.context || {}, null, 2) || '{}'
    case 'labels':
      return JSON.stringify(out.labels || [], null, 2)
    default:
      return ''
  }
})

// ── Watchers ──
watch(inputJson, () => {
  if (inputJson.value.trim()) {
    try {
      JSON.parse(inputJson.value)
      inputError.value = ''
    } catch (e) {
      inputError.value = e.message
    }
  } else {
    inputError.value = ''
  }
})

watch(() => props.nodeId, () => {
  // 切换节点时重置状态
  showFullOutput.value = false
  activeTab.value = 'output'
  dataSource.value = 'none'
  // 加载已保存的输入数据
  const saved = chainDataStore.getNodeTestInput(props.nodeId)
  if (saved) {
    inputJson.value = saved
    showInputEditor.value = true
  } else {
    inputJson.value = ''
    showInputEditor.value = !isTrigger.value
  }
}, { immediate: true })

// ── Methods ──

async function runTest() {
  if (!canRunNow.value || running.value) return
  running.value = true

  try {
    const upstreamOutputs = chainDataStore.getUpstreamOutputs(props.nodeId)
    let alertData = null
    const manualInput = chainDataStore.getNodeTestInput(props.nodeId)
    if (manualInput) {
      try { alertData = JSON.parse(manualInput) } catch { /* ignore */ }
    }

    if (isTrigger.value && !alertData && Object.keys(upstreamOutputs).length === 0) {
      alertData = { __test__: true }
    }

    const result = await chainApi.testNode(
      chainDataStore.nodes,
      chainDataStore.edges,
      props.nodeId,
      upstreamOutputs,
      alertData,
    )
    chainDataStore.setNodeTestResult(props.nodeId, result)
    showFullOutput.value = true
  } catch (e) {
    console.error('[NodeTestPanel] run failed:', e)
    chainDataStore.setNodeTestResult(props.nodeId, {
      success: false,
      error: e.message || String(e),
      duration_ms: 0,
    })
  } finally {
    running.value = false
  }
}

function saveInputData() {
  if (!inputJson.value.trim()) return
  try {
    JSON.parse(inputJson.value)
    chainDataStore.setNodeTestInput(props.nodeId, inputJson.value)
    dataSource.value = 'manual'
  } catch (e) {
    inputError.value = e.message
  }
}

function clearResult() {
  chainDataStore.clearNodeTestResult(props.nodeId)
}

function clearInputData() {
  inputJson.value = ''
  inputError.value = ''
  dataSource.value = 'none'
  // 清除 store 中已保存的输入数据
  chainDataStore.setNodeTestInput(props.nodeId, null)
}

function fillSampleData() {
  if (isTrigger.value) {
    inputJson.value = JSON.stringify({
      "chain_id": 1,
      "tx_hash": "0xabc123def456789012345678901234567890abcdef12345678901234567890abcd",
      "gas_price": 50000000000,
      "gas_used": 210000,
      "to_address": "0xa27a69e22bdeE48c1A2D745123BdC1844F49f1D8",
      "from_address": "0xdeadbeefdeadbeefdeadbeefdeadbeefdeadbeef",
      "value": "1000000000000000000",
      "input_data": "0x...",
      "eth_logs": [],
    }, null, 2)
    dataSource.value = 'sample'
  } else {
    inputJson.value = JSON.stringify({ "score": 50, "passed": true, "labels": ["test"] }, null, 2)
    dataSource.value = 'sample'
  }
}

// ── 知识库加载方法 ──

async function loadFromKB() {
  showKBPicker.value = true
  selectedKBSampleId.value = ''
  kbSampleDetail.value = null
  kbLoading.value = true

  try {
    // 如果知识库数据为空，先拉取
    if (kbStore.samples.length === 0) {
      await kbStore.fetchSamples()
    }
  } catch (e) {
    console.error('[NodeTestPanel] Failed to load KB samples:', e)
  } finally {
    kbLoading.value = false
  }
}

function clearDataSource() {
  dataSource.value = 'none'
}

function applyKBSample() {
  if (!kbSampleDetail.value?.alert_data) return
  try {
    inputJson.value = JSON.stringify(kbSampleDetail.value.alert_data, null, 2)
    showInputEditor.value = true
    chainDataStore.setNodeTestInput(props.nodeId, inputJson.value)
    inputError.value = ''
    dataSource.value = 'kb'
  } catch (e) {
    console.error('[NodeTestPanel] Failed to apply KB sample:', e)
  }
}

watch(selectedKBSampleId, async (newId) => {
  if (!newId) {
    kbSampleDetail.value = null
    return
  }
  try {
    const detail = await kbStore.fetchSampleDetail(newId)
    kbSampleDetail.value = detail
    // 选中样本后自动填入测试数据区域
    if (detail?.alert_data) {
      inputJson.value = JSON.stringify(detail.alert_data, null, 2)
      showInputEditor.value = true
      chainDataStore.setNodeTestInput(props.nodeId, inputJson.value)
      inputError.value = ''
      dataSource.value = 'kb'
      // 自动关闭选择器
      showKBPicker.value = false
    }
  } catch (e) {
    console.error('[NodeTestPanel] Failed to fetch sample detail:', e)
    kbSampleDetail.value = null
  }
})
</script>

<style scoped>
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.55);
  backdrop-filter: blur(6px);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 200;
}
.test-panel {
  background: #1e1e38;
  border: 1px solid #2d2d50;
  border-radius: 14px;
  width: min(92%, 600px);
  max-height: 88vh;
  display: flex;
  flex-direction: column;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.5);
}
.test-panel.panel-wide {
  width: min(94%, 780px);
}
.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 18px;
  border-bottom: 1px solid #2d2d50;
  flex-shrink: 0;
}
.header-left {
  display: flex;
  align-items: center;
  gap: 8px;
  overflow: hidden;
}
.header-icon { font-size: 16px; }
.panel-header h3 {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.node-type-tag {
  font-size: 10px;
  padding: 2px 8px;
  border-radius: 4px;
  background: rgba(99, 102, 241, 0.12);
  color: #a5b4fc;
  white-space: nowrap;
  flex-shrink: 0;
}
.header-actions { display: flex; gap: 4px; flex-shrink: 0; }
.action-btn {
  width: 28px; height: 28px;
  border-radius: 6px;
  border: none;
  background: transparent;
  color: #94a3b8;
  font-size: 14px;
  cursor: pointer;
  transition: all 0.15s;
}
.action-btn:hover { background: rgba(255,255,255,0.06); color: #e2e8f0; }
.close-btn:hover { background: rgba(239,68,68,0.15); color: #f87171; }

.panel-body {
  flex: 1;
  overflow-y: auto;
  padding: 12px 18px;
}

/* Sections */
.section { margin-bottom: 14px; }
.section-title {
  font-size: 11.5px;
  font-weight: 600;
  color: #94a3b8;
  text-transform: uppercase;
  letter-spacing: 0.03em;
}
.optional-hint {
  font-weight: 400;
  color: #6b7280;
  text-transform: none;
  letter-spacing: 0;
  margin-left: 4px;
}
.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 6px;
}

/* Upstream */
.upstream-section .upstream-list {
  display: flex;
  flex-direction: column;
  gap: 3px;
  margin-top: 6px;
}
.upstream-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 5px 8px;
  border-radius: 6px;
  background: rgba(99, 102, 241, 0.04);
  border: 1px solid transparent;
  transition: all 0.15s;
}
.upstream-item.has-data {
  background: rgba(16, 185, 129, 0.05);
  border-color: rgba(16, 185, 129, 0.1);
}
.upstream-label {
  font-size: 12px;
  color: #cbd5e1;
  font-weight: 500;
}
.upstream-status { font-size: 10.5px; margin-left: auto; }
.status-ok { color: #34d399; }
.status-none { color: #4b5563; }

/* Input editor */
.input-section { }
.input-editor { margin-top: 6px; }
.json-textarea {
  width: 100%;
  background: #16162a;
  border: 1px solid #2d2d50;
  border-radius: 8px;
  color: #e2e8f0;
  font-family: 'JetBrains Mono', 'Cascadia Code', 'Fira Code', monospace;
  font-size: 11.5px;
  line-height: 1.5;
  padding: 10px 12px;
  resize: vertical;
  min-height: 80px;
}
.json-textarea:focus {
  outline: none;
  border-color: rgba(99, 102, 241, 0.4);
  box-shadow: 0 0 0 2px rgba(99, 102, 241, 0.08);
}
.input-error {
  font-size: 11px;
  color: #f87171;
  margin-top: 4px;
}
.input-actions {
  display: flex;
  justify-content: flex-end;
  gap: 6px;
  margin-top: 6px;
}

/* Run bar */
.run-section .run-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 12px;
  border-radius: 8px;
  background: linear-gradient(135deg, rgba(99, 102, 241, 0.06), rgba(16, 185, 129, 0.04));
  border: 1px solid rgba(99, 102, 241, 0.1);
}
.run-hint { font-size: 11.5px; color: #94a3b8; display: flex; align-items: center; gap: 5px; }
.dot-green { width: 7px; height: 7px; border-radius: 50%; background: #10b981; display: inline-block; }
.dot-red { width: 7px; height: 7px; border-radius: 50%; background: #ef4444; display: inline-block; }

.btn {
  padding: 7px 16px;
  border-radius: 7px;
  font-size: 12.5px;
  font-weight: 600;
  cursor: pointer;
  border: none;
  transition: all 0.15s;
}
.btn:disabled { opacity: 0.45; cursor: not-allowed; }
.btn-sm { padding: 4px 10px; font-size: 11px; border-radius: 5px; }
.btn-secondary { background: #2d2d50; color: #94a3b8; }
.btn-secondary:hover:not(:disabled) { background: #3d3d65; }
.btn-ghost-danger { background: transparent; color: #94a3b8; border: 1px solid #2d2d50; }
.btn-ghost-danger:hover:not(:disabled) { background: rgba(239,68,68,0.08); color: #f87171; border-color: rgba(239,68,68,0.25); }
.btn-primary { background: #6366f1; color: white; }
.btn-primary:hover:not(:disabled) { background: #5855e6; }
.btn-run {
  background: linear-gradient(135deg, #10b981, #059669);
  color: white;
  padding: 8px 20px;
}
.btn-run:hover:not(:disabled) {
  background: linear-gradient(135deg, #059669, #047857);
  transform: translateY(-0.5px);
}

/* Result */
.result-section {
  margin-top: 14px;
  border-radius: 10px;
  border: 1px solid rgba(16, 185, 129, 0.12);
  background: rgba(16, 185, 129, 0.04);
}
.result-error {
  border-color: rgba(239, 68, 68, 0.15);
  background: rgba(239, 68, 68, 0.04);
}
.result-header {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  border-bottom: 1px solid rgba(255,255,255,0.04);
}
.result-badge {
  font-size: 12px;
  font-weight: 600;
  padding: 3px 10px;
  border-radius: 5px;
}
.badge-success { background: rgba(16,185,129,0.12); color: #34d399; }
.badge-error { background: rgba(239,68,68,0.12); color: #f87171; }
.result-meta {
  font-size: 11px;
  color: #6b7280;
  flex: 1;
}
.danger-btn:hover { background: rgba(239,68,68,0.1); color: #f87171; }

.result-error-detail {
  padding: 10px 12px;
  color: #fca5a5;
  font-size: 12px;
  font-family: monospace;
  word-break: break-all;
}

.result-preview {
  padding: 10px 12px;
  cursor: pointer;
}
.result-preview pre {
  margin: 0;
  font-family: 'JetBrains Mono', monospace;
  font-size: 10.5px;
  line-height: 1.5;
  color: #94a3b8;
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 200px;
  overflow: hidden;
}
.result-full { }
.output-tabs {
  display: flex;
  gap: 2px;
  padding: 8px 12px 0;
  border-bottom: 1px solid rgba(255,255,255,0.04);
}
.tab {
  padding: 5px 12px;
  border-radius: 6px 6px 0 0;
  border: 1px solid transparent;
  background: transparent;
  color: #6b7280;
  font-size: 11px;
  cursor: pointer;
  margin-bottom: -1px;
}
.tab.active {
  background: rgba(99, 102, 241, 0.08);
  border-color: rgba(99, 102, 241, 0.15);
  color: #a5b4fc;
}
.output-content {
  margin: 0;
  padding: 12px;
  font-family: 'JetBrains Mono', monospace;
  font-size: 10.5px;
  line-height: 1.55;
  color: #cbd5e1;
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 360px;
  overflow-y: auto;
  background: rgba(0,0,0,0.15);
  border-radius: 0 0 8px 8px;
}

/* Mini buttons */
.mini-btn {
  padding: 2px 8px;
  border-radius: 4px;
  border: 1px solid #2d2d50;
  background: transparent;
  color: #94a3b8;
  font-size: 10.5px;
  cursor: pointer;
  transition: all 0.12s;
}
.mini-btn:hover { background: rgba(255,255,255,0.05); color: #e2e8f0; }

/* Knowledge base picker */
.kb-picker {
  margin-top: 10px;
  padding: 12px;
  border-radius: 8px;
  background: rgba(99, 102, 241, 0.05);
  border: 1px solid rgba(99, 102, 241, 0.15);
}
.kb-picker-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}
.kb-picker-title {
  font-size: 11.5px;
  font-weight: 600;
  color: #a5b4fc;
}
.kb-picker-loading {
  text-align: center;
  color: #6b7280;
  font-size: 11px;
  padding: 8px;
}
.kb-select {
  width: 100%;
  background: #16162a;
  border: 1px solid #2d2d50;
  border-radius: 6px;
  color: #e2e8f0;
  font-size: 11.5px;
  padding: 6px 10px;
  outline: none;
}
.kb-select:focus {
  border-color: rgba(99, 102, 241, 0.4);
}
.kb-preview {
  margin-top: 8px;
}
.kb-preview-header {
  font-size: 11.5px;
  font-weight: 600;
  color: #94a3b8;
  margin-bottom: 4px;
}
.kb-preview-data {
  background: #0f0f1f;
  border: 1px solid #2d2d50;
  border-radius: 6px;
  padding: 8px 10px;
  font-size: 10.5px;
  color: #94a3b8;
  max-height: 180px;
  overflow-y: auto;
  white-space: pre-wrap;
  word-break: break-all;
  line-height: 1.45;
}

/* Data source tag */
.data-source-tag {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
  margin-bottom: 6px;
  border-radius: 6px;
  font-size: 11.5px;
  font-weight: 500;
}
.data-source-tag.src-kb {
  background: rgba(99, 102, 241, 0.12);
  color: #a5b4fc;
  border: 1px solid rgba(99, 102, 241, 0.25);
}
.data-source-tag.src-sample {
  background: rgba(16, 185, 129, 0.12);
  color: #34d399;
  border: 1px solid rgba(16, 185, 129, 0.25);
}
.data-source-tag.src-manual {
  background: rgba(245, 158, 11, 0.12);
  color: #fbbf24;
  border: 1px solid rgba(245, 158, 11, 0.25);
}
.tag-clear-btn {
  margin-left: auto;
  padding: 1px 5px;
  font-size: 13px;
  cursor: pointer;
}
.tag-clear-btn:hover { background: rgba(239, 68, 68, 0.15); }
</style>
