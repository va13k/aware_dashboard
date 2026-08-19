import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  base: process.env.VITE_BASE_PATH ?? '/',
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        // The live channel is a WebSocket, and the dev proxy forwards an upgrade
        // only when asked to. Without this `/api/live` fails to connect in `npm
        // run dev` while working in a deployment, where Nginx does the upgrade.
        ws: true,
        rewrite: path => path.replace(/^\/api/, ''),
      },
    },
  },
})
