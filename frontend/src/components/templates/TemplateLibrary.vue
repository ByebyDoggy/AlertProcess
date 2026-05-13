<template>
  <div class="template-library">
    <div class="header">
      <h2>脚本模板库</h2>
      <input
        v-model="searchQuery"
        type="text"
        placeholder="搜索模板..."
        class="search-input"
      />
    </div>

    <div class="categories">
      <button
        v-for="cat in categories"
        :key="cat.id"
        :class="['category-btn', { active: selectedCategory === cat.id }]"
        @click="selectedCategory = cat.id"
      >
        {{ cat.name }}
      </button>
    </div>

    <div class="templates-grid">
      <div
        v-for="template in filteredTemplates"
        :key="template.id"
        class="template-card"
        @click="selectTemplate(template)"
      >
        <h3>{{ template.name }}</h3>
        <p class="description">{{ template.description }}</p>
        <div class="tags">
          <span v-for="tag in template.tags" :key="tag" class="tag">
            {{ tag }}
          </span>
        </div>
      </div>
    </div>

    <div v-if="selectedTemplate" class="template-preview">
      <div class="preview-header">
        <h3>{{ selectedTemplate.name }}</h3>
        <button @click="closePreview" class="close-btn">✕</button>
      </div>
      <p>{{ selectedTemplate.description }}</p>
      <pre class="code-preview">{{ selectedTemplate.script }}</pre>
      <div class="preview-actions">
        <button @click="importTemplate" class="import-btn">导入到编辑器</button>
        <button @click="closePreview" class="cancel-btn">取消</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import templates from '@/data/scriptTemplates.json'

const searchQuery = ref('')
const selectedCategory = ref('all')
const selectedTemplate = ref(null)

const categories = [
  { id: 'all', name: '全部' },
  { id: 'detector', name: '检测器' },
  { id: 'analyzer', name: '分析器' },
  { id: 'filter', name: '过滤器' }
]

const filteredTemplates = computed(() => {
  let result = templates

  if (selectedCategory.value !== 'all') {
    result = result.filter(t => t.category === selectedCategory.value)
  }

  if (searchQuery.value) {
    const query = searchQuery.value.toLowerCase()
    result = result.filter(t =>
      t.name.toLowerCase().includes(query) ||
      t.description.toLowerCase().includes(query) ||
      t.tags.some(tag => tag.toLowerCase().includes(query))
    )
  }

  return result
})

const emit = defineEmits(['import'])

function selectTemplate(template) {
  selectedTemplate.value = template
}

function closePreview() {
  selectedTemplate.value = null
}

function importTemplate() {
  emit('import', selectedTemplate.value.script)
  closePreview()
}
</script>

<style scoped>
.template-library {
  padding: 20px;
  max-width: 1200px;
  margin: 0 auto;
}

.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.search-input {
  padding: 8px 12px;
  border: 1px solid #ddd;
  border-radius: 4px;
  width: 300px;
}

.categories {
  display: flex;
  gap: 10px;
  margin-bottom: 20px;
}

.category-btn {
  padding: 8px 16px;
  border: 1px solid #ddd;
  background: white;
  border-radius: 4px;
  cursor: pointer;
  transition: all 0.2s;
}

.category-btn:hover {
  background: #f5f5f5;
}

.category-btn.active {
  background: #1890ff;
  color: white;
  border-color: #1890ff;
}

.templates-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 20px;
  margin-bottom: 20px;
}

.template-card {
  border: 1px solid #ddd;
  border-radius: 8px;
  padding: 16px;
  cursor: pointer;
  transition: all 0.2s;
}

.template-card:hover {
  box-shadow: 0 4px 12px rgba(0,0,0,0.1);
  transform: translateY(-2px);
}

.template-card h3 {
  margin: 0 0 8px 0;
  font-size: 16px;
}

.description {
  color: #666;
  font-size: 14px;
  margin: 0 0 12px 0;
}

.tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.tag {
  background: #f0f0f0;
  padding: 2px 8px;
  border-radius: 3px;
  font-size: 12px;
  color: #666;
}

.template-preview {
  position: fixed;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  background: white;
  border: 1px solid #ddd;
  border-radius: 8px;
  padding: 24px;
  max-width: 800px;
  max-height: 80vh;
  overflow-y: auto;
  box-shadow: 0 8px 24px rgba(0,0,0,0.2);
  z-index: 1000;
}

.preview-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.close-btn {
  background: none;
  border: none;
  font-size: 24px;
  cursor: pointer;
  color: #999;
}

.close-btn:hover {
  color: #333;
}

.code-preview {
  background: #f5f5f5;
  padding: 16px;
  border-radius: 4px;
  overflow-x: auto;
  font-family: 'Courier New', monospace;
  font-size: 13px;
  line-height: 1.5;
  margin: 16px 0;
}

.preview-actions {
  display: flex;
  gap: 10px;
  justify-content: flex-end;
}

.import-btn, .cancel-btn {
  padding: 8px 16px;
  border-radius: 4px;
  cursor: pointer;
  border: none;
}

.import-btn {
  background: #1890ff;
  color: white;
}

.import-btn:hover {
  background: #40a9ff;
}

.cancel-btn {
  background: #f0f0f0;
  color: #333;
}

.cancel-btn:hover {
  background: #e0e0e0;
}
</style>
