<template>
  <div class="python-editor-wrapper">
    <div class="editor-toolbar">
      <span class="toolbar-hint">
        <span class="hint-key">result</span> = 布尔值
        <span class="hint-sep">|</span>
        <span class="hint-key">score</span> = 0-100
        <span class="hint-sep">|</span>
        <span class="hint-key">labels</span> = ["TAG"]
      </span>
      <div class="toolbar-actions">
        <button class="toolbar-btn" @click="resetToDefault" title="恢复示例代码">&#8634; 示例</button>
      </div>
    </div>
    <div ref="editorRef" class="editor-container" :class="{ 'has-error': hasError }"></div>
    <div v-if="hasError" class="editor-error">
      &#9888; {{ errorMessage }}
    </div>
    <div class="editor-hints">
      <span class="hint-title">可用变量：</span>
      <code>passed</code> 布尔列表 &nbsp;
      <code>scores</code> 分数列表 &nbsp;
      <code>ctx</code> 上下文字典 &nbsp;
      <code>inputs</code> 上游输出列表
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount, watch, shallowRef } from 'vue'
import { EditorView, keymap, lineNumbers, highlightActiveLineGutter, highlightSpecialChars, drawSelection, dropCursor, rectangularSelection, crosshairCursor, highlightActiveLine } from '@codemirror/view'
import { EditorState, Compartment } from '@codemirror/state'
import { defaultKeymap, history, historyKeymap, indentWithTab } from '@codemirror/commands'
import { syntaxHighlighting, indentOnInput, bracketMatching, foldGutter, foldKeymap } from '@codemirror/language'
import { python } from '@codemirror/lang-python'
import { oneDark } from '@codemirror/theme-one-dark'
import { closeBrackets, closeBracketsKeymap } from '@codemirror/autocomplete'

const props = defineProps({
  modelValue: { type: String, default: '' },
  placeholder: { type: String, default: '# Python 表达式\nresult = True\nscore = 75' },
})

const emit = defineEmits(['update:modelValue'])

const editorRef = ref(null)
const editorView = shallowRef(null)
const hasError = ref(false)
const errorMessage = ref('')
const readOnlyCompartment = new Compartment()

const DEFAULT_CODE = `# Python 表达式节点
# 设置 result = True/False 控制通过/失败
# 设置 score = 0-100（可选，默认使用上游平均分）
# 设置 labels = ["TAG1", "TAG2"]（可选）

# 示例：AND 逻辑
# result = all(passed)

# 示例：阈值比较
# result = scores[0] >= 50

# 示例：结合上下文
# if ctx.get("upgraded_contracts"):
#     result = any(passed)
#     score = 80
#     labels = ["UPGRADE_CORRELATED"]
# else:
#     result = False
`

function buildExtensions(readOnly = false) {
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
    syntaxHighlighting(syntaxHighlighting.defaultConfig, { fallback: true }),
    bracketMatching(),
    closeBrackets(),
    rectangularSelection(),
    crosshairCursor(),
    highlightActiveLine(),
    keymap.of([
      ...closeBracketsKeymap,
      ...defaultKeymap,
      ...historyKeymap,
      ...foldKeymap,
      indentWithTab,
    ]),
    python(),
    oneDark,
    EditorView.lineWrapping,
    EditorView.theme({
      '&': {
        height: '220px',
        fontSize: '13px',
        fontFamily: "'JetBrains Mono', 'Fira Code', 'Cascadia Code', 'Consolas', monospace",
      },
      '.cm-scroller': { overflow: 'auto' },
      '.cm-content': { padding: '8px 0' },
      '.cm-gutters': { background: '#1a1a2e', borderRight: '1px solid #2d2d50', minWidth: '40px' },
      '.cm-lineNumbers .cm-gutterElement': { color: '#4b5563', paddingLeft: '8px', paddingRight: '8px' },
      '.cm-activeLine': { background: 'rgba(99, 102, 241, 0.06)' },
      '.cm-activeLineGutter': { background: 'rgba(99, 102, 241, 0.08)' },
      '.cm-cursor': { borderLeftColor: '#a5b4fc' },
      '&.cm-focused .cm-selectionBackground, ::selection': { background: 'rgba(99, 102, 241, 0.2)' },
      '.cm-placeholder': { color: '#4b5563', fontStyle: 'italic' },
    }),
    EditorView.updateListener.of((update) => {
      if (update.docChanged) {
        const newValue = update.state.doc.toString()
        emit('update:modelValue', newValue)
        validateCode(newValue)
      }
    }),
  ]
  return base
}

function validateCode(code) {
  hasError.value = false
  errorMessage.value = ''
  if (!code.trim()) return
  try {
    compile(code, '<string>')
  } catch (e) {
    hasError.value = true
    errorMessage.value = e.message
  }
}

onMounted(() => {
  const startDoc = props.modelValue || props.placeholder
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
  }
})

function resetToDefault() {
  if (!editorView.value) return
  const current = editorView.value.state.doc.toString()
  editorView.value.dispatch({
    changes: { from: 0, to: current.length, insert: DEFAULT_CODE },
  })
  emit('update:modelValue', DEFAULT_CODE)
  hasError.value = false
  errorMessage.value = ''
}
</script>

<style scoped>
.python-editor-wrapper {
  border: 1px solid #2d2d50;
  border-radius: 10px;
  overflow: hidden;
  background: #1a1a2e;
  transition: border-color 0.15s;
}
.python-editor-wrapper:focus-within {
  border-color: rgba(99, 102, 241, 0.5);
}
.python-editor-wrapper.has-error {
  border-color: rgba(239, 68, 68, 0.5);
}
.editor-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 5px 12px;
  background: #16162a;
  border-bottom: 1px solid #2d2d50;
}
.toolbar-hint {
  font-size: 11px;
  color: #6b7280;
}
.hint-key {
  font-family: 'JetBrains Mono', 'Fira Code', monospace;
  color: #a5b4fc;
  background: rgba(99, 102, 241, 0.1);
  padding: 0 4px;
  border-radius: 3px;
  font-size: 10px;
}
.hint-sep {
  margin: 0 6px;
  color: #374151;
}
.toolbar-actions {
  display: flex;
  gap: 6px;
}
.toolbar-btn {
  background: none;
  border: 1px solid #2d2d50;
  color: #94a3b8;
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 5px;
  cursor: pointer;
  transition: all 0.15s;
}
.toolbar-btn:hover {
  background: rgba(99, 102, 241, 0.1);
  color: #e2e8f0;
  border-color: rgba(99, 102, 241, 0.3);
}
.editor-container {
  height: 220px;
  overflow: hidden;
}
.editor-error {
  padding: 4px 12px;
  font-size: 11px;
  color: #f87171;
  background: rgba(239, 68, 68, 0.08);
  border-top: 1px solid rgba(239, 68, 68, 0.15);
}
.editor-hints {
  padding: 4px 12px;
  font-size: 10px;
  color: #4b5563;
  background: #16162a;
  border-top: 1px solid #2d2d50;
  line-height: 1.6;
}
.hint-title {
  color: #6b7280;
  margin-right: 4px;
}
.editor-hints code {
  background: rgba(99, 102, 241, 0.08);
  color: #a5b4fc;
  padding: 0 3px;
  border-radius: 3px;
  font-family: 'JetBrains Mono', 'Fira Code', monospace;
}
</style>
