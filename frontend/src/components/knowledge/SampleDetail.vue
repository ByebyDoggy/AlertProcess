<template>
  <div class="modal-overlay" @click.self="$emit('close')">
    <div class="modal-dialog detail-dialog">
      <div class="modal-header">
        <h3>{{ sample.title }}</h3>
        <button class="modal-close" @click="$emit('close')">&times;</button>
      </div>
      <div class="modal-body">
        <!-- 基本信息 -->
        <div class="detail-grid">
          <div class="detail-item">
            <span class="detail-label">分类</span>
            <span class="detail-badge" :class="'cat-' + sample.category">
              {{ store.getCategoryLabel(sample.category) }}
            </span>
          </div>
          <div class="detail-item">
            <span class="detail-label">链 ID</span>
            <span class="detail-value">{{ sample.chain_id }}</span>
          </div>
          <div class="detail-item">
            <span class="detail-label">来源</span>
            <span class="detail-value">{{ sample.source }}</span>
          </div>
          <div class="detail-item" v-if="sample.expected_severity">
            <span class="detail-label">预期严重级别</span>
            <span class="severity-badge" :class="'sev-' + (sample.expected_severity || '').toLowerCase()">
              {{ sample.expected_severity }}
            </span>
          </div>
          <div class="detail-item" v-if="sample.expected_min_score">
            <span class="detail-label">预期最低评分</span>
            <span class="detail-value">{{ sample.expected_min_score }}</span>
          </div>
        </div>

        <div v-if="sample.description" class="detail-section">
          <div class="detail-section-title">描述</div>
          <p class="detail-text">{{ sample.description }}</p>
        </div>

        <!-- 标签 -->
        <div v-if="sample.tags && sample.tags.length" class="detail-section">
          <div class="detail-section-title">标签</div>
          <div class="tag-list">
            <span v-for="tag in sample.tags" :key="tag" class="tag-item">{{ tag }}</span>
          </div>
        </div>

        <!-- 地址信息 -->
        <div class="detail-section">
          <div class="detail-section-title">交易信息</div>
          <div class="addr-list">
            <div class="addr-row" v-if="sample.tx_hash">
              <span class="addr-label">Tx Hash</span>
              <code class="addr-value">{{ sample.tx_hash }}</code>
            </div>
            <div class="addr-row" v-if="sample.attacked_address">
              <span class="addr-label">攻击地址</span>
              <code class="addr-value">{{ sample.attacked_address }}</code>
            </div>
            <div class="addr-row" v-if="sample.exploiter_address">
              <span class="addr-label">攻击者</span>
              <code class="addr-value">{{ sample.exploiter_address }}</code>
            </div>
          </div>
        </div>

        <!-- 预期标签 -->
        <div v-if="sample.expected_labels && sample.expected_labels.length" class="detail-section">
          <div class="detail-section-title">预期标签</div>
          <div class="tag-list">
            <span v-for="tag in sample.expected_labels" :key="tag" class="tag-item tag-expected">{{ tag }}</span>
          </div>
        </div>

        <!-- 告警数据 -->
        <div class="detail-section">
          <div class="detail-section-title">告警数据 (alert_data)</div>
          <pre class="json-block">{{ JSON.stringify(sample.alert_data, null, 2) }}</pre>
        </div>

        <!-- 浏览器链接 -->
        <div v-if="sample.tx_explorer_url" class="detail-section">
          <a :href="sample.tx_explorer_url" target="_blank" class="explorer-link">
            &#128279; 在区块浏览器中查看
          </a>
        </div>

        <div class="detail-meta">
          创建: {{ formatDate(sample.created_at) }} | 更新: {{ formatDate(sample.updated_at) }}
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { useKnowledgeBaseStore } from '@/stores/knowledgeBase.js'

defineProps({
  sample: { type: Object, required: true },
})
defineEmits(['close'])

const store = useKnowledgeBaseStore()

function formatDate(dt) {
  if (!dt) return ''
  return new Date(dt).toLocaleString('zh-CN')
}
</script>

<style scoped>
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.6);
  backdrop-filter: blur(6px);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 200;
}
.modal-dialog {
  background: #1e1e38;
  border: 1px solid #2d2d50;
  border-radius: 16px;
  width: 90%;
  max-height: 85vh;
  display: flex;
  flex-direction: column;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.5);
}
.detail-dialog {
  max-width: 700px;
}
.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px;
  border-bottom: 1px solid #2d2d50;
}
.modal-header h3 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
}
.modal-close {
  background: none;
  border: none;
  color: #94a3b8;
  font-size: 20px;
  cursor: pointer;
  padding: 4px;
  line-height: 1;
}
.modal-close:hover {
  color: #e2e8f0;
}
.modal-body {
  padding: 20px;
  overflow-y: auto;
  flex: 1;
}
.detail-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin-bottom: 16px;
}
.detail-item {
  display: flex;
  align-items: center;
  gap: 6px;
}
.detail-label {
  font-size: 11px;
  color: #6b7280;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}
.detail-value {
  font-size: 13px;
  color: #e2e8f0;
}
.detail-badge {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 6px;
  font-weight: 500;
  background: rgba(99, 102, 241, 0.15);
  color: #a5b4fc;
}
.severity-badge {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 6px;
  font-weight: 600;
}
.sev-low { background: rgba(16, 185, 129, 0.15); color: #34d399; }
.sev-medium { background: rgba(245, 158, 11, 0.15); color: #fbbf24; }
.sev-high { background: rgba(249, 115, 22, 0.15); color: #fb923c; }
.sev-critical { background: rgba(239, 68, 68, 0.15); color: #f87171; }

.detail-section {
  margin-bottom: 16px;
}
.detail-section-title {
  font-size: 12px;
  font-weight: 600;
  color: #94a3b8;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin-bottom: 8px;
}
.detail-text {
  font-size: 13px;
  color: #cbd5e1;
  line-height: 1.6;
  margin: 0;
}
.tag-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.tag-item {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 6px;
  background: rgba(99, 102, 241, 0.1);
  color: #a5b4fc;
  border: 1px solid rgba(99, 102, 241, 0.2);
}
.tag-expected {
  background: rgba(16, 185, 129, 0.1);
  color: #34d399;
  border-color: rgba(16, 185, 129, 0.2);
}
.addr-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.addr-row {
  display: flex;
  align-items: center;
  gap: 8px;
}
.addr-label {
  font-size: 11px;
  color: #6b7280;
  min-width: 70px;
  flex-shrink: 0;
}
.addr-value {
  font-size: 12px;
  color: #a5b4fc;
  background: #16162a;
  padding: 3px 8px;
  border-radius: 6px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 500px;
}
.json-block {
  background: #16162a;
  border: 1px solid #2d2d50;
  border-radius: 8px;
  padding: 12px;
  font-size: 12px;
  color: #94a3b8;
  overflow-x: auto;
  margin: 0;
  max-height: 300px;
  overflow-y: auto;
  font-family: 'SF Mono', 'Fira Code', monospace;
  line-height: 1.5;
}
.explorer-link {
  font-size: 13px;
  color: #6366f1;
  text-decoration: none;
}
.explorer-link:hover {
  text-decoration: underline;
}
.detail-meta {
  font-size: 11px;
  color: #4a4a7a;
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid #2d2d50;
}
</style>
