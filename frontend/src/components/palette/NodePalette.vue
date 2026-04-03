<template>
  <div class="w-64 bg-[#1a1a2e] border-r border-[#2d2d50] p-3 overflow-y-auto flex flex-col">
    <!-- Search -->
    <div class="mb-3">
      <input
        v-model="search"
        placeholder="搜索节点..."
        class="form-input !py-1.5 text-sm"
      >
    </div>

    <div class="space-y-1 flex-1">
      <template v-for="cat in filteredCategories" :key="cat.key">
        <div class="palette-category">{{ cat.label }}</div>
        <PaletteItem
          v-for="nt in cat.filteredNodes"
          :key="nt.name"
          :node-type="nt"
        />
      </template>

      <div v-if="noResults" class="text-xs text-gray-500 text-center py-4">
        没有匹配的节点
      </div>
    </div>

    <!-- Guide -->
    <div class="mt-3 p-2.5 rounded-lg border border-[#2d2d50] bg-[#16162a]">
      <h4 class="text-xs text-gray-400 font-medium mb-1.5">操作指南</h4>
      <ul class="text-xs text-gray-500 space-y-0.5">
        <li>1. 拖入「告警触发器」开始</li>
        <li>2. 从输出端口拖线连接</li>
        <li>3. 双击节点编辑配置</li>
        <li>4. Ctrl+S 保存规则链</li>
      </ul>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useNodeTypesStore } from '../../stores/nodeTypes.js'
import PaletteItem from './PaletteItem.vue'

const nodeTypesStore = useNodeTypesStore()
const search = ref('')

const filteredCategories = computed(() => {
  const q = search.value.toLowerCase().trim()
  return nodeTypesStore.categories.map(cat => {
    const filteredNodes = cat.nodes.filter(nt => {
      if (!q) return true
      return (
        nt.label.toLowerCase().includes(q) ||
        nt.name.toLowerCase().includes(q) ||
        nt.description?.toLowerCase().includes(q) ||
        nt.category.toLowerCase().includes(q)
      )
    })
    return { ...cat, filteredNodes }
  }).filter(cat => cat.filteredNodes.length > 0)
})

const noResults = computed(() => {
  return filteredCategories.value.every(cat => cat.filteredNodes.length === 0)
})
</script>
