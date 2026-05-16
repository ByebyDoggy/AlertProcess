import { onMounted } from 'vue'
import { useNodeTypesStore } from '../stores/nodeTypes.js'

/**
 * 节点类型数据 composable
 * 确保节点类型在组件挂载时已加载
 */
export function useNodeTypes() {
  const store = useNodeTypesStore()

  onMounted(() => {
    store.reload()
  })

  return {
    ...store,
  }
}
