import { createRouter, createWebHistory } from 'vue-router'
import RuleChainEditor from './views/RuleChainEditor.vue'

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
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

export default router
