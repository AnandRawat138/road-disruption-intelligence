// Kept identical to vite.config.ts (Vite loads vite.config.js first).
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Development server only. In production the backend serves the built files from dist/.
export default defineConfig({
  plugins: [react()],
  server: {
    host: '127.0.0.1',
    port: 5173,
    proxy: { '/api': { target: 'http://127.0.0.1:8000', changeOrigin: false } },
  },
  build: { chunkSizeWarningLimit: 1500, sourcemap: false },
})
