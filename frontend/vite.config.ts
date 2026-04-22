import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  // Serve card art assets from project root
  publicDir: 'public',
  server: {
    port: 3000,
    proxy: {
      '/api': {
        target: 'http://localhost:8030',
        changeOrigin: true,
      },
      '/socket.io': {
        target: 'http://localhost:8030',
        changeOrigin: true,
        ws: true,
      },
    },
    // Serve assets from project root for card art
    fs: {
      allow: ['..'],
    },
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          // socket.io-client — bulky, used by all modes
          if (id.includes('node_modules/socket.io-client') || id.includes('node_modules/engine.io-client')) {
            return 'vendor-socketio';
          }
          // framer-motion — heavy animation lib used mainly by PKM/YGO
          if (id.includes('node_modules/framer-motion')) {
            return 'vendor-framer-motion';
          }
          // zustand — small but isolate for clarity
          if (id.includes('node_modules/zustand')) {
            return 'vendor-zustand';
          }
          // React core
          if (id.includes('node_modules/react-dom') || id.includes('node_modules/react/') || id.includes('node_modules/react-router')) {
            return 'vendor-react';
          }
        },
      },
    },
  },
})
