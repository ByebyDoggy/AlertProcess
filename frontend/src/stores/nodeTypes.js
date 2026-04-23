import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { fetchNodeTypes, fetchConnectionRules } from '../api/nodeSchema.js'

export const useNodeTypesStore = defineStore('nodeTypes', () => {
  const nodeTypeList = ref([])
  const connectionRules = ref(null)
  const loading = ref(false)
  const loaded = ref(false)

  /**
   * 按 name 查找节点类型
   */
  function getByName(name) {
    return nodeTypeList.value.find(n => n.name === name) || null
  }

  /**
   * 按 category 分组
   */
  const groupedByCategory = computed(() => {
    const groups = {}
    for (const nt of nodeTypeList.value) {
      const cat = nt.category || 'other'
      if (!groups[cat]) groups[cat] = []
      groups[cat].push(nt)
    }
    return groups
  })

  /**
   * 获取所有分类及其标签
   */
  const categories = computed(() => {
    const labels = {
      input: '输入',
      provider: '上下文查询',
      detection: '安全检测',
      comparison: '比较',
      scoring: '评分',
      logic: '逻辑',
      action: '动作',
      memory: '记忆',
      scripting: '脚本',
    }
    return Object.keys(groupedByCategory.value).map(cat => ({
      key: cat,
      label: labels[cat] || cat,
      nodes: groupedByCategory.value[cat],
    }))
  })

  /**
   * 从后端加载节点类型
   */
  async function load() {
    if (loaded.value) return
    loading.value = true
    try {
      nodeTypeList.value = await fetchNodeTypes()
      connectionRules.value = await fetchConnectionRules()
      loaded.value = true
    } catch (e) {
      console.error('Failed to load node types:', e)
    } finally {
      loading.value = false
    }
  }

  /**
   * 强制重新加载
   */
  async function reload() {
    loaded.value = false
    await load()
  }

  return {
    nodeTypeList,
    connectionRules,
    loading,
    loaded,
    getByName,
    groupedByCategory,
    categories,
    load,
    reload,
  }
})
