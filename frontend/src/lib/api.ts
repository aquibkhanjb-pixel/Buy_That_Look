import axios from 'axios'
import { ChatMessage, ChatResponse, TryOnResponse, TrendsResponse, SearchResult } from '@/types'

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
const API_PREFIX = '/api/v1'

const api = axios.create({
  baseURL: `${API_URL}${API_PREFIX}`,
  timeout: 90000,
})

/** Build Authorization header from backend JWT stored in NextAuth session. */
function authHeader(token: string) {
  return { Authorization: `Bearer ${token}` }
}

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
    fromTrend?: boolean
    outfitProduct?: Record<string, unknown>
    backendToken?: string
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
  if (options.fromTrend) {
    formData.append('from_trend', 'true')
  }
  if (options.outfitProduct) {
    formData.append('outfit_product', JSON.stringify(options.outfitProduct))
  }

  const headers: Record<string, string> = { 'Content-Type': 'multipart/form-data' }
  if (options.backendToken) {
    headers['Authorization'] = `Bearer ${options.backendToken}`
  }
  const response = await api.post<ChatResponse>('/chat/', formData, { headers })
  return response.data
}

export async function registerPriceAlerts(
  email: string,
  products: SearchResult[],
): Promise<{ registered: number }> {
  const payload = {
    email,
    products: products.map((p) => ({
      id:          p.id,
      product_url: p.product_url,
      title:       p.title,
      price:       p.price ?? null,
      image_url:   p.image_url ?? '',
      currency:    p.currency ?? 'INR',
      source_site: p.source_site ?? '',
    })),
  }
  const response = await api.post('/alerts/register', payload)
  return response.data
}

export async function getTrackedAlerts(email: string): Promise<{
  email: string
  alerts: TrackedAlert[]
  count: number
}> {
  const response = await api.get(`/alerts/${encodeURIComponent(email)}`)
  return response.data
}

export async function removeTrackedAlert(
  email: string,
  product_url: string,
): Promise<void> {
  await api.delete('/alerts/', { data: { email, product_url } })
}

export interface TrackedAlert {
  id: number
  email: string
  product_url: string
  title: string
  image_url: string
  last_price: number | null
  currency: string
  source_site: string
  created_at: string
  last_checked: string | null
  is_active: boolean
}

// ── Payments ────────────────────────────────────────────────────────────────

export interface RazorpayCheckout {
  subscription_id: string
  key_id: string
  user_name: string
  user_email: string
}

export async function createCheckoutSession(
  backendToken: string,
): Promise<RazorpayCheckout> {
  const response = await api.post('/payments/checkout', {}, {
    headers: authHeader(backendToken),
  })
  return response.data
}

export async function verifyPayment(
  backendToken: string,
  data: {
    razorpay_payment_id: string
    razorpay_subscription_id: string
    razorpay_signature: string
  },
): Promise<{ access_token: string; tier: string }> {
  const response = await api.post('/payments/verify', data, {
    headers: authHeader(backendToken),
  })
  return response.data
}

export async function cancelSubscription(
  backendToken: string,
): Promise<{ access_token: string; tier: string }> {
  const response = await api.post('/payments/cancel', {}, {
    headers: authHeader(backendToken),
  })
  return response.data
}

export async function refreshBackendToken(
  backendToken: string,
): Promise<{ access_token: string; tier: string }> {
  const response = await api.post('/users/refresh-token', {}, {
    headers: authHeader(backendToken),
  })
  return response.data
}

// ── Wishlist ─────────────────────────────────────────────────────────────────

export interface WishlistItemDB {
  id: number
  product_id: string
  title: string
  product_url: string
  image_url: string
  price: number | null
  currency: string
  source_site: string
  description: string | null
  brand: string | null
  created_at: string
}

export async function getWishlist(backendToken: string): Promise<WishlistItemDB[]> {
  const response = await api.get('/wishlist/', { headers: authHeader(backendToken) })
  return response.data.items
}

export async function addToWishlist(
  backendToken: string,
  product: Omit<WishlistItemDB, 'id' | 'created_at'>,
): Promise<{ item: WishlistItemDB; added: boolean }> {
  const response = await api.post('/wishlist/', product, { headers: authHeader(backendToken) })
  return response.data
}

export async function removeFromWishlist(
  backendToken: string,
  productId: string,
): Promise<void> {
  await api.delete(`/wishlist/${encodeURIComponent(productId)}`, {
    headers: authHeader(backendToken),
  })
}

export async function virtualTryOnAuth(
  backendToken: string,
  personImage: File,
  garmentImageUrl: string,
  garmentDescription: string = '',
): Promise<TryOnResponse> {
  const formData = new FormData()
  formData.append('person_image', personImage)
  formData.append('garment_image_url', garmentImageUrl)
  formData.append('garment_description', garmentDescription)

  const response = await api.post<TryOnResponse>('/tryon/', formData, {
    headers: { 'Content-Type': 'multipart/form-data', ...authHeader(backendToken) },
    timeout: 180000,
  })
  return response.data
}

// ── Chat History ─────────────────────────────────────────────────────────────

export interface ChatSessionSummary {
  id: string
  title: string
  created_at: string
  updated_at: string
}

export interface ChatHistoryMessage {
  id: number
  role: 'user' | 'assistant'
  content: string
  metadata_json: string | null   // JSON string: {products, web_results, options}
  created_at: string
}

export async function getChatHistory(backendToken: string): Promise<ChatSessionSummary[]> {
  const response = await api.get('/chat/history/', { headers: authHeader(backendToken) })
  return response.data.sessions
}

export async function getChatSession(
  backendToken: string,
  sessionId: string,
): Promise<{
  session_id: string
  title: string
  user_preferences: string | null   // raw JSON string of last known prefs
  messages: ChatHistoryMessage[]
}> {
  const response = await api.get(`/chat/history/${sessionId}`, { headers: authHeader(backendToken) })
  return response.data
}

export async function deleteChatSession(backendToken: string, sessionId: string): Promise<void> {
  await api.delete(`/chat/history/${sessionId}`, { headers: authHeader(backendToken) })
}

// ── Occasion Planner ──────────────────────────────────────────────────────────

export interface OccasionCategory {
  id: string
  label: string
  sublabel: string
  emoji: string
  budget_pct: number
  default: boolean
}

export interface OccasionContext {
  occasion_type: string
  party_subtype: string
  gender: string
  budget: number
  role: string
  style: string
  formality: string
  special_notes: string
  original_description: string
}

export interface OutfitPiece {
  category_id: string
  category_label: string
  title: string
  url: string
  price: string
  price_num: number
  image_url: string
  source_site: string
  rating?: number
  budget: number
}

export interface CompatibilityEdge {
  a: string
  a_label: string
  b: string
  b_label: string
  score: number       // 0=incompatible, 1=neutral, 2=compatible
  reason: string
}

export interface CompatibilityConflict {
  piece_a_id: string
  piece_b_id: string
  piece_a_label: string
  piece_b_label: string
  reason: string
  suggestion: string
}

export interface OccasionPlanResponse {
  pieces: OutfitPiece[]
  total_price: number
  budget: number
  outfit_story: string
  compatibility_graph: CompatibilityEdge[]
  conflicts: { has_conflicts: boolean; conflicts: CompatibilityConflict[] } | null
}

export async function getOccasionCategories(
  description: string,
  backendToken?: string,
): Promise<{ context: OccasionContext; categories: OccasionCategory[] }> {
  const headers = backendToken ? authHeader(backendToken) : {}
  const response = await api.post('/occasion/categories', { description }, { headers, timeout: 30000 })
  return response.data
}

export async function planOccasionOutfit(
  context: OccasionContext,
  selectedIds: string[],
  customItems: string[],
  brandTier: string,
  backendToken?: string,
): Promise<OccasionPlanResponse> {
  const headers = backendToken ? authHeader(backendToken) : {}
  const response = await api.post(
    '/occasion/plan',
    { context, selected_ids: selectedIds, custom_items: customItems, brand_tier: brandTier },
    { headers, timeout: 180000 },
  )
  return response.data
}

export async function swapOccasionPiece(
  context: OccasionContext,
  categoryId: string,
  categoryLabel: string,
  budget: number,
  lockedPieces: OutfitPiece[],
  brandTier: string,
  userHint: string,
  customLabel?: string,
  backendToken?: string,
): Promise<{ piece: OutfitPiece; gap_pieces: OutfitPiece[]; conflicts: { has_conflicts: boolean; conflicts: CompatibilityConflict[] } | null; compatibility_graph: CompatibilityEdge[] }> {
  const headers = backendToken ? authHeader(backendToken) : {}
  const response = await api.post(
    '/occasion/swap',
    {
      context, category_id: categoryId, category_label: categoryLabel,
      budget, locked_pieces: lockedPieces, custom_label: customLabel,
      brand_tier: brandTier, user_hint: userHint,
    },
    { headers, timeout: 120000 },
  )
  return response.data
}

// ── Find This Look ───────────────────────────────────────────────────────────

export async function findThisLook(options: {
  imageUrl?: string
  image?: File
}): Promise<ChatResponse> {
  const formData = new FormData()
  if (options.imageUrl) formData.append('image_url', options.imageUrl)
  if (options.image) formData.append('image', options.image)

  const response = await api.post<ChatResponse>('/findlook/', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 120000,
  })
  return response.data
}

// ── Admin ────────────────────────────────────────────────────────────────────

export async function getAppSettings(): Promise<Record<string, string>> {
  const response = await api.get('/settings')
  return response.data
}

export async function updateAppSettings(token: string, subscriptionPrice: number) {
  const response = await api.patch(
    '/admin/settings',
    { subscription_price: subscriptionPrice },
    { headers: authHeader(token) }
  )
  return response.data
}

export async function getAdminStats(token: string) {
  const response = await api.get('/admin/stats', { headers: authHeader(token) })
  return response.data
}

export async function getAdminUsers(
  token: string,
  params: { page?: number; limit?: number; search?: string; tier?: string } = {}
) {
  const response = await api.get('/admin/users', {
    headers: authHeader(token),
    params,
  })
  return response.data
}

export async function updateUserTier(token: string, userId: string, tier: string) {
  const response = await api.patch(
    `/admin/users/${userId}/tier`,
    { tier },
    { headers: authHeader(token) }
  )
  return response.data
}

export async function deleteUser(token: string, userId: string) {
  const response = await api.delete(`/admin/users/${userId}`, {
    headers: authHeader(token),
  })
  return response.data
}

export async function updateUserAdmin(token: string, userId: string, isAdmin: boolean) {
  const response = await api.patch(
    `/admin/users/${userId}/admin`,
    { is_admin: isAdmin },
    { headers: authHeader(token) }
  )
  return response.data
}

export async function getAdminGrowth(token: string, days = 30) {
  const response = await api.get('/admin/growth', {
    headers: authHeader(token),
    params: { days },
  })
  return response.data as { date: string; count: number }[]
}

export async function getAdminAlerts(
  token: string,
  params: { page?: number; limit?: number } = {}
) {
  const response = await api.get('/admin/alerts', {
    headers: authHeader(token),
    params,
  })
  return response.data
}

export async function deleteAdminAlert(token: string, alertId: number) {
  const response = await api.delete(`/admin/alerts/${alertId}`, {
    headers: authHeader(token),
  })
  return response.data
}

