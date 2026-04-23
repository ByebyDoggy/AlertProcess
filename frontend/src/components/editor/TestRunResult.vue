<template>
  <div class="result-card" :class="{ 'result-pass': result.success, 'result-fail': !result.success, 'result-critical': result.final_severity === 'CRITICAL' }">
    <!-- 头部 -->
    <div class="result-header">
      <div class="result-title">
        <span v-if="runIndex" class="run-order-badge">Step {{ runIndex }}/{{ totalCount }}</span>
        <span class="result-icon">{{ result.success ? '&#10003;' : '&#10007;' }}</span>
        <span>{{ result.sample_title || '自定义数据' }}</span>
      </div>
      <div class="result-badges">
        <span class="badge score-badge">{{ result.final_score.toFixed(1) }} 分</span>
        <span class="badge sev-badge" :class="'sev-' + result.final_severity.toLowerCase()">
          {{ result.final_severity }}
        </span>
        <span v-if="result.expected_matched === true" class="badge match-badge">&#10003; 匹配预期</span>
        <span v-else-if="result.expected_matched === false" class="badge mismatch-badge">&#10007; 不匹配预期</span>
      </div>
    </div>

    <!-- 标签 -->
    <div v-if="result.labels && result.labels.length" class="result-labels">
      <span v-for="label in result.labels" :key="label" class="result-label">{{ label }}</span>
    </div>

    <!-- 错误 -->
    <div v-if="result.errors && result.errors.length" class="result-errors">
      <div v-for="(err, i) in result.errors" :key="i" class="error-item">
        &#9888; {{ err }}
      </div>
    </div>

    <!-- 预期匹配详情 -->
    <div v-if="result.expected_details" class="result-expectations">
      <div class="expect-title">预期匹配详情</div>
      <div v-for="(val, key) in result.expected_details" :key="key" class="expect-item">
        <span class="expect-key">{{ key }}:</span>
        <span class="expect-val">{{ val }}</span>
      </div>
    </div>

    <!-- 节点执行详情 -->
    <div class="result-nodes">
      <div class="nodes-toggle" @click="expanded = !expanded">
        <span>{{ expanded ? '&#9660;' : '&#9654;' }} 节点执行详情</span>
        <span class="nodes-meta">{{ result.node_results?.length || 0 }} 个节点 &middot; {{ result.duration_ms }}ms</span>
      </div>
      <div v-if="expanded" class="nodes-list">
        <div
          v-for="node in result.node_results"
          :key="node.node_id"
          class="node-item"
          :class="{ 'node-pass': node.passed, 'node-fail': !node.passed }"
        >
          <div class="node-row">
            <span class="node-status-icon">{{ node.passed ? '&#10003;' : '&#10007;' }}</span>
            <span class="node-type">{{ node.node_type }}</span>
            <span v-if="node.score" class="node-score">{{ node.score }} 分</span>
            <span class="node-duration">{{ node.duration_ms }}ms</span>
          </div>
          <div v-if="node.error" class="node-error">{{ node.error }}</div>
        </div>
      </div>
    </div>

    <!-- 动作执行 -->
    <div v-if="result.actions_executed && result.actions_executed.length" class="result-actions">
      <div class="actions-title">动作执行</div>
      <div v-for="action in result.actions_executed" :key="action.node_id" class="action-item">
        <span class="action-type">{{ action.node_type || 'action' }}</span>
        <span class="action-status" :class="action.passed ? 'action-sim' : 'action-fail'">
          {{ action.result?.dry_run ? '(模拟)' : '' }} {{ action.passed ? '&#10003;' : '&#10007;' }}
        </span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'

defineProps({
  result: { type: Object, required: true },
  runIndex: { type: Number, default: null },
  totalCount: { type: Number, default: null },
})

const expanded = ref(false)
</script>

<style scoped>
.result-card {
  background: #16162a;
  border: 1px solid #2d2d50;
  border-radius: 12px;
  padding: 14px;
  margin-bottom: 10px;
  transition: background 0.3s ease, box-shadow 0.3s ease;
}
/* CRITICAL 级别 - 动态血红色闪烁背景 */
.result-critical {
  animation: bloodPulse 1.2s ease-in-out infinite;
}
@keyframes bloodPulse {
  0%, 100% {
    background: rgba(80, 0, 0, 0.3);
    box-shadow: 0 0 8px rgba(200, 0, 0, 0.3);
  }
  50% {
    background: rgba(180, 0, 0, 0.55);
    box-shadow: 0 0 20px rgba(220, 20, 20, 0.6), 0 0 40px rgba(180, 0, 0, 0.3);
  }
}
.result-pass {
  border-left: 3px solid #10b981;
}
.result-fail {
  border-left: 3px solid #ef4444;
}
.result-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}
.result-title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  font-weight: 600;
}
.result-pass .result-icon { color: #34d399; }
.result-fail .result-icon { color: #f87171; }
.run-order-badge {
  display: inline-flex;
  align-items: center;
  padding: 1px 7px;
  border-radius: 5px;
  background: rgba(99, 102, 241, 0.15);
  color: #a5b4fc;
  font-size: 10px;
  font-weight: 700;
  font-family: 'SF Mono', 'Fira Code', monospace;
}
.result-badges {
  display: flex;
  gap: 6px;
}
.badge {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 6px;
  font-weight: 500;
}
.score-badge {
  background: rgba(99, 102, 241, 0.15);
  color: #a5b4fc;
}
.sev-badge {
  font-weight: 600;
}
.sev-low { background: rgba(16, 185, 129, 0.12); color: #34d399; }
.sev-medium { background: rgba(245, 158, 11, 0.12); color: #fbbf24; }
.sev-high { background: rgba(249, 115, 22, 0.12); color: #fb923c; }
.sev-critical { background: rgba(239, 68, 68, 0.12); color: #f87171; }
.sev-unknown { background: rgba(107, 114, 128, 0.12); color: #9ca3af; }
.match-badge {
  background: rgba(16, 185, 129, 0.12);
  color: #34d399;
}
.mismatch-badge {
  background: rgba(239, 68, 68, 0.12);
  color: #f87171;
}
.result-labels {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-bottom: 8px;
}
.result-label {
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 4px;
  background: rgba(99, 102, 241, 0.1);
  color: #a5b4fc;
}
.result-errors {
  margin-bottom: 8px;
}
.error-item {
  font-size: 11px;
  color: #f87171;
  padding: 3px 8px;
  background: rgba(239, 68, 68, 0.08);
  border-radius: 4px;
  margin-bottom: 3px;
}
.result-expectations {
  background: rgba(99, 102, 241, 0.05);
  border: 1px solid rgba(99, 102, 241, 0.1);
  border-radius: 8px;
  padding: 10px;
  margin-bottom: 8px;
}
.expect-title {
  font-size: 11px;
  font-weight: 600;
  color: #a5b4fc;
  margin-bottom: 6px;
}
.expect-item {
  font-size: 11px;
  color: #94a3b8;
  margin-bottom: 3px;
  font-family: 'SF Mono', 'Fira Code', monospace;
}
.expect-key {
  color: #a5b4fc;
  margin-right: 4px;
}
.result-nodes {
  border-top: 1px solid #2d2d50;
  padding-top: 8px;
  margin-top: 6px;
}
.nodes-toggle {
  display: flex;
  align-items: center;
  justify-content: space-between;
  cursor: pointer;
  font-size: 12px;
  color: #94a3b8;
  padding: 4px 0;
  user-select: none;
}
.nodes-toggle:hover {
  color: #e2e8f0;
}
.nodes-meta {
  font-size: 10px;
  color: #6b7280;
}
.nodes-list {
  margin-top: 6px;
}
.node-item {
  display: flex;
  flex-direction: column;
  padding: 6px 10px;
  border-radius: 6px;
  margin-bottom: 4px;
  background: rgba(255, 255, 255, 0.02);
}
.node-row {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
}
.node-status-icon {
  font-size: 12px;
  flex-shrink: 0;
}
.node-pass .node-status-icon { color: #34d399; }
.node-fail .node-status-icon { color: #f87171; }
.node-type {
  flex: 1;
  color: #cbd5e1;
  font-family: 'SF Mono', 'Fira Code', monospace;
  font-size: 11px;
}
.node-score {
  color: #fbbf24;
  font-weight: 500;
  font-size: 11px;
}
.node-duration {
  color: #6b7280;
  font-size: 10px;
}
.node-error {
  font-size: 11px;
  color: #f87171;
  margin-top: 3px;
  padding-left: 22px;
}
.result-actions {
  border-top: 1px solid #2d2d50;
  padding-top: 8px;
  margin-top: 6px;
}
.actions-title {
  font-size: 11px;
  font-weight: 600;
  color: #94a3b8;
  margin-bottom: 6px;
}
.action-item {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  padding: 4px 0;
}
.action-type {
  color: #cbd5e1;
  font-family: 'SF Mono', 'Fira Code', monospace;
  font-size: 11px;
}
.action-status {
  font-size: 12px;
}
.action-sim { color: #fbbf24; }
.action-fail { color: #f87171; }
</style>
