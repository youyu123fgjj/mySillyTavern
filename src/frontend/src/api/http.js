import axios from 'axios'

/** 后端统一返回 { data, msg }。这里拦截：成功解包出响应体，失败抛出带 msg 的 Error */
const http = axios.create({ baseURL: '' })

http.interceptors.request.use((config) => {
  const key = localStorage.getItem('api_key')
  if (key) config.headers.Authorization = key
  return config
})

http.interceptors.response.use(
  (resp) => resp.data,
  (error) => {
    const msg = error.response?.data?.msg || error.message || '请求失败'
    const e = new Error(msg)
    e.status = error.response?.status
    return Promise.reject(e)
  }
)

/** 发送 POST 请求，返回响应体 { data, msg } */
export function post(path, body) {
  return http.post(path, body)
}

export default http