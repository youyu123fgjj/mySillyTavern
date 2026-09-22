import { defineStore } from 'pinia'
import { api } from '@/api'

export const useSettingsStore = defineStore('settings', {
  state: () => ({
    defaultTemperature: 0.7,
    defaultMaxTokens: 2048,
    theme: 'light'
  }),
  actions: {
    async load() {
      try {
        const res = await api.settingsGet()
        const s = res.data || {}
        this.defaultTemperature = s.default_temperature ?? 0.7
        this.defaultMaxTokens = s.default_max_tokens ?? 2048
        this.theme = s.theme || 'light'
      } catch (e) {
        // 旧账号可能无配置，忽略
      }
    },
    async save() {
      await api.settingsUpdate({
        default_temperature: Number(this.defaultTemperature),
        default_max_tokens: Number(this.defaultMaxTokens),
        theme: this.theme
      })
    }
  }
})