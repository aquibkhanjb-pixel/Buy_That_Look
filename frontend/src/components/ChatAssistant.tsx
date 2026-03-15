'use client'

import { useState, useRef, useEffect, useCallback, MutableRefObject } from 'react'
import Image from 'next/image'
import Link from 'next/link'
import {
  Send, Sparkles, ExternalLink, ImageIcon, X, Shirt, Heart, Wand2,
  History, Crown, Trash2, Plus, ChevronLeft, Loader2,
} from 'lucide-react'
import { useSession } from 'next-auth/react'
import { ChatMessage, SearchResult } from '@/types'
import {
  sendChatMessage,
  getChatHistory,
  getChatSession,
  deleteChatSession,
  ChatSessionSummary,
} from '@/lib/api'
import { formatPrice, formatSimilarity } from '@/lib/utils'
import TryOnModal from './TryOnModal'

// ── Types ──────────────────────────────────────────────────────────────────

interface WebLink {
  title: string
  url: string
  snippet?: string
  price?: string
  source_site?: string
  image_url?: string
  rating?: number
  rating_count?: number
  source?: string
}

interface MessageBubble {
  role: 'user' | 'assistant'
  content: string
  imagePreview?: string
  products?: SearchResult[]
  webLinks?: WebLink[]
  options?: string[]
  isLoading?: boolean
  isOutfitResult?: boolean
}

// ── Constants ──────────────────────────────────────────────────────────────

const WELCOME: MessageBubble = {
  role: 'assistant',
  content: "Hello! I'm your personal AI stylist ✦\n\nTell me what you're looking for — a special occasion outfit, a daily staple, or something inspired by a trend. You can also upload a photo!\n\nTry:\n• \"Find me a casual blue kurta under ₹1000\"\n• \"Something elegant for a wedding\"\n• \"I uploaded an image — find similar styles\"",
}

const SUGGESTIONS = [
  'Casual kurta for men under ₹800',
  'Floral summer dresses',
  'Wedding outfit under ₹2000',
  'Trending co-ord sets for women',
]

// ── Source badge ────────────────────────────────────────────────────────────

function SourceBadge({ source }: { source?: string }) {
  if (source === 'lens') {
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-blue-50 text-blue-600 border border-blue-100 text-[10px] font-medium">
        🔍 Google Lens
      </span>
    )
  }
  return (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-700 border border-emerald-100 text-[10px] font-medium">
      🛒 Web Search
    </span>
  )
}

// ── ProductCard ─────────────────────────────────────────────────────────────

function ProductCard({
  product, onProductClick, onTryOn, onWishlistToggle, wishlisted, onCompleteTheLook, hideCompleteTheLook = false,
}: {
  product: SearchResult
  onProductClick: (p: SearchResult) => void
  onTryOn: (imageUrl: string, title: string) => void
  onWishlistToggle: (p: SearchResult) => void
  wishlisted: boolean
  onCompleteTheLook: (p: SearchResult) => void
  hideCompleteTheLook?: boolean
}) {
  return (
    <div
      onClick={() => onProductClick(product)}
      className="relative flex-shrink-0 w-36 rounded-2xl border border-ivory-dark bg-white overflow-hidden cursor-pointer hover:shadow-md hover:border-gold/30 transition-all group"
    >
      <div className="relative">
        <div className="w-full h-36 relative bg-ivory">
          <Image src={product.image_url} alt={product.title} fill className="object-cover" sizes="144px"
            onError={(e) => { (e.target as HTMLImageElement).style.display = 'none' }} />
        </div>
        <div className="absolute top-1.5 left-1.5">
          {formatSimilarity(product.similarity) && (
            <span className="text-[9px] bg-noir/70 text-white px-1.5 py-0.5 rounded-full backdrop-blur-sm">
              {formatSimilarity(product.similarity)}
            </span>
          )}
        </div>
        <button
          onClick={(e) => { e.stopPropagation(); onWishlistToggle(product) }}
          className="absolute top-1.5 right-1.5 w-6 h-6 rounded-full bg-white/90 flex items-center justify-center shadow-sm hover:scale-110 transition-transform"
        >
          <Heart className={`h-3 w-3 ${wishlisted ? 'fill-red-500 text-red-500' : 'text-noir/40'}`} />
        </button>
      </div>
      <div className="p-2 space-y-1.5">
        <p className="text-[11px] font-medium text-noir line-clamp-2 leading-snug">{product.title}</p>
        {product.price && (
          <p className="text-[11px] font-semibold text-gold">{formatPrice(product.price, product.currency)}</p>
        )}
        <div className="flex gap-1 pt-0.5">
          {product.image_url && (
            <button
              onClick={(e) => { e.stopPropagation(); onTryOn(product.image_url, product.title) }}
              className="flex-1 flex items-center justify-center gap-1 text-[10px] text-noir/50 hover:text-purple-600 transition-colors py-1 rounded-lg hover:bg-purple-50"
            >
              <Shirt className="h-3 w-3" /> Try
            </button>
          )}
          {!hideCompleteTheLook && (
            <button
              onClick={(e) => { e.stopPropagation(); onCompleteTheLook(product) }}
              className="flex-1 flex items-center justify-center gap-1 text-[10px] text-noir/50 hover:text-gold transition-colors py-1 rounded-lg hover:bg-gold/10"
            >
              <Wand2 className="h-3 w-3" /> Complete
            </button>
          )}
        </div>
      </div>
    </div>
  )
}

// ── WebLinkCard ─────────────────────────────────────────────────────────────

function WebLinkCard({
  link, onTryOn, onWishlistToggle, wishlisted, onCompleteTheLook, hideCompleteTheLook = false,
}: {
  link: WebLink
  onTryOn: (imageUrl: string, title: string) => void
  onWishlistToggle: (product: SearchResult) => void
  wishlisted: boolean
  onCompleteTheLook: (product: SearchResult) => void
  hideCompleteTheLook?: boolean
}) {
  const asProduct: SearchResult = {
    id: link.url,
    product_id: link.url,
    title: link.title,
    product_url: link.url,
    image_url: link.image_url || '',
    price: link.price ? parseFloat(link.price.replace(/[^0-9.]/g, '')) || undefined : undefined,
    currency: 'INR',
    source_site: link.source_site || '',
    similarity: 0,
  }

  return (
    <div className="rounded-2xl border border-ivory-dark bg-white overflow-hidden hover:shadow-md hover:border-gold/30 transition-all">
      <div className="flex gap-3 p-3">
        {link.image_url && (
          <div className="w-16 h-16 relative rounded-xl overflow-hidden flex-shrink-0 bg-ivory">
            <Image src={link.image_url} alt={link.title} fill className="object-cover" sizes="64px"
              onError={(e) => { (e.target as HTMLImageElement).style.display = 'none' }} />
          </div>
        )}
        <div className="flex-1 min-w-0 space-y-1.5">
          <div className="mb-1.5 flex items-center justify-between gap-2">
            <SourceBadge source={link.source} />
            <button
              onClick={() => onWishlistToggle(asProduct)}
              className="w-6 h-6 rounded-full bg-white flex items-center justify-center shadow-sm hover:scale-110 transition-transform flex-shrink-0"
            >
              <Heart className={`h-3 w-3 ${wishlisted ? 'fill-red-500 text-red-500' : 'text-noir/40'}`} />
            </button>
          </div>
          <a href={link.url} target="_blank" rel="noopener noreferrer" onClick={(e) => e.stopPropagation()}>
            <p className="text-sm font-medium text-noir line-clamp-1 hover:text-gold transition-colors">{link.title}</p>
          </a>
          <button
            onClick={() => onWishlistToggle(asProduct)}
            className="w-6 h-6 rounded-full bg-white flex items-center justify-center shadow-sm hover:scale-110 transition-transform flex-shrink-0 mt-0.5 hidden"
          >
            <Heart className={`h-3 w-3 ${wishlisted ? 'fill-red-500 text-red-500' : 'text-noir/40'}`} />
          </button>
          {link.price && (
            <p className="text-[11px] font-semibold text-gold">{link.price}</p>
          )}
          {link.snippet && (
            <p className="text-[11px] text-noir/50 line-clamp-2">{link.snippet}</p>
          )}
          <div className="flex items-center gap-2 pt-1">
            <a href={link.url} target="_blank" rel="noopener noreferrer"
              className="flex items-center gap-1 text-[10px] text-noir/40 hover:text-gold transition-colors">
              <ExternalLink className="h-3 w-3" />
              {link.source_site || 'View product'}
            </a>
            {link.image_url && (
              <button
                onClick={() => onTryOn(link.image_url!, link.title)}
                className="flex items-center gap-1 text-[10px] text-noir/40 hover:text-purple-600 transition-colors"
              >
                <Shirt className="h-3 w-3" /> Try on
              </button>
            )}
            {!hideCompleteTheLook && (
              <button
                onClick={() => onCompleteTheLook(asProduct)}
                className="flex items-center gap-1 text-[10px] text-noir/40 hover:text-gold transition-colors"
              >
                <Wand2 className="h-3 w-3" /> Complete
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

// ── History Sidebar ─────────────────────────────────────────────────────────

function HistorySidebar({
  token,
  tier,
  activeSessionId,
  onSelectSession,
  onNewChat,
  onClose,
}: {
  token?: string
  tier: string
  activeSessionId?: string
  onSelectSession: (
    sessionId: string,
    messages: { role: string; content: string; metadata_json?: string | null }[],
    userPrefsJson?: string | null,
  ) => void
  onNewChat: () => void
  onClose: () => void
}) {
  const [sessions, setSessions] = useState<ChatSessionSummary[]>([])
  const [loading, setLoading] = useState(false)
  const [deleting, setDeleting] = useState<string | null>(null)

  const loadSessions = useCallback(async () => {
    if (!token || tier !== 'premium') return
    setLoading(true)
    try {
      const data = await getChatHistory(token)
      setSessions(data)
    } catch {
      // silent
    } finally {
      setLoading(false)
    }
  }, [token, tier])

  useEffect(() => { loadSessions() }, [loadSessions])

  const handleSelect = async (sessionId: string) => {
    if (!token) return
    try {
      const data = await getChatSession(token, sessionId)
      onSelectSession(sessionId, data.messages, data.user_preferences)
    } catch {
      // silent
    }
  }

  const handleDelete = async (e: React.MouseEvent, sessionId: string) => {
    e.stopPropagation()
    if (!token) return
    setDeleting(sessionId)
    try {
      await deleteChatSession(token, sessionId)
      setSessions((prev) => prev.filter((s) => s.id !== sessionId))
    } catch {
      // silent
    } finally {
      setDeleting(null)
    }
  }

  const formatDate = (iso: string) => {
    const d = new Date(iso)
    const today = new Date()
    const diff = Math.floor((today.getTime() - d.getTime()) / 86400000)
    if (diff === 0) return 'Today'
    if (diff === 1) return 'Yesterday'
    if (diff < 7) return `${diff} days ago`
    return d.toLocaleDateString('en-IN', { day: 'numeric', month: 'short' })
  }

  return (
    <div className="flex flex-col h-full bg-white border-r border-ivory-dark w-60 flex-shrink-0">
      {/* Sidebar header */}
      <div className="flex items-center justify-between px-4 py-3.5 border-b border-ivory-dark">
        <div className="flex items-center gap-2">
          <History className="h-4 w-4 text-noir/50" />
          <span className="text-sm font-semibold text-noir">History</span>
        </div>
        <button onClick={onClose} className="p-1 rounded-lg hover:bg-ivory transition-colors">
          <ChevronLeft className="h-4 w-4 text-noir/40" />
        </button>
      </div>

      {/* New chat button */}
      <div className="px-3 py-2.5 border-b border-ivory-dark">
        <button
          onClick={onNewChat}
          className="w-full flex items-center gap-2 px-3 py-2 rounded-xl bg-noir text-ivory text-[12px] font-medium hover:bg-noir/80 transition-colors"
        >
          <Plus className="h-3.5 w-3.5" />
          New conversation
        </button>
      </div>

      {/* Sessions list */}
      <div className="flex-1 overflow-y-auto py-2">
        {tier !== 'premium' ? (
          /* Premium gate for free users */
          <div className="mx-3 mt-4 rounded-xl bg-noir p-4 text-center space-y-2">
            <Crown className="h-6 w-6 text-gold mx-auto" />
            <p className="text-[11px] text-ivory/80 font-medium">Chat history is a Premium feature</p>
            <p className="text-[10px] text-ivory/50">Save and revisit your last 30 days of conversations.</p>
            <Link
              href="/pricing"
              className="inline-block mt-1 bg-gold text-white text-[11px] font-medium px-4 py-1.5 rounded-lg hover:bg-amber-600 transition-colors"
            >
              Upgrade — ₹99/mo
            </Link>
          </div>
        ) : loading ? (
          <div className="flex justify-center py-8">
            <Loader2 className="h-5 w-5 text-noir/30 animate-spin" />
          </div>
        ) : sessions.length === 0 ? (
          <div className="text-center py-8 px-4">
            <p className="text-[11px] text-noir/30">No conversations yet.</p>
            <p className="text-[10px] text-noir/20 mt-1">Start chatting to save history.</p>
          </div>
        ) : (
          sessions.map((s) => (
            <button
              key={s.id}
              onClick={() => handleSelect(s.id)}
              className={`w-full text-left px-3 py-2.5 mx-0 hover:bg-ivory transition-colors group flex items-start gap-2 ${
                activeSessionId === s.id ? 'bg-gold/10 border-r-2 border-gold' : ''
              }`}
            >
              <div className="flex-1 min-w-0">
                <p className="text-[12px] font-medium text-noir line-clamp-2 leading-snug">{s.title}</p>
                <p className="text-[10px] text-noir/30 mt-0.5">{formatDate(s.updated_at)}</p>
              </div>
              <button
                onClick={(e) => handleDelete(e, s.id)}
                disabled={deleting === s.id}
                className="opacity-0 group-hover:opacity-100 transition-opacity p-1 rounded-lg hover:bg-red-50 hover:text-red-500 text-noir/20 flex-shrink-0 mt-0.5"
              >
                {deleting === s.id
                  ? <Loader2 className="h-3 w-3 animate-spin" />
                  : <Trash2 className="h-3 w-3" />
                }
              </button>
            </button>
          ))
        )}
      </div>
    </div>
  )
}

// ── Main component ─────────────────────────────────────────────────────────

interface ChatAssistantProps {
  onProductClick: (product: SearchResult) => void
  triggerRef?: MutableRefObject<((query: string) => void) | null>
  onWishlistToggle: (product: SearchResult) => void
  isWishlisted: (id: string) => boolean
}

export default function ChatAssistant({ onProductClick, triggerRef, onWishlistToggle, isWishlisted }: ChatAssistantProps) {
  const { data: session } = useSession()
  const backendToken = session?.backendToken
  const userTier = session?.user?.tier ?? 'free'

  const [bubbles, setBubbles] = useState<MessageBubble[]>([WELCOME])
  const [input, setInput] = useState('')
  const [pendingImage, setPendingImage] = useState<File | null>(null)
  const [imagePreview, setImagePreview] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [conversationId, setConversationId] = useState<string | undefined>()
  const [userPreferences, setUserPreferences] = useState<Record<string, unknown>>({})
  const [clarificationCount, setClarificationCount] = useState(0)
  const [tryOnGarment, setTryOnGarment] = useState<{ imageUrl: string; title: string } | null>(null)
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [activeHistorySession, setActiveHistorySession] = useState<string | undefined>()

  const apiMessages = useRef<ChatMessage[]>([])
  const bottomRef   = useRef<HTMLDivElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [bubbles])

  useEffect(() => {
    if (triggerRef) triggerRef.current = (query: string) => sendMessage(query, undefined, true)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const startNewChat = useCallback(() => {
    setBubbles([WELCOME])
    apiMessages.current = []
    setConversationId(undefined)
    setUserPreferences({})
    setClarificationCount(0)
    setActiveHistorySession(undefined)
    setInput('')
  }, [])

  const loadHistorySession = useCallback((
    sessionId: string,
    messages: { role: string; content: string; metadata_json?: string | null }[],
    userPrefsJson?: string | null,
  ) => {
    const loadedBubbles: MessageBubble[] = messages.map((m) => {
      const bubble: MessageBubble = {
        role: m.role as 'user' | 'assistant',
        content: m.content,
      }
      // Restore product cards and web links from saved metadata
      if (m.role === 'assistant' && m.metadata_json) {
        try {
          const meta = JSON.parse(m.metadata_json)
          if (meta.products?.length)    bubble.products  = meta.products  as SearchResult[]
          if (meta.web_results?.length) bubble.webLinks  = meta.web_results as WebLink[]
          if (meta.options?.length)     bubble.options   = meta.options    as string[]
        } catch { /* ignore malformed JSON */ }
      }
      return bubble
    })

    setBubbles(loadedBubbles.length > 0 ? loadedBubbles : [WELCOME])
    // Only text content goes into apiMessages — the LangGraph only needs conversation text for context
    apiMessages.current = messages.map((m) => ({
      role: m.role as 'user' | 'assistant',
      content: m.content,
    }))
    setConversationId(sessionId)
    setActiveHistorySession(sessionId)

    // Restore accumulated user preferences so the graph has full context on resume
    try {
      setUserPreferences(userPrefsJson ? JSON.parse(userPrefsJson) : {})
    } catch {
      setUserPreferences({})
    }
    setClarificationCount(0)
  }, [])

  const handleCompleteTheLook = (product: SearchResult) => {
    sendMessage(`Complete the look for this: ${product.title}`, undefined, false, product)
  }

  const handleImageSelect = (file: File) => {
    setPendingImage(file)
    const reader = new FileReader()
    reader.onload = (e) => setImagePreview(e.target?.result as string)
    reader.readAsDataURL(file)
  }

  const clearImage = () => {
    setPendingImage(null)
    setImagePreview(null)
    if (fileInputRef.current) fileInputRef.current.value = ''
  }

  const sendMessage = async (
    text: string,
    imageFile?: File,
    fromTrend = false,
    outfitProduct?: SearchResult,
  ) => {
    const messageText = text.trim()
    if (!messageText && !imageFile) return
    if (isLoading) return

    const displayText = messageText || (imageFile ? 'I uploaded an image — find similar products.' : '')
    setBubbles((prev) => [
      ...prev,
      { role: 'user', content: displayText, imagePreview: imageFile ? imagePreview || undefined : undefined },
      { role: 'assistant', content: '', isLoading: true },
    ])
    setInput('')
    clearImage()
    setIsLoading(true)
    apiMessages.current = [...apiMessages.current, { role: 'user', content: displayText }]

    try {
      const response = await sendChatMessage(apiMessages.current, {
        conversationId, image: imageFile, userPreferences, clarificationCount, fromTrend,
        outfitProduct: outfitProduct as unknown as Record<string, unknown>,
        backendToken: backendToken || undefined,
      })
      if (response.conversation_id) {
        setConversationId(response.conversation_id)
        setActiveHistorySession(response.conversation_id)
      }
      if (response.user_preferences) setUserPreferences(response.user_preferences as Record<string, unknown>)
      if (response.clarification_count !== undefined) setClarificationCount(response.clarification_count)
      apiMessages.current = [...apiMessages.current, { role: 'assistant', content: response.message }]
      setBubbles((prev) => [
        ...prev.slice(0, -1),
        {
          role: 'assistant',
          content: response.message,
          products:       response.products  as unknown as SearchResult[],
          webLinks:       response.web_results as unknown as WebLink[],
          options:        response.options,
          isOutfitResult: response.is_outfit_completion,
        },
      ])
    } catch (err: unknown) {
      const status = (err as { response?: { status?: number; data?: { detail?: string } } })?.response?.status
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      const errorMsg = status === 403 && detail?.includes('Daily limit')
        ? `You've used all 15 free messages for today. [Upgrade to Premium](/pricing) for unlimited chat.`
        : 'Something went wrong. Please try again.'
      setBubbles((prev) => [
        ...prev.slice(0, -1),
        { role: 'assistant', content: errorMsg },
      ])
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div className="flex h-[680px]">

      {/* History sidebar */}
      {sidebarOpen && (
        <HistorySidebar
          token={backendToken}
          tier={userTier}
          activeSessionId={activeHistorySession}
          onSelectSession={(sid, msgs, prefs) => loadHistorySession(sid, msgs, prefs)}
          onNewChat={() => { startNewChat(); setSidebarOpen(false) }}
          onClose={() => setSidebarOpen(false)}
        />
      )}

      {/* Main chat area */}
      <div className="flex flex-col flex-1 min-w-0">

        {/* Chat header bar */}
        <div className="flex items-center gap-3 px-5 py-3.5 border-b border-ivory-dark bg-white">
          {/* History toggle */}
          <button
            onClick={() => setSidebarOpen((o) => !o)}
            className={`p-1.5 rounded-xl transition-colors ${sidebarOpen ? 'bg-gold/10 text-gold' : 'text-noir/30 hover:text-noir hover:bg-ivory'}`}
            title="Chat history"
          >
            <History className="h-4 w-4" />
          </button>

          <div className="w-8 h-8 rounded-full bg-noir flex items-center justify-center">
            <Sparkles className="h-4 w-4 text-gold" />
          </div>
          <div>
            <p className="text-sm font-semibold text-noir tracking-tight">AI Style Assistant</p>
            <p className="text-[10px] text-noir/40 tracking-wide">Powered by Gemini · Serper</p>
          </div>
          <div className="ml-auto flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
            <span className="text-[10px] text-noir/40">Online</span>
          </div>
        </div>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto px-5 py-5 space-y-5 bg-ivory/30">
          {bubbles.map((msg, i) => (
            <div key={i} className={`flex gap-3 ${msg.role === 'user' ? 'justify-end' : 'justify-start'} animate-slide-up`}>

              {/* Assistant avatar */}
              {msg.role === 'assistant' && (
                <div className="w-7 h-7 rounded-full bg-noir flex items-center justify-center flex-shrink-0 mt-1">
                  <Sparkles className="h-3.5 w-3.5 text-gold" />
                </div>
              )}

              <div className="max-w-[80%] space-y-3">
                {/* Uploaded image preview */}
                {msg.imagePreview && (
                  <div className="w-32 h-32 relative rounded-2xl overflow-hidden border border-ivory-dark shadow-sm">
                    <Image src={msg.imagePreview} alt="uploaded" fill className="object-cover" sizes="128px" />
                  </div>
                )}

                {/* Bubble */}
                <div className={`rounded-2xl px-4 py-3 text-sm leading-relaxed ${
                  msg.role === 'user'
                    ? 'bg-noir text-white rounded-tr-none'
                    : 'bg-white text-noir border border-ivory-dark rounded-tl-none shadow-sm'
                }`}>
                  {msg.isLoading ? (
                    <div className="flex gap-1.5 py-0.5">
                      {[0, 150, 300].map((d) => (
                        <span key={d} className="w-1.5 h-1.5 bg-noir/20 rounded-full animate-bounce"
                          style={{ animationDelay: `${d}ms` }} />
                      ))}
                    </div>
                  ) : (
                    <p className="whitespace-pre-line">{msg.content}</p>
                  )}
                </div>

                {/* MCQ clarification chips */}
                {msg.role === 'assistant' && msg.options && msg.options.length > 0 && (
                  <div className="flex flex-wrap gap-2 pt-1">
                    {msg.options.map((opt) => (
                      <button
                        key={opt}
                        onClick={() => sendMessage(opt)}
                        disabled={isLoading}
                        className="text-[12px] px-3.5 py-1.5 bg-white border border-ivory-dark text-noir/70 rounded-full hover:bg-gold/10 hover:border-gold/40 hover:text-noir transition-all disabled:opacity-40 shadow-sm"
                      >
                        {opt}
                      </button>
                    ))}
                  </div>
                )}

                {/* Product strip */}
                {msg.products && msg.products.length > 0 && (
                  <div>
                    <div className="flex items-center gap-2 mb-2.5">
                      <span className="text-[10px] tracking-[0.2em] uppercase text-noir/40">Similar Products</span>
                      <span className="inline-flex items-center px-2 py-0.5 rounded-full bg-gold/10 text-amber-700 border border-gold/30 text-[10px] font-semibold">
                        📦 {msg.products.length} results
                      </span>
                    </div>
                    <div className="flex gap-3 overflow-x-auto pb-1 scrollbar-hide">
                      {msg.products.map((product) => (
                        <ProductCard
                          key={product.id}
                          product={product}
                          onProductClick={onProductClick}
                          onTryOn={(url, title) => setTryOnGarment({ imageUrl: url, title })}
                          onWishlistToggle={onWishlistToggle}
                          wishlisted={isWishlisted(product.id)}
                          onCompleteTheLook={handleCompleteTheLook}
                          hideCompleteTheLook={msg.isOutfitResult}
                        />
                      ))}
                    </div>
                  </div>
                )}

                {/* Web results */}
                {msg.webLinks && msg.webLinks.length > 0 && (
                  <div className="space-y-2">
                    <div className="flex items-center gap-2 mb-1">
                      <span className="text-[10px] tracking-[0.2em] uppercase text-noir/40">Online Finds</span>
                      <span className="text-[10px] text-noir/30">{msg.webLinks.length} products</span>
                    </div>
                    {msg.webLinks.map((link, li) => (
                      <WebLinkCard
                        key={li}
                        link={link}
                        onTryOn={(url, title) => setTryOnGarment({ imageUrl: url, title })}
                        onWishlistToggle={onWishlistToggle}
                        wishlisted={isWishlisted(link.url)}
                        onCompleteTheLook={handleCompleteTheLook}
                        hideCompleteTheLook={msg.isOutfitResult}
                      />
                    ))}
                  </div>
                )}
              </div>

              {/* User avatar */}
              {msg.role === 'user' && (
                <div className="w-7 h-7 rounded-full bg-ivory-dark flex items-center justify-center flex-shrink-0 mt-1">
                  <span className="text-xs font-bold text-noir/50">U</span>
                </div>
              )}
            </div>
          ))}
          <div ref={bottomRef} />
        </div>

        {/* Suggestion chips */}
        {bubbles.length === 1 && (
          <div className="px-5 pt-3 pb-1 flex flex-wrap gap-2 bg-white border-t border-ivory-dark">
            {SUGGESTIONS.map((s) => (
              <button
                key={s}
                onClick={() => sendMessage(s)}
                className="text-[11px] px-3 py-1.5 bg-ivory border border-ivory-dark text-noir/60 rounded-full hover:bg-gold/10 hover:border-gold/30 hover:text-noir transition-all"
              >
                {s}
              </button>
            ))}
          </div>
        )}

        {/* Pending image preview */}
        {imagePreview && (
          <div className="px-5 py-2 bg-white border-t border-ivory-dark">
            <div className="relative inline-block">
              <img src={imagePreview} alt="pending" className="h-14 w-14 object-cover rounded-xl border border-ivory-dark" />
              <button onClick={clearImage}
                className="absolute -top-1.5 -right-1.5 w-5 h-5 bg-noir text-white rounded-full flex items-center justify-center hover:bg-red-600 transition-colors">
                <X className="h-3 w-3" />
              </button>
            </div>
          </div>
        )}

        {/* Input bar */}
        <div className="px-5 py-4 bg-white border-t border-ivory-dark">
          <div className="flex items-center gap-2.5 bg-ivory rounded-2xl px-3 py-2 border border-ivory-dark focus-within:border-gold/50 focus-within:shadow-sm transition-all">
            {/* Image upload */}
            <button
              onClick={() => fileInputRef.current?.click()}
              disabled={isLoading}
              className="p-1.5 text-noir/30 hover:text-gold rounded-xl transition-colors disabled:opacity-30"
              title="Upload image"
            >
              <ImageIcon className="h-4 w-4" />
            </button>
            <input ref={fileInputRef} type="file" accept="image/jpeg,image/png,image/webp"
              className="hidden"
              onChange={(e) => { const f = e.target.files?.[0]; if (f) handleImageSelect(f) }} />

            {/* Text input */}
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(input, pendingImage || undefined) } }}
              placeholder={pendingImage ? 'Add a description (optional)...' : 'Ask your AI stylist anything...'}
              disabled={isLoading}
              className="flex-1 bg-transparent text-sm text-noir placeholder:text-noir/30 outline-none disabled:opacity-50"
            />

            {/* Send */}
            <button
              onClick={() => sendMessage(input, pendingImage || undefined)}
              disabled={(!input.trim() && !pendingImage) || isLoading}
              className="p-2 bg-noir text-white rounded-xl hover:bg-noir-soft disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
            >
              <Send className="h-3.5 w-3.5" />
            </button>
          </div>
        </div>
      </div>

      {tryOnGarment && (
        <TryOnModal
          garmentImageUrl={tryOnGarment.imageUrl}
          garmentTitle={tryOnGarment.title}
          onClose={() => setTryOnGarment(null)}
        />
      )}
    </div>
  )
}
