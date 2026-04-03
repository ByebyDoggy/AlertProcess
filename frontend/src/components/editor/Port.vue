<template>
  <div
    :data-port-key="portDef.key"
    :data-port-side="side"
    :class="['port-dot', side === 'left' ? 'input-port' : 'output-port', connected ? 'connected' : '']"
    :style="dotStyle"
    @mousedown.stop="$emit('startDrag', $event)"
  />
</template>

<script setup>
import { computed } from 'vue'
import { DATA_TYPE_COLORS } from '../../config/connectionRules.js'

const props = defineProps({
  portDef: { type: Object, required: true },
  side: { type: String, required: true }, // 'left' | 'right'
  connected: { type: Boolean, default: false },
})
defineEmits(['startDrag'])

const dotStyle = computed(() => {
  const color = DATA_TYPE_COLORS[props.portDef.data_type] || DATA_TYPE_COLORS.any
  return {
    color,
    background: props.connected ? color : '#2d2d50',
  }
})
</script>
