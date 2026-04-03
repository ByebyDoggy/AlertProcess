<template>
  <Teleport to="body">
    <div
      v-if="visible && node"
      class="fixed inset-0 bg-black/60 modal-overlay flex items-center justify-center z-50"
      @click.self="$emit('close')"
    >
      <div class="bg-[#1e1e38] rounded-xl p-6 w-full max-w-xl mx-4 border border-[#2d2d50] shadow-2xl max-h-[85vh] flex flex-col">
        <!-- Header -->
        <div class="flex justify-between items-center mb-5 flex-shrink-0">
          <div class="flex items-center gap-3">
            <div class="w-9 h-9 rounded-lg flex items-center justify-center text-lg" :style="{ background: headerBg }">
              {{ nodeType?.icon || '?' }}
            </div>
            <div>
              <h3 class="text-base font-bold text-white">{{ nodeType?.label || '节点配置' }}</h3>
              <p class="text-xs text-gray-400">{{ nodeType?.description || '' }}</p>
            </div>
          </div>
          <button @click="$emit('close')" class="text-gray-500 hover:text-white text-2xl leading-none transition">&times;</button>
        </div>

        <!-- Form body -->
        <div class="flex-1 overflow-y-auto space-y-4 pr-1">
          <!-- Node name -->
          <div>
            <label class="block text-xs font-medium text-gray-400 mb-1.5">节点名称</label>
            <input v-model="formData.label" class="form-input">
          </div>

          <!-- Port manager (multi-input nodes) -->
          <PortManager
            v-if="showPortManager"
            :node-id="node.id"
            :port-keys="formData.config.inputPorts || []"
            @update:port-keys="onPortKeysChange"
          />

          <!-- Dynamic schema form -->
          <div v-if="hasSchemaFields">
            <div class="text-xs font-medium text-gray-400 mb-2">配置参数</div>
            <SchemaForm
              :schema="nodeType.config_schema || {}"
              v-model="formData.config"
            />
          </div>

          <!-- No config hint -->
          <div v-if="!hasSchemaFields && !showPortManager" class="text-xs text-gray-500 text-center py-3">
            此节点无需额外配置
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
import { reactive, computed, watch } from 'vue'
import { useNodeTypesStore } from '../../stores/nodeTypes.js'
import { deepClone } from '../../utils/helpers.js'
import SchemaForm from './SchemaForm.vue'
import PortManager from './PortManager.vue'

const props = defineProps({
  node: { type: Object, default: null },
  visible: { type: Boolean, default: false },
})
const emit = defineEmits(['save', 'close'])

const nodeTypesStore = useNodeTypesStore()

const formData = reactive({ label: '', config: {} })

const nodeType = computed(() => nodeTypesStore.getByName(props.node?.type))

const headerBg = computed(() => {
  const c = nodeType.value?.color || '#6366f1'
  return `${c}22`
})

const hasSchemaFields = computed(() => {
  const props_ = nodeType.value?.config_schema?.properties || {}
  return Object.keys(props_).length > 0
})

const showPortManager = computed(() => {
  const inputs = nodeType.value?.inputs || []
  return inputs.some(p => p.multi)
})

watch(() => props.visible, (v) => {
  if (v && props.node) {
    formData.label = props.node.label
    formData.config = deepClone(props.node.config || {})
  }
})

function onPortKeysChange(newPorts) {
  formData.config.inputPorts = newPorts
}

function onSave() {
  emit('save', {
    ...props.node,
    label: formData.label,
    config: deepClone(formData.config),
  })
}
</script>
