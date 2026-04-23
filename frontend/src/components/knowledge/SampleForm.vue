<template>
  <div class="modal-overlay" @click.self="$emit('close')">
    <div class="modal-dialog kb-form-dialog">
      <div class="modal-header">
        <h3>{{ isEdit ? '编辑样本' : '新建样本' }}</h3>
        <button class="modal-close" @click="$emit('close')">&times;</button>
      </div>
      <div class="modal-body">

        <!-- ═══ 新建模式 Step 1: 简洁输入 ═══ -->
        <template v-if="!isEdit && !fetchedData">
          <div class="step-indicator">Step 1 / 2 — 输入交易信息</div>
          <div class="form-row">
            <div class="form-group flex-1">
              <label>交易哈希 (TxHash) <span class="required">*</span></label>
              <input
                v-model="form.tx_hash"
                class="form-input mono"
                placeholder="0xabc123... (64位十六进制)"
                @keyup.enter="fetchData"
              />
            </div>
            <div class="form-group" style="width: 140px">
              <label>链 ID <span class="required">*</span></label>
              <select v-model.number="form.chain_id" class="form-select">
                <option :value="1">Ethereum</option>
                <option :value="56">BSC</option>
                <option :value="137">Polygon</option>
                <option :value="42161">Arbitrum</option>
                <option :value="10">Optimism</option>
                <option :value="43114">Avalanche</option>
              </select>
            </div>
          </div>
          <div v-if="fetchError" class="form-error" style="margin-bottom: 12px">{{ fetchError }}</div>
          <div class="fetch-hint">
            输入交易哈希后，系统将自动从链上获取交易数据并解析为标准格式，无需手动输入 JSON。
          </div>
        </template>

        <!-- ═══ 新建模式 Step 2: 数据预览 + 补充信息 ═══ -->
        <template v-if="!isEdit && fetchedData">
          <div class="step-indicator">
            Step 2 / 2 — 确认数据
            <button class="btn btn-ghost btn-xs" @click="resetFetch">重新输入</button>
          </div>

          <div class="preview-card">
            <div class="preview-header">
              <span class="preview-title">{{ fetchedData.title }}</span>
              <a v-if="fetchedData.tx_explorer_url" :href="fetchedData.tx_explorer_url" target="_blank" class="explorer-link">
                区块浏览器 &rarr;
              </a>
            </div>
            <div class="preview-grid">
              <div class="preview-item">
                <span class="preview-label">链</span>
                <span class="preview-value">{{ chainName }}</span>
              </div>
              <div class="preview-item">
                <span class="preview-label">From</span>
                <span class="preview-value mono">{{ fetchedData.alert_data?.from_address || '-' }}</span>
              </div>
              <div class="preview-item">
                <span class="preview-label">To</span>
                <span class="preview-value mono">{{ fetchedData.alert_data?.to_address || 'Contract Create' }}</span>
              </div>
              <div class="preview-item">
                <span class="preview-label">Value</span>
                <span class="preview-value">{{ fetchedData.alert_data?.value_eth?.toFixed(4) || '0' }} ETH</span>
              </div>
              <div class="preview-item">
                <span class="preview-label">状态</span>
                <span class="preview-value" :class="fetchedData.alert_data?.status === 'success' ? 'status-ok' : 'status-fail'">
                  {{ fetchedData.alert_data?.status === 'success' ? '成功' : 'REVERTED' }}
                </span>
              </div>
              <div class="preview-item">
                <span class="preview-label">Transfer 数</span>
                <span class="preview-value">{{ fetchedData.alert_data?.transfers?.length || 0 }}</span>
              </div>
            </div>
          </div>

          <div class="form-row">
            <div class="form-group" style="width: 160px">
              <label>分类</label>
              <select v-model="form.category" class="form-select">
                <option v-for="cat in store.categories" :key="cat.value" :value="cat.value">
                  {{ cat.label }}
                </option>
              </select>
            </div>
            <div class="form-group flex-1">
              <label>标签 <span class="hint">（逗号分隔）</span></label>
              <input v-model="tagsInput" class="form-input" placeholder="闪电贷, Aave, DeFi" />
            </div>
          </div>

          <div class="form-group">
            <label>描述</label>
            <textarea v-model="form.description" class="form-textarea" rows="2" placeholder="样本描述（可选）"></textarea>
          </div>

          <details class="alert-data-details">
            <summary>查看完整链上数据 (alert_data)</summary>
            <pre class="alert-data-pre">{{ JSON.stringify(fetchedData.alert_data, null, 2) }}</pre>
          </details>

          <div class="form-section-title">预期结果（可选，用于测试验证）</div>
          <div class="form-row">
            <div class="form-group">
              <label>预期严重级别</label>
              <select v-model="form.expected_severity" class="form-select">
                <option value="">不限</option>
                <option value="LOW">LOW</option>
                <option value="MEDIUM">MEDIUM</option>
                <option value="HIGH">HIGH</option>
                <option value="CRITICAL">CRITICAL</option>
              </select>
            </div>
            <div class="form-group">
              <label>预期最低评分</label>
              <input v-model.number="form.expected_min_score" type="number" class="form-input" placeholder="如 80" />
            </div>
          </div>
          <div class="form-group">
            <label>预期标签 <span class="hint">（逗号分隔）</span></label>
            <input v-model="expectedLabelsInput" class="form-input" placeholder="LARGE_FLASH_LOAN_ATTACK, high_gas" />
          </div>
        </template>

        <!-- ═══ 编辑模式：保留完整表单 ═══ -->
        <template v-if="isEdit">
          <div class="form-row">
            <div class="form-group flex-1">
              <label>标题 <span class="required">*</span></label>
              <input v-model="form.title" class="form-input" placeholder="输入样本标题" />
            </div>
            <div class="form-group" style="width: 160px">
              <label>分类</label>
              <select v-model="form.category" class="form-select">
                <option v-for="cat in store.categories" :key="cat.value" :value="cat.value">
                  {{ cat.label }}
                </option>
              </select>
            </div>
          </div>
          <div class="form-group">
            <label>描述</label>
            <textarea v-model="form.description" class="form-textarea" rows="2" placeholder="样本描述（可选）"></textarea>
          </div>
          <div class="form-row">
            <div class="form-group flex-1">
              <label>交易哈希 <span class="required">*</span></label>
              <input v-model="form.tx_hash" class="form-input" placeholder="0x..." />
            </div>
            <div class="form-group" style="width: 100px">
              <label>链 ID</label>
              <input v-model.number="form.chain_id" type="number" class="form-input" />
            </div>
          </div>
          <div class="form-row">
            <div class="form-group flex-1">
              <label>攻击地址</label>
              <input v-model="form.attacked_address" class="form-input" placeholder="被攻击地址（可选）" />
            </div>
            <div class="form-group flex-1">
              <label>攻击者地址</label>
              <input v-model="form.exploiter_address" class="form-input" placeholder="攻击者地址（可选）" />
            </div>
          </div>
          <div class="form-group">
            <label>标签 <span class="hint">（逗号分隔）</span></label>
            <input v-model="tagsInput" class="form-input" placeholder="闪电贷, Aave, DeFi" />
          </div>
          <div class="form-group">
            <label>告警数据 (JSON) <span class="required">*</span></label>
            <textarea
              v-model="alertDataStr"
              class="form-textarea mono"
              rows="8"
              placeholder='{"chain_id": 1, "tx_hash": "0x...", ...}'
              @blur="validateJson"
            ></textarea>
            <div v-if="jsonError" class="form-error">{{ jsonError }}</div>
          </div>
          <div class="form-section-title">预期结果（可选，用于测试验证）</div>
          <div class="form-row">
            <div class="form-group">
              <label>预期严重级别</label>
              <select v-model="form.expected_severity" class="form-select">
                <option value="">不限</option>
                <option value="LOW">LOW</option>
                <option value="MEDIUM">MEDIUM</option>
                <option value="HIGH">HIGH</option>
                <option value="CRITICAL">CRITICAL</option>
              </select>
            </div>
            <div class="form-group">
              <label>预期最低评分</label>
              <input v-model.number="form.expected_min_score" type="number" class="form-input" placeholder="如 80" />
            </div>
          </div>
          <div class="form-group">
            <label>预期标签 <span class="hint">（逗号分隔）</span></label>
            <input v-model="expectedLabelsInput" class="form-input" placeholder="LARGE_FLASH_LOAN_ATTACK, high_gas" />
          </div>
        </template>

      </div>

      <div class="modal-footer">
        <button class="btn btn-ghost" @click="$emit('close')">取消</button>
        <!-- 新建 Step 1: 获取数据按钮 -->
        <button
          v-if="!isEdit && !fetchedData"
          class="btn btn-primary"
          :disabled="!form.tx_hash || fetching"
          @click="fetchData"
        >
          {{ fetching ? '获取中...' : '获取链上数据' }}
        </button>
        <!-- 新建 Step 2: 创建按钮 -->
        <button
          v-if="!isEdit && fetchedData"
          class="btn btn-primary"
          :disabled="submitting"
          @click="submitQuickCreate"
        >
          {{ submitting ? '创建中...' : '确认创建' }}
        </button>
        <!-- 编辑模式: 更新按钮 -->
        <button
          v-if="isEdit"
          class="btn btn-primary"
          :disabled="!canSubmitEdit || submitting"
          @click="submit"
        >
          {{ submitting ? '保存中...' : '更新' }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import { useKnowledgeBaseStore } from '@/stores/knowledgeBase.js'
import { fetchTxData, createSample } from '@/api/knowledgeBase.js'

const CHAIN_NAMES = { 1: 'Ethereum', 56: 'BSC', 137: 'Polygon', 42161: 'Arbitrum', 10: 'Optimism', 43114: 'Avalanche' }

const props = defineProps({
  sample: { type: Object, default: null },
})
const emit = defineEmits(['close', 'saved'])

const store = useKnowledgeBaseStore()
const submitting = ref(false)
const fetching = ref(false)
const fetchError = ref('')
const jsonError = ref('')
const fetchedData = ref(null)

const emptyForm = () => ({
  title: '',
  description: '',
  category: 'unknown',
  tags: [],
  chain_id: 1,
  tx_hash: '',
  attacked_address: '',
  exploiter_address: '',
  alert_data: {},
  expected_severity: '',
  expected_labels: [],
  expected_min_score: null,
  source: 'manual',
  tx_explorer_url: '',
})

const form = ref(emptyForm())
const isEdit = computed(() => !!props.sample?.id)

const chainName = computed(() => CHAIN_NAMES[form.value.chain_id] || `Chain-${form.value.chain_id}`)

const tagsInput = computed({
  get: () => (form.value.tags || []).join(', '),
  set: (v) => { form.value.tags = v ? v.split(/[,，]/).map(s => s.trim()).filter(Boolean) : [] },
})

const expectedLabelsInput = computed({
  get: () => (form.value.expected_labels || []).join(', '),
  set: (v) => { form.value.expected_labels = v ? v.split(/[,，]/).map(s => s.trim()).filter(Boolean) : [] },
})

const alertDataStr = ref('{}')
watch(alertDataStr, (val) => {
  try {
    form.value.alert_data = JSON.parse(val || '{}')
    jsonError.value = ''
  } catch {
    // jsonError will be shown on blur
  }
})

function validateJson() {
  try {
    form.value.alert_data = JSON.parse(alertDataStr.value || '{}')
    jsonError.value = ''
  } catch (e) {
    jsonError.value = 'JSON 格式不正确: ' + e.message
  }
}

const canSubmitEdit = computed(() => form.value.title && form.value.tx_hash && !jsonError.value)

onMounted(() => {
  if (store.categories.length === 0) store.fetchCategories()
  if (props.sample) {
    form.value = { ...emptyForm(), ...props.sample }
    alertDataStr.value = JSON.stringify(props.sample.alert_data || {}, null, 2)
  }
})

// ── 新建模式: Step 1 → Step 2 ──

async function fetchData() {
  if (!form.value.tx_hash) return
  fetching.value = true
  fetchError.value = ''
  try {
    const result = await fetchTxData(form.value.chain_id, form.value.tx_hash)
    fetchedData.value = result
    // 将推断的地址填充到 form
    form.value.attacked_address = result.attacked_address || ''
    form.value.exploiter_address = result.exploiter_address || ''
    form.value.tx_explorer_url = result.tx_explorer_url || ''
    form.value.title = result.title || ''
  } catch (e) {
    fetchError.value = '获取链上数据失败: ' + (e.message || '未知错误')
  } finally {
    fetching.value = false
  }
}

function resetFetch() {
  fetchedData.value = null
  fetchError.value = ''
  form.value = emptyForm()
}

// ── 新建模式: Step 2 → 创建 ──
// 复用 Step 1 已获取的 fetchedData，直接走 createSample CRUD 端点，
// 避免后端重复调用链上 RPC（RPC 调用可能不稳定导致第二次失败）

async function submitQuickCreate() {
  if (submitting.value || !fetchedData.value) return
  submitting.value = true
  try {
    // 深拷贝，防止 Vue 响应式或后续修改影响原始数据
    const alertData = JSON.parse(JSON.stringify(fetchedData.value.alert_data))
    const payload = {
      title: form.value.title || fetchedData.value.title,
      description: form.value.description || null,
      category: form.value.category,
      tags: [...form.value.tags],
      chain_id: fetchedData.value.chain_id,
      tx_hash: fetchedData.value.tx_hash,
      attacked_address: form.value.attacked_address || null,
      exploiter_address: form.value.exploiter_address || null,
      alert_data: alertData,
      expected_severity: form.value.expected_severity || null,
      expected_labels: [...form.value.expected_labels],
      expected_min_score: form.value.expected_min_score || null,
      source: 'auto_fetch',
      tx_explorer_url: fetchedData.value.tx_explorer_url || null,
    }
    await createSample(payload)
    emit('saved')
  } catch (e) {
    alert('创建失败: ' + (e.message || '未知错误'))
  } finally {
    submitting.value = false
  }
}

// ── 编辑模式: 更新 ──

async function submit() {
  validateJson()
  if (!canSubmitEdit.value || submitting.value) return

  submitting.value = true
  try {
    const payload = {
      ...form.value,
      expected_severity: form.value.expected_severity || null,
      expected_min_score: form.value.expected_min_score || null,
    }
    await store.editSample(props.sample.id, payload)
    emit('saved')
  } catch (e) {
    alert('保存失败: ' + e.message)
  } finally {
    submitting.value = false
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
.modal-dialog {
  background: #1e1e38;
  border: 1px solid #2d2d50;
  border-radius: 16px;
  width: 90%;
  max-width: 720px;
  max-height: 85vh;
  display: flex;
  flex-direction: column;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.5);
}
.kb-form-dialog {
  max-width: 720px;
}
.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px;
  border-bottom: 1px solid #2d2d50;
}
.modal-header h3 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
}
.modal-close {
  background: none;
  border: none;
  color: #94a3b8;
  font-size: 20px;
  cursor: pointer;
  padding: 4px;
  line-height: 1;
}
.modal-close:hover {
  color: #e2e8f0;
}
.modal-body {
  padding: 20px;
  overflow-y: auto;
  flex: 1;
}
.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding: 12px 20px;
  border-top: 1px solid #2d2d50;
}
.form-group {
  margin-bottom: 14px;
}
.form-group label {
  display: block;
  font-size: 12px;
  color: #94a3b8;
  margin-bottom: 4px;
  font-weight: 500;
}
.required {
  color: #ef4444;
}
.hint {
  color: #6b7280;
  font-weight: 400;
}
.form-row {
  display: flex;
  gap: 12px;
}
.flex-1 {
  flex: 1;
}
.form-section-title {
  font-size: 13px;
  font-weight: 600;
  color: #a5b4fc;
  margin: 16px 0 10px;
  padding-bottom: 6px;
  border-bottom: 1px solid #2d2d50;
}
.form-error {
  font-size: 11px;
  color: #ef4444;
  margin-top: 4px;
}
.btn {
  padding: 8px 16px;
  border-radius: 8px;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  border: none;
  transition: all 0.15s;
}
.btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.btn-ghost {
  background: transparent;
  color: #94a3b8;
  border: 1px solid #2d2d50;
}
.btn-ghost:hover:not(:disabled) {
  background: rgba(99, 102, 241, 0.08);
  color: #e2e8f0;
}
.btn-primary {
  background: #6366f1;
  color: white;
}
.btn-primary:hover:not(:disabled) {
  background: #4f46e5;
}
.btn-xs {
  padding: 4px 10px;
  font-size: 11px;
  margin-left: 12px;
  vertical-align: middle;
}
.mono {
  font-family: 'JetBrains Mono', 'Fira Code', 'Consolas', monospace;
  font-size: 12px;
}

/* ── Step indicator ── */
.step-indicator {
  font-size: 13px;
  font-weight: 600;
  color: #a5b4fc;
  margin-bottom: 16px;
  padding-bottom: 8px;
  border-bottom: 1px solid #2d2d50;
}

/* ── Fetch hint ── */
.fetch-hint {
  font-size: 12px;
  color: #6b7280;
  margin-top: 8px;
  padding: 10px 12px;
  background: rgba(99, 102, 241, 0.06);
  border-radius: 8px;
  border: 1px dashed #3b3b5c;
  line-height: 1.5;
}

/* ── Preview card ── */
.preview-card {
  background: #16162a;
  border: 1px solid #2d2d50;
  border-radius: 12px;
  padding: 14px 16px;
  margin-bottom: 16px;
}
.preview-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}
.preview-title {
  font-size: 14px;
  font-weight: 600;
  color: #e2e8f0;
}
.explorer-link {
  font-size: 12px;
  color: #818cf8;
  text-decoration: none;
}
.explorer-link:hover {
  color: #a5b4fc;
  text-decoration: underline;
}
.preview-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px 16px;
}
.preview-item {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.preview-label {
  font-size: 11px;
  color: #6b7280;
  font-weight: 500;
}
.preview-value {
  font-size: 12px;
  color: #cbd5e1;
  word-break: break-all;
}
.status-ok { color: #34d399; }
.status-fail { color: #f87171; font-weight: 600; }

/* ── Alert data details ── */
.alert-data-details {
  margin-bottom: 14px;
}
.alert-data-details summary {
  font-size: 12px;
  color: #818cf8;
  cursor: pointer;
  margin-bottom: 8px;
}
.alert-data-details summary:hover {
  color: #a5b4fc;
}
.alert-data-pre {
  background: #0f0f1f;
  border: 1px solid #2d2d50;
  border-radius: 8px;
  padding: 12px;
  font-size: 11px;
  color: #94a3b8;
  max-height: 200px;
  overflow-y: auto;
  margin: 0;
  font-family: 'JetBrains Mono', 'Fira Code', 'Consolas', monospace;
}
</style>
