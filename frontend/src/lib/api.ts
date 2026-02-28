import axios from 'axios'
import { SearchResponse, SearchFilters } from '@/types'

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
