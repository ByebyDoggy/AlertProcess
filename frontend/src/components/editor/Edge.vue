<template>
  <g style="pointer-events: none;" @click.stop="$emit('click')" @contextmenu.prevent="$emit('contextMenu', $event)">
    <path :d="path" :class="['edge-path', { selected: edgeSelected, 'multi-selected': multiSelected }, invalid ? 'edge-invalid' : '', hasMapping ? 'edge-mapped' : '']" :marker-end="markerRef" style="pointer-events: visibleStroke;" />

    <!-- Expression/Transformer badge on edge (always clickable) -->
    <g class="edge-badge clickable-badge" @click.stop="$emit('editExpression', { x: midpoint.x, y: midpoint.y, currentExpr })">
      <!-- 有表达式时显示表达式文字 -->
      <template v-if="hasExpression">
        <rect :x="exprBadgeRect.x" :y="exprBadgeRect.y" :width="exprBadgeRect.width" :height="exprBadgeRect.height" rx="5" class="expr-bg" />
        <text text-anchor="middle" dominant-baseline="central" class="expr-text">{{ displayLabel }}</text>
        <text :x="midpoint.x + exprBadgeRect.width/2 + 4" :y="midpoint.y" dominant-baseline="central" class="expr-edit-icon">&#9998;</text>
      </template>
      <!-- 无表达式时显示 + 按钮 -->
      <template v-else>
        <circle :cx="midpoint.x" :cy="midpoint.y" r="9" class="expr-add-bg" />
        <text :x="midpoint.x" :y="midpoint.y" dominant-baseline="central" text-anchor="middle" class="expr-add-icon">+</text>
      </template>
    </g>

    <!-- Standard label (e.g., 满足/不满足) for non-expression edges -->
    <g v-if="label && !hasExpression" :transform="`translate(${midpoint.x}, ${midpoint.y})`">
      <rect x="-20" y="-9" width="40" height="18" class="edge-label-bg" />
      <text text-anchor="middle" dy="4" class="edge-label-text">{{ label }}</text>
    </g>

    <!-- Mapping count badge (when there's field mapping but no single expression) -->
    <g v-else-if="hasMapping && !hasExpression" :transform="`translate(${midpoint.x}, ${midpoint.y - 8})`">
      <rect :x="mappingBadgeX" y="-9" :width="mappingBadgeW" height="16" rx="3" class="mapping-label-bg" />
      <text text-anchor="middle" dy="4" class="mapping-label-text">{{ mappingLabel }}</text>
    </g>
  </g>
</template>

<script setup>
import { computed } from 'vue'
import { getEdgePath, getEdgeMidpoint } from '../../utils/geometry.js'

const props = defineProps({
  from: { type: Object, required: true },
  to: { type: Object, required: true },
  /** 单选连线高亮（点击选中某条连线时） */
  selected: { type: Boolean, default: false },
  /** 多选高亮：连线两端节点是否都在 selectedNodeIds 中 */
  multiSelected: { type: Boolean, default: false },
  invalid: { type: Boolean, default: false },
  label: { type: String, default: '' },
  fieldMapping: { type: Object, default: null },
  /** Expression string (e.g., "$json.detection.score") for the edge */
  expression: { type: String, default: '' },
})

const edgeSelected = computed(() => props.selected || props.multiSelected)
defineEmits(['click', 'editExpression', 'contextMenu'])

const path = computed(() => getEdgePath(props.from, props.to))
const midpoint = computed(() => getEdgeMidpoint(props.from, props.to))

/** 是否有字段映射 */
const hasMapping = computed(() =>
  props.fieldMapping && Object.keys(props.fieldMapping).length > 0
)

/** 是否有表达式（单条映射或显式设置的 expression） */
const hasExpression = computed(() => {
  if (props.expression) return true
  // If there's exactly one field mapping entry, treat as an expression
  if (hasMapping.value && Object.keys(props.fieldMapping).length === 1) return true
  return false
})

/** 当前表达式文本 */
const currentExpr = computed(() => {
  if (props.expression) return props.expression
  if (!hasMapping.value || !hasExpression.value) return ''
  const [path] = Object.keys(props.fieldMapping)
  return path || ''
})

/** 显示在连线上方的标签文字 */
const displayLabel = computed(() => {
  const expr = currentExpr.value
  if (!expr) return ''
  // Shorten long paths: show only last segment or truncate
  const short = expr.split('.').pop()
  return expr.length > 24 ? `${short} \u2192 ...` : expr
})

/** Expression badge dimensions based on text length */
const exprBadgeRect = computed(() => {
  const textLen = displayLabel.value.length * 7 + 36
  const w = Math.max(60, Math.min(textLen, 160))
  return { x: -w / 2, y: -11, width: w, height: 20 }
})

/** Mapping badge position */
const mappingBadgeX = computed(() => -22)
const mappingBadgeW = computed(() => 44)

/** 映射标签文字（显示已映射的字段数或具体字段名） */
const mappingLabel = computed(() => {
  if (!props.fieldMapping) return ''
  const count = Object.keys(props.fieldMapping).length
  if (count === 1) {
    const [path] = Object.entries(props.fieldMapping)[0]
    const shortKey = path.split('.').pop()
    return `${shortKey} \u2192 ${props.fieldMapping[path]?.targetKey || ''}`
  }
  return `${count} fields`
})

const markerRef = computed(() => {
  if (props.invalid) return 'url(#arrow-invalid)'
  if (props.selected || props.multiSelected) return 'url(#arrow-selected)'
  return 'url(#arrow-default)'
})
</script>

<style scoped>
.edge-path {
  fill: none;
  stroke: #4a4a7a;
  stroke-width: 1.8px;
  transition: stroke 0.15s, stroke-width 0.15s;
}
.edge-path.selected { stroke: #f59e0b; stroke-width: 2px; }
/* 多选连线：两端节点都被框选时，虚线高亮 */
.edge-path.multi-selected { stroke: #818cf8; stroke-width: 2px; stroke-dasharray: 5 3; }
.edge-path.edge-invalid { stroke: #ef4444; }
.edge-path.edge-mapped { stroke: #22c55e; opacity: 0.6; }

/* Standard label (满足/不满足) */
.edge-label-bg {
  fill: rgba(30, 30, 60, 0.88);
  rx: 3px;
}
.edge-label-text {
  fill: #a0a0c0;
  font-size: 9px;
  text-anchor: middle;
  pointer-events: none;
}

/* Mapping label (count badge) */
.mapping-label-bg {
  fill: rgba(34, 197, 94, 0.12);
  stroke: rgba(34, 197, 94, 0.25);
  stroke-width: 0.5px;
}
.mapping-label-text {
  fill: #34d399;
  font-size: 7.5px;
  font-family: 'JetBrains Mono', 'SF Mono', monospace;
  text-anchor: middle;
  pointer-events: none;
}

/* Expression badge on edge */
.clickable-badge {
  cursor: pointer;
  pointer-events: all !important;
}
.expr-bg {
  fill: rgba(15, 15, 32, 0.92);
  stroke: rgba(34, 197, 94, 0.35);
  stroke-width: 1px;
  transition: all 0.12s;
}
.clickable-badge:hover .expr-bg {
  stroke: rgba(34, 197, 94, 0.65);
  fill: rgba(15, 15, 32, 0.97);
}
.expr-text {
  fill: #34d399;
  font-size: 8px;
  font-family: 'JetBrains Mono', 'SF Mono', monospace;
  text-anchor: middle;
  pointer-events: none;
}
.expr-edit-icon {
  fill: #818cf8;
  font-size: 10px;
  pointer-events: none;
  opacity: 0;
  transition: opacity 0.12s;
}
.clickable-badge:hover .expr-edit-icon {
  opacity: 0.7;
}

/* Add expression (+) button on edges without expression */
.expr-add-bg {
  fill: rgba(30, 30, 60, 0.75);
  stroke: rgba(129, 140, 248, 0.5);
  stroke-width: 1px;
  transition: all 0.12s;
}
.clickable-badge:hover .expr-add-bg {
  fill: rgba(99, 102, 241, 0.35);
  stroke: rgba(129, 140, 248, 0.85);
  r: 10;
}
.expr-add-icon {
  fill: #818cf8;
  font-size: 13px;
  font-weight: 700;
  font-family: sans-serif;
  text-anchor: middle;
  pointer-events: none;
  dominant-baseline: central;
}
</style>
