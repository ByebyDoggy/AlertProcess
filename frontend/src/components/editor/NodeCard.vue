<template>
  <div
    :data-node-id="node.id"
    :class="['n8n-node', selected ? 'selected' : '', { 'has-test-result': !!testResult, 'node-critical': isCriticalResult }, 'cat-' + categoryClass]"
    :style="nodeStyle"
    @mousedown.stop="$emit('startDrag', $event, node)"
    @click.stop="$emit('click', node.id)"
    @dblclick.stop="$emit('dblClick', node)"
  >
    <!-- CRITICAL 高危测试结果 - 全卡片血红色脉冲 -->
    <div v-if="isCriticalResult" class="critical-overlay"></div>
    <!-- Delete button -->
    <div class="node-delete-btn" @click.stop="$emit('delete', node.id)">&times;</div>

    <!-- ═══ Header ═══ -->
    <div class="node-header" :class="'header-' + categoryClass">
      <div class="node-header-icon">{{ nodeType?.icon || '?' }}</div>
      <span class="node-header-label">{{ node.label }}</span>
      <span class="node-type-badge" :class="'badge-' + categoryClass">{{ nodeType?.label || node.type }}</span>
      <div style="margin-left:auto;display:flex;align-items:center;gap:4px;">
        <span v-if="testResult && !isTestFailed" style="font-size:9px;color:#4ade80;font-family:'JetBrains Mono','SF Mono',monospace;">&#10003;</span>
      </div>
      <button
        v-if="canTest"
        class="node-test-btn"
        :class="{ running: testing, 'has-result': !!testResult }"
        :title="testResult ? '重新测试' : '运行测试'"
        :disabled="testing"
        @click.stop="handleTest"
      >
        {{ testing ? '...' : (testResult ? '&#10003;' : '&#9654;') }}
      </button>
    </div>

    <!-- Test Result Preview Bar -->
    <div v-if="testResult" class="node-test-preview" :class="isTestFailed ? 'preview-error' : 'preview-success'" @click.stop="$emit('openTest', node.id)">
      <span class="preview-icon">{{ isTestFailed ? '&#10007;' : '&#10003;' }}</span>
      <span class="preview-text">{{ testResultText }}</span>
      <span class="preview-detail">点击详情 &rsaquo;</span>
    </div>

    <!-- Required input port anchors -->
    <template v-for="(port, idx) in requiredInputPorts" :key="'in-'+port.key">
      <div class="port-anchor input-port-anchor"
           :style="{ top: inputPortY(idx) + 'px' }"
           :data-port-key="port.key" data-port-side="left"
           :title="port.description ? (port.label + '：' + port.description) : ('输入端口 - ' + port.label)"
           @mousedown.stop="$emit('portDrag', $event, node, port.key, 'left')"
      ></div>
    </template>

    <!-- ═══ INPUT DATA PANELS (per-port) ═══ -->
    <template v-for="(group, idx) in inputPortGroups" :key="'in-group-'+idx">
      <div v-if="group.fields.length > 0" class="input-data-panel">
        <div class="panel-section-header input-panel-header clickable"
             @click.stop="togglePanel('input-' + idx)"
             :title="(panelCollapsed['input-' + idx] ? '展开' : '收起') + ' 输入数据面板'"
        >
          <span class="panel-icon">{{ panelCollapsed['input-' + idx] ? '&#9654;' : '&#9660;' }}</span>
          <div class="port-label-row">
            <span>{{ inputPortGroups.length > 1 ? group.port.label : '输入数据' }}</span>
            <span v-if="inputPortGroups.length > 1" class="port-key-badge">{{ group.port.key }}</span>
          </div>
          <div v-if="group.port.description" class="port-desc-hint">{{ group.port.description }}</div>
        </div>
        <transition name="panel-collapse">
          <div v-show="!panelCollapsed['input-' + idx]">
            <div
              v-for="field in group.fields"
              :key="field.key"
              class="input-field-row"
              :title="field.description || field.label"
            >
              <span class="field-dot" :class="'dot-' + field.type"></span>
              <span class="field-key">{{ field.key }}</span>
              <span v-if="field.label && field.label !== field.key" class="field-label-text">
                {{ field.label }}
              </span>
              <span v-if="field.required" class="field-required" title="必填">*</span>
              <span class="field-type-tag" :class="'tag-' + field.type">{{ field.type }}</span>
            </div>
          </div>
        </transition>
      </div>
    </template>

    <!-- Optional input port anchors (dashed, placed after input panels) -->
    <div v-if="optionalInputPorts.length > 0" class="optional-port-row">
      <template v-for="port in optionalInputPorts" :key="'in-opt-'+port.key">
        <div class="port-anchor input-port-anchor optional-port-anchor"
             :data-port-key="port.key" data-port-side="left"
             :title="port.description ? (port.label + '：' + port.description) : ('可选输入端口 - ' + port.label)"
             @mousedown.stop="$emit('portDrag', $event, node, port.key, 'left')"
        ></div>
      </template>
    </div>

    <!-- ═══ OUTPUT DATA PANELS (per-port) ═══ -->
    <template v-for="(group, idx) in outputPortGroups" :key="'out-group-'+idx">
      <div v-if="group.fields.length > 0" class="output-data-panel">
        <div class="panel-section-header output-panel-header clickable"
             :class="'header-port-' + group.port.key"
             @click.stop="togglePanel('output-' + idx)"
             :title="(panelCollapsed['output-' + idx] ? '展开' : '收起') + ' 输出数据面板'"
        >
          <!-- 输出面板：箭头+文字靠右，紧邻连线圆圈 -->
          <span class="output-label-right">
            {{ panelCollapsed['output-' + idx] ? '&#9654;' : '&#9660;' }}
            {{ outputPortGroups.length > 1 ? group.port.label : '输出数据' }}
            <span v-if="outputPortGroups.length > 1" class="port-key-badge" :class="'badge-port-' + group.port.key">{{ group.port.key }}</span>
            <span class="port-type-badge">{{ group.port.data_type }}</span>
          </span>
          <!-- 端口圆圈内嵌在header中，CSS相对定位自动对齐到文字行中心 -->
          <div class="port-anchor output-port-anchor inline-port-anchor"
               :data-port-key="group.port.key" data-port-side="right"
               :title="'输出端口: ' + group.port.label + ' (' + group.port.data_type + ')'"
               @mousedown.stop="$emit('portDrag', $event, node, group.port.key, 'right')"
          ></div>
        </div>

        <transition name="panel-collapse">
          <div v-show="!panelCollapsed['output-' + idx]">
            <!-- 该端口的字段列表 -->
            <div v-for="field in group.fields" :key="field.key" class="output-field-row"
                 :draggable="true"
                 @dragstart="(e) => onFieldDragStart(e, field, null, group.port)"
                 @dragend="onFieldDragEnd"
                 :data-field-key="field.key"
                 :data-field-type="field.type"
                 :data-port-key="group.port.key"
                 :title="(field.description || field.label) + ' [' + group.port.key + ']'"
            >
              <div class="drag-handle">&#8964;</div>
              <span class="field-dot" :class="'dot-' + field.type"></span>
              <span class="field-key">{{ field.key }}</span>
              <span v-if="field.label && field.label !== field.key" class="field-label-text">{{ field.label }}</span>
              <span class="field-type-tag" :class="'tag-' + field.type">{{ field.type }}</span>
            </div>
          </div>
        </transition>
      </div>
    </template>

    <!-- Description footer -->
    <div v-if="nodeType?.description" class="node-desc-footer" :title="nodeType.description">
      {{ nodeType.description }}
    </div>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { useNodeTypesStore } from '../../stores/nodeTypes.js'
import { useChainDataStore } from '../../stores/chainData.js'
import * as chainApi from '../../api/ruleChain.js'
import { PORT_START_Y, PORT_ROW_HEIGHT } from '../../utils/geometry.js'
import { outputSchemaToFields, inputSchemaToFields } from '../../utils/schemaFields.js'

const props = defineProps({
  node: { type: Object, required: true },
  selected: { type: Boolean, default: false },
})
const emit = defineEmits(['click', 'dblClick', 'delete', 'startDrag', 'portDrag', 'openTest', 'openFieldPicker'])

const nodeTypesStore = useNodeTypesStore()
const chainDataStore = useChainDataStore()

const nodeType = computed(() => nodeTypesStore.getByName(props.node.type))

/** 节点分类 class 名称 */
const categoryClass = computed(() => {
  const cat = nodeType.value?.category || 'detection'
  return {
    input: 'trigger',
    provider: 'provider',
    detection: 'detection',
    comparison: 'logic',
    scoring: 'detection',
    logic: 'logic',
    action: 'action',
    memory: 'memory',
    temporal: 'memory',
    scripting: 'scripting',
    storage: 'storage',
  }[cat] || 'detection'
})

const nodeStyle = computed(() => ({
  left: props.node.position.x + 'px',
  top: props.node.position.y + 'px',
}))

// ── 节点测试状态 ──
const testing = ref(false)

const canTest = computed(() => {
  if (!nodeType.value) return false
  if (nodeType.value.category === 'input') return true
  if (chainDataStore.hasUpstreamOutput(props.node.id)) return true
  if (chainDataStore.getNodeTestInput(props.node.id)) return true
  return false
})

const testResult = computed(() => chainDataStore.nodeTestResults[props.node.id] || null)
const isTestFailed = computed(() => !!testResult.value?.error)
const isCriticalResult = computed(() => {
  const out = testResult.value?.output
  if (!out) return false
  const severity = out.severity || out.final_severity || ''
  return severity.toUpperCase() === 'CRITICAL'
})

const testResultText = computed(() => {
  const r = testResult.value
  if (!r) return ''
  if (r.error) return r.error.length > 30 ? r.error.substring(0, 30) + '...' : r.error
  const out = r.output || {}
  const parts = []
  if (out.score != null) parts.push(`score: ${out.score}`)
  if (out.passed !== undefined) parts.push(out.passed ? 'passed' : 'not passed')
  if (out.severity) parts.push(out.severity)
  if (r.duration_ms) parts.push(`${r.duration_ms}ms`)
  return parts.join(' | ') || '执行成功'
})

async function handleTest() {
  if (testing.value || !canTest.value) return
  testing.value = true

  try {
    const upstreamOutputs = chainDataStore.getUpstreamOutputs(props.node.id)
    let alertData = null
    const manualInput = chainDataStore.getNodeTestInput(props.node.id)
    if (manualInput) {
      try { alertData = JSON.parse(manualInput) } catch { /* ignore */ }
    }
    const nt = nodeType.value
    if (nt.category === 'input' && !alertData && Object.keys(upstreamOutputs).length === 0) {
      alertData = { __test__: true }
    }

    const result = await chainApi.testNode(
      chainDataStore.nodes, chainDataStore.edges, props.node.id,
      upstreamOutputs, alertData,
    )
    chainDataStore.setNodeTestResult(props.node.id, result)
    emit('openTest', props.node.id)
  } catch (e) {
    console.error(`[NodeTest] ${props.node.id} failed:`, e)
    chainDataStore.setNodeTestResult(props.node.id, {
      success: false, error: e.message || String(e), duration_ms: 0,
    })
  } finally {
    testing.value = false
  }
}

// ── Ports ──
const inputPorts = computed(() => {
  const nt = nodeType.value
  if (!nt) return []
  const definedInputs = nt.inputs || []
  if (props.node.config?.inputPorts && props.node.config.inputPorts.length > 0) {
    const basePort = definedInputs.find(p => p.multi) || definedInputs[0]
    return props.node.config.inputPorts.map((key, idx) => ({
      ...basePort, key,
      label: basePort?.label ? `${basePort.label.split(' ')[0]} ${idx + 1}` : `输入 ${idx + 1}`,
      required: idx === 0, multi: false,
    }))
  }
  return definedInputs
})

const requiredInputPorts = computed(() => inputPorts.value.filter(p => p.required !== false))
const optionalInputPorts = computed(() => inputPorts.value.filter(p => p.required === false))

const outputPorts = computed(() => nodeType.value?.outputs || []) // 仅用于回退（outputPortGroups 为空时）

/** 输入端口圆圈的 top 值（像素） */
function inputPortY(idx) {
  return PORT_START_Y + idx * PORT_ROW_HEIGHT
}

/** 根据面板索引计算该输出端口的 top 值（对齐到输出面板右侧） */
function outputPortYByGroup(idx) {
  // 面板基础高度估算
  const HEADER_H = 18        // 面板 header 行高度
  const FIELD_H = 20         // 每个字段行高度
  const MARGIN = 5            // 面板上下 margin
  const NODE_HEADER_H = 47   // 节点头部高度
  const TEST_PREVIEW_H = 26  // 测试预览条高度（如果有）
  const PORT_Y_OFFSET = 0    // 端口在面板 header 内的垂直居中偏移

  /** 计算单个面板的渲染高度（考虑折叠状态） */
  function getPanelRenderHeight(group, collapsedKey) {
    if (!group || group.fields.length === 0) return 0
    const base = HEADER_H + MARGIN * 2
    if (panelCollapsed.value[collapsedKey]) return base // 折叠时只有标题栏
    return base + group.fields.length * FIELD_H
  }

  // 累计高度（从节点顶部算起）
  let accumulated = NODE_HEADER_H

  // 如果有测试预览条，加上高度
  if (testResult.value) {
    accumulated += TEST_PREVIEW_H
  }

  // 加上所有输入面板的高度（考虑折叠状态）
  for (let i = 0; i < inputPortGroups.value.length; i++) {
    const group = inputPortGroups.value[i]
    if (group.fields.length > 0) {
      accumulated += getPanelRenderHeight(group, 'input-' + i)
    }
  }

  // 加上当前输出面板之前的所有输出面板高度
  for (let i = 0; i < idx; i++) {
    const group = outputPortGroups.value[i]
    if (group.fields.length > 0) {
      accumulated += getPanelRenderHeight(group, 'output-' + i)
    }
  }

  // 目标面板的位置：端口圆圈对齐到目标面板的 header 行中心
  if (outputPortGroups.value[idx]?.fields.length > 0) {
    const targetGroup = outputPortGroups.value[idx]
    const panelH = getPanelRenderHeight(targetGroup, 'output-' + idx)
    return accumulated - panelH + MARGIN + PORT_Y_OFFSET
  }

  // 如果目标面板为空，使用旧方式（基于输出端口索引）
  return PORT_START_Y + idx * PORT_ROW_HEIGHT
}

// ── Per-port field groups ──
// 输入字段：按端口分组，每组包含该端口的 InputModel 字段
const inputPortGroups = computed(() => {
  const nt = nodeType.value
  if (!nt) return []

  const schemas = nt.input_schemas || []
  const ports = nt.inputs || []

  // 如果有 input_schemas，按端口分组
  if (schemas.length > 0) {
    return ports.map((port, idx) => ({
      port,
      fields: schemas[idx]
        ? inputSchemaToFields(schemas[idx])
        : [],
    }))
  }

  // Fallback：旧格式 input_schema（单一模型）
  if (nt.input_schema && ports.length > 0) {
    const allFields = inputSchemaToFields(nt.input_schema)
    return ports.map((port, idx) => ({
      port,
      fields: idx === 0 ? allFields : [],
    }))
  }

  return ports.map(port => ({ port, fields: [] }))
})

// 输出字段：按端口分组，每组包含该端口的 OutputModel 字段
const outputPortGroups = computed(() => {
  const nt = nodeType.value
  if (!nt) return []

  const schemas = nt.output_schemas || []
  const ports = nt.outputs || []

  // 如果有 output_schemas，按端口分组
  if (schemas.length > 0) {
    return ports.map((port, idx) => ({
      port,
      fields: schemas[idx]
        ? outputSchemaToFields(schemas[idx])
        : [],
    }))
  }

  // Fallback：旧格式 output_schema（单一模型 → 所有端口共享）
  if (nt.output_schema && ports.length > 0) {
    const allFields = outputSchemaToFields(nt.output_schema)
    return ports.map((port, idx) => ({
      port,
      fields: idx === 0 ? allFields : [],
    }))
  }

  return ports.map(port => ({ port, fields: [] }))
})

function onFieldDragStart(event, field, parentKey, port) {
  event.stopPropagation()
  const dragData = {
    sourceNodeId: props.node.id,
    sourceNodeType: props.node.type,
    fieldName: field.key,
    fieldType: field.type,
    fieldPath: parentKey ? `${parentKey}.${field.key}` : field.key,
    fieldLabel: field.label,
    portKey: port?.key || '',
  }
  event.dataTransfer.setData('application/output-field', JSON.stringify(dragData))
  event.dataTransfer.effectAllowed = 'copy'
  requestAnimationFrame(() => { event.target.classList.add('field-dragging') })
}
function onFieldDragEnd(event) { event.target.classList.remove('field-dragging') }

// ── Panel Collapse State ──
/** key: 'input-{idx}' | 'output-{idx}' → boolean */
const panelCollapsed = ref({})

/** Toggle collapse state of a panel */
function togglePanel(key) {
  panelCollapsed.value[key] = !panelCollapsed.value[key]
}

/** Initialize collapsed state: output panels default to true */
const initCollapsedState = () => {
  const state = {}
  for (let i = 0; i < inputPortGroups.value.length; i++) {
    if (inputPortGroups.value[i].fields.length > 0) state[`input-${i}`] = false // input 默认展开
  }
  for (let i = 0; i < outputPortGroups.value.length; i++) {
    if (outputPortGroups.value[i].fields.length > 0) state[`output-${i}`] = true // output 默认折叠
  }
  panelCollapsed.value = state
}
// Watch node type changes to re-init (e.g., when switching between nodes)
import { watch } from 'vue'
watch(nodeType, () => { initCollapsedState() }, { immediate: true })
</script>

<style scoped>
/* ─── Node Card Base ─── */
.n8n-node {
  position: absolute;
  width: 300px;
  min-height: 60px;
  background: #16162a;
  border: 1px solid #2a2a4a;
  border-radius: 12px;
  box-shadow: 0 4px 24px rgba(0,0,0,0.4), 0 1px 3px rgba(0,0,0,0.3);
  display: flex;
  flex-direction: column;
  animation: nodeAppear 0.25s ease-out;
}
@keyframes nodeAppear {
  from { opacity: 0; transform: scale(0.94) translateY(6px); }
  to { opacity: 1; transform: scale(1) translateY(0); }
}
.n8n-node.selected { border-color: #818cf8; box-shadow: 0 0 0 2px rgba(99,102,241,0.25), 0 4px 24px rgba(0,0,0,0.4); }
.n8n-node.has-test-result { box-shadow: 0 0 0 1px rgba(99,102,241,0.12), 0 2px 8px rgba(0,0,0,0.3); }

/* CRITICAL 高危节点 - 血红色边框脉冲 */
.n8n-node.node-critical {
  border-color: rgba(220, 20, 20, 0.7) !important;
  animation: nodeCriticalPulse 1.1s ease-in-out infinite;
  z-index: 100;
}
@keyframes nodeCriticalPulse {
  0%, 100% {
    box-shadow: 0 0 8px rgba(200, 0, 0, 0.35), 0 4px 24px rgba(0,0,0,0.4);
  }
  50% {
    box-shadow: 0 0 22px rgba(220, 20, 20, 0.65), 0 0 50px rgba(180, 0, 0, 0.25), 0 4px 24px rgba(0,0,0,0.4);
  }
}
.critical-overlay {
  position: absolute;
  inset: 0;
  border-radius: 12px;
  pointer-events: none;
  animation: criticalBgPulse 1.1s ease-in-out infinite;
  z-index: 0;
}
@keyframes criticalBgPulse {
  0%, 100% {
    background: rgba(60, 0, 0, 0.25);
    border: 2px solid rgba(180, 0, 0, 0.5);
  }
  50% {
    background: rgba(150, 0, 0, 0.5);
    border: 2px solid rgba(220, 30, 30, 0.85);
  }
}

.node-delete-btn {
  position: absolute; top: -8px; right: -8px; z-index: 10;
  width: 20px; height: 20px; border-radius: 50%;
  background: #ef4444; color: white; border: none;
  font-size: 12px; cursor: pointer; display: flex;
  align-items: center; justify-content: center;
  opacity: 0; transition: all 0.15s;
  line-height: 1;
}
.n8n-node:hover .node-delete-btn { opacity: 1; }
.node-delete-btn:hover { background: #dc2626; transform: scale(1.15); }

/* ─── Header ─── */
.node-header {
  display: flex; align-items: center; gap: 8px;
  padding: 9px 12px; border-radius: 11px 11px 0 0;
  border-bottom: 1px solid rgba(255,255,255,0.05);
  position: relative;
}
.header-trigger   { background: linear-gradient(135deg, rgba(239,68,68,0.14), rgba(239,68,68,0.06)); }
.header-provider   { background: linear-gradient(135deg, rgba(20,184,166,0.14), rgba(20,184,166,0.06)); }
.node-critical .node-header { background: linear-gradient(135deg, rgba(220,0,0,0.28), rgba(180,0,0,0.1)) !important; }
.header-detection  { background: linear-gradient(135deg, rgba(59,130,246,0.14), rgba(59,130,246,0.06)); }
.header-logic      { background: linear-gradient(135deg, rgba(34,197,94,0.14), rgba(34,197,94,0.06)); }
.header-action     { background: linear-gradient(135deg, rgba(245,158,11,0.14), rgba(245,158,11,0.06)); }
.header-memory     { background: linear-gradient(135deg, rgba(139,92,246,0.14), rgba(139,92,246,0.06)); }
.header-scripting  { background: linear-gradient(135deg, rgba(34,197,94,0.14), rgba(34,197,94,0.06)); }
.header-storage    { background: linear-gradient(135deg, rgba(5,150,105,0.14), rgba(5,150,105,0.06)); }

.node-header-icon {
  width: 26px; height: 26px; border-radius: 7px;
  display: flex; align-items: center; justify-content: center;
  font-size: 13px; flex-shrink: 0;
}
.cat-trigger .node-header-icon    { background: rgba(239,68,68,0.18); }
.cat-provider .node-header-icon   { background: rgba(20,184,166,0.18); }
.cat-detection .node-header-icon  { background: rgba(59,130,246,0.18); }
.cat-logic .node-header-icon      { background: rgba(34,197,94,0.18); }
.cat-action .node-header-icon     { background: rgba(245,158,11,0.18); }
.cat-memory .node-header-icon     { background: rgba(139,92,246,0.18); }
.cat-scripting .node-header-icon  { background: rgba(34,197,94,0.18); }
.cat-storage .node-header-icon    { background: rgba(5,150,105,0.18); }

.node-header-label {
  font-size: 12.5px; font-weight: 600; color: #e2e8f0;
  flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.node-type-badge {
  font-size: 9px; font-weight: 600; padding: 2px 7px; border-radius: 4px; flex-shrink: 0;
}
.badge-trigger    { background: rgba(239,68,68,0.16); color: #f87171; }
.badge-provider   { background: rgba(20,184,166,0.16); color: #2dd4bf; }
.badge-detection  { background: rgba(59,130,246,0.16); color: #60a5fa; }
.badge-logic      { background: rgba(34,197,94,0.16); color: #4ade80; }
.badge-action     { background: rgba(245,158,11,0.16); color: #fbbf24; }
.badge-memory     { background: rgba(139,92,246,0.16); color: #a78bfa; }
.badge-scripting  { background: rgba(34,197,94,0.16); color: #4ade80; }
.badge-storage     { background: rgba(5,150,105,0.16); color: #34d399; }

/* Test button */
.node-test-btn {
  width: 22px; height: 22px; border-radius: 6px; border: none;
  background: rgba(16,185,129,0.15); color: #10b981;
  font-size: 11px; cursor: pointer; display: flex;
  align-items: center; justify-content: center; margin-left: auto;
  flex-shrink: 0; transition: all 0.15s;
}
.node-test-btn:hover:not(:disabled) { background: rgba(16,185,129,0.3); }
.node-test-btn:disabled { opacity: 0.6; cursor: wait; }
.node-test-btn.running { background: rgba(99,102,241,0.2); color: #818cf8; }
.node-test-btn.has-result { background: rgba(16,185,129,0.25); color: #34d399; }

/* Test result preview bar */
.node-test-preview {
  display: flex; align-items: center; gap: 6px;
  padding: 4px 10px; margin: 2px 8px 3px;
  border-radius: 6px; font-size: 10.5px; cursor: pointer; transition: opacity 0.15s;
}
.node-test-preview:hover { opacity: 0.85; }
.preview-success { background: rgba(16,185,129,0.08); color: #34d399; border: 1px solid rgba(16,185,129,0.15); }
.preview-error   { background: rgba(239,68,68,0.08); color: #f87171; border: 1px solid rgba(239,68,68,0.15); }
.node-critical .node-test-preview {
  background: rgba(220, 0, 0, 0.18) !important;
  color: #ff6060 !important;
  border: 1px solid rgba(220, 30, 30, 0.5) !important;
  animation: previewPulse 1.1s ease-in-out infinite;
}
@keyframes previewPulse {
  0%, 100% { background: rgba(220, 0, 0, 0.18); }
  50%       { background: rgba(180, 0, 0, 0.32); }
}
.preview-icon { flex-shrink: 0; font-weight: bold; }
.preview-text { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; min-width: 0; }
.preview-detail { flex-shrink: 0; opacity: 0.5; font-size: 9px; }

/* ─── Port Anchors (positioned on node edges) ─── */
.port-anchor {
  position: absolute; transform: translateY(-50%);
  width: 14px; height: 14px; border-radius: 50%;
  border: 2px solid #3d3d6b; background: #0f0f1a; cursor: crosshair; z-index: 5;
  transition: all 0.15s;
}
.port-anchor::after {
  content: ''; width: 6px; height: 6px; border-radius: 50%;
  position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%);
  transition: background 0.15s;
}
.input-port-anchor { left: -7px; border-color: #22c55e; }
.input-port-anchor::after { background: #22c55e; }
.input-port-anchor:hover { transform: translateY(-50%) scale(1.3); box-shadow: 0 0 12px rgba(34,197,94,0.35); }

.optional-port-anchor { border-style: dashed; border-color: #22c55e; }
.optional-port-anchor::after { background: #22c55e; }
.optional-port-anchor:hover { box-shadow: 0 0 12px rgba(34,197,94,0.35); }

.optional-port-row {
  position: relative;
  height: 20px;
  margin: 0 6px;
}
.optional-port-row .port-anchor {
  position: absolute;
  left: -13px;
  top: 50%;
  transform: translateY(-50%);
}

.output-port-anchor { right: -7px; left: auto; border-color: #f59e0b; }
.output-port-anchor::after { background: #f59e0b; }
.output-port-anchor:hover { transform: translateY(-50%) scale(1.3); box-shadow: 0 0 12px rgba(245,158,11,0.35); }

/** 输出面板内嵌端口圆圈：相对header定位，自动垂直居中对齐 */
.inline-port-anchor {
  position: absolute;
  right: -7px;
  top: 50%;
  transform: translateY(-50%);
}

/* ─── INPUT DATA PANEL ─── */
.input-data-panel {
  padding: 0; margin: 2px 6px 3px;
  border-top: 1px solid rgba(255,255,255,0.05);
  background: rgba(34,197,94,0.02);
  border-radius: 0 0 8px 8px;
}

.panel-section-header {
  display: flex; align-items: center; gap: 4px;
  font-size: 7.5px; font-weight: 700; text-transform: uppercase;
  letter-spacing: 0.6px; padding: 3px 0 4px 1px;
}
.input-panel-header { color: #22c55e; }
.panel-icon { font-size: 9px; }

/* Input field row */
.input-field-row {
  display: flex; align-items: center; gap: 5px;
  font-size: 8.5px; line-height: 1.4; color: #8892a8;
  padding: 2px 4px; margin: 1px 0; border-radius: 3px;
  transition: all 0.12s;
}
.input-field-row:hover { background: rgba(34,197,94,0.06); color: #b4bcd0; }
.input-field-row .field-key {
  font-family: 'JetBrains Mono', 'SF Mono', monospace;
  font-size: 8px; color: #94a3b8; flex-shrink: 0;
}
.input-field-row .field-label-text {
  flex: 1; overflow: hidden; text-overflow: ellipsis;
  white-space: nowrap; color: #6b7280; font-size: 8px;
}
.input-field-row .field-required { color: #ef4444; font-weight: bold; flex-shrink: 0; }

/* ─── OUTPUT DATA PANEL ─── */
.output-data-panel {
  padding: 0; margin: 2px 6px 3px;
  border-top: 1px solid rgba(255,255,255,0.05);
  background: rgba(245,158,11,0.02);
  border-radius: 0 0 8px 8px;
}

.output-panel-header { color: #f59e0b; position: relative; }

/* Per-port header colors */
.header-port-context { color: #60a5fa; }
.header-port-detection { color: #f472b6; }
.header-port-output { color: #f59e0b; }

/* Port key badge in panel header */
.port-key-badge {
  font-size: 6px; padding: 0px 3px; border-radius: 2px;
  background: rgba(99,102,241,0.15); color: #818cf8;
}
.badge-port-context { background: rgba(96,165,250,0.15); color: #60a5fa; }
.badge-port-detection { background: rgba(244,114,182,0.15); color: #f472b6; }

/* Port label row (label + key badge in one flex line) */
.port-label-row {
  display: flex;
  align-items: center;
  gap: 4px;
}

/* Port description hint below label */
.port-desc-hint {
  font-size: 9px;
  color: #6b7280;
  line-height: 1.3;
  margin-top: 1px;
}
.badge-port-output { background: rgba(245,158,11,0.15); color: #fbbf24; }

/* Port data type badge */
.port-type-badge {
  font-size: 6px; font-weight: 600;
  padding: 1px 4px; border-radius: 3px;
  background: rgba(255,255,255,0.06);
  color: #6b7280;
}

/** 输出面板标题文字靠右，紧邻连线圆圈 */
.output-label-right {
  margin-left: auto;
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
.output-label-right .port-type-badge {
  margin-left: 0; /* 在 output-label-right 内部不需要 margin-left:auto */
}

/* Clickable panel header */
.panel-section-header.clickable {
  cursor: pointer;
  user-select: none;
  transition: opacity 0.12s;
}
.panel-section-header.clickable:hover {
  opacity: 0.8;
}

/* Panel collapse transition */
.panel-collapse-enter-active,
.panel-collapse-leave-active {
  transition: all 0.2s ease;
  overflow: hidden;
}
.panel-collapse-enter-from,
.panel-collapse-leave-to {
  max-height: 0;
  opacity: 0;
}
.panel-collapse-enter-to,
.panel-collapse-leave-from {
  max-height: 500px; /* enough to show all fields without scroll */
  opacity: 1;
}

/* Field dot */
.field-dot {
  width: 6px; height: 6px; border-radius: 50%; flex-shrink: 0;
}
.dot-string  { background: #60a5fa; }
.dot-number  { background: #34d399; }
.dot-boolean { background: #fbbf24; }
.dot-array   { background: #a78bfa; }
.dot-object  { background: #f472b6; }
.dot-integer { background: #34d399; }
.dot-any     { background: #9ca3af; }

/* Output field row — draggable */
.output-field-row {
  display: flex; align-items: center; gap: 4px;
  font-size: 9px; line-height: 1.5; color: #8892a8;
  padding: 2px 6px; margin: 1px 0; border-radius: 3px;
  cursor: grab; transition: all 0.12s; user-select: none;
}
.output-field-row:hover { background: rgba(245,158,11,0.06); color: #b4bcd0; }
.output-field-row.field-dragging { opacity: 0.45; }

/* Drag handle indicator */
.drag-handle {
  width: 12px; flex-shrink: 0; opacity: 0; transition: opacity 0.12s;
  display: flex; align-items: center; justify-content: center;
  font-size: 7px; color: #4a5568; letter-spacing: -0.5px; line-height: 1;
}
.output-field-row:hover .drag-handle { opacity: 0.45; }

/* Field key/label in output rows */
.output-field-row .field-key {
  font-family: 'JetBrains Mono', 'SF Mono', monospace;
  font-size: 8px; color: #94a3b8; flex-shrink: 0;
}
.output-field-row .field-label-text {
  flex: 1; overflow: hidden; text-overflow: ellipsis;
  white-space: nowrap; color: #6b7280; font-size: 8px;
}

.field-type-tag {
  font-size: 7px; padding: 0 4px; border-radius: 2px;
  margin-left: auto; flex-shrink: 0; font-weight: 500;
}
.tag-string  { background: rgba(96,165,250,0.13); color: #60a5fa; }
.tag-number  { background: rgba(52,211,153,0.13); color: #34d399; }
.tag-boolean { background: rgba(251,191,36,0.13); color: #fbbf24; }
.tag-array   { background: rgba(167,138,250,0.13); color: #a78bfa; }
.tag-object  { background: rgba(244,114,182,0.13); color: #f472b6; }
.tag-integer { background: rgba(52,211,153,0.13); color: #34d399; }
.tag-any     { background: rgba(156,163,175,0.13); color: #9ca3af; }

/* Description footer */
.node-desc-footer {
  font-size: 8.5px; color: #4a5568; padding: 4px 12px 6px;
  line-height: 1.4; overflow: hidden; text-overflow: ellipsis;
  white-space: nowrap; border-top: 1px solid rgba(255,255,255,0.03);
}
</style>
