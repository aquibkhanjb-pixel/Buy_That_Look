import axios from 'axios'
import { ChatMessage, ChatResponse, TryOnResponse, TrendsResponse } from '@/types'

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
const API_PREFIX = '/api/v1'

const api = axios.create({
  baseURL: `${API_URL}${API_PREFIX}`,
  timeout: 90000,
})

export async function getProduct(productId: string) {
  const response = await api.get(`/products/${productId}`)
  return response.data
}

export async function getTrends(refresh = false): Promise<TrendsResponse> {
  const response = await api.get<TrendsResponse>(`/trends/${refresh ? '?refresh=true' : ''}`)
  return response.data
}

export async function getHealthStatus() {
  const response = await api.get('/health/ready')
  return response.data
}

export async function virtualTryOn(
  personImage: File,
  garmentImageUrl: string,
  garmentDescription: string = '',
): Promise<TryOnResponse> {
  const formData = new FormData()
  formData.append('person_image', personImage)
  formData.append('garment_image_url', garmentImageUrl)
  formData.append('garment_description', garmentDescription)

  const response = await api.post<TryOnResponse>('/tryon/', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 180000,  // 3 min — HuggingFace queue can be slow
  })
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
