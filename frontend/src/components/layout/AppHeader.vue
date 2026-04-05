<template>
  <header class="app-header">
    <div class="header-left">
      <router-link to="/" class="header-logo">
        <span class="logo-icon">&#9888;</span>
        <span class="logo-text">AlertProcessor</span>
      </router-link>
    </div>
    <nav class="header-nav">
      <router-link
        v-for="item in navItems"
        :key="item.path"
        :to="item.path"
        class="nav-link"
        active-class="nav-link-active"
      >
        <span class="nav-icon">{{ item.icon }}</span>
        <span>{{ item.label }}</span>
      </router-link>
    </nav>
  </header>
</template>

<script setup>
const navItems = [
  { path: '/rule-chain', label: '规则链编辑器', icon: '\u26A1' },
  { path: '/knowledge-base', label: '知识库', icon: '\uD83D\uDCDA' },
]
</script>

<style scoped>
.app-header {
  height: 48px;
  background: #16162a;
  border-bottom: 1px solid #2d2d50;
  display: flex;
  align-items: center;
  padding: 0 16px;
  gap: 24px;
  flex-shrink: 0;
  z-index: 100;
}
.header-left {
  flex-shrink: 0;
}
.header-logo {
  display: flex;
  align-items: center;
  gap: 8px;
  text-decoration: none;
  color: #e2e8f0;
  font-weight: 700;
  font-size: 14px;
}
.logo-icon {
  font-size: 18px;
  color: #f59e0b;
}
.header-nav {
  display: flex;
  gap: 4px;
}
.nav-link {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 14px;
  border-radius: 8px;
  font-size: 13px;
  color: #94a3b8;
  text-decoration: none;
  transition: all 0.15s;
}
.nav-link:hover {
  color: #e2e8f0;
  background: rgba(99, 102, 241, 0.08);
}
.nav-link-active {
  color: #e2e8f0;
  background: rgba(99, 102, 241, 0.15);
  font-weight: 500;
}
.nav-icon {
  font-size: 14px;
}
</style>
