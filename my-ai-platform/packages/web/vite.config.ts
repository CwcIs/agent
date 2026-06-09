import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    proxy: {
      '/chat': 'http://localhost:8000',
      '/notes': 'http://localhost:8000',
      '/digest': 'http://localhost:8000',
    },
  },
})
