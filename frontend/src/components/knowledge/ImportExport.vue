<template>
  <div class="modal-overlay" @click.self="$emit('close')">
    <div class="modal-dialog import-dialog">
      <div class="modal-header">
        <h3>{{ mode === 'import' ? '导入样本' : '导出样本' }}</h3>
        <button class="modal-close" @click="$emit('close')">&times;</button>
      </div>
      <div class="modal-body">
        <template v-if="mode === 'import'">
          <p class="import-hint">
            粘贴 JSON 数组格式的样本数据，每个样本需包含 <code>title</code>、<code>tx_hash</code>、<code>alert_data</code> 字段。
          </p>
          <textarea
            v-model="jsonInput"
            class="form-textarea import-textarea"
            rows="12"
            placeholder='[{"title": "...", "tx_hash": "0x...", "alert_data": {...}}]'
          ></textarea>
          <div v-if="parseError" class="form-error">{{ parseError }}</div>
          <div v-if="parsedSamples.length" class="parse-info">
            已解析 {{ parsedSamples.length }} 条样本
          </div>
        </template>

        <template v-else>
          <div v-if="loading" class="export-loading">导出中...</div>
          <div v-else-if="exportData">
            <p class="export-info">共 {{ exportData.total }} 条样本数据</p>
            <textarea
              :value="JSON.stringify(exportData.samples, null, 2)"
              class="form-textarea export-textarea"
              rows="14"
              readonly
            ></textarea>
            <button class="btn btn-primary" style="margin-top: 8px" @click="copyExport">
              {{ copied ? '已复制!' : '复制到剪贴板' }}
            </button>
          </div>
        </template>
      </div>

      <div class="modal-footer" v-if="mode === 'import'">
        <button class="btn btn-ghost" @click="$emit('close')">取消</button>
        <button class="btn btn-primary" :disabled="!canImport || importing" @click="doImport">
          {{ importing ? '导入中...' : `导入 ${parsedSamples.length} 条` }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { importSamples, exportSamples } from '@/api/knowledgeBase.js'

const props = defineProps({
  mode: { type: String, required: true },
})
const emit = defineEmits(['close', 'imported'])

const jsonInput = ref('')
const parseError = ref('')
const importing = ref(false)
const loading = ref(false)
const exportData = ref(null)
const copied = ref(false)

const parsedSamples = computed(() => {
  parseError.value = ''
  if (!jsonInput.value.trim()) return []
  try {
    const data = JSON.parse(jsonInput.value)
    if (!Array.isArray(data)) {
      parseError.value = '数据必须是 JSON 数组格式'
      return []
    }
    return data
  } catch (e) {
    parseError.value = 'JSON 解析错误: ' + e.message
    return []
  }
})

const canImport = computed(() => parsedSamples.value.length > 0 && !parseError.value)

async function doImport() {
  if (!canImport.value || importing.value) return
  importing.value = true
  try {
    const result = await importSamples(parsedSamples.value)
    alert(`成功导入 ${result.imported} 条样本`)
    emit('imported')
  } catch (e) {
    alert('导入失败: ' + e.message)
  } finally {
    importing.value = false
  }
}

async function loadExport() {
  loading.value = true
  try {
    exportData.value = await exportSamples()
  } catch (e) {
    alert('导出失败: ' + e.message)
  } finally {
    loading.value = false
  }
}

function copyExport() {
  const text = JSON.stringify(exportData.value.samples, null, 2)
  navigator.clipboard.writeText(text).then(() => {
    copied.value = true
    setTimeout(() => { copied.value = false }, 2000)
  })
}

if (props.mode === 'export') {
  loadExport()
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
  max-height: 85vh;
  display: flex;
  flex-direction: column;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.5);
}
.import-dialog {
  max-width: 640px;
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
.import-hint {
  font-size: 13px;
  color: #94a3b8;
  margin: 0 0 12px;
  line-height: 1.6;
}
.import-hint code {
  font-size: 12px;
  color: #a5b4fc;
  background: rgba(99, 102, 241, 0.1);
  padding: 1px 4px;
  border-radius: 3px;
}
.import-textarea,
.export-textarea {
  font-size: 12px;
  min-height: 200px;
}
.form-error {
  font-size: 11px;
  color: #ef4444;
  margin-top: 6px;
}
.parse-info {
  font-size: 12px;
  color: #34d399;
  margin-top: 6px;
}
.export-loading,
.export-info {
  font-size: 13px;
  color: #94a3b8;
  text-align: center;
  padding: 20px;
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
