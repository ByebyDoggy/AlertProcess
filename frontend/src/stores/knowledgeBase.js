import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import {
  getSamples,
  getSample,
  createSample,
  updateSample,
  deleteSample,
  getCategories,
} from '@/api/knowledgeBase.js'

export const useKnowledgeBaseStore = defineStore('knowledgeBase', () => {
  // ── 列表 ──
  const samples = ref([])
  const totalLoaded = ref(0)
  const loading = ref(false)

  // ── 当前查看 ──
  const currentSample = ref(null)
  const loadingDetail = ref(false)

  // ── 分类 ──
  const categories = ref([])
  const categoryMap = ref({})

  // ── 筛选条件 ──
  const filterCategory = ref('')
  const filterChainId = ref(null)
  const filterSearch = ref('')
  const filterTag = ref('')
  const pageSkip = ref(0)
  const pageLimit = ref(20)

  // ── 计算属性 ──
  const hasMore = computed(() => samples.value.length >= pageLimit.value)

  // ── 方法 ──
  async function fetchCategories() {
    try {
      const data = await getCategories()
      categories.value = data.preset || []
      const map = {}
      for (const cat of categories.value) {
        map[cat.value] = cat.label
      }
      // 添加已使用但不在预设中的分类
      for (const used of data.used || []) {
        if (!map[used]) map[used] = used
      }
      categoryMap.value = map
    } catch (e) {
      console.error('Failed to fetch categories:', e)
    }
  }

  async function fetchSamples(reset = true) {
    loading.value = true
    try {
      if (reset) {
        samples.value = []
        pageSkip.value = 0
      }
      const params = {
        skip: pageSkip.value,
        limit: pageLimit.value,
      }
      if (filterCategory.value) params.category = filterCategory.value
      if (filterChainId.value != null) params.chain_id = filterChainId.value
      if (filterSearch.value) params.search = filterSearch.value
      if (filterTag.value) params.tag = filterTag.value

      const data = await getSamples(params)
      if (reset) {
        samples.value = data
      } else {
        samples.value.push(...data)
      }
      totalLoaded.value = samples.value.length
    } catch (e) {
      console.error('Failed to fetch samples:', e)
    } finally {
      loading.value = false
    }
  }

  async function loadMore() {
    if (!hasMore.value || loading.value) return
    pageSkip.value += pageLimit.value
    await fetchSamples(false)
  }

  async function fetchSampleDetail(id) {
    loadingDetail.value = true
    try {
      const sample = await getSample(id)
      currentSample.value = sample
      return sample
    } catch (e) {
      console.error('Failed to fetch sample detail:', e)
      return null
    } finally {
      loadingDetail.value = false
    }
  }

  async function addSample(data) {
    const created = await createSample(data)
    samples.value.unshift(created)
    totalLoaded.value++
    return created
  }

  async function editSample(id, data) {
    const updated = await updateSample(id, data)
    const idx = samples.value.findIndex((s) => s.id === id)
    if (idx !== -1) samples.value[idx] = updated
    if (currentSample.value?.id === id) currentSample.value = updated
    return updated
  }

  async function removeSample(id) {
    await deleteSample(id)
    samples.value = samples.value.filter((s) => s.id !== id)
    totalLoaded.value--
    if (currentSample.value?.id === id) currentSample.value = null
  }

  function resetFilters() {
    filterCategory.value = ''
    filterChainId.value = null
    filterSearch.value = ''
    filterTag.value = ''
  }

  function getCategoryLabel(value) {
    return categoryMap.value[value] || value || '未分类'
  }

  return {
    samples,
    totalLoaded,
    loading,
    currentSample,
    loadingDetail,
    categories,
    categoryMap,
    filterCategory,
    filterChainId,
    filterSearch,
    filterTag,
    pageLimit,
    hasMore,
    fetchCategories,
    fetchSamples,
    loadMore,
    fetchSampleDetail,
    addSample,
    editSample,
    removeSample,
    resetFilters,
    getCategoryLabel,
  }
})
