export interface Product {
  id: string
  product_id: string
  title: string
  description?: string
  brand?: string
  price?: number
  original_price?: number
  currency: string
  category?: string
  subcategory?: string
  color?: string
  image_url: string
  additional_images?: string[]
  product_url: string
  source_site: string
  similarity?: number
}

export interface SearchResult extends Product {
  similarity: number
}

export interface SearchResponse {
  query_id: string
  results: SearchResult[]
  latency_ms: number
  total_results: number
  filters_applied?: SearchFilters
  model_version?: string
}

export interface SearchFilters {
  min_price?: number
  max_price?: number
  category?: string
  brand?: string
  color?: string
}

export interface ApiError {
  detail: string
}
