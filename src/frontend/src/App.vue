<script setup>
import { computed, onMounted, watch } from 'vue'
import { NMessageProvider, NLoadingBarProvider, NDialogProvider, NConfigProvider } from 'naive-ui'
import { darkTheme } from 'naive-ui'
import { useAuthStore } from '@/stores/auth'
import { useSettingsStore } from '@/stores/settings'

const auth = useAuthStore()
const settings = useSettingsStore()

const theme = computed(() => (settings.theme === 'dark' ? darkTheme : undefined))

onMounted(() => {
  if (auth.isLoggedIn) settings.load()
})

// 深色模式下把页面背景/文字同步成主题色，使 AppShell 等自定义表面跟随主题
watch(
  () => settings.theme,
  (t) => {
    const dark = t === 'dark'
    document.body.style.background = dark ? '#18181c' : '#ffffff'
    document.body.style.color = dark ? '#e5e5e8' : '#1f1f1f'
  },
  { immediate: true }
)
</script>

<template>
  <n-message-provider>
    <n-dialog-provider>
      <n-loading-bar-provider>
        <n-config-provider :theme="theme">
          <router-view />
        </n-config-provider>
      </n-loading-bar-provider>
    </n-dialog-provider>
  </n-message-provider>
</template>