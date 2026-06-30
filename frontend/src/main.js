import { createApp } from 'vue'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import * as ElementPlusIconsVue from '@element-plus/icons-vue'
import zhCn from 'element-plus/es/locale/lang/zh-cn'

import App from './App.vue'
import router from './router'
import { createPinia } from 'pinia'
import './assets/main.css'

const app = createApp(App)
const pinia = createPinia()

app.use(pinia)
app.use(router)
app.use(ElementPlus, { locale: zhCn })

for (const [key, component] of Object.entries(ElementPlusIconsVue)) {
    app.component(key, component)
}

router.afterEach((to) => {
    const title = to.meta?.title
        ? `${to.meta.title} - AIOps`
        : 'AIOps 智能运维平台'
    document.title = title
})

try {
  app.mount('#app')
} catch (e) {
  document.getElementById('app').innerHTML = '<pre style="padding:20px;color:red">Vue Error: ' + e.message + '</pre>'
  console.error(e)
}

window.addEventListener('error', (e) => {
  window.__vueErrors = window.__vueErrors || []
  window.__vueErrors.push(e.message)
})
