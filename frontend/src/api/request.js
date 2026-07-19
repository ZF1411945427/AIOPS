import axios from 'axios'
import { ElMessage } from 'element-plus'

const request = axios.create({
    baseURL: '',
    timeout: 30000,
    withCredentials: true,
})

request.interceptors.response.use(
    (response) => {
        // 后端 fail-soft 策略：200 + warning 字段表示依赖服务不可用（如 K8s 集群禁用）
        // 全局弹出 warning 提示，避免每个页面单独处理
        const data = response.data
        if (data && typeof data === 'object' && data.warning) {
            ElMessage.warning(data.warning)
        }
        return data
    },
    (error) => {
        if (error.response?.status === 403 && error.response?.data?.license_status) {
            if (window._navigateTo) {
                window._navigateTo('license')
            }
            return Promise.reject(new Error(error.response.data.detail || '授权失效，请上传有效许可证'))
        }
        const message = error.response?.data?.detail
            || error.response?.data?.message
            || error.response?.data?.error
            || error.message
            || '请求失败'
        return Promise.reject(new Error(message))
    },
)

export default request
