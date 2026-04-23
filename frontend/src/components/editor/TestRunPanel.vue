<template>
  <div class="modal-overlay" @click.self="$emit('close')">
    <div class="testrun-panel">
      <!-- 头部 -->
      <div class="panel-header">
        <h3>&#9889; 测试运行</h3>
        <button class="panel-close" @click="$emit('close')">&times;</button>
      </div>

      <!-- 未保存提示 -->
      <div v-if="!chainId" class="panel-empty">
        <div class="empty-icon">&#128276;</div>
        <p>请先保存规则链后再进行测试</p>
      </div>

      <template v-else>
        <!-- 选择测试数据 + 执行队列（左右分栏） -->
        <div class="panel-body-split">
          <!-- 左侧：选择区域 -->
          <div class="panel-left">
            <div class="data-source-tabs">
              <button
                :class="['tab-btn', { active: dataSource === 'samples' }]"
                @click="dataSource = 'samples'"
              >
                从知识库选择
              </button>
              <button
                :class="['tab-btn', { active: dataSource === 'custom' }]"
                @click="dataSource = 'custom'"
              >
                自定义 JSON
              </button>
            </div>

            <!-- 从知识库选择 -->
            <div v-if="dataSource === 'samples'" class="sample-selector">
              <div class="selector-toolbar">
                <input
                  v-model="sampleSearch"
                  class="form-input search-input"
                  placeholder="搜索样本..."
                />
              </div>
              <div class="sample-list" v-if="kbSamples.length">
                <label
                  v-for="s in filteredSamples"
                  :key="s.id"
                  class="sample-option"
                  :class="{ selected: selectedIds.has(s.id) }"
                >
                  <input type="checkbox" :value="s.id" v-model="selectedArr" class="sample-check" @change="onSelectionChange(s.id, $event)" />
                  <div class="sample-info">
                    <span class="sample-title">{{ s.title }}</span>
                    <span class="sample-meta">
                      <span class="cat-chip">{{ kbStore.getCategoryLabel(s.category) }}</span>
                      <span v-if="s.expected_severity" class="sev-chip" :class="'sev-' + s.expected_severity.toLowerCase()">
                        {{ s.expected_severity }}
                      </span>
                    </span>
                  </div>
                  <button
                    v-if="selectedIds.has(s.id)"
                    class="btn-add-queue"
                    title="添加到执行队列"
                    @click.stop="addToQueue(s)"
                  >&#10140;</button>
                </label>
              </div>
              <div v-else-if="!kbStore.loading" class="no-samples">
                暂无知识库样本，请先前往
                <router-link to="/knowledge-base" class="link" @click="$emit('close')">知识库</router-link>
                添加
              </div>
            </div>

            <!-- 自定义 JSON -->
            <div v-else class="custom-json">
              <textarea
                v-model="customJson"
                class="form-textarea json-input"
                rows="8"
                placeholder='{"chain_id": 1, "tx_hash": "0x...", ...}'
              ></textarea>
              <div v-if="jsonError" class="form-error">{{ jsonError }}</div>
              <button
                v-if="customJson.trim() && !jsonError"
                class="btn-add-custom"
                @click="addCustomToQueue"
              >+ 添加到执行队列</button>
            </div>
          </div>

          <!-- 右侧：执行队列（拖拽排序） -->
          <div class="panel-right">
            <div class="queue-header">
              <span class="queue-title">执行队列</span>
              <span class="queue-count">{{ executionQueue.length }} 条日志</span>
              <button v-if="executionQueue.length" class="btn-clear-queue" @click="clearQueue">清空</button>
            </div>
            <div
              class="execution-queue"
              @dragover.prevent="onDragOver"
              @drop="onDrop"
            >
              <div
                v-for="(item, idx) in executionQueue"
                :key="item.uid"
                class="queue-item"
                :class="{ 'drag-over': dragOverIdx === idx }"
                draggable="true"
                @dragstart="onDragStart($event, idx)"
                @dragover.prevent="onDragOverItem($event, idx)"
                @dragend="onDragEnd"
              >
                <span class="queue-order">{{ idx + 1 }}</span>
                <span class="queue-drag-handle">&#9776;</span>
                <div class="queue-item-info">
                  <span class="queue-item-title">{{ item.title }}</span>
                  <span v-if="item.severity" class="sev-chip-mini" :class="'sev-' + item.severity.toLowerCase()">{{ item.severity }}</span>
                </div>
                <button class="queue-remove" @click="removeFromQueue(idx)" title="移除">&times;</button>
              </div>
              <div v-if="!executionQueue.length" class="queue-empty">
                从左侧选择日志并添加到此处<br/>支持拖拽调整顺序
              </div>
            </div>
          </div>
        </div>

        <!-- 执行按钮 -->
        <div class="panel-actions">
          <span class="run-info">
            <template v-if="executionQueue.length">
              队列 {{ executionQueue.length }} 条日志 &middot; 按{{ dataSource === 'custom' ? '自定义' : '选择' }}顺序执行
            </template>
            <template v-else>请添加日志到执行队列</template>
          </span>
          <button
            class="btn btn-run"
            :disabled="!canRun || running"
            @click="executeTest"
          >
            {{ running ? `执行中... ${currentRunIdx + 1}/${executionQueue.length}` : '&#9654; 顺序执行测试' }}
          </button>
        </div>

        <!-- 进度条 -->
        <div v-if="running && executionQueue.length > 1" class="run-progress">
          <div class="progress-bar">
            <div class="progress-fill" :style="{ width: progressPercent + '%' }"></div>
          </div>
          <span class="progress-text">正在执行: {{ currentRunItem?.title || '' }}</span>
        </div>

        <!-- 结果区域 -->
        <div v-if="results.length" class="panel-results" :class="{ 'has-critical': hasCritical }">
          <div class="results-header">
            <span>测试结果 (按执行顺序)</span>
            <span class="results-summary">
              <span class="summary-pass">&#10003; {{ passCount }}</span>
              <span class="summary-fail">&#10007; {{ failCount }}</span>
              <span class="summary-time">总耗时 {{ totalDurationMs.toFixed(0) }}ms</span>
            </span>
          </div>
          <div class="results-list">
            <TestRunResult
              v-for="(r, i) in results"
              :key="i"
              :result="r"
              :run-index="i + 1"
              :total-count="results.length"
            />
          </div>
        </div>

        <!-- 运行错误 -->
        <div v-if="runError" class="run-error">
          &#9888; {{ runError }}
        </div>
      </template>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { testRunChain } from '@/api/knowledgeBase.js'
import { useKnowledgeBaseStore } from '@/stores/knowledgeBase.js'
import TestRunResult from './TestRunResult.vue'

const props = defineProps({
  chainId: { type: String, default: null },
})
defineEmits(['close'])

const kbStore = useKnowledgeBaseStore()

// ── 数据源选择 ──
const dataSource = ref('samples')
const selectedArr = ref([])
const sampleSearch = ref('')
const customJson = ref('')
const jsonError = ref('')
const running = ref(false)
const results = ref([])
const runError = ref('')

// ── 执行队列（支持拖拽排序） ──
let uidCounter = 0
const executionQueue = ref([]) // { uid, id, title, severity, type: 'sample'|'custom', data? }
const dragOverIdx = ref(-1)
const dragStartIdx = ref(-1)
const currentRunIdx = ref(0)

// ── 计算属性 ──
const kbSamples = computed(() => kbStore.samples)

const selectedIds = computed(() => new Set(selectedArr.value))

const filteredSamples = computed(() => {
  if (!sampleSearch.value) return kbSamples.value
  const q = sampleSearch.value.toLowerCase()
  return kbSamples.value.filter(
    (s) =>
      s.title.toLowerCase().includes(q) ||
      s.category.toLowerCase().includes(q) ||
      (s.tags || []).some((t) => t.toLowerCase().includes(q))
  )
})

/** 基于执行队列判断是否可以运行 */
const canRun = computed(() => {
  if (!props.chainId) return false
  return executionQueue.value.length > 0
})

const passCount = computed(() => results.value.filter((r) => r.success).length)
const failCount = computed(() => results.value.filter((r) => !r.success).length)
const hasCritical = computed(() => results.value.some((r) => r.final_severity === 'CRITICAL'))
const totalDurationMs = computed(() => results.value.reduce((sum, r) => sum + (r.duration_ms || 0), 0))
const progressPercent = computed(() => executionQueue.value.length > 1 ? ((currentRunIdx.value + 1) / executionQueue.value.length * 100) : 100)
const currentRunItem = computed(() => executionQueue.value[currentRunIdx.value] || null)

watch(customJson, () => {
  jsonError.value = ''
  if (customJson.value.trim()) {
    try {
      JSON.parse(customJson.value)
    } catch (e) {
      jsonError.value = 'JSON 格式错误: ' + e.message
    }
  }
})

onMounted(async () => {
  if (kbStore.samples.length === 0) {
    await kbStore.fetchSamples()
  }
  if (kbStore.categories.length === 0) {
    await kbStore.fetchCategories()
  }
})

// ── 队列操作 ──

function onSelectionChange(sampleId, event) {
  // checkbox 变化时自动添加到队列
  if (event.target.checked) {
    const sample = kbSamples.value.find(s => s.id === sampleId)
    if (sample && !executionQueue.value.find(item => item.id === sampleId)) {
      addToQueue(sample)
    }
  }
}

function addToQueue(sample) {
  executionQueue.value.push({
    uid: ++uidCounter,
    id: sample.id,
    title: sample.title,
    severity: sample.expected_severity || null,
    type: 'sample',
  })
}

function addCustomToQueue() {
  if (!customJson.value.trim() || jsonError.value) return
  let parsed
  try { parsed = JSON.parse(customJson.value) } catch { return }
  executionQueue.value.push({
    uid: ++uidCounter,
    id: null,
    title: `自定义数据 ${executionQueue.value.filter(i => i.type === 'custom').length + 1}`,
    severity: null,
    type: 'custom',
    data: parsed,
  })
}

function removeFromQueue(idx) {
  executionQueue.value.splice(idx, 1)
}

function clearQueue() {
  executionQueue.value = []
  selectedArr.value = []
}

// ── 拖拽排序 ──

function onDragStart(event, idx) {
  dragStartIdx.value = idx
  event.dataTransfer.effectAllowed = 'move'
  event.dataTransfer.setData('text/plain', String(idx))
}

function onDragOverItem(event, idx) {
  event.preventDefault()
  if (dragStartIdx.value !== idx && dragStartIdx.value !== -1) {
    dragOverIdx.value = idx
  }
}

function onDragOver(event) {
  event.preventDefault()
}

function onDrop(event) {
  const fromIdx = parseInt(event.dataTransfer.getData('text/plain'))
  if (isNaN(fromIdx)) return

  const toIdx = dragOverIdx.value
  if (toIdx !== -1 && fromIdx !== toIdx) {
    const items = [...executionQueue.value]
    const [moved] = items.splice(fromIdx, 1)
    items.splice(toIdx, 0, moved)
    executionQueue.value = items
  }

  onDragEnd()
}

function onDragEnd() {
  dragStartIdx.value = -1
  dragOverIdx.value = -1
}

// ── 执行测试（按队列顺序逐个执行） ──

async function executeTest() {
  if (!canRun.value || running.value) return
  running.value = true
  runError.value = ''
  results.value = []

  try {
    for (let i = 0; i < executionQueue.value.length; i++) {
      currentRunIdx.value = i
      const item = executionQueue.value[i]
      const body = {}
      if (item.type === 'sample') {
        body.sample_ids = [item.id]
        body.execution_order = i  // 告诉后端期望的执行序号
      } else {
        body.alert_data = item.data
        body.execution_order = i
      }

      const data = await testRunChain(props.chainId, body)
      const resultItems = data.results || []
      if (resultItems.length > 0) {
        // 注入执行序号信息到结果中
        resultItems[0]._run_order = i + 1
        resultItems[0]._run_total = executionQueue.value.length
        results.value.push(resultItems[0])
      }
    }
  } catch (e) {
    runError.value = e.message
  } finally {
    running.value = false
    currentRunIdx.value = 0
  }
}
</script>

<style scoped>
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.6);
  backdrop-filter: blur(6px);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 200;
}
.testrun-panel {
  background: #1e1e38;
  border: 1px solid #2d2d50;
  border-radius: 16px;
  width: 92%;
  max-width: 960px;
  max-height: 90vh;
  display: flex;
  flex-direction: column;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.5);
}
.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 20px;
  border-bottom: 1px solid #2d2d50;
  flex-shrink: 0;
}
.panel-header h3 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
}
.panel-close {
  background: none;
  border: none;
  color: #94a3b8;
  font-size: 20px;
  cursor: pointer;
  padding: 4px;
  line-height: 1;
}
.panel-close:hover {
  color: #e2e8f0;
}
.panel-empty {
  padding: 40px 20px;
  text-align: center;
  color: #6b7280;
}
.empty-icon {
  font-size: 36px;
  margin-bottom: 10px;
  opacity: 0.4;
}

/* ── 左右分栏 ── */
.panel-body-split {
  display: flex;
  gap: 12px;
  padding: 14px 20px;
  min-height: 280px;
  max-height: 360px;
  overflow: hidden;
  flex-shrink: 0;
}
.panel-left {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.panel-right {
  width: 300px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  border-left: 1px solid #2d2d50;
  padding-left: 12px;
}

.data-source-tabs {
  display: flex;
  gap: 4px;
  margin-bottom: 10px;
  flex-shrink: 0;
}
.tab-btn {
  flex: 1;
  padding: 7px 10px;
  border-radius: 8px;
  border: 1px solid #2d2d50;
  background: transparent;
  color: #94a3b8;
  font-size: 12px;
  cursor: pointer;
  transition: all 0.15s;
}
.tab-btn.active {
  background: rgba(99, 102, 241, 0.15);
  color: #e2e8f0;
  border-color: rgba(99, 102, 241, 0.3);
}
.tab-btn:hover:not(.active) {
  background: rgba(99, 102, 241, 0.06);
}

/* 样本选择器 */
.sample-selector {
  flex: 1;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
}
.selector-toolbar {
  margin-bottom: 6px;
  flex-shrink: 0;
}
.search-input {
  width: 100%;
}
.sample-list {
  display: flex;
  flex-direction: column;
  gap: 3px;
}
.sample-option {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 7px 8px;
  border-radius: 8px;
  cursor: pointer;
  transition: background 0.1s;
  position: relative;
}
.sample-option:hover {
  background: rgba(99, 102, 241, 0.06);
}
.sample-option.selected {
  background: rgba(99, 102, 241, 0.08);
  border: 1px solid rgba(99, 102, 241, 0.18);
}
.sample-check {
  flex-shrink: 0;
  width: 14px;
  height: 14px;
  accent-color: #6366f1;
}
.sample-info {
  flex: 1;
  min-width: 0;
}
.sample-title {
  display: block;
  font-size: 12px;
  color: #e2e8f0;
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.sample-meta {
  display: flex;
  gap: 6px;
  margin-top: 2px;
}
.cat-chip {
  font-size: 9px;
  padding: 1px 5px;
  border-radius: 4px;
  background: rgba(99, 102, 241, 0.1);
  color: #a5b4fc;
}
.sev-chip {
  font-size: 9px;
  padding: 1px 5px;
  border-radius: 4px;
  font-weight: 500;
}
.sev-low { background: rgba(16, 185, 129, 0.12); color: #34d399; }
.sev-medium { background: rgba(245, 158, 11, 0.12); color: #fbbf24; }
.sev-high { background: rgba(249, 115, 22, 0.12); color: #fb923c; }
.sev-critical { background: rgba(239, 68, 68, 0.12); color: #f87171; }

.btn-add-queue {
  flex-shrink: 0;
  width: 22px;
  height: 22px;
  border-radius: 6px;
  background: rgba(16, 185, 129, 0.12);
  color: #34d399;
  border: 1px solid rgba(16, 185, 129, 0.25);
  font-size: 12px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.15s;
  opacity: 0;
}
.sample-option.selected .btn-add-queue {
  opacity: 1;
}
.btn-add-queue:hover {
  background: rgba(16, 185, 129, 0.25);
  transform: scale(1.1);
}

.no-samples {
  text-align: center;
  padding: 20px;
  color: #6b7280;
  font-size: 12px;
}
.link {
  color: #6366f1;
  text-decoration: none;
}
.link:hover {
  text-decoration: underline;
}

/* 自定义 JSON */
.custom-json {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow-y: auto;
}
.json-input {
  min-height: 140px;
  font-size: 11px;
  flex: 1;
}
.form-error {
  font-size: 11px;
  color: #ef4444;
  margin-top: 4px;
}
.btn-add-custom {
  margin-top: 8px;
  padding: 7px 14px;
  border-radius: 8px;
  background: rgba(99, 102, 241, 0.12);
  color: #a5b4fc;
  border: 1px solid rgba(99, 102, 241, 0.25);
  font-size: 12px;
  cursor: pointer;
  transition: all 0.15s;
  align-self: flex-start;
}
.btn-add-custom:hover {
  background: rgba(99, 102, 241, 0.25);
}

/* ── 执行队列 ── */
.queue-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
  flex-shrink: 0;
}
.queue-title {
  font-size: 13px;
  font-weight: 600;
  color: #e2e8f0;
}
.queue-count {
  font-size: 11px;
  color: #6b7280;
  background: rgba(99, 102, 241, 0.1);
  padding: 1px 7px;
  border-radius: 10px;
}
.btn-clear-queue {
  margin-left: auto;
  background: none;
  border: none;
  color: #94a3b8;
  font-size: 11px;
  cursor: pointer;
  padding: 2px 6px;
  border-radius: 4px;
  transition: all 0.15s;
}
.btn-clear-queue:hover {
  color: #f87171;
  background: rgba(239, 68, 68, 0.08);
}

.execution-queue {
  flex: 1;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 3px;
  min-height: 80px;
}

.queue-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 7px 8px;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid transparent;
  cursor: grab;
  transition: all 0.15s;
  user-select: none;
}
.queue-item:hover {
  background: rgba(99, 102, 241, 0.06);
  border-color: rgba(99, 102, 241, 0.15);
}
.queue-item.drag-over {
  border: 1px dashed #6366f1;
  background: rgba(99, 102, 241, 0.1);
}
.queue-item:active {
  cursor: grabbing;
}

.queue-order {
  flex-shrink: 0;
  width: 20px;
  height: 20px;
  border-radius: 6px;
  background: rgba(99, 102, 241, 0.15);
  color: #a5b4fc;
  font-size: 11px;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
}
.queue-drag-handle {
  flex-shrink: 0;
  color: #4b5563;
  font-size: 13px;
  cursor: grab;
  opacity: 0.4;
}
.queue-item:hover .queue-drag-handle {
  opacity: 0.8;
}
.queue-item-info {
  flex: 1;
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 6px;
}
.queue-item-title {
  font-size: 12px;
  color: #cbd5e1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.sev-chip-mini {
  font-size: 8px;
  padding: 1px 4px;
  border-radius: 3px;
  font-weight: 500;
  flex-shrink: 0;
}
.sev-chip-mini.low { background: rgba(16, 185, 129, 0.12); color: #34d399; }
.sev-chip-mini.medium { background: rgba(245, 158, 11, 0.12); color: #fbbf24; }
.sev-chip-mini.high { background: rgba(249, 115, 22, 0.12); color: #fb923c; }
.sev-chip-mini.critical { background: rgba(239, 68, 68, 0.12); color: #f87171; }

.queue-remove {
  flex-shrink: 0;
  background: none;
  border: none;
  color: #6b7280;
  font-size: 14px;
  cursor: pointer;
  padding: 2px 4px;
  border-radius: 4px;
  opacity: 0;
  transition: all 0.15s;
}
.queue-item:hover .queue-remove {
  opacity: 1;
}
.queue-remove:hover {
  color: #f87171;
  background: rgba(239, 68, 68, 0.1);
}

.queue-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  text-align: center;
  color: #4b5563;
  font-size: 12px;
  padding: 30px 10px;
  line-height: 1.6;
  border: 1px dashed #2d2d50;
  border-radius: 8px;
}

/* ── 执行按钮区 ── */
.panel-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 20px;
  border-top: 1px solid #2d2d50;
  flex-shrink: 0;
}
.run-info {
  font-size: 12px;
  color: #6b7280;
}
.btn {
  padding: 8px 18px;
  border-radius: 8px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  border: none;
  transition: all 0.15s;
}
.btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.btn-run {
  background: linear-gradient(135deg, #10b981, #059669);
  color: white;
}
.btn-run:hover:not(:disabled) {
  background: linear-gradient(135deg, #059669, #047857);
}

/* ── 进度条 ── */
.run-progress {
  padding: 6px 20px;
  display: flex;
  align-items: center;
  gap: 12px;
  border-bottom: 1px solid #2d2d50;
  flex-shrink: 0;
}
.progress-bar {
  flex: 1;
  height: 4px;
  background: #2d2d50;
  border-radius: 2px;
  overflow: hidden;
}
.progress-fill {
  height: 100%;
  background: linear-gradient(90deg, #6366f1, #8b5cf6);
  border-radius: 2px;
  transition: width 0.3s ease;
}
.progress-text {
  font-size: 11px;
  color: #a5b4fc;
  white-space: nowrap;
  max-width: 220px;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* ── 结果区域 ── */
.has-critical {
  border: 1px solid rgba(200, 0, 0, 0.6);
  border-radius: 8px;
  animation: globalDangerPulse 1.5s ease-in-out infinite;
}
@keyframes globalDangerPulse {
  0%, 100% {
    border-color: rgba(180, 0, 0, 0.5);
    box-shadow: inset 0 0 12px rgba(180, 0, 0, 0.1);
  }
  50% {
    border-color: rgba(220, 20, 20, 0.9);
    box-shadow: inset 0 0 25px rgba(200, 0, 0, 0.25);
  }
}

.panel-results {
  flex: 1;
  overflow-y: auto;
  padding: 12px 20px;
}
.results-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 13px;
  font-weight: 600;
  color: #e2e8f0;
  margin-bottom: 10px;
}
.results-summary {
  display: flex;
  gap: 12px;
  font-size: 11px;
  align-items: center;
}
.summary-pass { color: #34d399; }
.summary-fail { color: #f87171; }
.summary-time { color: #6b7280; }

.run-error {
  padding: 10px 20px;
  font-size: 12px;
  color: #f87171;
  background: rgba(239, 68, 68, 0.08);
}
</style>
