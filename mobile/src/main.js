import { createSSRApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'

// 拦截所有点击，查找包含"拨号"文字的按钮
document.addEventListener('click', function(e) {
  let el = e.target
  while (el && el !== document) {
    const text = el.textContent || el.innerText || ''
    if (text.trim() === '拨号') {
      console.log('[INTERCEPT] found dial button:', el.tagName, el.className)
      e.preventDefault()
      e.stopPropagation()
      fetch('/api/sre/oncall/current').then(r=>r.json()).then(d=>{
        const phone = (d && d.phone) || ''
        console.log('[INTERCEPT] phone from API:', phone)
        uni.showToast({ title: phone ? '电话:' + phone : '无电话', icon: 'none' })
        if (phone) uni.makePhoneCall({ phoneNumber: phone })
      }).catch(e2=>{
        console.log('[INTERCEPT] fetch error:', e2)
        uni.showToast({ title: '请求失败:'+e2.message, icon: 'none' })
      })
      break
    }
    el = el.parentElement
  }
}, true)

export function createApp() {
  const app = createSSRApp(App)
  app.use(createPinia())
  return { app }
}
