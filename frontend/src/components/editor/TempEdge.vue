<template>
  <path v-if="visible" :d="path" :class="['temp-edge-path', valid ? '' : 'temp-edge-invalid']" />
</template>

<script setup>
defineProps({
  path: { type: String, default: '' },
  visible: { type: Boolean, default: false },
  valid: { type: Boolean, default: true },
})
</script>
