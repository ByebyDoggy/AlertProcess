import { createRouter, createWebHistory } from 'vue-router'
import RuleChainEditor from './views/RuleChainEditor.vue'
import KnowledgeBase from './views/KnowledgeBase.vue'

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
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

export default router
