import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
    plugins: [vue()],
    build: {
        outDir: 'dist',
        chunkSizeWarningLimit: 900,
    },
    server: {
        host: '0.0.0.0',
        port: 3000,
        proxy: {
            '/api': {
                target: 'http://127.0.0.1:8000',
                changeOrigin: true,
            },
            '/login': {
                target: 'http://127.0.0.1:8000',
                changeOrigin: true,
            },
            '/logout': {
                target: 'http://127.0.0.1:8000',
                changeOrigin: true,
            },
            '/agent': {
                target: 'http://127.0.0.1:8000',
                changeOrigin: true,
            },
            '/ai': {
                target: 'http://127.0.0.1:8000',
                changeOrigin: true,
            },
            '/vue-assets': {
                target: 'http://127.0.0.1:8000',
                changeOrigin: true,
            },
        },
    },
    resolve: {
        alias: {
            '@': '/src',
        },
    },
})
