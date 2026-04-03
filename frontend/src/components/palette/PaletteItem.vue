<template>
  <div
    class="palette-item p-2.5 flex items-center gap-2.5"
    draggable="true"
    @dragstart="onDragStart"
  >
    <div class="w-8 h-8 rounded-lg flex items-center justify-center text-base flex-shrink-0"
      :style="{ background: bgStyle, color: nodeType.color }">
      {{ nodeType.icon }}
    </div>
    <div class="min-w-0">
      <div class="text-sm text-gray-200 font-medium">{{ nodeType.label }}</div>
      <div class="text-xs text-gray-500 truncate">{{ nodeType.description }}</div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  nodeType: { type: Object, required: true },
})

const bgStyle = computed(() => {
  const c = props.nodeType.color || '#6366f1'
  return `${c}22`
})

function onDragStart(event) {
  event.dataTransfer.setData('nodeType', props.nodeType.name)
  event.dataTransfer.effectAllowed = 'copy'
}
</script>
