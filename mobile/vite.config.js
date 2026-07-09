import { defineConfig } from 'vite'
import path from 'path'
import uni from '@dcloudio/vite-plugin-uni'

export default defineConfig({
    plugins: [uni()],
    base: '/mobile-app/',
    server: {
        port: 5173,
        host: '0.0.0.0',
        proxy: {
            '/api': {
                target: 'http://127.0.0.1:8000',
                changeOrigin: true
            },
            '/login': {
                target: 'http://127.0.0.1:8000',
                changeOrigin: true
            },
            '/logout': {
                target: 'http://127.0.0.1:8000',
                changeOrigin: true
            },
            '/me': {
                target: 'http://127.0.0.1:8000',
                changeOrigin: true
            },
            '/alerts': {
                target: 'http://127.0.0.1:8000',
                changeOrigin: true
            },
            '/assets': {
                target: 'http://127.0.0.1:8000',
                changeOrigin: true
            },
            '/agent': {
                target: 'http://127.0.0.1:8000',
                changeOrigin: true
            },
            '/agent-workflow': {
                target: 'http://127.0.0.1:8000',
                changeOrigin: true
            },
            '/workflow': {
                target: 'http://127.0.0.1:8000',
                changeOrigin: true
            },
            '/mobile': {
                target: 'http://127.0.0.1:8000',
                changeOrigin: true
            }
        }
    },
    resolve: {
        alias: {
            '@': path.resolve(__dirname, './src')
        }
    }
})
