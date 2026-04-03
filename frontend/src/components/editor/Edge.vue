<template>
  <g style="pointer-events: none;" @click.stop="$emit('click')">
    <path :d="path" :class="['edge-path', selected ? 'selected' : '', invalid ? 'edge-invalid' : '']" :marker-end="markerRef" style="pointer-events: visibleStroke;" />
    <g v-if="label" :transform="`translate(${midpoint.x}, ${midpoint.y})`">
      <rect x="-20" y="-9" width="40" height="18" class="edge-label-bg" />
      <text text-anchor="middle" dy="4" class="edge-label-text">{{ label }}</text>
    </g>
  </g>
</template>

<script setup>
import { computed } from 'vue'
import { getEdgePath, getEdgeMidpoint } from '../../utils/geometry.js'

const props = defineProps({
  from: { type: Object, required: true },
  to: { type: Object, required: true },
  selected: { type: Boolean, default: false },
  invalid: { type: Boolean, default: false },
  label: { type: String, default: '' },
})
defineEmits(['click'])

const path = computed(() => getEdgePath(props.from, props.to))
const midpoint = computed(() => getEdgeMidpoint(props.from, props.to))

const markerRef = computed(() => {
  if (props.invalid) return 'url(#arrow-invalid)'
  if (props.selected) return 'url(#arrow-selected)'
  return 'url(#arrow-default)'
})
</script>
