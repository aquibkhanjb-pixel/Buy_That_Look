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
  llm_score?: number | null
}

export interface SearchResponse {
  query_id: string
  results: SearchResult[]
  latency_ms: number
  total_results: number
  filters_applied?: SearchFilters
  model_version?: string
  expanded_query?: string
  llm_enhanced?: boolean
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

// Chat Assistant types
export interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
}

export interface ChatResponse {
  message: string
  products: SearchResult[]
  web_results: WebSearchResult[]
  conversation_id: string
  search_performed: boolean
  web_search_performed: boolean
  user_preferences: Record<string, unknown>
  clarification_count: number
  options: string[]  // MCQ quick-pick chips for clarification questions
}

export interface WebSearchResult {
  title: string
  url: string
  snippet?: string
  price?: string
  source_site?: string
  image_url?: string
  rating?: number
  rating_count?: number
  source?: string   // "google_lens" | "serper_shopping" | undefined
}

export interface TryOnResponse {
  result_image: string   // base64-encoded JPEG
  model_used: string
  latency_ms: number
}

export interface TrendItem {
  name: string
  description: string
  category: string
  badge: string
  search_query: string
  example_items: string[]
}

export interface TrendsResponse {
  trends: TrendItem[]
  updated_at: string
  source: string
}
