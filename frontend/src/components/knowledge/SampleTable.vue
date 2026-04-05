<template>
  <div>
    <!-- 搜索与筛选栏 -->
    <div class="filter-bar">
      <div class="filter-left">
        <div class="search-box">
          <span class="search-icon">&#128269;</span>
          <input
            v-model="store.filterSearch"
            class="form-input search-input"
            placeholder="搜索标题..."
            @input="debouncedSearch"
          />
        </div>
        <select v-model="store.filterCategory" class="form-select filter-select" @change="store.fetchSamples()">
          <option value="">全部分类</option>
          <option v-for="cat in store.categories" :key="cat.value" :value="cat.value">
            {{ cat.label }}
          </option>
        </select>
        <select v-model="store.filterChainId" class="form-select filter-select" @change="store.fetchSamples()">
          <option :value="null">全部链</option>
          <option :value="1">Ethereum (1)</option>
          <option :value="56">BSC (56)</option>
          <option :value="137">Polygon (137)</option>
          <option :value="42161">Arbitrum (42161)</option>
          <option :value="10">Optimism (10)</option>
        </select>
      </div>
      <div class="filter-right">
        <button class="btn btn-ghost btn-sm" @click="store.resetFilters(); store.fetchSamples()">
          重置
        </button>
        <button class="btn btn-ghost btn-sm" @click="$emit('export')">
          导出
        </button>
        <button class="btn btn-primary btn-sm" @click="$emit('create')">
          + 新建样本
        </button>
      </div>
    </div>

    <!-- 表格 -->
    <div class="table-wrapper">
      <table v-if="store.samples.length" class="kb-table">
        <thead>
          <tr>
            <th>标题</th>
            <th>分类</th>
            <th>链 ID</th>
            <th>交易哈希</th>
            <th>标签</th>
            <th>预期严重级别</th>
            <th>来源</th>
            <th>更新时间</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="s in store.samples" :key="s.id" class="table-row">
            <td class="td-title">
              <span class="title-text" @click="$emit('detail', s)">{{ s.title }}</span>
            </td>
            <td>
              <span class="cat-badge">{{ store.getCategoryLabel(s.category) }}</span>
            </td>
            <td>{{ s.chain_id }}</td>
            <td class="td-hash">
              <code>{{ shortenHash(s.tx_hash) }}</code>
            </td>
            <td class="td-tags">
              <span v-for="tag in (s.tags || []).slice(0, 3)" :key="tag" class="tag-chip">{{ tag }}</span>
              <span v-if="(s.tags || []).length > 3" class="tag-more">+{{ s.tags.length - 3 }}</span>
            </td>
            <td>
              <span v-if="s.expected_severity" class="sev-badge" :class="'sev-' + s.expected_severity.toLowerCase()">
                {{ s.expected_severity }}
              </span>
              <span v-else class="text-muted">--</span>
            </td>
            <td>
              <span :class="['source-badge', 'source-' + s.source]">{{ sourceLabel(s.source) }}</span>
            </td>
            <td class="td-time">{{ formatTime(s.updated_at) }}</td>
            <td class="td-actions">
              <button class="action-btn" title="查看详情" @click="$emit('detail', s)">&#128065;</button>
              <button class="action-btn" title="编辑" @click="$emit('edit', s)">&#9998;</button>
              <button class="action-btn action-btn-danger" title="删除" @click="confirmDelete(s)">&#128465;</button>
            </td>
          </tr>
        </tbody>
      </table>

      <!-- 空状态 -->
      <div v-else-if="!store.loading" class="empty-state">
        <div class="empty-icon">&#128218;</div>
        <p class="empty-text">暂无样本数据</p>
        <button class="btn btn-ghost btn-sm" @click="$emit('create')">
          + 创建第一个样本
        </button>
      </div>
    </div>

    <!-- 加载更多 -->
    <div v-if="store.hasMore && store.samples.length > 0" class="load-more">
      <button class="btn btn-ghost btn-sm" :disabled="store.loading" @click="store.loadMore()">
        {{ store.loading ? '加载中...' : '加载更多' }}
      </button>
      <span class="load-count">已加载 {{ store.totalLoaded }} 条</span>
    </div>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { useKnowledgeBaseStore } from '@/stores/knowledgeBase.js'

defineEmits(['create', 'edit', 'detail', 'export'])

const store = useKnowledgeBaseStore()
let debounceTimer = null

function debouncedSearch() {
  clearTimeout(debounceTimer)
  debounceTimer = setTimeout(() => store.fetchSamples(), 300)
}

function shortenHash(hash) {
  if (!hash || hash.length < 14) return hash || ''
  return hash.slice(0, 8) + '...' + hash.slice(-6)
}

function formatTime(dt) {
  if (!dt) return ''
  const d = new Date(dt)
  const month = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  const hour = String(d.getHours()).padStart(2, '0')
  const min = String(d.getMinutes()).padStart(2, '0')
  return `${month}-${day} ${hour}:${min}`
}

function sourceLabel(source) {
  const map = { preset: '预置', manual: '手动', import: '导入', forta: 'Forta', api: 'API' }
  return map[source] || source
}

async function confirmDelete(sample) {
  if (!confirm(`确定删除样本 "${sample.title}" 吗？`)) return
  try {
    await store.removeSample(sample.id)
  } catch (e) {
    alert('删除失败: ' + e.message)
  }
}

onMounted(() => {
  store.fetchCategories()
})
</script>

<style scoped>
.filter-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  border-bottom: 1px solid #2d2d50;
  gap: 12px;
  flex-wrap: wrap;
}
.filter-left {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1;
  min-width: 0;
}
.filter-right {
  display: flex;
  gap: 6px;
  flex-shrink: 0;
}
.search-box {
  position: relative;
  flex: 1;
  max-width: 260px;
}
.search-icon {
  position: absolute;
  left: 10px;
  top: 50%;
  transform: translateY(-50%);
  font-size: 14px;
  opacity: 0.5;
}
.search-input {
  padding-left: 32px !important;
}
.filter-select {
  width: auto;
  min-width: 120px;
}
.btn {
  padding: 6px 12px;
  border-radius: 8px;
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  border: none;
  transition: all 0.15s;
}
.btn-sm {
  padding: 5px 10px;
  font-size: 11px;
}
.btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.btn-ghost {
  background: transparent;
  color: #94a3b8;
  border: 1px solid #2d2d50;
}
.btn-ghost:hover:not(:disabled) {
  background: rgba(99, 102, 241, 0.08);
  color: #e2e8f0;
}
.btn-primary {
  background: #6366f1;
  color: white;
}
.btn-primary:hover:not(:disabled) {
  background: #4f46e5;
}

.table-wrapper {
  overflow-x: auto;
}
.kb-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}
.kb-table th {
  text-align: left;
  padding: 10px 12px;
  color: #6b7280;
  font-weight: 600;
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  border-bottom: 1px solid #2d2d50;
  white-space: nowrap;
}
.kb-table td {
  padding: 10px 12px;
  border-bottom: 1px solid rgba(45, 45, 80, 0.5);
  white-space: nowrap;
}
.table-row:hover {
  background: rgba(99, 102, 241, 0.04);
}
.td-title {
  max-width: 200px;
}
.title-text {
  color: #e2e8f0;
  cursor: pointer;
  font-weight: 500;
}
.title-text:hover {
  color: #6366f1;
}
.td-hash code {
  font-size: 11px;
  color: #a5b4fc;
  background: rgba(99, 102, 241, 0.08);
  padding: 2px 6px;
  border-radius: 4px;
}
.td-tags {
  max-width: 160px;
}
.tag-chip {
  display: inline-block;
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 4px;
  background: rgba(99, 102, 241, 0.1);
  color: #a5b4fc;
  margin-right: 3px;
}
.tag-more {
  font-size: 10px;
  color: #6b7280;
}
.cat-badge {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 6px;
  background: rgba(99, 102, 241, 0.12);
  color: #a5b4fc;
}
.sev-badge {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 6px;
  font-weight: 600;
}
.sev-low { background: rgba(16, 185, 129, 0.12); color: #34d399; }
.sev-medium { background: rgba(245, 158, 11, 0.12); color: #fbbf24; }
.sev-high { background: rgba(249, 115, 22, 0.12); color: #fb923c; }
.sev-critical { background: rgba(239, 68, 68, 0.12); color: #f87171; }
.text-muted {
  color: #4a4a7a;
}
.source-badge {
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 4px;
  background: rgba(107, 114, 128, 0.15);
  color: #9ca3af;
}
.source-preset {
  background: rgba(16, 185, 129, 0.1);
  color: #34d399;
}
.td-time {
  color: #6b7280;
  font-size: 11px;
}
.td-actions {
  display: flex;
  gap: 4px;
}
.action-btn {
  background: none;
  border: none;
  font-size: 14px;
  cursor: pointer;
  padding: 4px 6px;
  border-radius: 6px;
  transition: background 0.15s;
}
.action-btn:hover {
  background: rgba(99, 102, 241, 0.12);
}
.action-btn-danger:hover {
  background: rgba(239, 68, 68, 0.12);
}

.empty-state {
  text-align: center;
  padding: 60px 20px;
}
.empty-icon {
  font-size: 48px;
  margin-bottom: 12px;
  opacity: 0.4;
}
.empty-text {
  color: #6b7280;
  font-size: 14px;
  margin-bottom: 16px;
}

.load-more {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 12px;
}
.load-count {
  font-size: 11px;
  color: #6b7280;
}
</style>
