<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useMessage } from 'naive-ui'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const message = useMessage()
const auth = useAuthStore()

const tab = ref('login')
const username = ref('')
const password = ref('')
const confirm = ref('')
const loading = ref(false)

async function submit() {
  if (!username.value.trim()) return message.warning('请输入用户名')
  if (!password.value) return message.warning('请输入密码')
  if (tab.value === 'register') {
    if (password.value !== confirm.value) return message.warning('两次密码不一致')
    loading.value = true
    try {
      await auth.register(username.value.trim(), password.value)
      message.success('注册成功，请登录')
      tab.value = 'login'
    } catch (e) {
      message.error(e.message)
    } finally {
      loading.value = false
    }
    return
  }
  loading.value = true
  try {
    await auth.login(username.value.trim(), password.value)
    message.success('登录成功')
    router.push('/chat')
  } catch (e) {
    message.error(e.message)
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="page">
    <div class="card">
      <h1 class="brand">My SillyTavern</h1>
      <n-tabs v-model:value="tab" type="line" size="large" animated>
        <n-tab-pane name="login" tab="登录">
          <n-form label-placement="top" @submit.prevent="submit">
            <n-form-item label="用户名">
              <n-input v-model:value="username" placeholder="用户名" />
            </n-form-item>
            <n-form-item label="密码">
              <n-input v-model:value="password" type="password" show-password-on="click" placeholder="密码"
                @keyup.enter="submit" />
            </n-form-item>
            <n-button type="primary" block :loading="loading" @click="submit">登录</n-button>
          </n-form>
        </n-tab-pane>
        <n-tab-pane name="register" tab="注册">
          <n-form label-placement="top">
            <n-form-item label="用户名">
              <n-input v-model:value="username" placeholder="用户名" />
            </n-form-item>
            <n-form-item label="密码">
              <n-input v-model:value="password" type="password" show-password-on="click" placeholder="密码" />
            </n-form-item>
            <n-form-item label="确认密码">
              <n-input v-model:value="confirm" type="password" show-password-on="click" placeholder="确认密码"
                @keyup.enter="submit" />
            </n-form-item>
            <n-button type="primary" block :loading="loading" @click="submit">注册</n-button>
          </n-form>
        </n-tab-pane>
      </n-tabs>
    </div>
  </div>
</template>

<style scoped>
.page {
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #667eea22, #764ba222);
}
.card {
  width: 360px;
  padding: 32px;
  background: var(--n-color, #fff);
  border-radius: 12px;
  box-shadow: 0 8px 40px rgba(0, 0, 0, 0.12);
}
.brand {
  text-align: center;
  margin-bottom: 16px;
  font-size: 24px;
}
</style>