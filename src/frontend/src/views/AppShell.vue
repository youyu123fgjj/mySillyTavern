<script setup>
import { onMounted, computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { NSpace, NAvatar, NDropdown, useMessage } from 'naive-ui'
import { useAuthStore } from '@/stores/auth'
import { useSettingsStore } from '@/stores/settings'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const settings = useSettingsStore()
const message = useMessage()

// 导航侧边栏折叠：小屏默认收起，避免占满移动端
const siderCollapsed = ref(false)
const isMobile = () => window.innerWidth < 768
onMounted(() => {
  siderCollapsed.value = isMobile()
  settings.load()
})

const menuOptions = [
  { label: '对话', key: 'chat' },
  { label: '角色卡', key: 'characters' },
  { label: '知识库', key: 'knowledge' },
  { label: '设置', key: 'settings' }
]

const activeKey = computed(() => route.name)

// 移动端点击菜单跳转后自动收起导航抽屉，避免其遮挡目标页面
function onMenuSelect(key) {
  router.push({ name: key })
  if (isMobile()) siderCollapsed.value = true
}

const userOptions = [{ label: '退出登录', key: 'logout' }]

function onUserAction(key) {
  if (key === 'logout') {
    auth.logout()
    message.success('已退出登录')
    router.push('/login')
  }
}
</script>

<template>
  <div class="shell">
    <aside class="sider" :class="{ collapsed: siderCollapsed }">
      <div class="brand-row">
        <div class="brand">My SillyTavern</div>
        <n-button quaternary size="small" class="sider-close" @click="siderCollapsed = true">
          ✕
        </n-button>
      </div>
      <n-menu :value="activeKey" :options="menuOptions" @update:value="onMenuSelect" />
    </aside>
    <div v-if="!siderCollapsed" class="sider-mask" @click="siderCollapsed = true"></div>
    <div class="main">
      <header class="header">
        <div class="header-left">
          <n-button quaternary size="medium" class="menu-toggle" @click="siderCollapsed = !siderCollapsed">
            <template #icon>
              <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2"
                stroke-linecap="round">
                <line x1="3" y1="6" x2="21" y2="6" />
                <line x1="3" y1="12" x2="21" y2="12" />
                <line x1="3" y1="18" x2="21" y2="18" />
              </svg>
            </template>
          </n-button>
          <span class="title">{{ (route.meta && route.meta.title) || '' }}</span>
        </div>
        <n-dropdown :options="userOptions" @select="onUserAction">
          <n-space align="center" class="user">
            <n-avatar round size="small">{{ (auth.username || 'U')[0].toUpperCase() }}</n-avatar>
            <span>{{ auth.username }}</span>
          </n-space>
        </n-dropdown>
      </header>
      <div class="content">
        <router-view />
      </div>
    </div>
  </div>
</template>

<style scoped>
.shell {
  display: flex;
  height: 100vh;
}
.sider {
  width: 180px;
  flex-shrink: 0;
  border-right: 1px solid var(--n-border-color, #eee);
  display: flex;
  flex-direction: column;
  margin-left: 0;
  transition: margin-left 0.2s ease;
}
.sider.collapsed {
  margin-left: -180px;
}
.brand-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-right: 8px;
}
.brand {
  flex: 1;
  padding: 16px;
  font-weight: 700;
  font-size: 16px;
  white-space: nowrap;
}
.sider-close {
  display: none;
  flex-shrink: 0;
}
.sider-mask {
  display: none;
}
.main {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
}
.header {
  height: 52px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 16px;
  border-bottom: 1px solid var(--n-border-color, #eee);
  flex-shrink: 0;
  gap: 12px;
}
.header-left {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}
.title {
  font-weight: 600;
}
.user {
  cursor: pointer;
}
.content {
  flex: 1;
  overflow: hidden;
}
@media (max-width: 767.98px) {
  .sider {
    position: fixed;
    left: 0;
    top: 0;
    bottom: 0;
    z-index: 100;
    background: var(--n-color, #fff);
    box-shadow: 2px 0 12px rgba(0, 0, 0, 0.12);
  }
  /* 抽屉打开时露出关闭按钮与点外关闭遮罩 */
  .sider-close {
    display: inline-flex;
  }
  .sider-mask {
    display: block;
    position: fixed;
    inset: 0;
    z-index: 99;
    background: rgba(0, 0, 0, 0.35);
  }
}
</style>