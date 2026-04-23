<template>
  <div class="fpti" :style="{ paddingLeft: depth * 14 + 'px' }">
    <div
      :class="['fpti-row', { 'fpti-leaf': isLeaf, 'fpti-obj': isObj || isArray }]"
      :title="isLeaf ? (typeof data === 'string' ? data : JSON.stringify(data)) : (isExpanded ? '\u6298\u5219' : '\u5c55\u5f00') + ' ' + path"
      @click="handleClick"
    >
      <span v-if="isObj || isArray" class="fpti-toggle">{{ isExpanded ? '&#9660;' : '&#9658;' }}</span>
      <span v-else class="fpti-spacer"></span>
      <span :class="['fpti-type-dot', 'type-' + (isLeaf ? getTypeTag(data) : (isArray ? 'array' : 'object'))]"></span>
      <span class="fpti-key">{{ isArray ? '[' + lastKey + ']' : lastKey }}</span>
      <span v-if="isLeaf" class="fpti-val">{{ formatValue(data) }}</span>
      <span v-else class="fpii-meta">{{ isArray ? data.length + ' items' : Object.keys(data).length + ' keys' }}</span>
    </div>
    <FPTreeItem
      v-for="item in entries"
      :key="item.key"
      :data="item.value"
      :path="path + '.' + item.key"
      :depth="depth + 1"
      :target-input-type="targetInputType"
      :expanded-set="expandedSet"
      :field-defs="fieldDefs"
      @toggle="$emit('toggle', $event)"
      @select="$emit('select', $event)"
    />
  </div>
</template>

<script setup>
import { computed, toRefs } from 'vue'

const props = defineProps({
  data: { type: [Object, Array, String, Number, Boolean, null], required: true },
  path: { type: String, required: true },
  depth: { type: Number, default: 0 },
  targetInputType: { type: String, default: '' },
  expandedSet: { type: Set, required: true },
  fieldDefs: { type: Array, default: () => [] },
})

const emit = defineEmits(['select', 'toggle'])

const data = props.data
const isArray = Array.isArray(data)
const isObj = typeof data === 'object' && data !== null && !Array.isArray(data)
const isLeaf = !isObj && !isArray
const lastKey = computed(() => props.path.split('.').pop())

function getTypeTag(val) {
  if (val === null || val === undefined) return 'null'
  if (typeof val === 'number') return 'number'
  if (typeof val === 'boolean') return 'boolean'
  if (Array.isArray(val)) return `array[${val.length}]`
  if (typeof val === 'object') return 'object'
  return typeof val
}

function formatValue(val) {
  if (val === null || val === undefined) return 'null'
  if (typeof val === 'string') return val.length > 40 ? val.slice(0, 40) + '...' : val
  if (Array.isArray(val)) return `[${val.length}]`
  if (typeof val === 'object') return '{...}'
  return String(val)
}

const entries = computed(() => {
  if (!isObj && !isArray) return []
  const items = Array.isArray(data) ? data.map((v, i) => ({ key: String(i), value: v })) :
    Object.entries(data).map(([k, v]) => ({ key: k, value: v }))
  return items.sort((a, b) => {
    const aObj = typeof a.value === 'object' && a.value !== null && !Array.isArray(a.value)
    const bObj = typeof b.value === 'object' && b.value !== null && !Array.isArray(b.value)
    if (aObj !== bObj) return aObj ? -1 : 1
    return a.key.localeCompare(b.key)
  })
})

function handleClick() {
  if (isLeaf || (!isObj && !isArray)) {
    emit('select', { path: props.path, value: data })
  } else {
    emit('toggle', props.path)
  }
}
</script>

<style scoped>
.fpti-row {
  display: flex; align-items: center; gap: 5px;
  padding: 3px 6px; border-radius: 4px; cursor: pointer;
  font-size: 11px; line-height: 1.5; color: #8892a8;
  transition: background .1s;
}
.fpti-row:hover { background: rgba(99,102,241,0.06); color: #b4bcd0; }
.fpti-leaf:hover { background: rgba(34,197,94,0.06); color: #6ee7b7; }

.fpti-toggle { width: 14px; text-align: center; font-size: 9px; color: #4a5568; flex-shrink: 0; }
.fpti-spacer { width: 14px; flex-shrink: 0; }
.fpti-key { color: #94a3b8; font-weight: 500; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.fpti-val {
  color: #34d399; font-family: inherit; font-size: 10.5px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  max-width: 160px; flex-shrink: 0;
}
.fpii-meta { color: #4b5563; font-size: 9px; margin-left: auto; flex-shrink: 0; }
</style>
