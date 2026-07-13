import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
    base: '/vue-assets/',
    plugins: [vue()],
    build: {
        outDir: 'dist',
        chunkSizeWarningLimit: 900,
        rollupOptions: {
            output: {
                manualChunks: {
                    'vendor-vue': ['vue', 'vue-router', 'pinia'],
                    'vendor-element': ['element-plus', '@element-plus/icons-vue'],
                    'vendor-echarts': ['echarts'],
                },
            },
        },
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
            '/assets': {
                target: 'http://127.0.0.1:8000',
                changeOrigin: true,
            },
            '/vue-assets': {
                target: 'http://127.0.0.1:8000',
                changeOrigin: true,
            },
            '/k8s': {
                target: 'http://127.0.0.1:8000',
                changeOrigin: true,
            },
            '/containers': {
                target: 'http://127.0.0.1:8000',
                changeOrigin: true,
                ws: true,
            },
        },
    },
    resolve: {
        alias: {
            '@': '/src',
        },
    },
})
