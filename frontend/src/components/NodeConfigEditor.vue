<template>
  <Teleport to="body">
    <div v-if="visible && node" class="fixed inset-0 bg-black/60 modal-overlay flex items-center justify-center z-50" @click.self="$emit('close')">
      <div class="bg-[#1e1e38] rounded-xl p-6 w-full max-w-xl mx-4 border border-[#2d2d50] shadow-2xl max-h-[85vh] flex flex-col">
        <!-- Header -->
        <div class="flex justify-between items-center mb-5 flex-shrink-0">
          <div class="flex items-center gap-3">
            <div class="w-9 h-9 rounded-lg flex items-center justify-center text-lg" :style="{ background: typeInfo?.lightBg }">
              {{ typeInfo?.icon }}
            </div>
            <div>
              <h3 class="text-base font-bold text-white">节点配置</h3>
              <p class="text-xs text-gray-400">{{ typeInfo?.description }}</p>
            </div>
          </div>
          <button @click="$emit('close')" class="text-gray-500 hover:text-white text-2xl leading-none transition">&times;</button>
        </div>

        <!-- Form body (scrollable) -->
        <div class="flex-1 overflow-y-auto space-y-4 pr-1">
          <!-- Node name -->
          <div>
            <label class="block text-xs font-medium text-gray-400 mb-1.5">节点名称</label>
            <input v-model="formData.label" class="form-input">
          </div>

          <!-- Detector type selector -->
          <div v-if="node.type === 'detector'">
            <label class="block text-xs font-medium text-gray-400 mb-1.5">检测器类型</label>
            <select v-model="formData.config.detectorType" class="form-select" @change="onDetectorTypeChange">
              <option v-for="d in detectorOptions" :key="d.value" :value="d.value">{{ d.label }}</option>
            </select>

            <!-- Detector-specific config -->
            <div v-if="currentDetectorFields.length > 0" class="mt-4 p-3 rounded-lg bg-[#16162a] border border-[#2d2d50]">
              <div class="text-xs font-medium text-gray-300 mb-3 flex items-center gap-2">
                <span class="var-tag">{{ formData.config.detectorType }}</span>
                <span>参数配置</span>
              </div>
              <div class="space-y-3">
                <div v-for="field in currentDetectorFields" :key="field.key">
                  <label class="block text-xs text-gray-400 mb-1">{{ field.description || field.key }}</label>
                  <!-- Boolean -->
                  <label v-if="field.type === 'boolean'" class="flex items-center gap-2 cursor-pointer">
                    <input type="checkbox" v-model="formData.config.detectorParams[field.key]"
                      class="w-4 h-4 rounded bg-[#16162a] border-[#2d2d50]">
                    <span class="text-xs text-gray-300">启用</span>
                  </label>
                  <!-- Number / Integer -->
                  <input v-else-if="field.type === 'number' || field.type === 'integer'" type="number"
                    v-model="formData.config.detectorParams[field.key]" class="form-input">
                  <!-- String / default -->
                  <input v-else-if="field.type === 'string'" type="text"
                    v-model="formData.config.detectorParams[field.key]" class="form-input">
                  <!-- Object / Array - show JSON hint -->
                  <div v-else class="text-xs text-gray-500 p-2 rounded bg-[#0f0f24]">
                    <span class="text-gray-400">{{ field.type }}</span>: 使用默认值
                    <span class="text-gray-600 ml-1">{{ JSON.stringify(field.default)?.substring(0, 50) }}</span>
                  </div>
                </div>
              </div>
            </div>

            <!-- Output variables -->
            <div v-if="node.type === 'detector'" class="mt-4 p-3 rounded-lg border border-[#2d2d50]">
              <div class="text-xs font-medium text-gray-400 mb-2">输出变量</div>
              <div class="flex flex-wrap gap-1.5">
                <span class="var-tag" v-for="v in typeInfo?.variables" :key="v.key" v-text="varExpr(v.key)"></span>
              </div>
            </div>
          </div>

          <!-- Condition logic -->
          <div v-if="node.type === 'condition'">
            <label class="block text-xs font-medium text-gray-400 mb-1.5">逻辑方式</label>
            <div class="flex gap-2 mb-3">
              <button v-for="opt in logicOptions" :key="opt.value"
                @click="formData.config.logic = opt.value"
                :class="['px-3 py-1.5 rounded-lg text-xs font-medium transition',
                  formData.config.logic === opt.value ? 'bg-indigo-600 text-white' : 'bg-[#16162a] text-gray-400 border border-[#2d2d50] hover:border-[#4a4a7a]']">
                {{ opt.label }}
              </button>
            </div>

            <!-- Conditions list -->
            <div class="space-y-2">
              <div v-for="(cond, idx) in formData.config.conditions" :key="idx" class="condition-row">
                <input v-model="cond.field" placeholder="变量引用" class="form-input text-xs !py-1.5 !px-2" style="min-width: 120px;">
                <select v-model="cond.operator" class="form-select text-xs !py-1.5 !px-2" style="min-width: 90px;">
                  <option v-for="op in operators" :key="op.value" :value="op.value">{{ op.label }}</option>
                </select>
                <input v-if="!['is_true', 'is_false', 'exists'].includes(cond.operator)"
                  v-model="cond.value" placeholder="值" class="form-input text-xs !py-1.5 !px-2" style="min-width: 100px;">
                <button @click="removeCondition(idx)" class="text-red-400 hover:text-red-300 text-sm px-1">&times;</button>
              </div>
              <button @click="addCondition" class="text-xs text-indigo-400 hover:text-indigo-300 transition">
                + 添加条件
              </button>
            </div>

            <!-- Variable hint -->
            <div class="mt-3 p-2.5 rounded-lg bg-[#16162a] border border-[#2d2d50]">
              <div class="text-xs text-gray-500">
                变量引用格式: <span class="var-tag" v-text="'{{节点名.变量名}}'"></span>
              </div>
            </div>
          </div>

          <!-- Action type -->
          <div v-if="node.type === 'action'">
            <label class="block text-xs font-medium text-gray-400 mb-1.5">操作类型</label>
            <select v-model="formData.config.actionType" class="form-select">
              <option v-for="opt in actionTypeOptions" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
            </select>

            <div class="mt-3" v-if="formData.config.actionType !== 'annotate_address'">
              <label class="block text-xs font-medium text-gray-400 mb-1.5">参数值</label>
              <input v-model="formData.config.actionValue" :placeholder="actionPlaceholder" class="form-input">
            </div>

            <!-- Annotation type -->
            <div v-if="formData.config.actionType === 'annotate_address'" class="mt-3 space-y-3">
              <div>
                <label class="block text-xs font-medium text-gray-400 mb-1.5">标注类型</label>
                <select v-model="formData.config.annotationType" class="form-select">
                  <option v-for="opt in annotationOptions" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
                </select>
              </div>
              <div>
                <label class="block text-xs font-medium text-gray-400 mb-1.5">目标地址</label>
                <input v-model="formData.config.actionValue" placeholder="输入要标注的地址" class="form-input">
              </div>
            </div>

            <!-- Severity quick-select for set_severity -->
            <div v-if="formData.config.actionType === 'set_severity'" class="mt-3 flex gap-2 flex-wrap">
              <button v-for="sev in severityOptions" :key="sev.value"
                @click="formData.config.actionValue = sev.value"
                :class="['px-2.5 py-1 rounded-lg text-xs font-medium transition border',
                  formData.config.actionValue === sev.value ? 'border-white/30' : 'border-transparent opacity-60 hover:opacity-100']"
                :style="{ background: sev.color }">
                {{ sev.value }}
              </button>
            </div>
          </div>

          <!-- Notifier config -->
          <div v-if="node.type === 'notifier'" class="space-y-3">
            <div>
              <label class="block text-xs font-medium text-gray-400 mb-1.5">通知类型</label>
              <select v-model="formData.config.notifierType" class="form-select">
                <option value="webhook">Webhook</option>
                <option value="telegram">Telegram</option>
              </select>
            </div>
            <div>
              <label class="block text-xs font-medium text-gray-400 mb-1.5">目标地址</label>
              <input v-model="formData.config.targetUrl" :placeholder="formData.config.notifierType === 'telegram' ? 'Telegram Bot Token:Chat ID' : 'https://...'" class="form-input">
            </div>
            <div>
              <label class="block text-xs font-medium text-gray-400 mb-1.5">消息模板</label>
              <textarea v-model="formData.config.messageTemplate"
                placeholder="支持变量: {{trigger.tx_hash}} {{detector.detected}}"
                class="form-textarea" rows="3"></textarea>
              <p class="text-xs text-gray-500 mt-1">使用 <span class="var-tag" v-text="'{{节点名.变量名}}'"></span> 引用上游输出</p>
            </div>
          </div>
        </div>

        <!-- Footer -->
        <div class="flex justify-end gap-2 mt-5 pt-4 border-t border-[#2d2d50] flex-shrink-0">
          <button @click="$emit('close')" class="px-4 py-2 bg-[#16162a] hover:bg-[#252545] rounded-lg text-gray-300 text-sm transition border border-[#2d2d50]">取消</button>
          <button @click="onSave" class="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 rounded-lg text-white text-sm font-medium transition">应用</button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup>
import { reactive, ref, computed, watch, onMounted } from 'vue'
import { NODE_TYPES, CONDITION_OPERATORS, SEVERITY_OPTIONS } from '../config.js'
import { deepClone } from '../utils.js'
import apiService from '../api.js'

const props = defineProps({ node: { type: Object, default: null }, visible: { type: Boolean, default: false } })
const emit = defineEmits(['save', 'close'])

const formData = reactive({ label: '', config: {} })
const allDetectors = ref([])

const typeInfo = computed(() => props.node ? NODE_TYPES[props.node.type] || null : null)

const operators = CONDITION_OPERATORS
const severityOptions = SEVERITY_OPTIONS
const logicOptions = [
  { value: 'and', label: 'AND 全部满足' },
  { value: 'or', label: 'OR 任一满足' },
  { value: 'if', label: 'IF 单一条件' },
]
const actionTypeOptions = [
  { value: 'set_severity', label: '设置严重级别' },
  { value: 'set_score', label: '设置风险评分' },
  { value: 'add_tag', label: '添加标签' },
  { value: 'annotate_address', label: '地址标注' },
]
const annotationOptions = [
  { value: 'hacker', label: '攻击者' },
  { value: 'victim', label: '受害者' },
  { value: 'contract_exploit', label: '合约利用' },
  { value: 'phishing', label: '钓鱼' },
  { value: 'suspicious', label: '可疑' },
  { value: 'safe', label: '安全' },
]

const actionPlaceholder = computed(() => {
  const t = formData.config.actionType
  if (t === 'set_severity') return '选择级别或输入: CRITICAL / HIGH / MEDIUM / LOW'
  if (t === 'set_score') return '输入评分: 0 - 100'
  if (t === 'add_tag') return '输入标签: suspicious, flash_loan'
  return ''
})

const detectorOptions = computed(() => {
  return allDetectors.value.map(d => ({ value: d.type_key, label: d.description }))
})

const currentDetectorFields = computed(() => {
  const dt = formData.config.detectorType
  if (!dt) return []
  const det = allDetectors.value.find(d => d.type_key === dt)
  return det?.config_fields?.filter(f => f.type !== 'object' && f.type !== 'array' && f.key !== 'name' && f.key !== 'enabled') || []
})

function varExpr(key) {
  return `{{${formData.label}.${key}}}`
}

onMounted(async () => {
  try {
    const data = await apiService.getDetectors()
    allDetectors.value = data.detectors || []
  } catch (e) {
    console.warn('Failed to load detectors:', e)
  }
})

watch(() => props.visible, (v) => {
  if (v && props.node) {
    formData.label = props.node.label
    const config = deepClone(props.node.config || {})
    // Ensure detectorParams exists
    if (!config.detectorParams) config.detectorParams = {}
    // Ensure conditions exists
    if (props.node.type === 'condition' && (!config.conditions || config.conditions.length === 0)) {
      config.conditions = [{ field: '', operator: 'equals', value: '' }]
    }
    formData.config = config
  }
})

function onDetectorTypeChange() {
  // Reset detector params when type changes
  const dt = formData.config.detectorType
  const det = allDetectors.value.find(d => d.type_key === dt)
  if (det) {
    formData.config.detectorParams = deepClone(det.default_config || {})
  } else {
    formData.config.detectorParams = {}
  }
}

function addCondition() {
  formData.config.conditions.push({ field: '', operator: 'equals', value: '' })
}

function removeCondition(idx) {
  if (formData.config.conditions.length > 1) {
    formData.config.conditions.splice(idx, 1)
  }
}

function onSave() {
  const saveData = deepClone(formData)
  // For detector: merge detectorParams into top-level config for backend
  if (props.node.type === 'detector') {
    delete saveData.config.detectorParams
    // The detectorParams are already part of config via v-model
  }
  emit('save', { ...props.node, label: saveData.label, config: saveData.config })
}
</script>
