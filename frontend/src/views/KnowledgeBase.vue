<template>
  <div class="kb-page">
    <SampleTable
      @create="openCreate"
      @edit="openEdit"
      @detail="openDetail"
      @export="openExport"
    />

    <!-- 创建/编辑表单 -->
    <SampleForm
      v-if="showForm"
      :sample="editingSample"
      @close="showForm = false"
      @saved="onSaved"
    />

    <!-- 详情面板 -->
    <SampleDetail
      v-if="detailSample"
      :sample="detailSample"
      @close="detailSample = null"
    />

    <!-- 导入导出 -->
    <ImportExport
      v-if="showImportExport"
      :mode="importExportMode"
      @close="showImportExport = false"
      @imported="onImported"
    />
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useKnowledgeBaseStore } from '@/stores/knowledgeBase.js'
import SampleTable from '@/components/knowledge/SampleTable.vue'
import SampleForm from '@/components/knowledge/SampleForm.vue'
import SampleDetail from '@/components/knowledge/SampleDetail.vue'
import ImportExport from '@/components/knowledge/ImportExport.vue'

const store = useKnowledgeBaseStore()
const showForm = ref(false)
const editingSample = ref(null)
const detailSample = ref(null)
const showImportExport = ref(false)
const importExportMode = ref('import')

onMounted(() => {
  store.fetchSamples()
  store.fetchCategories()
})

function openCreate() {
  editingSample.value = null
  showForm.value = true
}

function openEdit(sample) {
  editingSample.value = sample
  showForm.value = true
}

function openDetail(sample) {
  store.fetchSampleDetail(sample.id)
  detailSample.value = sample
}

function openExport() {
  importExportMode.value = 'export'
  showImportExport.value = true
}

function onSaved() {
  showForm.value = false
  store.fetchSamples()
}

function onImported() {
  showImportExport.value = false
  store.fetchSamples()
}
</script>

<style scoped>
.kb-page {
  height: 100%;
  display: flex;
  flex-direction: column;
  background: #1a1a2e;
}
</style>
