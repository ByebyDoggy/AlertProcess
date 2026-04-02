<template>
  <Teleport to="body">
    <div v-if="visible" class="toast fixed top-4 right-4 z-[100] px-4 py-3 rounded-lg shadow-lg text-sm font-medium" :class="typeClass">
      {{ message }}
    </div>
  </Teleport>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  message: { type: String, required: true },
  type: { type: String, default: 'info' }, // info, success, error
  visible: { type: Boolean, default: false },
})

const typeClass = computed(() => {
  switch (props.type) {
    case 'success': return 'bg-green-600 text-white'
    case 'error': return 'bg-red-600 text-white'
    default: return 'bg-gray-700 text-white border border-gray-600'
  }
})
</script>
