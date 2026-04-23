<template>
  <div v-if="tabStore.tabCount > 0" class="tab-bar">
    <div class="tab-bar-inner">
      <div
        v-for="tab in tabStore.tabs"
        :key="tab.id"
        :class="['tab-item', { active: tab.id === tabStore.activeTabId }]"
        @click="$emit('switch', tab.id)"
        @contextmenu.prevent="onContextMenu($event, tab.id)"
      >
        <span class="tab-icon">&#x1F517;</span>
        <span class="tab-name" :title="tab.name">{{ tab.name }}</span>
        <span v-if="tab.isModified" class="tab-modified" title="未保存">&#9679;</span>
        <button
          class="tab-close"
          @click.stop="$emit('close', tab.id)"
          title="关闭"
        >&times;</button>
      </div>
    </div>

    <!-- 右键菜单 -->
    <div
      v-if="contextMenu.visible"
      class="tab-context-menu"
      :style="{ left: contextMenu.x + 'px', top: contextMenu.y + 'px' }"
    >
      <div class="menu-item" @click="closeOthers">关闭其他</div>
      <div class="menu-item" @click="closeRight">关闭右侧</div>
      <div class="menu-item danger" @click="closeThis">关闭</div>
    </div>
  </div>
</template>

<script setup>
import { reactive, onMounted, onUnmounted } from 'vue'
import { useTabStore } from '../../stores/tabStore.js'

const tabStore = useTabStore()
const emit = defineEmits(['switch', 'close', 'closeOthers', 'closeRight'])

const contextMenu = reactive({ visible: false, x: 0, y: 0, tabId: null })

function onContextMenu(e, tabId) {
  contextMenu.visible = true
  contextMenu.x = e.clientX
  contextMenu.y = e.clientY
  contextMenu.tabId = tabId
}

function closeOthers() {
  emit('closeOthers', contextMenu.tabId)
  contextMenu.visible = false
}

function closeRight() {
  emit('closeRight', contextMenu.tabId)
  contextMenu.visible = false
}

function closeThis() {
  emit('close', contextMenu.tabId)
  contextMenu.visible = false
}

function onClickOutside() {
  contextMenu.visible = false
}

onMounted(() => document.addEventListener('click', onClickOutside))
onUnmounted(() => document.removeEventListener('click', onClickOutside))
</script>

<style scoped>
.tab-bar {
  background: #111127;
  border-bottom: 1px solid #2d2d50;
  flex-shrink: 0;
  position: relative;
  user-select: none;
}

.tab-bar-inner {
  display: flex;
  overflow-x: auto;
  overflow-y: hidden;
  scrollbar-width: thin;
  scrollbar-color: #2d2d50 transparent;
}

.tab-bar-inner::-webkit-scrollbar {
  height: 3px;
}
.tab-bar-inner::-webkit-scrollbar-thumb {
  background: #2d2d50;
  border-radius: 2px;
}

.tab-item {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 5px 10px;
  font-size: 12px;
  color: #8888aa;
  background: #16162a;
  border-right: 1px solid #2d2d50;
  cursor: pointer;
  white-space: nowrap;
  min-width: 100px;
  max-width: 180px;
  transition: background 0.15s, color 0.15s;
  position: relative;
}

.tab-item:hover {
  background: #1e1e3a;
  color: #bbbbdd;
}

.tab-item.active {
  background: #1a1a2e;
  color: #e0e0ff;
  border-bottom: 2px solid #6366f1;
  padding-bottom: 3px;
}

.tab-icon {
  font-size: 11px;
  flex-shrink: 0;
}

.tab-name {
  overflow: hidden;
  text-overflow: ellipsis;
  flex: 1;
}

.tab-modified {
  color: #fbbf24;
  font-size: 8px;
  flex-shrink: 0;
  line-height: 1;
}

.tab-close {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 16px;
  height: 16px;
  border: none;
  background: transparent;
  color: #6666aa;
  font-size: 14px;
  line-height: 1;
  border-radius: 3px;
  flex-shrink: 0;
  opacity: 0;
  transition: opacity 0.15s, background 0.15s, color 0.15s;
  cursor: pointer;
  padding: 0;
}

.tab-item:hover .tab-close,
.tab-item.active .tab-close {
  opacity: 1;
}

.tab-close:hover {
  background: #ef4444;
  color: white;
}

/* 右键菜单 */
.tab-context-menu {
  position: fixed;
  z-index: 9999;
  background: #1e1e3a;
  border: 1px solid #2d2d50;
  border-radius: 6px;
  padding: 4px 0;
  min-width: 120px;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.4);
}

.menu-item {
  padding: 6px 14px;
  font-size: 12px;
  color: #ccccee;
  cursor: pointer;
  transition: background 0.12s;
}

.menu-item:hover {
  background: #2d2d50;
}

.menu-item.danger:hover {
  background: #7f1d1d;
  color: #fca5a5;
}
</style>
