<template>
  <Teleport to="body">
    <div v-if="visible" class="expr-overlay" :style="overlayStyle" @click.stop>
      <div class="expr-selector">
        <!-- Header -->
        <div class="expr-header">
          <div class="expr-title">&#9998; 连线字段表达式</div>
          <button class="expr-close-btn" @click="$emit('close')">&times;</button>
        </div>

        <!-- Body -->
        <div class="expr-body">
          <!-- Expression input -->
          <div class="expr-input-wrap">
            <span class="expr-prefix">{{ '{' }}{ ' }}</span>
            <input
              ref="inputRef"
              class="expr-input"
              type="text"
              v-model="localExpr"
              :placeholder="placeholderText"
              spellcheck="false"
              @keydown.enter="onConfirm"
              @keydown.esc="$emit('close')"
            />
          </div>
          <div class="expr-hint">支持 JS 表达式语法，例如 $json.detection.score * 2 或 $json.labels[0]</div>

          <!-- Available fields list -->
          <div class="avail-fields-section">
            <div class="avail-fields-title">&#127919; 可用字段（{{ sourceLabel }}）</div>

            <div
              v-for="field in availableFields"
              :key="field.jsonPath || field.key || field.fullPath"
              class="avail-field-item"
              :class="{ selected: isSelected(field) }"
              @click.stop="selectField(field)"
            >
              <span class="avail-dot" :class="'dot-' + field.type"></span>
              <span class="avail-path">{{ field.jsonPath || `$json.${field.fullPath || field.key}` }}</span>
              <span class="avail-type-tag" :class="'chip-' + (field.type || 'string')">{{ field.type || 'string' }}</span>
              <span v-if="isSelected(field)" class="avail-check">&#10003;</span>
            </div>
          </div>

          <!-- Action buttons -->
          <div class="expr-actions">
            <button class="expr-btn expr-btn-primary" @click.stop="onConfirm">确认映射</button>
            <button class="expr-btn expr-btn-secondary" @click.stop="$emit('close')">取消</button>
          </div>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup>
import { computed, nextTick, ref, watch } from 'vue'

const props = defineProps({
  visible: { type: Boolean, default: false },
  /** Position of the selector overlay { x, y } in viewport pixels */
  position: { type: Object, default: () => ({ x: 400, y: 200 }) },
  /** Current expression value (v-model) */
  modelValue: { type: String, default: '' },
  /** Source node label for display */
  sourceLabel: { type: String, default: '上游节点' },
  /** Available fields from upstream node output */
  fields: { type: Array, default: () => [] }, // [{ key, label, type, jsonPath?, fullPath? }]
})

const emit = defineEmits(['update:modelValue', 'confirm', 'close'])

const inputRef = ref(null)
const localExpr = ref(props.modelValue || '')

watch(() => props.modelValue, (val) => { localExpr.value = val || '' })
watch(() => props.visible, (val) => {
  if (val) {
    localExpr.value = props.modelValue || ''
    nextTick(() => inputRef.value?.focus())
  }
})

const placeholderText = '输入字段路径或表达式...'

const overlayStyle = computed(() => ({
  left: Math.min(props.position.x, window.innerWidth - 360) + 'px',
  top: Math.min(props.position.y, window.innerHeight - 420) + 'px',
}))

/** Enrich fields with jsonPath if missing */
const availableFields = computed(() => {
  return (props.fields || []).map(f => ({
    ...f,
    jsonPath: f.jsonPath || `$json.${f.fullPath || f.key}`,
  }))
})

function isSelected(field) {
  return localExpr.value === (field.jsonPath || `$json.${field.fullPath || field.key}`)
}

function selectField(field) {
  const path = field.jsonPath || `$json.${field.fullPath || field.key}`
  if (localExpr.value === path) {
    localExpr.value = '' // toggle off
  } else {
    localExpr.value = path
  }
}

function onConfirm() {
  emit('update:modelValue', localExpr.value)
  emit('confirm', localExpr.value)
}
</script>

<style scoped>
.expr-overlay {
  position: fixed;
  z-index: 200;
  filter: drop-shadow(0 12px 40px rgba(0,0,0,0.6));
}

.expr-selector {
  width: 340px;
  background: #1a1a30;
  border: 1px solid rgba(99,102,241,0.28);
  border-radius: 10px;
  overflow: hidden;
  animation: exprIn 0.18s ease-out;
}
@keyframes exprIn {
  from { opacity: 0; transform: translateY(-4px) scale(0.97); }
  to { opacity: 1; transform: translateY(0) scale(1); }
}

/* Header */
.expr-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 10px 14px;
  background: rgba(99,102,241,0.08);
  border-bottom: 1px solid rgba(99,102,241,0.15);
}
.expr-title {
  font-size: 11px; font-weight: 600; color: #a5b4fc;
  display: flex; align-items: center; gap: 6px;
}
.expr-close-btn {
  width: 22px; height: 22px; border-radius: 5px; border: none;
  background: rgba(239,68,68,0.1); color: #f87171;
  font-size: 13px; cursor: pointer; display: flex;
  align-items: center; justify-content: center;
}
.expr-close-btn:hover { background: rgba(239,68,68,0.25); }

/* Body */
.expr-body { padding: 10px 14px; }

/* Input */
.expr-input-wrap {
  display: flex; align-items: center; gap: 6px;
  background: rgba(0,0,0,0.3); border: 1px solid rgba(99,102,241,0.2);
  border-radius: 6px; padding: 7px 10px; margin-bottom: 7px;
}
.expr-prefix {
  font-family: 'JetBrains Mono', monospace; font-size: 11px;
  color: #818cf8; font-weight: 600; flex-shrink: 0;
}
.expr-input {
  flex: 1; background: transparent; border: none; outline: none;
  font-family: 'JetBrains Mono', 'SF Mono', monospace; font-size: 11.5px;
  color: #e2e8f0; caret-color: #818cf8;
}
.expr-input::placeholder { color: #3d3d6b; }
.expr-hint {
  font-size: 8px; color: #52527a; margin-top: -4px;
  margin-bottom: 10px; padding-left: 2px;
}

/* Available fields */
.avail-fields-section { max-height: 220px; overflow-y: auto; }
.avail-fields-section::-webkit-scrollbar { width: 4px; }
.avail-fields-section::-webkit-scrollbar-thumb { background: #3d3d6b; border-radius: 2px; }

.avail-fields-title {
  font-size: 8.5px; font-weight: 700; text-transform: uppercase;
  letter-spacing: 0.5px; color: #52527a; margin-bottom: 6px;
}

.avail-field-item {
  display: flex; align-items: center; gap: 6px;
  padding: 5px 7px; border-radius: 5px; cursor: pointer;
  transition: all 0.12s; font-size: 9.5px; margin-bottom: 1px;
}
.avail-field-item:hover { background: rgba(99,102,241,0.07); }
.avail-field-item.selected {
  background: rgba(99,102,241,0.11); border: 1px solid rgba(99,102,241,0.22);
}

.avail-dot {
  width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0;
}
.dot-string { background: #60a5fa; }
.dot-number { background: #34d399; }
.dot-boolean{ background: #fbbf24; }
.dot-array  { background: #a78bfa; }
.dot-object { background: #f472b6; }

.avail-path {
  font-family: 'JetBrains Mono', 'SF Mono', monospace; font-size: 9px;
  color: #94a3b8; flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}

.avail-type-tag {
  font-size: 7px; font-weight: 600; padding: 1px 5px; border-radius: 3px;
  flex-shrink: 0; margin-left: 3px;
}
.chip-string { background: rgba(96,165,250,0.13); color: #60a5fa; }
.chip-number{ background: rgba(52,211,153,0.13); color: #34d399; }
.chip-boolean{background: rgba(251,191,36,0.13); color: #fbbf24; }
.chip-array { background: rgba(167,138,250,0.13); color: #a78bfa; }
.chip-object{ background: rgba(244,114,182,0.13); color: #f472b6; }

.avail-check { color: #22c55e; font-size: 10px; font-weight: 700; margin-left: 2px; }

/* Actions */
.expr-actions {
  margin-top: 10px; padding-top: 8px;
  border-top: 1px solid rgba(255,255,255,0.06);
  display: flex; gap: 6px;
}
.expr-btn {
  padding: 6px 0; border-radius: 6px; border: none; cursor: pointer;
  font-size: 10px; font-weight: 600; transition: all 0.12s;
}
.expr-btn-primary {
  flex: 1; background: linear-gradient(135deg, #6366f1, #8b5cf6); color: white;
}
.expr-btn-primary:hover { opacity: 0.9; transform: translateY(-0.5px); }
.expr-btn-secondary {
  padding: 6px 16px; background: transparent; color: #64748b;
  border: 1px solid rgba(255,255,255,0.08);
}
.expr-btn-secondary:hover { color: #94a3b8; background: rgba(255,255,255,0.04); }
</style>
