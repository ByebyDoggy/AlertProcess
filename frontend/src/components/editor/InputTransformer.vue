<template>
  <div class="transformer-section">
    <div class="transformer-header">
      <span class="transformer-icon">&#9881;</span>
      <span>输入转换</span>
      <div class="lang-switch">
        <button
          v-for="lang in languages"
          :key="lang.value"
          :class="['lang-btn', { active: currentLang === lang.value }]"
          @click.stop="switchLang(lang.value)"
          :title="lang.title"
        >{{ lang.label }}</button>
      </div>
    </div>

    <!-- Expression editor -->
    <div class="expr-editor-wrap">
      <textarea
        class="expr-editor"
        :value="localExpression"
        @input="onInput($event)"
        @keydown.tab.prevent="insertTab"
        placeholder="表达式：用 input 引用上游数据，返回变换后的对象"
        rows="4"
        spellcheck="false"
      ></textarea>
      <div class="expr-status" :class="statusClass">
        <span v-if="validating" class="status-loading">...</span>
        <span v-else-if="lastError" class="status-error" :title="lastError">&#10007;</span>
        <span v-else-if="localExpression.trim()" class="status-ok" title="语法正确">&#10003;</span>
      </div>
    </div>

    <!-- Preview output -->
    <div v-if="previewOutput !== null" class="preview-panel">
      <div class="preview-header">
        <span class="preview-icon">&#10148;</span>
        <span>预览输出</span>
      </div>
      <pre class="preview-json">{{ formatJson(previewOutput) }}</pre>
    </div>

    <!-- JS translated preview -->
    <div v-if="currentLang === 'javascript' && translatedExpr" class="translated-panel">
      <div class="translated-header">
        <span class="translated-icon">&#8634;</span>
        <span>Python 等价</span>
      </div>
      <pre class="translated-code">{{ translatedExpr }}</pre>
    </div>
  </div>
</template>

<script setup>
import { ref, watch, computed, onUnmounted } from 'vue'
import * as chainApi from '../../api/ruleChain.js'

const props = defineProps({
  modelValue: { type: Object, default: null },
  // modelValue: { expression: string, language: "python"|"javascript" } | null
  sampleInput: { type: Object, default: () => ({}) },
})

const emit = defineEmits(['update:modelValue'])

const languages = [
  { value: 'python', label: 'Py', title: 'Python 表达式' },
  { value: 'javascript', label: 'JS', title: 'JavaScript 表达式' },
]

const localExpression = ref(props.modelValue?.expression || '')
const currentLang = ref(props.modelValue?.language || 'python')
const lastError = ref(null)
const validating = ref(false)
const previewOutput = ref(null)
const translatedExpr = ref('')

let validateTimer = null
let previewTimer = null

// Sync from parent
watch(() => props.modelValue, (val) => {
  if (val) {
    if (val.expression !== undefined && val.expression !== localExpression.value) {
      localExpression.value = val.expression
      scheduleValidation()
    }
    if (val.language && val.language !== currentLang.value) {
      currentLang.value = val.language
      scheduleValidation()
    }
  } else {
    localExpression.value = ''
  }
}, { deep: true })

// Re-preview when sampleInput changes (e.g., upstream test result updated)
watch(() => props.sampleInput, () => {
  if (localExpression.value.trim()) {
    doPreview()
  }
})

// Debounced validation
function scheduleValidation() {
  clearTimeout(validateTimer)
  clearTimeout(previewTimer)
  // 不再立即清除旧预览 — 让新预览结果覆盖旧值
  validateTimer = setTimeout(doValidate, 400)
  previewTimer = setTimeout(doPreview, 800)
}

async function doValidate() {
  const expr = localExpression.value.trim()
  if (!expr) {
    lastError.value = null
    translatedExpr.value = ''
    previewOutput.value = null
    return
  }
  validating.value = true
  try {
    const res = await chainApi.validateTransformer(expr, currentLang.value)
    lastError.value = res.valid ? null : res.error
    translatedExpr.value = res.translated || ''
  } catch {
    lastError.value = '校验请求失败'
  } finally {
    validating.value = false
  }
}

async function doPreview() {
  const expr = localExpression.value.trim()
  if (!expr) {
    previewOutput.value = null
    return
  }
  // 不再因 lastError 阻断预览 — 验证错误不影响预览尝试
  try {
    const sampleInput = props.sampleInput
    const res = await chainApi.previewTransformer(expr, currentLang.value, sampleInput || {})
    if (res.success && res.output) {
      previewOutput.value = res.output
    } else {
      // API 返回失败时保留旧值（不清除），或设为null显示无结果
      previewOutput.value = res.output || null
    }
  } catch (err) {
    // 网络错误等 — 不覆盖已有的成功预览
    console.warn('[InputTransformer] preview failed:', err.message || err)
  }
}

function onInput(event) {
  localExpression.value = event.target.value
  emitUpdate()
  scheduleValidation()
}

function switchLang(lang) {
  currentLang.value = lang
  emitUpdate()
  scheduleValidation()
}

function emitUpdate() {
  const expr = localExpression.value.trim()
  if (!expr) {
    emit('update:modelValue', null)
  } else {
    emit('update:modelValue', {
      expression: localExpression.value,
      language: currentLang.value,
    })
  }
}

function insertTab(event) {
  const ta = event.target
  const start = ta.selectionStart
  const end = ta.selectionEnd
  localExpression.value = localExpression.value.substring(0, start) + '  ' + localExpression.value.substring(end)
  ta.selectionStart = ta.selectionEnd = start + 2
  emitUpdate()
}

function formatJson(obj) {
  try {
    return JSON.stringify(obj, null, 2)
  } catch {
    return String(obj)
  }
}

const statusClass = computed(() => {
  if (validating.value) return 'status-validating'
  if (lastError.value) return 'status-error'
  if (localExpression.value.trim()) return 'status-ok'
  return ''
})

onUnmounted(() => {
  clearTimeout(validateTimer)
  clearTimeout(previewTimer)
})
</script>

<style scoped>
.transformer-section {
  margin: 2px 6px 3px;
  padding: 4px 8px 6px;
  background: rgba(99, 102, 241, 0.03);
  border-top: 1px solid rgba(255,255,255,0.04);
  border-radius: 0 0 8px 8px;
}

.transformer-header {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 7.5px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.6px;
  padding: 3px 0 4px 1px;
  color: #818cf8;
}

.transformer-icon { font-size: 9px; }

.lang-switch {
  margin-left: auto;
  display: flex;
  gap: 2px;
}

.lang-btn {
  font-size: 7px;
  padding: 1px 5px;
  border-radius: 3px;
  border: 1px solid rgba(99,102,241,0.2);
  background: transparent;
  color: #6b7280;
  cursor: pointer;
  transition: all 0.12s;
  font-family: 'JetBrains Mono', monospace;
  font-weight: 600;
}

.lang-btn:hover { border-color: rgba(99,102,241,0.4); color: #818cf8; }
.lang-btn.active {
  background: rgba(99,102,241,0.15);
  border-color: rgba(99,102,241,0.5);
  color: #a5b4fc;
}

.expr-editor-wrap {
  position: relative;
  margin-top: 3px;
}

.expr-editor {
  width: 100%;
  min-height: 60px;
  max-height: 160px;
  padding: 5px 26px 5px 6px;
  background: rgba(15,15,26,0.8);
  border: 1px solid rgba(99,102,241,0.15);
  border-radius: 5px;
  color: #c4b5fd;
  font-family: 'JetBrains Mono', 'SF Mono', 'Cascadia Code', monospace;
  font-size: 8.5px;
  line-height: 1.5;
  resize: vertical;
  outline: none;
  transition: border-color 0.15s;
  box-sizing: border-box;
}

.expr-editor:focus {
  border-color: rgba(99,102,241,0.4);
  box-shadow: 0 0 0 1px rgba(99,102,241,0.1);
}

.expr-editor::placeholder {
  color: #4b5563;
  font-style: italic;
}

.expr-status {
  position: absolute;
  top: 4px;
  right: 5px;
  font-size: 9px;
  font-weight: bold;
}

.status-loading { color: #818cf8; }
.status-error .status-error { color: #f87171; }
.status-ok .status-ok { color: #4ade80; }

.status-validating { color: #818cf8; }
.status-error { color: #f87171; }
.status-ok { color: #4ade80; }

.preview-panel, .translated-panel {
  margin-top: 4px;
  border-radius: 4px;
  overflow: hidden;
}

.preview-header, .translated-header {
  display: flex;
  align-items: center;
  gap: 3px;
  font-size: 7px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  padding: 2px 5px;
  color: #6b7280;
}

.preview-header { background: rgba(52,211,153,0.06); color: #34d399; }
.translated-header { background: rgba(251,191,36,0.06); color: #fbbf24; }

.preview-icon, .translated-icon { font-size: 8px; }

.preview-json, .translated-code {
  margin: 0;
  padding: 4px 6px;
  background: rgba(15,15,26,0.6);
  font-family: 'JetBrains Mono', 'SF Mono', monospace;
  font-size: 7.5px;
  line-height: 1.45;
  color: #94a3b8;
  max-height: 100px;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-all;
}

.translated-code {
  color: #fbbf24;
  max-height: 60px;
}
</style>
