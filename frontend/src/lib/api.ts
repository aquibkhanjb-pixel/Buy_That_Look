import axios from 'axios'
import { SearchResponse, SearchFilters, ChatMessage, ChatResponse } from '@/types'

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
const API_PREFIX = '/api/v1'

const api = axios.create({
  baseURL: `${API_URL}${API_PREFIX}`,
  timeout: 30000,
})

export async function searchByImage(
  file: File,
  k: number = 20,
  filters?: SearchFilters
): Promise<SearchResponse> {
  const formData = new FormData()
  formData.append('image', file)

  const params = new URLSearchParams()
  params.append('k', k.toString())

  if (filters?.min_price) params.append('min_price', filters.min_price.toString())
  if (filters?.max_price) params.append('max_price', filters.max_price.toString())
  if (filters?.category) params.append('category', filters.category)
  if (filters?.brand) params.append('brand', filters.brand)

  const response = await api.post<SearchResponse>(
    `/search/image?${params.toString()}`,
    formData,
    {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    }
  )

  return response.data
}

export async function searchByText(
  query: string,
  k: number = 20,
  filters?: SearchFilters
): Promise<SearchResponse> {
  const response = await api.post<SearchResponse>('/search/text', {
    query,
    k,
    filters: filters && Object.keys(filters).length > 0 ? filters : undefined,
  })

  return response.data
}

export async function searchHybrid(
  file: File,
  query: string,
  alpha: number = 0.5,
  k: number = 20,
  filters?: SearchFilters
): Promise<SearchResponse> {
  const formData = new FormData()
  formData.append('image', file)
  formData.append('query', query)
  formData.append('alpha', alpha.toString())
  formData.append('k', k.toString())

  if (filters?.min_price) formData.append('min_price', filters.min_price.toString())
  if (filters?.max_price) formData.append('max_price', filters.max_price.toString())
  if (filters?.category) formData.append('category', filters.category)
  if (filters?.brand) formData.append('brand', filters.brand)

  const response = await api.post<SearchResponse>('/search/hybrid', formData, {
    headers: {
      'Content-Type': 'multipart/form-data',
    },
  })

  return response.data
}

export async function getProduct(productId: string) {
  const response = await api.get(`/products/${productId}`)
  return response.data
}

export async function getSimilarProducts(productId: string, k: number = 20) {
  const response = await api.get<SearchResponse>(`/products/${productId}/similar?k=${k}`)
  return response.data
}

export async function getHealthStatus() {
  const response = await api.get('/health/ready')
  return response.data
}

export async function sendChatMessage(
  messages: ChatMessage[],
  options: {
    conversationId?: string
    image?: File
    userPreferences?: Record<string, unknown>
    clarificationCount?: number
  } = {}
): Promise<ChatResponse> {
  const formData = new FormData()
  formData.append('messages', JSON.stringify(messages))

  if (options.conversationId) {
    formData.append('conversation_id', options.conversationId)
  }
  if (options.userPreferences && Object.keys(options.userPreferences).length > 0) {
    formData.append('user_preferences', JSON.stringify(options.userPreferences))
  }
  if (options.clarificationCount !== undefined) {
    formData.append('clarification_count', String(options.clarificationCount))
  }
  if (options.image) {
    formData.append('image', options.image)
  }

  const response = await api.post<ChatResponse>('/chat/', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return response.data
}
