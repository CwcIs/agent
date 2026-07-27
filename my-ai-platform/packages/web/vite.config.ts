import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    proxy: {
      '/chat': 'http://localhost:8000',
      '/notes': 'http://localhost:8000',
      '/digest': 'http://localhost:8000',
      '/traces': 'http://localhost:8000',
      '/user': 'http://localhost:8000',
      '/admin': 'http://localhost:8000',
      '/suggestions': 'http://localhost:8000',
      '/collisions': 'http://localhost:8000',
      '/tags': 'http://localhost:8000',
      '/custom-tools': 'http://localhost:8000',
    },
  },
})
