import { defineStore } from 'pinia'
import { api } from '@/api'

const KEY = 'api_key'
const NAME = 'username'

export const useAuthStore = defineStore('auth', {
  state: () => ({
    apiKey: localStorage.getItem(KEY) || '',
    username: localStorage.getItem(NAME) || ''
  }),
  getters: {
    isLoggedIn: (s) => !!s.apiKey
  },
  actions: {
    async login(username, password) {
      const res = await api.login({ username, password })
      this.setSession(res.data, username)
      return res
    },
    async register(username, password) {
      return await api.register({ username, password })
    },
    setSession(apiKey, username) {
      this.apiKey = apiKey
      this.username = username
      localStorage.setItem(KEY, apiKey)
      localStorage.setItem(NAME, username)
    },
    logout() {
      this.apiKey = ''
      this.username = ''
      localStorage.removeItem(KEY)
      localStorage.removeItem(NAME)
    }
  }
})