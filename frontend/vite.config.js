import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
    base: '/vue-assets/',
    plugins: [vue()],
    build: {
        outDir: 'dist',
        // P1 任务#7: 首屏体积监控 — 警告阈值 500KB，强制细分 chunk
        chunkSizeWarningLimit: 500,
        reportCompressedSize: true,
        rollupOptions: {
            output: {
                // 按业务依赖细分 chunk：echarts/element/element-icons/vue-flow/xterm/markdown 各自独立
                // 仅首页用到的 vendor 进首屏 chunk，其余懒加载
                manualChunks(id) {
                    if (id.includes('node_modules')) {
                        if (id.includes('echarts')) return 'vendor-echarts'
                        if (id.includes('@element-plus/icons-vue')) return 'vendor-element-icons'
                        if (id.includes('element-plus')) return 'vendor-element'
                        if (id.includes('@vue-flow')) return 'vendor-vue-flow'
                        if (id.includes('@xterm') || id.includes('/xterm/')) return 'vendor-xterm'
                        if (id.includes('markdown-it')) return 'vendor-markdown'
                        if (id.includes('vue-router') || id.includes('pinia') || id.includes('@vue/')) return 'vendor-vue'
                        if (id.includes('axios')) return 'vendor-axios'
                        return 'vendor'
                    }
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
                proxyTimeout: 300000,
                timeout: 300000,
            },
            '/ai': {
                target: 'http://127.0.0.1:8000',
                changeOrigin: true,
            },
            '/assets': {
                target: 'http://127.0.0.1:8000',
                changeOrigin: true,
            },
            '/metrics': {
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
            '/tenant': {
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
