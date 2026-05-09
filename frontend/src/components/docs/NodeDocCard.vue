<template>
  <div
    class="doc-card cursor-pointer rounded-lg p-3 border transition-all duration-200"
    :class="active ? 'border-indigo-500/60 bg-indigo-500/10' : 'border-[#2d2d50] bg-[#1e1e38]/60 hover:border-indigo-500/30 hover:bg-indigo-500/5'"
    @click="$emit('select')"
  >
    <div class="flex items-center gap-2.5">
      <span class="doc-card-icon text-base" :style="{ color: node.color || '#818cf8' }">{{ node.icon || '&#9679;' }}</span>
      <div class="min-w-0 flex-1">
        <div class="text-sm font-medium text-gray-200 truncate">{{ node.label }}</div>
        <div class="text-xs text-gray-500 truncate">{{ node.name }}</div>
      </div>
    </div>
    <p v-if="node.description" class="mt-1.5 text-xs text-gray-400 line-clamp-2 leading-relaxed">{{ node.description }}</p>
  </div>
</template>

<script setup>
defineProps({
  node: { type: Object, required: true },
  active: { type: Boolean, default: false },
})
defineEmits(['select'])
</script>

<style scoped>
.line-clamp-2 {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
</style>
