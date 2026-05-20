import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

export default defineConfig(({ command }) => ({
  plugins: [react()],
  base: command === 'build' ? '/static/tienda_dist/' : '/',
  server: {
    proxy: {
      '/api/tienda': 'http://127.0.0.1:5003'
    }
  },
  build: {
    outDir: path.resolve(__dirname, '../app/static/tienda_dist'),
    emptyOutDir: true,
    assetsInlineLimit: 0
  }
}))
