import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath, URL } from 'node:url'

// 后端 FastAPI 运行在 localhost:9000，接口与前端使用相同路径前缀。
// 开发时把后端各前缀代理过去，无需路径重写；生产时由后端直接提供服务。
const backend = {
  target: 'http://localhost:9000',
  changeOrigin: true
}

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) }
  },
  server: {
    port: 5173,
    proxy: {
      '/user': backend,
      '/chat': backend,
      '/knowledge': backend,
      '/session': backend,
      '/message': backend,
      '/review': backend,
      '/log': backend,
      '/admin': backend
    }
  }
})