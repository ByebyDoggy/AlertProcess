import { createRouter, createWebHistory } from 'vue-router'
import RuleChainEditor from './views/RuleChainEditor.vue'
import KnowledgeBase from './views/KnowledgeBase.vue'
import ChainAnalysis from './views/ChainAnalysis.vue'
import PoolConfig from './views/PoolConfig.vue'
import SystemConfig from './views/SystemConfig.vue'
import NodeDocsView from './views/NodeDocsView.vue'
import ScriptEditorDemo from './views/ScriptEditorDemo.vue'

const routes = [
  {
    path: '/',
    redirect: '/rule-chain',
  },
  {
    path: '/rule-chain',
    name: 'RuleChain',
    component: RuleChainEditor,
  },
  {
    path: '/node-docs',
    name: 'NodeDocs',
    component: NodeDocsView,
  },
  {
    path: '/knowledge-base',
    name: 'KnowledgeBase',
    component: KnowledgeBase,
  },
  {
    path: '/chain-analysis',
    name: 'ChainAnalysis',
    component: ChainAnalysis,
    meta: { title: 'Chain Analysis' }
  },
  {
    path: '/pool-config',
    name: 'PoolConfig',
    component: PoolConfig,
    meta: { title: 'Pool Configuration' }
  },
  {
    path: '/system-config',
    name: 'SystemConfig',
    component: SystemConfig,
    meta: { title: 'System Configuration' }
  },
  {
    path: '/script-editor-demo',
    name: 'ScriptEditorDemo',
    component: ScriptEditorDemo,
    meta: { title: 'Script Editor Demo' }
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

export default router
