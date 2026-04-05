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
        <!-- 选择测试数据 -->
        <div class="panel-body">
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
                <input type="checkbox" :value="s.id" v-model="selectedArr" class="sample-check" />
                <div class="sample-info">
                  <span class="sample-title">{{ s.title }}</span>
                  <span class="sample-meta">
                    <span class="cat-chip">{{ kbStore.getCategoryLabel(s.category) }}</span>
                    <span v-if="s.expected_severity" class="sev-chip" :class="'sev-' + s.expected_severity.toLowerCase()">
                      {{ s.expected_severity }}
                    </span>
                  </span>
                </div>
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
              rows="10"
              placeholder='{"chain_id": 1, "tx_hash": "0x...", "gas_price": 50000000000, "gas_used": 210000, "to_address": "0x...", "input_data": "0x...", "value": "1000000000000000000"}'
            ></textarea>
            <div v-if="jsonError" class="form-error">{{ jsonError }}</div>
          </div>
        </div>

        <!-- 执行按钮 -->
        <div class="panel-actions">
          <span class="run-info">
            <template v-if="dataSource === 'samples'">
              已选择 {{ selectedArr.length }} 个样本
            </template>
            <template v-else>
              使用自定义数据
            </template>
          </span>
          <button
            class="btn btn-run"
            :disabled="!canRun || running"
            @click="executeTest"
          >
            {{ running ? '执行中...' : '&#9654; 执行测试' }}
          </button>
        </div>

        <!-- 结果区域 -->
        <div v-if="results.length" class="panel-results">
          <div class="results-header">
            <span>测试结果</span>
            <span class="results-summary">
              <span class="summary-pass">&#10003; {{ passCount }}</span>
              <span class="summary-fail">&#10007; {{ failCount }}</span>
            </span>
          </div>
          <div class="results-list">
            <TestRunResult
              v-for="(r, i) in results"
              :key="i"
              :result="r"
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

const dataSource = ref('samples')
const selectedArr = ref([])
const sampleSearch = ref('')
const customJson = ref('')
const jsonError = ref('')
const running = ref(false)
const results = ref([])
const runError = ref('')

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

const canRun = computed(() => {
  if (!props.chainId) return false
  if (dataSource.value === 'samples') return selectedArr.value.length > 0
  if (dataSource.value === 'custom') {
    if (!customJson.value.trim()) return false
    try {
      JSON.parse(customJson.value)
      return true
    } catch {
      return false
    }
  }
  return false
})

const passCount = computed(() => results.value.filter((r) => r.success).length)
const failCount = computed(() => results.value.filter((r) => !r.success).length)

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

async function executeTest() {
  if (!canRun.value || running.value) return
  running.value = true
  runError.value = ''
  results.value = []

  try {
    const body = {}
    if (dataSource.value === 'samples') {
      body.sample_ids = selectedArr.value
    } else {
      body.alert_data = JSON.parse(customJson.value)
    }

    const data = await testRunChain(props.chainId, body)
    results.value = data.results || []
  } catch (e) {
    runError.value = e.message
  } finally {
    running.value = false
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
  width: 90%;
  max-width: 680px;
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
.panel-body {
  padding: 16px 20px;
  overflow-y: auto;
  flex-shrink: 0;
}
.data-source-tabs {
  display: flex;
  gap: 4px;
  margin-bottom: 12px;
}
.tab-btn {
  flex: 1;
  padding: 8px 12px;
  border-radius: 8px;
  border: 1px solid #2d2d50;
  background: transparent;
  color: #94a3b8;
  font-size: 13px;
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
  max-height: 240px;
  overflow-y: auto;
}
.selector-toolbar {
  margin-bottom: 8px;
}
.search-input {
  width: 100%;
}
.sample-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.sample-option {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 10px;
  border-radius: 8px;
  cursor: pointer;
  transition: background 0.1s;
}
.sample-option:hover {
  background: rgba(99, 102, 241, 0.06);
}
.sample-option.selected {
  background: rgba(99, 102, 241, 0.1);
  border: 1px solid rgba(99, 102, 241, 0.2);
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
  font-size: 13px;
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
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 4px;
  background: rgba(99, 102, 241, 0.1);
  color: #a5b4fc;
}
.sev-chip {
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 4px;
  font-weight: 500;
}
.sev-low { background: rgba(16, 185, 129, 0.12); color: #34d399; }
.sev-medium { background: rgba(245, 158, 11, 0.12); color: #fbbf24; }
.sev-high { background: rgba(249, 115, 22, 0.12); color: #fb923c; }
.sev-critical { background: rgba(239, 68, 68, 0.12); color: #f87171; }
.no-samples {
  text-align: center;
  padding: 24px;
  color: #6b7280;
  font-size: 13px;
}
.link {
  color: #6366f1;
  text-decoration: none;
}
.link:hover {
  text-decoration: underline;
}

/* 自定义 JSON */
.json-input {
  min-height: 160px;
  font-size: 12px;
}
.form-error {
  font-size: 11px;
  color: #ef4444;
  margin-top: 4px;
}

/* 执行按钮 */
.panel-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 20px;
  border-top: 1px solid #2d2d50;
  border-bottom: 1px solid #2d2d50;
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
  background: #10b981;
  color: white;
}
.btn-run:hover:not(:disabled) {
  background: #059669;
}

/* 结果 */
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
  font-size: 12px;
}
.summary-pass { color: #34d399; }
.summary-fail { color: #f87171; }

.run-error {
  padding: 10px 20px;
  font-size: 12px;
  color: #f87171;
  background: rgba(239, 68, 68, 0.08);
}
</style>
