<template>
  <div class="modal-overlay" @click.self="$emit('close')">
    <div class="modal-dialog kb-form-dialog">
      <div class="modal-header">
        <h3>{{ isEdit ? '编辑样本' : '新建样本' }}</h3>
        <button class="modal-close" @click="$emit('close')">&times;</button>
      </div>
      <div class="modal-body">
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
          <label>
            告警数据 (JSON) <span class="required">*</span>
          </label>
          <textarea
            v-model="alertDataStr"
            class="form-textarea"
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
      </div>

      <div class="modal-footer">
        <button class="btn btn-ghost" @click="$emit('close')">取消</button>
        <button class="btn btn-primary" :disabled="!canSubmit || submitting" @click="submit">
          {{ submitting ? '保存中...' : (isEdit ? '更新' : '创建') }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import { useKnowledgeBaseStore } from '@/stores/knowledgeBase.js'

const props = defineProps({
  sample: { type: Object, default: null },
})
const emit = defineEmits(['close', 'saved'])

const store = useKnowledgeBaseStore()
const submitting = ref(false)
const jsonError = ref('')

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

const canSubmit = computed(() => form.value.title && form.value.tx_hash && !jsonError.value)

onMounted(() => {
  if (store.categories.length === 0) store.fetchCategories()
  if (props.sample) {
    form.value = { ...emptyForm(), ...props.sample }
    alertDataStr.value = JSON.stringify(props.sample.alert_data || {}, null, 2)
  }
})

async function submit() {
  validateJson()
  if (!canSubmit.value || submitting.value) return

  submitting.value = true
  try {
    const payload = {
      ...form.value,
      expected_severity: form.value.expected_severity || null,
      expected_min_score: form.value.expected_min_score || null,
    }
    if (isEdit.value) {
      await store.editSample(props.sample.id, payload)
    } else {
      await store.addSample(payload)
    }
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
</style>
