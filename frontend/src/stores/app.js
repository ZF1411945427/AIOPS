import { defineStore } from 'pinia'
import { ref, watch } from 'vue'
import request from '@/api/request'

export const useAppStore = defineStore('app', () => {
    const sidebarCollapsed = ref(false)
    const theme = ref(localStorage.getItem('aiops-theme') || 'light')
    const colorScheme = ref(localStorage.getItem('aiops-color-scheme') || 'indigo')
    const dbMode = ref(localStorage.getItem('aiops-db-mode') || 'demo')

    function toggleSidebar() {
        sidebarCollapsed.value = !sidebarCollapsed.value
    }

    function toggleTheme() {
        theme.value = theme.value === 'dark' ? 'light' : 'dark'
    }

    function setColorScheme(scheme) {
        colorScheme.value = scheme
    }

    async function fetchDbMode() {
        try {
            const data = await request.get('/api/system/db-mode')
            dbMode.value = data.mode
            localStorage.setItem('aiops-db-mode', data.mode)
        } catch (e) {
            console.error('获取数据库模式失败:', e)
        }
    }

    async function switchDbMode(mode) {
        try {
            const data = await request.post('/api/system/db-switch', { mode })
            dbMode.value = data.mode
            localStorage.setItem('aiops-db-mode', data.mode)
            return data
        } catch (e) {
            console.error('切换数据库模式失败:', e)
            throw e
        }
    }

    watch(theme, (val) => {
        localStorage.setItem('aiops-theme', val)
        document.documentElement.setAttribute('data-theme', val)
    }, { immediate: true })

    watch(colorScheme, (val) => {
        localStorage.setItem('aiops-color-scheme', val)
        document.documentElement.setAttribute('data-color-scheme', val)
    }, { immediate: true })

    watch(dbMode, (val) => {
        localStorage.setItem('aiops-db-mode', val)
    })

    return {
        sidebarCollapsed, theme, colorScheme, dbMode,
        toggleSidebar, toggleTheme, setColorScheme,
        fetchDbMode, switchDbMode,
    }
})
