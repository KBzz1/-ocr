import react from '@vitejs/plugin-react';
import { defineConfig } from 'vitest/config';

export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: 5173,
    strictPort: false,
    allowedHosts: true,
    proxy: {
      '/api': 'http://127.0.0.1:8081'
    }
  },
  preview: {
    host: '127.0.0.1',
    port: 4173,
    strictPort: false
  },
  build: {
    assetsInlineLimit: 0,
    sourcemap: false
  },
  test: {
    environment: 'jsdom',
    environmentOptions: {
      jsdom: {
        url: 'http://127.0.0.1:5173/'
      }
    },
    globals: true,
    exclude: ['node_modules', 'dist', 'tests/e2e/**'],
    setupFiles: ['./tests/setupTests.ts'],
    restoreMocks: true,
    clearMocks: true,
    mockReset: true
  }
});
