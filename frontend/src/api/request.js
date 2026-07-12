import axios from 'axios'

const request = axios.create({
    baseURL: '',
    timeout: 30000,
    withCredentials: true,
})

request.interceptors.response.use(
    (response) => response.data,
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
