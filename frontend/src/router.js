import { createRouter, createWebHistory } from 'vue-router'
import RuleChainEditor from './views/RuleChainEditor.vue'
import KnowledgeBase from './views/KnowledgeBase.vue'
import ChainAnalysis from './views/ChainAnalysis.vue'
import PoolConfig from './views/PoolConfig.vue'

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
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

export default router
