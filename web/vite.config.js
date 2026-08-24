import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { execSync } from 'node:child_process'

let commit = 'dev'
try {
  commit = execSync('git rev-parse --short HEAD').toString().trim()
} catch { /* no git — keep dev */ }
const builtAt = new Date().toISOString().slice(5, 16).replace('T', ' ')

export default defineConfig({
  plugins: [react()],
  define: {
    __CLIENT_VERSION__: JSON.stringify(`${commit} · ${builtAt}`),
  },
  server: {
    proxy: { '/api': 'http://localhost:8000' }
  },
  build: { outDir: 'dist' }
})
