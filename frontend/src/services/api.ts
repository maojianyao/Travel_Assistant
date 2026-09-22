import axios from 'axios'
import type { TripFormData, TripPlanResponse, TripDetailResponse, TripListResponse, POIInfo } from '@/types'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'

const apiClient = axios.create({
  baseURL: API_BASE_URL,
  timeout: 120000, // 2分钟超时
  headers: {
    'Content-Type': 'application/json'
  }
})

// 请求拦截器
apiClient.interceptors.request.use(
  (config) => {
    console.log('发送请求:', config.method?.toUpperCase(), config.url)
    return config
  },
  (error) => {
    console.error('请求错误:', error)
    return Promise.reject(error)
  }
)

// 响应拦截器
apiClient.interceptors.response.use(
  (response) => {
    console.log('收到响应:', response.status, response.config.url)
    return response
  },
  (error) => {
    console.error('响应错误:', error.response?.status, error.message)
    return Promise.reject(error)
  }
)

/**
 * 生成旅行计划
 */
export async function generateTripPlan(formData: TripFormData): Promise<TripPlanResponse> {
  try {
    const response = await apiClient.post<TripPlanResponse>('/api/trip/plan', formData)
    return response.data
  } catch (error: any) {
    console.error('生成旅行计划失败:', error)
    throw new Error(error.response?.data?.detail || error.message || '生成旅行计划失败')
  }
}

/**
 * 健康检查
 */
export async function healthCheck(): Promise<any> {
  try {
    const response = await apiClient.get('/health')
    return response.data
  } catch (error: any) {
    console.error('健康检查失败:', error)
    throw new Error(error.message || '健康检查失败')
  }
}

/**
 * 流式生成旅行计划(SSE), 实时回调生成进度
 */
export async function generateTripPlanStream(
  formData: TripFormData,
  onProgress?: (percent: number, message: string) => void
): Promise<TripPlanResponse> {
  const response = await fetch(`${API_BASE_URL}/api/trip/plan/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(formData)
  })

  if (!response.ok || !response.body) {
    throw new Error(`请求失败: ${response.status}`)
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder('utf-8')
  let buffer = ''
  let result: TripPlanResponse | null = null

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })

    // SSE事件以空行分隔
    const chunks = buffer.split('\n\n')
    buffer = chunks.pop() || ''
    for (const chunk of chunks) {
      const line = chunk.trim()
      if (!line.startsWith('data:')) continue
      const payload = JSON.parse(line.slice(5).trim())
      if (payload.type === 'progress') {
        onProgress?.(payload.percent, payload.message)
      } else if (payload.type === 'result') {
        result = {
          success: true,
          message: payload.message,
          data: payload.data,
          trip_id: payload.trip_id
        }
      } else if (payload.type === 'error') {
        throw new Error(payload.message || '生成旅行计划失败')
      }
    }
  }

  if (!result) throw new Error('未收到生成结果')
  return result
}

/**
 * 按ID获取行程详情(二次查看/分享链接)
 */
export async function getTripDetail(tripId: string): Promise<TripDetailResponse> {
  try {
    const response = await apiClient.get<TripDetailResponse>(`/api/trip/detail/${tripId}`)
    return response.data
  } catch (error: any) {
    throw new Error(error.response?.data?.detail || error.message || '行程加载失败')
  }
}

/**
 * 获取行程历史列表
 */
export async function listTrips(limit = 10): Promise<TripListResponse> {
  const response = await apiClient.get<TripListResponse>('/api/trip/list', { params: { limit } })
  return response.data
}

/**
 * POI搜索(用于添加/替换景点)
 */
export async function searchPoi(keywords: string, city: string): Promise<{ success: boolean; data: POIInfo[] }> {
  const response = await apiClient.get('/api/poi/search', { params: { keywords, city } })
  return response.data
}

export default apiClient

