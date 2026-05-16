<template>
  <div class="h-screen flex bg-[#1a1a2e]">
    <!-- Left: Category List -->
    <div class="w-80 flex-shrink-0 border-r border-[#2d2d50] flex flex-col bg-[#16162a]">
      <!-- Header -->
      <div class="px-4 py-4 border-b border-[#2d2d50]">
        <h1 class="text-base font-bold text-white flex items-center gap-2">
          <span class="text-indigo-400">&#128218;</span> 节点文档
        </h1>
        <p class="text-xs text-gray-500 mt-1">基于 Pydantic 模型自动生成</p>
        <!-- Search -->
        <input v-model="search" placeholder="搜索节点..." class="form-input !py-1.5 !text-sm mt-3 !w-full">
      </div>

      <!-- Node list by category -->
      <div class="flex-1 overflow-y-auto p-3 space-y-4">
        <template v-for="cat in filteredCategories" :key="cat.key">
          <div>
            <div class="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2 px-1">
              {{ cat.label }} ({{ cat.nodes.length }})
            </div>
            <div class="space-y-1.5">
              <NodeDocCard
                v-for="nt in cat.nodes"
                :key="nt.name"
                :node="nt"
                :active="selectedName === nt.name"
                @select="selectedName = nt.name"
              />
            </div>
          </div>
        </template>

        <div v-if="noResults" class="text-center py-8 text-gray-500 text-sm">
          没有匹配的节点
        </div>
      </div>

      <!-- Back link -->
      <div class="p-3 border-t border-[#2d2d50]">
        <router-link to="/rule-chain" class="text-xs text-indigo-400 hover:text-indigo-300 flex items-center gap-1">
          <span>&#8592;</span> 返回规则链编辑器
        </router-link>
      </div>
    </div>

    <!-- Right: Detail -->
    <div class="flex-1 overflow-y-auto p-6">
      <NodeDocDetail :node="selectedNode" />
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { fetchNodeDocs } from '../api/nodeSchema.js'
import NodeDocCard from '../components/docs/NodeDocCard.vue'
import NodeDocDetail from '../components/docs/NodeDocDetail.vue'

const allNodes = ref([])
const search = ref('')
const selectedName = ref(null)
const loading = ref(true)

onMounted(async () => {
  try {
    allNodes.value = await fetchNodeDocs()
    if (allNodes.value.length && !selectedName.value) {
      selectedName.value = allNodes.value[0].name
    }
  } catch (e) {
    console.error('Failed to load node docs:', e)
  } finally {
    loading.value = false
  }
})

const CATEGORY_LABELS = {
  input: '输入',
  provider: '上下文查询',
  detection: '安全检测',
  comparison: '比较',
  scoring: '评分',
  logic: '逻辑',
  action: '动作',
  memory: '记忆',
  temporal: '时序',
  scripting: '脚本',
  storage: '存储',
}

const filteredCategories = computed(() => {
  const q = search.value.toLowerCase().trim()
  const groups = {}
  for (const nt of allNodes.value) {
    if (q) {
      const match = nt.label.toLowerCase().includes(q)
        || nt.name.toLowerCase().includes(q)
        || (nt.description || '').toLowerCase().includes(q)
        || nt.category.toLowerCase().includes(q)
      if (!match) continue
    }
    const cat = nt.category || 'other'
    if (!groups[cat]) groups[cat] = []
    groups[cat].push(nt)
  }

  // 按固定顺序排列分类
  const order = ['input', 'provider', 'detection', 'comparison', 'scoring', 'logic', 'action', 'memory', 'temporal', 'scripting', 'storage']
  return order
    .filter(k => groups[k])
    .map(k => ({ key: k, label: CATEGORY_LABELS[k] || k, nodes: groups[k] }))
    .concat(
      Object.entries(groups)
        .filter(([k]) => !order.includes(k))
        .map(([k]) => ({ key: k, label: CATEGORY_LABELS[k] || k, nodes: groups[k] }))
    )
})

const noResults = computed(() => filteredCategories.value.every(c => c.nodes.length === 0))

const selectedNode = computed(() => {
  if (!selectedName.value) return null
  return allNodes.value.find(n => n.name === selectedName.value) || null
})
</script>
