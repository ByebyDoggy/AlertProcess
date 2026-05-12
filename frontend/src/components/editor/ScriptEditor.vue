<template>
  <div class="script-editor-wrapper" :class="{ fullscreen: isFullscreen }">
    <!-- Toolbar -->
    <div class="editor-toolbar">
      <div class="toolbar-left">
        <span class="toolbar-title">Python 脚本编辑器</span>
        <button
          class="toolbar-btn"
          :class="{ active: showContextHelp }"
          @click="showContextHelp = !showContextHelp"
          title="显示/隐藏 API 参考"
        >
          <span class="btn-icon">&#9432;</span> API
        </button>
      </div>
      <div class="toolbar-right">
        <button
          class="toolbar-btn"
          @click="formatCode"
          title="格式化代码 (Ctrl+Shift+F)"
        >
          <span class="btn-icon">&#10021;</span> 格式化
        </button>
        <button
          class="toolbar-btn"
          :class="{ active: theme === 'dark' }"
          @click="toggleTheme"
          title="切换主题"
        >
          <span class="btn-icon">{{ theme === 'dark' ? '&#9790;' : '&#9788;' }}</span>
        </button>
        <button
          class="toolbar-btn"
          @click="toggleFullscreen"
          :title="isFullscreen ? '退出全屏 (Esc)' : '全屏 (F11)'"
        >
          <span class="btn-icon">{{ isFullscreen ? '&#10697;' : '&#10697;' }}</span>
        </button>
        <button
          class="toolbar-btn primary"
          @click="saveCode"
          title="保存 (Ctrl+S)"
          :disabled="!hasChanges"
        >
          <span class="btn-icon">&#10004;</span> 保存
        </button>
      </div>
    </div>

    <!-- Context Help Panel -->
    <transition name="slide-down">
      <div v-if="showContextHelp" class="context-help-panel">
        <div class="help-section">
          <div class="help-title">ScriptContext API</div>
          <div class="help-grid">
            <div class="help-item">
              <code class="help-code">ctx.alert_data</code>
              <span class="help-desc">原始告警数据字典</span>
            </div>
            <div class="help-item">
              <code class="help-code">ctx.node_outputs</code>
              <span class="help-desc">所有节点输出 (dict[str, NodeOutput])</span>
            </div>
            <div class="help-item">
              <code class="help-code">ctx.get_output(node_id)</code>
              <span class="help-desc">获取指定节点输出</span>
            </div>
            <div class="help-item">
              <code class="help-code">ctx.collected_labels</code>
              <span class="help-desc">聚合的标签列表</span>
            </div>
            <div class="help-item">
              <code class="help-code">ctx.final_severity</code>
              <span class="help-desc">最终严重级别 (CRITICAL/HIGH/MEDIUM/LOW)</span>
            </div>
            <div class="help-item">
              <code class="help-code">ctx.final_score</code>
              <span class="help-desc">最终评分 (0-100)</span>
            </div>
          </div>
        </div>
        <div class="help-section">
          <div class="help-title">TransactionContext 字段</div>
          <div class="help-grid">
            <div class="help-item">
              <code class="help-code">tx.chain_id</code>
              <span class="help-desc">区块链网络 ID (1=ETH, 56=BSC)</span>
            </div>
            <div class="help-item">
              <code class="help-code">tx.tx_hash</code>
              <span class="help-desc">交易哈希</span>
            </div>
            <div class="help-item">
              <code class="help-code">tx.from_address</code>
              <span class="help-desc">交易发起者地址</span>
            </div>
            <div class="help-item">
              <code class="help-code">tx.to_address</code>
              <span class="help-desc">交易目标地址</span>
            </div>
            <div class="help-item">
              <code class="help-code">tx.value</code>
              <span class="help-desc">转账金额 (wei)</span>
            </div>
            <div class="help-item">
              <code class="help-code">tx.gas_price</code>
              <span class="help-desc">Gas 价格 (wei)</span>
            </div>
            <div class="help-item">
              <code class="help-code">tx.logs</code>
              <span class="help-desc">Event Log 列表</span>
            </div>
            <div class="help-item">
              <code class="help-code">tx.extra</code>
              <span class="help-desc">扩展字段字典</span>
            </div>
          </div>
        </div>
      </div>
    </transition>

    <!-- Editor Container -->
    <div ref="editorRef" class="editor-container" :class="{ 'has-error': hasError }"></div>

    <!-- Error Display -->
    <transition name="fade">
      <div v-if="hasError" class="editor-error">
        <span class="error-icon">&#9888;</span>
        <span class="error-message">{{ errorMessage }}</span>
      </div>
    </transition>

    <!-- Status Bar -->
    <div class="editor-status-bar">
      <div class="status-left">
        <span class="status-item">
          <span class="status-label">行:</span>
          <span class="status-value">{{ cursorLine }}</span>
        </span>
        <span class="status-item">
          <span class="status-label">列:</span>
          <span class="status-value">{{ cursorCol }}</span>
        </span>
        <span class="status-item">
          <span class="status-label">字符:</span>
          <span class="status-value">{{ charCount }}</span>
        </span>
      </div>
      <div class="status-right">
        <span v-if="hasChanges" class="status-modified">● 未保存</span>
        <span class="status-item">Python</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount, watch, shallowRef, computed } from 'vue'
import { EditorView, keymap, lineNumbers, highlightActiveLineGutter, highlightSpecialChars, drawSelection, dropCursor, rectangularSelection, crosshairCursor, highlightActiveLine } from '@codemirror/view'
import { EditorState, Compartment } from '@codemirror/state'
import { defaultKeymap, history, historyKeymap, indentWithTab } from '@codemirror/commands'
import { syntaxHighlighting, indentOnInput, bracketMatching, foldGutter, foldKeymap, defaultHighlightStyle } from '@codemirror/language'
import { python } from '@codemirror/lang-python'
import { oneDark } from '@codemirror/theme-one-dark'
import { closeBrackets, closeBracketsKeymap, autocompletion, completionKeymap } from '@codemirror/autocomplete'

const props = defineProps({
  modelValue: { type: String, default: '' },
  placeholder: { type: String, default: '# 编写 Python 脚本\n# 可用变量: ctx (ExecutionContext), tx (TransactionContext)\n' },
  readonly: { type: Boolean, default: false },
})

const emit = defineEmits(['update:modelValue', 'save'])

// Editor state
const editorRef = ref(null)
const editorView = shallowRef(null)
const hasError = ref(false)
const errorMessage = ref('')
const theme = ref('dark')
const isFullscreen = ref(false)
const showContextHelp = ref(false)
const hasChanges = ref(false)
const initialValue = ref('')

// Cursor position
const cursorLine = ref(1)
const cursorCol = ref(1)
const charCount = computed(() => editorView.value?.state.doc.toString().length || 0)

// Compartments for dynamic reconfiguration
const themeCompartment = new Compartment()
const readOnlyCompartment = new Compartment()

// Custom autocompletion for ScriptContext API
function scriptContextCompletions(context) {
  const word = context.matchBefore(/\w*/)
  if (!word || (word.from === word.to && !context.explicit)) return null

  const completions = [
    // ExecutionContext
    { label: 'ctx', type: 'variable', info: 'ExecutionContext 实例' },
    { label: 'ctx.alert_data', type: 'property', info: '原始告警数据字典' },
    { label: 'ctx.node_outputs', type: 'property', info: '所有节点输出字典' },
    { label: 'ctx.get_output', type: 'method', info: '获取指定节点输出' },
    { label: 'ctx.collected_labels', type: 'property', info: '聚合的标签列表' },
    { label: 'ctx.final_severity', type: 'property', info: '最终严重级别' },
    { label: 'ctx.final_score', type: 'property', info: '最终评分 (0-100)' },
    { label: 'ctx.logs', type: 'property', info: '执行日志列表' },
    { label: 'ctx.errors', type: 'property', info: '错误列表' },
    { label: 'ctx.dry_run', type: 'property', info: '是否为测试运行模式' },

    // TransactionContext
    { label: 'tx', type: 'variable', info: 'TransactionContext 实例' },
    { label: 'tx.chain_id', type: 'property', info: '区块链网络 ID' },
    { label: 'tx.tx_hash', type: 'property', info: '交易哈希' },
    { label: 'tx.block_number', type: 'property', info: '区块号' },
    { label: 'tx.from_address', type: 'property', info: '交易发起者地址' },
    { label: 'tx.to_address', type: 'property', info: '交易目标地址' },
    { label: 'tx.value', type: 'property', info: '转账金额 (wei)' },
    { label: 'tx.gas_price', type: 'property', info: 'Gas 价格 (wei)' },
    { label: 'tx.gas_used', type: 'property', info: 'Gas 消耗量' },
    { label: 'tx.input_data', type: 'property', info: '交易 calldata' },
    { label: 'tx.timestamp', type: 'property', info: '交易时间戳' },
    { label: 'tx.logs', type: 'property', info: 'Event Log 列表' },
    { label: 'tx.extra', type: 'property', info: '扩展字段字典' },
    { label: 'tx.get_extra', type: 'method', info: '从 extra 获取字段' },
    { label: 'tx.set_extra', type: 'method', info: '向 extra 设置字段' },

    // Common Python keywords
    { label: 'result', type: 'variable', info: '返回结果变量' },
    { label: 'score', type: 'variable', info: '评分 (0-100)' },
    { label: 'passed', type: 'variable', info: '是否通过 (bool)' },
    { label: 'labels', type: 'variable', info: '标签列表' },
    { label: 'severity', type: 'variable', info: '严重级别' },
  ]

  return {
    from: word.from,
    options: completions,
  }
}

function buildExtensions() {
  const base = [
    lineNumbers(),
    highlightActiveLineGutter(),
    highlightSpecialChars(),
    history(),
    foldGutter(),
    drawSelection(),
    dropCursor(),
    EditorState.allowMultipleSelections.of(true),
    indentOnInput(),
    syntaxHighlighting(defaultHighlightStyle, { fallback: true }),
    bracketMatching(),
    closeBrackets(),
    rectangularSelection(),
    crosshairCursor(),
    highlightActiveLine(),
    autocompletion({
      override: [scriptContextCompletions],
      activateOnTyping: true,
    }),
    keymap.of([
      ...closeBracketsKeymap,
      ...defaultKeymap,
      ...historyKeymap,
      ...foldKeymap,
      ...completionKeymap,
      indentWithTab,
      { key: 'Ctrl-s', run: () => { saveCode(); return true } },
      { key: 'Ctrl-Shift-f', run: () => { formatCode(); return true } },
      { key: 'F11', run: () => { toggleFullscreen(); return true } },
      { key: 'Escape', run: () => { if (isFullscreen.value) { toggleFullscreen(); return true } return false } },
    ]),
    python(),
    themeCompartment.of(theme.value === 'dark' ? oneDark : []),
    readOnlyCompartment.of(EditorState.readOnly.of(props.readonly)),
    EditorView.lineWrapping,
    EditorView.theme({
      '&': {
        height: '100%',
        fontSize: '14px',
        fontFamily: "'JetBrains Mono', 'Fira Code', 'Cascadia Code', 'Consolas', monospace",
      },
      '.cm-scroller': { overflow: 'auto' },
      '.cm-content': { padding: '12px 0', minHeight: '100%' },
      '.cm-gutters': {
        background: theme.value === 'dark' ? '#1a1a2e' : '#f5f5f5',
        borderRight: `1px solid ${theme.value === 'dark' ? '#2d2d50' : '#e0e0e0'}`,
        minWidth: '50px'
      },
      '.cm-lineNumbers .cm-gutterElement': {
        color: theme.value === 'dark' ? '#6b7280' : '#9ca3af',
        paddingLeft: '12px',
        paddingRight: '12px'
      },
      '.cm-activeLine': { background: theme.value === 'dark' ? 'rgba(99, 102, 241, 0.06)' : 'rgba(99, 102, 241, 0.08)' },
      '.cm-activeLineGutter': { background: theme.value === 'dark' ? 'rgba(99, 102, 241, 0.08)' : 'rgba(99, 102, 241, 0.12)' },
      '.cm-cursor': { borderLeftColor: theme.value === 'dark' ? '#a5b4fc' : '#6366f1' },
      '&.cm-focused .cm-selectionBackground, ::selection': {
        background: theme.value === 'dark' ? 'rgba(99, 102, 241, 0.2)' : 'rgba(99, 102, 241, 0.15)'
      },
      '.cm-placeholder': { color: '#6b7280', fontStyle: 'italic' },
      '.cm-tooltip-autocomplete': {
        background: theme.value === 'dark' ? '#1e1e3f' : '#ffffff',
        border: `1px solid ${theme.value === 'dark' ? '#2d2d50' : '#e0e0e0'}`,
        borderRadius: '6px',
        boxShadow: '0 4px 12px rgba(0, 0, 0, 0.15)',
      },
      '.cm-tooltip-autocomplete ul li[aria-selected]': {
        background: theme.value === 'dark' ? 'rgba(99, 102, 241, 0.2)' : 'rgba(99, 102, 241, 0.1)',
      },
    }),
    EditorView.updateListener.of((update) => {
      if (update.docChanged) {
        const newValue = update.state.doc.toString()
        emit('update:modelValue', newValue)
        hasChanges.value = newValue !== initialValue.value
        validateCode(newValue)
      }
      if (update.selectionSet) {
        const pos = update.state.selection.main.head
        const line = update.state.doc.lineAt(pos)
        cursorLine.value = line.number
        cursorCol.value = pos - line.from + 1
      }
    }),
  ]
  return base
}

function validateCode(code) {
  hasError.value = false
  errorMessage.value = ''
  if (!code.trim()) return

  // Basic Python syntax validation (client-side)
  // Check for common syntax errors
  const lines = code.split('\n')
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i].trim()
    if (!line || line.startsWith('#')) continue

    // Check for unclosed strings
    const singleQuotes = (line.match(/'/g) || []).length
    const doubleQuotes = (line.match(/"/g) || []).length
    if (singleQuotes % 2 !== 0 || doubleQuotes % 2 !== 0) {
      hasError.value = true
      errorMessage.value = `第 ${i + 1} 行: 未闭合的引号`
      return
    }

    // Check for unmatched brackets
    const openBrackets = (line.match(/[\(\[\{]/g) || []).length
    const closeBrackets = (line.match(/[\)\]\}]/g) || []).length
    if (openBrackets !== closeBrackets) {
      hasError.value = true
      errorMessage.value = `第 ${i + 1} 行: 括号不匹配`
      return
    }
  }
}

function formatCode() {
  if (!editorView.value) return

  // Basic Python formatting (indentation normalization)
  const code = editorView.value.state.doc.toString()
  const lines = code.split('\n')
  let formatted = []
  let indentLevel = 0

  for (let line of lines) {
    const trimmed = line.trim()

    // Decrease indent for closing statements
    if (trimmed.startsWith('elif ') || trimmed.startsWith('else:') ||
        trimmed.startsWith('except') || trimmed.startsWith('finally:')) {
      indentLevel = Math.max(0, indentLevel - 1)
    }

    // Add formatted line
    if (trimmed) {
      formatted.push('    '.repeat(indentLevel) + trimmed)
    } else {
      formatted.push('')
    }

    // Increase indent after colon
    if (trimmed.endsWith(':')) {
      indentLevel++
    }

    // Decrease indent after dedent keywords
    if (trimmed.startsWith('return') || trimmed.startsWith('break') ||
        trimmed.startsWith('continue') || trimmed.startsWith('pass')) {
      // Don't change indent level, but next non-empty line might dedent
    }
  }

  const formattedCode = formatted.join('\n')
  const current = editorView.value.state.doc.toString()
  editorView.value.dispatch({
    changes: { from: 0, to: current.length, insert: formattedCode },
  })
}

function toggleTheme() {
  theme.value = theme.value === 'dark' ? 'light' : 'dark'
  if (editorView.value) {
    editorView.value.dispatch({
      effects: themeCompartment.reconfigure(theme.value === 'dark' ? oneDark : [])
    })
  }
}

function toggleFullscreen() {
  isFullscreen.value = !isFullscreen.value
}

function saveCode() {
  if (!editorView.value) return
  const code = editorView.value.state.doc.toString()
  initialValue.value = code
  hasChanges.value = false
  emit('save', code)
}

onMounted(() => {
  const startDoc = props.modelValue || props.placeholder
  initialValue.value = props.modelValue || ''

  const state = EditorState.create({
    doc: startDoc,
    extensions: buildExtensions(),
  })

  editorView.value = new EditorView({
    state,
    parent: editorRef.value,
  })

  if (props.modelValue) {
    validateCode(props.modelValue)
  }
})

onBeforeUnmount(() => {
  editorView.value?.destroy()
})

watch(() => props.modelValue, (newVal) => {
  if (!editorView.value) return
  const current = editorView.value.state.doc.toString()
  if (newVal !== current) {
    editorView.value.dispatch({
      changes: { from: 0, to: current.length, insert: newVal || '' },
    })
    initialValue.value = newVal || ''
    hasChanges.value = false
  }
})

watch(() => props.readonly, (newVal) => {
  if (!editorView.value) return
  editorView.value.dispatch({
    effects: readOnlyCompartment.reconfigure(EditorState.readOnly.of(newVal))
  })
})
</script>

<style scoped>
.script-editor-wrapper {
  display: flex;
  flex-direction: column;
  height: 100%;
  border: 1px solid #2d2d50;
  border-radius: 12px;
  overflow: hidden;
  background: #1a1a2e;
  transition: all 0.2s;
}

.script-editor-wrapper:focus-within {
  border-color: rgba(99, 102, 241, 0.5);
  box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.1);
}

.script-editor-wrapper.has-error {
  border-color: rgba(239, 68, 68, 0.5);
}

.script-editor-wrapper.fullscreen {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  z-index: 9999;
  border-radius: 0;
  margin: 0;
}

/* Toolbar */
.editor-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 16px;
  background: #16162a;
  border-bottom: 1px solid #2d2d50;
  flex-shrink: 0;
}

.toolbar-left,
.toolbar-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.toolbar-title {
  font-size: 13px;
  font-weight: 600;
  color: #e2e8f0;
  margin-right: 12px;
}

.toolbar-btn {
  display: flex;
  align-items: center;
  gap: 4px;
  background: none;
  border: 1px solid #2d2d50;
  color: #94a3b8;
  font-size: 12px;
  padding: 4px 10px;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.15s;
  font-family: inherit;
}

.toolbar-btn:hover:not(:disabled) {
  background: rgba(99, 102, 241, 0.1);
  color: #e2e8f0;
  border-color: rgba(99, 102, 241, 0.3);
}

.toolbar-btn.active {
  background: rgba(99, 102, 241, 0.15);
  color: #a5b4fc;
  border-color: rgba(99, 102, 241, 0.4);
}

.toolbar-btn.primary {
  background: #6366f1;
  color: white;
  border-color: #6366f1;
}

.toolbar-btn.primary:hover:not(:disabled) {
  background: #4f46e5;
  border-color: #4f46e5;
}

.toolbar-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.btn-icon {
  font-size: 14px;
}

/* Context Help Panel */
.context-help-panel {
  background: #16162a;
  border-bottom: 1px solid #2d2d50;
  padding: 12px 16px;
  max-height: 300px;
  overflow-y: auto;
  flex-shrink: 0;
}

.help-section {
  margin-bottom: 16px;
}

.help-section:last-child {
  margin-bottom: 0;
}

.help-title {
  font-size: 12px;
  font-weight: 600;
  color: #a5b4fc;
  margin-bottom: 8px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.help-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 8px;
}

.help-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
  background: rgba(99, 102, 241, 0.05);
  border: 1px solid rgba(99, 102, 241, 0.1);
  border-radius: 6px;
  transition: all 0.15s;
}

.help-item:hover {
  background: rgba(99, 102, 241, 0.1);
  border-color: rgba(99, 102, 241, 0.2);
}

.help-code {
  font-family: 'JetBrains Mono', 'Fira Code', monospace;
  font-size: 11px;
  color: #a5b4fc;
  background: rgba(99, 102, 241, 0.15);
  padding: 2px 6px;
  border-radius: 4px;
  white-space: nowrap;
  flex-shrink: 0;
}

.help-desc {
  font-size: 11px;
  color: #94a3b8;
  line-height: 1.4;
}

/* Editor Container */
.editor-container {
  flex: 1;
  overflow: hidden;
  min-height: 0;
}

/* Error Display */
.editor-error {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 16px;
  font-size: 12px;
  color: #f87171;
  background: rgba(239, 68, 68, 0.08);
  border-top: 1px solid rgba(239, 68, 68, 0.15);
  flex-shrink: 0;
}

.error-icon {
  font-size: 16px;
}

.error-message {
  flex: 1;
}

/* Status Bar */
.editor-status-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 4px 16px;
  background: #16162a;
  border-top: 1px solid #2d2d50;
  font-size: 11px;
  color: #6b7280;
  flex-shrink: 0;
}

.status-left,
.status-right {
  display: flex;
  align-items: center;
  gap: 16px;
}

.status-item {
  display: flex;
  align-items: center;
  gap: 4px;
}

.status-label {
  color: #6b7280;
}

.status-value {
  color: #94a3b8;
  font-family: 'JetBrains Mono', 'Fira Code', monospace;
}

.status-modified {
  color: #f59e0b;
  font-weight: 600;
}

/* Transitions */
.slide-down-enter-active,
.slide-down-leave-active {
  transition: all 0.2s ease;
  max-height: 300px;
}

.slide-down-enter-from,
.slide-down-leave-to {
  max-height: 0;
  opacity: 0;
  padding-top: 0;
  padding-bottom: 0;
}

.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.15s;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}

/* Scrollbar styling */
.context-help-panel::-webkit-scrollbar {
  width: 8px;
}

.context-help-panel::-webkit-scrollbar-track {
  background: #1a1a2e;
}

.context-help-panel::-webkit-scrollbar-thumb {
  background: #2d2d50;
  border-radius: 4px;
}

.context-help-panel::-webkit-scrollbar-thumb:hover {
  background: #3d3d60;
}
</style>
