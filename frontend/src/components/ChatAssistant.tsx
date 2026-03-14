'use client'

import { useState, useRef, useEffect, MutableRefObject } from 'react'
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
  source?: string
}

interface MessageBubble {
  role: 'user' | 'assistant'
  content: string
  imagePreview?: string
  products?: SearchResult[]
  webLinks?: WebLink[]
  options?: string[]   // MCQ chips for clarification questions
  isLoading?: boolean
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

// ── Source badge ───────────────────────────────────────────────────────────

function SourceBadge({ source }: { source?: string }) {
  if (source === 'google_lens') {
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-blue-50 text-blue-700 border border-blue-100">
        🔍 Google Lens
      </span>
    )
  }
  return (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-emerald-50 text-emerald-700 border border-emerald-100">
      🛒 Web Search
    </span>
  )
}

// ── Product card ───────────────────────────────────────────────────────────

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
      className="flex-shrink-0 w-36 bg-white rounded-2xl border border-ivory-dark overflow-hidden cursor-pointer hover:shadow-md hover:-translate-y-0.5 transition-all duration-200 group"
    >
      <div className="aspect-[3/4] relative bg-ivory">
        <Image src={product.image_url} alt={product.title} fill className="object-cover" sizes="144px" />
        <div className="absolute top-1.5 left-1.5 px-1.5 py-0.5 bg-white/95 rounded-full text-[10px] font-semibold text-noir/70 shadow-sm">
          {formatSimilarity(product.similarity)}
        </div>
        <div className="absolute inset-0 bg-noir/0 group-hover:bg-noir/5 transition-colors" />
      </div>
      <div className="p-2.5">
        <p className="text-[11px] font-medium text-noir leading-tight line-clamp-2 mb-1.5">{product.title}</p>
        {product.price && (
          <p className="text-xs font-bold text-noir">{formatPrice(product.price, product.currency)}</p>
        )}
        <div className="mt-2 flex items-center gap-2">
          {product.product_url && (
            <a
              href={product.product_url}
              target="_blank"
              rel="noopener noreferrer"
              onClick={(e) => e.stopPropagation()}
              className="flex items-center gap-0.5 text-[10px] text-noir/50 hover:text-gold transition-colors"
            >
              <ExternalLink className="h-2.5 w-2.5" /> View
            </a>
          )}
          <button
            onClick={(e) => { e.stopPropagation(); onTryOn(product.image_url, product.title) }}
            className="flex items-center gap-0.5 text-[10px] text-noir/50 hover:text-gold transition-colors"
          >
            <Shirt className="h-2.5 w-2.5" /> Try
          </button>
        </div>
      </div>
    </div>
  )
}

// ── Web link card ──────────────────────────────────────────────────────────

function WebLinkCard({ link, onTryOn }: { link: WebLink; onTryOn: (imageUrl: string, title: string) => void }) {
  if (link.image_url) {
    return (
      <div className="flex items-start gap-3 p-3.5 bg-ivory rounded-2xl border border-ivory-dark hover:border-gold/30 hover:shadow-sm transition-all">
        <a href={link.url} target="_blank" rel="noopener noreferrer"
          className="w-20 h-20 relative flex-shrink-0 rounded-xl overflow-hidden bg-white border border-ivory-dark">
          <Image src={link.image_url} alt={link.title} fill className="object-cover" sizes="80px" />
        </a>
        <div className="min-w-0 flex-1">
          <div className="mb-1.5">
            <SourceBadge source={link.source} />
          </div>
          <a href={link.url} target="_blank" rel="noopener noreferrer">
            <p className="text-sm font-medium text-noir line-clamp-2 leading-tight hover:text-gold transition-colors">{link.title}</p>
          </a>
          {link.price && <p className="text-sm font-bold text-noir mt-1">{link.price}</p>}
          {link.rating && (
            <p className="text-xs text-amber-600 mt-0.5">
              ★ {link.rating.toFixed(1)}{link.rating_count ? ` (${link.rating_count.toLocaleString()})` : ''}
            </p>
          )}
          <p className="text-[11px] text-noir/40 mt-0.5">{link.source_site || ''}</p>
          {link.snippet && <p className="text-xs text-noir/50 mt-1 line-clamp-2 italic">{link.snippet}</p>}
          <button
            onClick={() => onTryOn(link.image_url!, link.title)}
            className="mt-2 flex items-center gap-1 text-[11px] text-noir/50 hover:text-gold font-medium transition-colors"
          >
            <Shirt className="h-3 w-3" /> Virtual Try‑On
          </button>
        </div>
      </div>
    )
  }

  return (
    <a href={link.url} target="_blank" rel="noopener noreferrer"
      className="flex items-start gap-3 p-3.5 bg-ivory rounded-2xl border border-ivory-dark hover:border-gold/30 hover:shadow-sm transition-all">
      <div className="w-8 h-8 rounded-xl bg-noir flex items-center justify-center flex-shrink-0 mt-0.5">
        <ExternalLink className="h-3.5 w-3.5 text-gold" />
      </div>
      <div className="min-w-0">
        <p className="text-sm font-medium text-noir line-clamp-1">{link.title}</p>
        {link.price && <p className="text-xs font-bold text-noir mt-0.5">{link.price}</p>}
        <p className="text-[11px] text-noir/40 mt-0.5">{link.source_site || link.url}</p>
        {link.snippet && <p className="text-xs text-noir/50 mt-1 line-clamp-2">{link.snippet}</p>}
      </div>
    </a>
  )
}

// ── Main component ─────────────────────────────────────────────────────────

interface ChatAssistantProps {
  onProductClick: (product: SearchResult) => void
  triggerRef?: MutableRefObject<((query: string) => void) | null>
}

export default function ChatAssistant({ onProductClick, triggerRef }: ChatAssistantProps) {
  const [bubbles, setBubbles] = useState<MessageBubble[]>([WELCOME])
  const [input, setInput] = useState('')
  const [pendingImage, setPendingImage] = useState<File | null>(null)
  const [imagePreview, setImagePreview] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [conversationId, setConversationId] = useState<string | undefined>()
  const [userPreferences, setUserPreferences] = useState<Record<string, unknown>>({})
  const [clarificationCount, setClarificationCount] = useState(0)
  const [tryOnGarment, setTryOnGarment] = useState<{ imageUrl: string; title: string } | null>(null)

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

  const sendMessage = async (text: string, imageFile?: File, fromTrend = false) => {
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
      })
      if (response.conversation_id) setConversationId(response.conversation_id)
      if (response.user_preferences) setUserPreferences(response.user_preferences as Record<string, unknown>)
      if (response.clarification_count !== undefined) setClarificationCount(response.clarification_count)
      apiMessages.current = [...apiMessages.current, { role: 'assistant', content: response.message }]
      setBubbles((prev) => [
        ...prev.slice(0, -1),
        {
          role: 'assistant',
          content: response.message,
          products:  response.products  as unknown as SearchResult[],
          webLinks:  response.web_results as unknown as WebLink[],
          options:   response.options,
        },
      ])
    } catch {
      setBubbles((prev) => [
        ...prev.slice(0, -1),
        { role: 'assistant', content: 'Something went wrong. Please try again.' },
      ])
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div className="flex flex-col h-[680px]">

      {/* Chat header bar */}
      <div className="flex items-center gap-3 px-5 py-3.5 border-b border-ivory-dark bg-white">
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

              {/* Local DB product strip */}
              {msg.products && msg.products.length > 0 && (
                <div>
                  <div className="flex items-center gap-2 mb-2.5">
                    <span className="text-[10px] tracking-[0.2em] uppercase text-noir/40">Local Database</span>
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
