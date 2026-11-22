/// <reference types="vitest/config" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      // xfwd adds X-Forwarded-For so Django rate-limits each visitor by their own IP
      // (pair with NUM_PROXIES=1 in .env); otherwise everyone shares 127.0.0.1.
      '/api': { target: 'http://127.0.0.1:8000', changeOrigin: true, xfwd: true },
      '/ws': { target: 'ws://127.0.0.1:8000', ws: true, changeOrigin: true, xfwd: true },
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    css: false,
    restoreMocks: true,
  },
})
