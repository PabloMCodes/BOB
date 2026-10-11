import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig, loadEnv } from 'vite'

export default defineConfig(({ mode }) => ({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      '/_bob/hub': {
        target: loadEnv(mode, process.cwd(), 'VITE_').VITE_HUB_URL || 'http://127.0.0.1:8780',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/_bob\/hub/, ''),
      },
    },
  },
}))
