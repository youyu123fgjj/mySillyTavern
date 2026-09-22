<script setup>
import { onMounted, ref } from 'vue'
import { useMessage } from 'naive-ui'
import { useSettingsStore } from '@/stores/settings'

const message = useMessage()
const settings = useSettingsStore()

const temperature = ref(0.7)
const maxTokens = ref(2048)
const theme = ref('light')
const saving = ref(false)

const themeOptions = [
  { label: '浅色', value: 'light' },
  { label: '深色', value: 'dark' }
]

onMounted(async () => {
  await settings.load()
  temperature.value = settings.defaultTemperature
  maxTokens.value = settings.defaultMaxTokens
  theme.value = settings.theme
})

async function save() {
  saving.value = true
  try {
    settings.defaultTemperature = Number(temperature.value)
    settings.defaultMaxTokens = Number(maxTokens.value)
    settings.theme = theme.value
    await settings.save()
    message.success('已保存')
  } catch (e) {
    message.error(e.message)
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <div class="page">
    <div class="card">
      <h3>用户设置</h3>
      <p class="tip">这些作为新角色的默认值；单个角色可单独覆盖。</p>
      <n-form label-placement="top" label-width="160">
        <n-form-item label="默认温度 (temperature)">
          <n-input-number v-model:value="temperature" :min="0" :max="2" :step="0.1" style="width: 200px" />
        </n-form-item>
        <n-form-item label="默认最大 tokens">
          <n-input-number v-model:value="maxTokens" :min="1" :max="8192" :step="128" style="width: 200px" />
        </n-form-item>
        <n-form-item label="主题">
          <n-radio-group v-model:value="theme">
            <n-space>
              <n-radio v-for="o in themeOptions" :key="o.value" :value="o.value">{{ o.label }}</n-radio>
            </n-space>
          </n-radio-group>
        </n-form-item>
      </n-form>
      <n-button type="primary" :loading="saving" @click="save">保存设置</n-button>
    </div>
  </div>
</template>

<style scoped>
.page {
  height: 100%;
  padding: 24px;
  overflow-y: auto;
}
.card {
  max-width: 560px;
}
.tip {
  color: var(--n-text-color-3, #999);
  font-size: 13px;
}
</style>