'use client'

import { useState, useRef, useEffect } from 'react'
import Image from 'next/image'
import { Send, Sparkles, ExternalLink, ImageIcon, X, Shirt } from 'lucide-react'
import { ChatMessage, SearchResult } from '@/types'
import { sendChatMessage } from '@/lib/api'
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
  source?: string   // "google_lens" | undefined (undefined = web/serper search)
}

interface MessageBubble {
  role: 'user' | 'assistant'
  content: string
  imagePreview?: string      // base64 preview of uploaded image
  products?: SearchResult[]
  webLinks?: WebLink[]
  isLoading?: boolean
}

// ── Constants ──────────────────────────────────────────────────────────────

const WELCOME: MessageBubble = {
  role: 'assistant',
  content:
    "Hi! I'm your AI fashion assistant ✨\n\nTell me what you're looking for and I'll find the best matches. You can also upload an image!\n\nTry:\n• \"Find me a casual blue kurta under ₹1000\"\n• \"Something elegant for a wedding\"\n• \"Show me floral summer dresses\"",
}

const SUGGESTIONS = [
  'Find me a casual kurta for men',
  'Floral summer dresses for women',
  'Something for a wedding under ₹2000',
  'Casual tops for women',
]

// ── Product mini-card ──────────────────────────────────────────────────────

function ProductCard({
  product,
  onProductClick,
  onTryOn,
}: {
  product: SearchResult
  onProductClick: (p: SearchResult) => void
  onTryOn: (imageUrl: string, title: string) => void
}) {
  return (
    <div
      onClick={() => onProductClick(product)}
      className="flex-shrink-0 w-36 bg-white rounded-xl border border-gray-200 overflow-hidden cursor-pointer hover:shadow-md transition-shadow"
    >
      <div className="aspect-[3/4] relative bg-gray-100">
        <Image
          src={product.image_url}
          alt={product.title}
          fill
          className="object-cover"
          sizes="144px"
        />
        <div className="absolute top-1 left-1 px-1.5 py-0.5 bg-white/90 rounded-full text-xs font-medium text-purple-700">
          {formatSimilarity(product.similarity)}
        </div>
      </div>
      <div className="p-2">
        <p className="text-xs font-medium text-gray-800 line-clamp-2 leading-tight mb-1">
          {product.title}
        </p>
        {product.price && (
          <p className="text-xs font-bold text-gray-900">
            {formatPrice(product.price, product.currency)}
          </p>
        )}
        <div className="mt-1 flex items-center gap-2">
          {product.product_url && (
            <a
              href={product.product_url}
              target="_blank"
              rel="noopener noreferrer"
              onClick={(e) => e.stopPropagation()}
              className="flex items-center gap-1 text-xs text-purple-600 hover:text-purple-800"
            >
              <ExternalLink className="h-3 w-3" />
              View
            </a>
          )}
          <button
            onClick={(e) => { e.stopPropagation(); onTryOn(product.image_url, product.title) }}
            className="flex items-center gap-1 text-xs text-emerald-600 hover:text-emerald-800"
            title="Virtual Try-On"
          >
            <Shirt className="h-3 w-3" />
            Try
          </button>
        </div>
      </div>
    </div>
  )
}

// ── Source badge ───────────────────────────────────────────────────────────

function SourceBadge({ source }: { source?: string }) {
  if (source === 'google_lens') {
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-blue-50 text-blue-700 border border-blue-200">
        🔍 Google Lens
      </span>
    )
  }
  return (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
      🛒 Web Search
    </span>
  )
}

// ── Web link card ──────────────────────────────────────────────────────────

function WebLinkCard({ link, onTryOn }: { link: WebLink; onTryOn: (imageUrl: string, title: string) => void }) {
  // Product card (Serper results — has image)
  if (link.image_url) {
    return (
      <div className="flex items-start gap-3 p-3 bg-white border border-gray-200 rounded-xl hover:border-purple-300 hover:shadow-sm transition-all">
        <a href={link.url} target="_blank" rel="noopener noreferrer" className="w-20 h-20 relative flex-shrink-0 rounded-lg overflow-hidden bg-gray-100">
          <Image
            src={link.image_url}
            alt={link.title}
            fill
            className="object-cover"
            sizes="80px"
          />
        </a>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 mb-1">
            <SourceBadge source={link.source} />
          </div>
          <a href={link.url} target="_blank" rel="noopener noreferrer">
            <p className="text-sm font-medium text-gray-900 line-clamp-2 leading-tight hover:text-purple-700">{link.title}</p>
          </a>
          {link.price && (
            <p className="text-sm font-bold text-gray-900 mt-1">{link.price}</p>
          )}
          {link.rating && (
            <p className="text-xs text-amber-600 mt-0.5">
              ★ {link.rating.toFixed(1)}{link.rating_count ? ` (${link.rating_count.toLocaleString()})` : ''}
            </p>
          )}
          <p className="text-xs text-purple-600 mt-0.5">{link.source_site || link.url}</p>
          {link.snippet && (
            <p className="text-xs text-emerald-700 mt-1 line-clamp-2 italic">{link.snippet}</p>
          )}
          <button
            onClick={() => onTryOn(link.image_url!, link.title)}
            className="mt-2 flex items-center gap-1 text-xs text-emerald-600 hover:text-emerald-800 font-medium"
          >
            <Shirt className="h-3 w-3" />
            Virtual Try-On
          </button>
        </div>
      </div>
    )
  }

  // Link card (direct e-commerce search links — no image)
  return (
    <a
      href={link.url}
      target="_blank"
      rel="noopener noreferrer"
      className="flex items-start gap-3 p-3 bg-white border border-gray-200 rounded-xl hover:border-purple-300 hover:shadow-sm transition-all"
    >
      <div className="w-8 h-8 rounded-lg bg-purple-100 flex items-center justify-center flex-shrink-0 mt-0.5">
        <ExternalLink className="h-4 w-4 text-purple-600" />
      </div>
      <div className="min-w-0">
        <p className="text-sm font-medium text-gray-900 line-clamp-1">{link.title}</p>
        {link.price && <p className="text-xs font-bold text-gray-700 mt-0.5">{link.price}</p>}
        <p className="text-xs text-purple-600 mt-0.5">{link.source_site || link.url}</p>
        {link.snippet && (
          <p className="text-xs text-gray-500 mt-1 line-clamp-2">{link.snippet}</p>
        )}
      </div>
    </a>
  )
}

// ── Main component ─────────────────────────────────────────────────────────

interface ChatAssistantProps {
  onProductClick: (product: SearchResult) => void
}

export default function ChatAssistant({ onProductClick }: ChatAssistantProps) {
  const [bubbles, setBubbles] = useState<MessageBubble[]>([WELCOME])
  const [input, setInput] = useState('')
  const [pendingImage, setPendingImage] = useState<File | null>(null)
  const [imagePreview, setImagePreview] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(false)

  // Session state — mirrored from server responses
  const [conversationId, setConversationId] = useState<string | undefined>()
  const [userPreferences, setUserPreferences] = useState<Record<string, unknown>>({})
  const [clarificationCount, setClarificationCount] = useState(0)

  // Virtual Try-On state
  const [tryOnGarment, setTryOnGarment] = useState<{ imageUrl: string; title: string } | null>(null)

  const openTryOn = (imageUrl: string, title: string) => {
    setTryOnGarment({ imageUrl, title })
  }

  // API-format messages (role + content only)
  const apiMessages = useRef<ChatMessage[]>([])

  const bottomRef = useRef<HTMLDivElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [bubbles])

  // ── Image selection ────────────────────────────────────────────────────

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

  // ── Send message ───────────────────────────────────────────────────────

  const sendMessage = async (text: string, imageFile?: File) => {
    const messageText = text.trim()
    if (!messageText && !imageFile) return
    if (isLoading) return

    const displayText = messageText || (imageFile ? 'I uploaded an image — find similar products.' : '')

    // User bubble
    const userBubble: MessageBubble = {
      role: 'user',
      content: displayText,
      imagePreview: imageFile ? imagePreview || undefined : undefined,
    }
    const loadingBubble: MessageBubble = { role: 'assistant', content: '', isLoading: true }

    setBubbles((prev) => [...prev, userBubble, loadingBubble])
    setInput('')
    clearImage()
    setIsLoading(true)

    // Update API history
    apiMessages.current = [
      ...apiMessages.current,
      { role: 'user', content: displayText },
    ]

    try {
      const response = await sendChatMessage(apiMessages.current, {
        conversationId,
        image: imageFile,
        userPreferences,
        clarificationCount,
      })

      // Persist session state from server
      if (response.conversation_id) setConversationId(response.conversation_id)
      if (response.user_preferences) setUserPreferences(response.user_preferences as Record<string, unknown>)
      if (response.clarification_count !== undefined) setClarificationCount(response.clarification_count)

      // Update API history with assistant reply
      apiMessages.current = [
        ...apiMessages.current,
        { role: 'assistant', content: response.message },
      ]

      // Replace loading bubble with real response
      setBubbles((prev) => [
        ...prev.slice(0, -1),
        {
          role: 'assistant',
          content: response.message,
          products: response.products as unknown as SearchResult[],
          webLinks: response.web_results as unknown as WebLink[],
        },
      ])
    } catch {
      setBubbles((prev) => [
        ...prev.slice(0, -1),
        { role: 'assistant', content: "Sorry, something went wrong. Please try again." },
      ])
    } finally {
      setIsLoading(false)
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      sendMessage(input, pendingImage || undefined)
    }
  }

  // ── Render ─────────────────────────────────────────────────────────────

  return (
    <div className="flex flex-col h-[640px]">

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {bubbles.map((msg, i) => (
          <div key={i} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>

            {/* Assistant avatar */}
            {msg.role === 'assistant' && (
              <div className="w-7 h-7 rounded-full bg-purple-100 flex items-center justify-center mr-2 flex-shrink-0 mt-1">
                <Sparkles className="h-4 w-4 text-purple-600" />
              </div>
            )}

            <div className="max-w-[80%] space-y-3">
              {/* Uploaded image preview (user side) */}
              {msg.imagePreview && (
                <div className="w-32 h-32 relative rounded-xl overflow-hidden border border-gray-200">
                  <Image src={msg.imagePreview} alt="uploaded" fill className="object-cover" sizes="128px" />
                </div>
              )}

              {/* Message bubble */}
              <div
                className={`rounded-2xl px-4 py-3 text-sm ${
                  msg.role === 'user'
                    ? 'bg-primary-600 text-white rounded-tr-none'
                    : 'bg-gray-100 text-gray-800 rounded-tl-none'
                }`}
              >
                {msg.isLoading ? (
                  <div className="flex gap-1 py-1">
                    <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                    <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                    <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
                  </div>
                ) : (
                  <p className="whitespace-pre-line leading-relaxed">{msg.content}</p>
                )}
              </div>

              {/* Product cards strip — Local Database results */}
              {msg.products && msg.products.length > 0 && (
                <div>
                  <p className="text-xs font-semibold px-1 mb-2 flex items-center gap-1.5">
                    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-purple-50 text-purple-700 border border-purple-200">
                      📦 Local Database
                    </span>
                    <span className="text-gray-400 font-normal">{msg.products.length} results</span>
                  </p>
                  <div className="flex gap-3 overflow-x-auto pb-2">
                    {msg.products.map((product) => (
                      <ProductCard
                        key={product.id}
                        product={product}
                        onProductClick={onProductClick}
                        onTryOn={openTryOn}
                      />
                    ))}
                  </div>
                </div>
              )}

              {/* Web search links — Serper Shopping + Google Lens */}
              {msg.webLinks && msg.webLinks.length > 0 && (
                <div className="space-y-2">
                  <p className="text-xs text-gray-500 font-medium px-1">
                    {msg.webLinks.some(l => l.image_url)
                      ? '🌐 Online results:'
                      : '🌐 Search results from the web:'}
                    {' '}
                    <span className="text-gray-400 font-normal">{msg.webLinks.length} found</span>
                  </p>
                  {msg.webLinks.map((link, li) => (
                    <WebLinkCard key={li} link={link} onTryOn={openTryOn} />
                  ))}
                </div>
              )}
            </div>
          </div>
        ))}
        <div ref={bottomRef} />
      </div>

      {/* Suggestion chips — only at start */}
      {bubbles.length === 1 && (
        <div className="px-4 pb-2 flex flex-wrap gap-2">
          {SUGGESTIONS.map((s) => (
            <button
              key={s}
              onClick={() => sendMessage(s)}
              className="text-xs px-3 py-1.5 bg-purple-50 border border-purple-200 text-purple-700 rounded-full hover:bg-purple-100 transition-colors"
            >
              {s}
            </button>
          ))}
        </div>
      )}

      {/* Pending image preview */}
      {imagePreview && (
        <div className="px-4 pb-2">
          <div className="relative inline-block">
            <img src={imagePreview} alt="pending" className="h-16 w-16 object-cover rounded-lg border border-gray-200" />
            <button
              onClick={clearImage}
              className="absolute -top-1.5 -right-1.5 w-5 h-5 bg-red-500 text-white rounded-full flex items-center justify-center"
            >
              <X className="h-3 w-3" />
            </button>
          </div>
        </div>
      )}

      {/* Input bar */}
      <div className="border-t border-gray-100 p-4">
        <div className="flex items-center gap-2">
          {/* Image upload button */}
          <button
            onClick={() => fileInputRef.current?.click()}
            disabled={isLoading}
            className="p-2.5 text-gray-400 hover:text-purple-600 hover:bg-purple-50 rounded-xl transition-colors disabled:opacity-40"
            title="Upload image"
          >
            <ImageIcon className="h-4 w-4" />
          </button>
          <input
            ref={fileInputRef}
            type="file"
            accept="image/jpeg,image/png,image/webp"
            className="hidden"
            onChange={(e) => {
              const file = e.target.files?.[0]
              if (file) handleImageSelect(file)
            }}
          />

          {/* Text input */}
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={pendingImage ? 'Add a description (optional)...' : 'Ask me to find fashion items...'}
            disabled={isLoading}
            className="flex-1 px-4 py-2.5 rounded-xl border border-gray-200 focus:outline-none focus:ring-2 focus:ring-purple-300 focus:border-transparent text-sm disabled:opacity-50"
          />

          {/* Send button */}
          <button
            onClick={() => sendMessage(input, pendingImage || undefined)}
            disabled={(!input.trim() && !pendingImage) || isLoading}
            className="p-2.5 bg-purple-600 text-white rounded-xl hover:bg-purple-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            <Send className="h-4 w-4" />
          </button>
        </div>

        <p className="text-xs text-gray-400 mt-2 text-center">
          Powered by Gemini AI + CLIP · LangGraph
        </p>
      </div>

      {/* Virtual Try-On Modal */}
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
