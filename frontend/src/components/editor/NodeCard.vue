<template>
  <div
    :data-node-id="node.id"
    :class="['n8n-node', selected ? 'selected' : '']"
    :style="nodeStyle"
    @mousedown.stop="$emit('startDrag', $event, node)"
    @click.stop="$emit('click', node.id)"
    @dblclick.stop="$emit('dblClick', node)"
  >
    <!-- Delete button -->
    <div class="node-delete-btn" @click.stop="$emit('delete', node.id)">&times;</div>

    <!-- Header -->
    <div class="node-header" :style="{ background: headerBg }">
      <div class="node-header-icon">{{ nodeType?.icon || '?' }}</div>
      <span class="node-header-label">{{ node.label }}</span>
      <span class="node-type-badge">{{ nodeType?.label || node.type }}</span>
    </div>

    <!-- Ports -->
    <div class="node-ports">
      <!-- Input ports -->
      <div
        v-for="(port, idx) in inputPorts"
        :key="port.key"
        class="port-row input-row"
      >
        <Port
          :port-def="port"
          :side="'left'"
          :connected="isPortConnected(port.key, 'input')"
          @start-drag="(e) => $emit('portDrag', e, node, port.key, 'left')"
        />
        <span class="port-label">{{ port.label }}</span>
      </div>

      <!-- Output ports -->
      <div
        v-for="(port, idx) in outputPorts"
        :key="port.key"
        class="port-row output-row"
      >
        <span class="port-label">{{ port.label }}</span>
        <Port
          :port-def="port"
          :side="'right'"
          :connected="isPortConnected(port.key, 'output')"
          @start-drag="(e) => $emit('portDrag', e, node, port.key, 'right')"
        />
      </div>
    </div>

    <!-- Config summary -->
    <div v-if="summary" class="node-body">
      {{ summary }}
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import Port from './Port.vue'
import { useNodeTypesStore } from '../../stores/nodeTypes.js'
import { useChainDataStore } from '../../stores/chainData.js'
import { NODE_WIDTH } from '../../utils/geometry.js'

const props = defineProps({
  node: { type: Object, required: true },
  selected: { type: Boolean, default: false },
})
const emit = defineEmits(['click', 'dblClick', 'delete', 'startDrag', 'portDrag'])

const nodeTypesStore = useNodeTypesStore()
const chainDataStore = useChainDataStore()

const nodeType = computed(() => nodeTypesStore.getByName(props.node.type))

const nodeStyle = computed(() => ({
  left: props.node.position.x + 'px',
  top: props.node.position.y + 'px',
}))

const headerBg = computed(() => {
  const c = nodeType.value?.color || '#6366f1'
  return `${c}22`
})

/**
 * 输入端口列表 — 支持动态多输入
 */
const inputPorts = computed(() => {
  const nt = nodeType.value
  if (!nt) return []

  const definedInputs = nt.inputs || []

  // 如果有配置的 inputPorts（多输入场景），用配置的
  if (props.node.config?.inputPorts && props.node.config.inputPorts.length > 0) {
    const portMap = {}
    for (const p of definedInputs) portMap[p.key] = p

    const basePort = definedInputs.find(p => p.multi) || definedInputs[0]
    return props.node.config.inputPorts.map((key, idx) => ({
      ...basePort,
      key,
      label: basePort?.label ? `${basePort.label.split(' ')[0]} ${idx + 1}` : `输入 ${idx + 1}`,
      required: idx === 0 ? true : false,
      multi: false,
    }))
  }

  return definedInputs
})

const outputPorts = computed(() => nodeType.value?.outputs || [])

function isPortConnected(portKey, direction) {
  return chainDataStore.edges.some(e => {
    if (direction === 'input') return e.target === props.node.id && e.targetPort === portKey
    return e.source === props.node.id && e.sourcePort === portKey
  })
}

const summary = computed(() => {
  const config = props.node.config || {}
  if (!nodeType.value) return ''

  // 根据配置 schema 生成摘要
  const schema = nodeType.value.config_schema
  if (!schema || !schema.properties) return ''

  const entries = Object.entries(schema.properties)
  if (entries.length === 0) return ''

  const parts = []
  for (const [key, field] of entries.slice(0, 2)) {
    if (config[key] !== undefined && config[key] !== '') {
      if (field.type === 'boolean') {
        parts.push(config[key] ? field.description || key : '')
      } else {
        const val = Array.isArray(config[key]) ? config[key].join(', ') : String(config[key])
        parts.push(val.length > 20 ? val.substring(0, 20) + '...' : val)
      }
    }
  }
  return parts.filter(Boolean).join(' | ')
})
</script>
