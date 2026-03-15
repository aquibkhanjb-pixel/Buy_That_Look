'use client'

import { useState, useRef } from 'react'
import Image from 'next/image'
import {
  Search, Upload, X, ExternalLink, Heart, Shirt, ImageIcon, Sparkles, Link2
} from 'lucide-react'
import { SearchResult, ChatResponse } from '@/types'
import { findThisLook } from '@/lib/api'
import { formatPrice, formatSimilarity } from '@/lib/utils'
import TryOnModal from './TryOnModal'

interface FindThisLookProps {
  onProductClick: (product: SearchResult) => void
  onWishlistToggle: (product: SearchResult) => void
  isWishlisted: (id: string) => boolean
}

interface ResultState {
  message: string
  products: SearchResult[]
  webLinks: {
    title: string; url: string; snippet?: string; price?: string
    source_site?: string; image_url?: string; rating?: number
    rating_count?: number; source?: string
  }[]
}

export default function FindThisLook({
  onProductClick,
  onWishlistToggle,
  isWishlisted,
}: FindThisLookProps) {
  const [imageUrl, setImageUrl] = useState('')
  const [pendingImage, setPendingImage] = useState<File | null>(null)
  const [imagePreview, setImagePreview] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [result, setResult] = useState<ResultState | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [tryOnGarment, setTryOnGarment] = useState<{ imageUrl: string; title: string } | null>(null)

  const fileInputRef = useRef<HTMLInputElement>(null)

  const handleFileSelect = (file: File) => {
    setPendingImage(file)
    setImageUrl('')
    const reader = new FileReader()
    reader.onload = (e) => setImagePreview(e.target?.result as string)
    reader.readAsDataURL(file)
    setResult(null)
    setError(null)
  }

  const clearImage = () => {
    setPendingImage(null)
    setImagePreview(null)
    if (fileInputRef.current) fileInputRef.current.value = ''
  }

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    const file = e.dataTransfer.files?.[0]
    if (file && file.type.startsWith('image/')) handleFileSelect(file)
  }

  const handleAnalyse = async () => {
    if (!imageUrl.trim() && !pendingImage) return
    if (isLoading) return

    setIsLoading(true)
    setResult(null)
    setError(null)

    try {
      const response: ChatResponse = await findThisLook({
        imageUrl: imageUrl.trim() || undefined,
        image: pendingImage || undefined,
      })
      setResult({
        message: response.message,
        products: response.products as unknown as SearchResult[],
        webLinks: response.web_results as unknown as ResultState['webLinks'],
      })
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        'Something went wrong. Please try again.'
      setError(msg)
    } finally {
      setIsLoading(false)
    }
  }

  const hasInput = imageUrl.trim() || pendingImage

  return (
    <div className="space-y-6">

      {/* Hero label */}
      <div className="text-center">
        <h2 className="font-serif text-2xl text-noir">Find This Look</h2>
        <p className="text-sm text-noir/50 mt-1">
          Paste any image URL or upload a photo — we&apos;ll find where to buy it.
        </p>
      </div>

      {/* Input card */}
      <div className="bg-white rounded-3xl border border-ivory-dark shadow-sm p-6 space-y-4">

        {/* URL input */}
        <div>
          <label className="text-xs tracking-[0.2em] uppercase text-noir/40 mb-2 block">
            Paste Image URL
          </label>
          <div className="flex gap-2">
            <div className="flex-1 flex items-center gap-2 bg-ivory rounded-2xl px-4 py-2.5 border border-ivory-dark focus-within:border-gold/50 transition-all">
              <Link2 className="h-4 w-4 text-noir/30 flex-shrink-0" />
              <input
                type="url"
                value={imageUrl}
                onChange={(e) => {
                  setImageUrl(e.target.value)
                  if (e.target.value) { clearImage(); setResult(null); setError(null) }
                }}
                onKeyDown={(e) => { if (e.key === 'Enter') handleAnalyse() }}
                placeholder="https://example.com/dress.jpg or any product image URL"
                disabled={!!pendingImage || isLoading}
                className="flex-1 bg-transparent text-sm text-noir placeholder:text-noir/30 outline-none disabled:opacity-40"
              />
              {imageUrl && (
                <button onClick={() => { setImageUrl(''); setError(null) }}>
                  <X className="h-3.5 w-3.5 text-noir/30 hover:text-noir transition-colors" />
                </button>
              )}
            </div>
          </div>
        </div>

        {/* Divider */}
        <div className="flex items-center gap-3">
          <div className="flex-1 h-px bg-ivory-dark" />
          <span className="text-[10px] tracking-[0.2em] uppercase text-noir/30">or upload</span>
          <div className="flex-1 h-px bg-ivory-dark" />
        </div>

        {/* Drop zone */}
        {!pendingImage ? (
          <div
            onDrop={handleDrop}
            onDragOver={(e) => e.preventDefault()}
            onClick={() => fileInputRef.current?.click()}
            className="border-2 border-dashed border-ivory-dark rounded-2xl py-8 flex flex-col items-center gap-3 cursor-pointer hover:border-gold/40 hover:bg-gold/5 transition-all"
          >
            <div className="w-12 h-12 rounded-full bg-ivory flex items-center justify-center">
              <Upload className="h-5 w-5 text-noir/30" />
            </div>
            <div className="text-center">
              <p className="text-sm font-medium text-noir/60">Drop a screenshot here</p>
              <p className="text-xs text-noir/30 mt-0.5">JPEG, PNG, WebP · max 10 MB</p>
            </div>
          </div>
        ) : (
          <div className="relative inline-block">
            <img
              src={imagePreview!}
              alt="preview"
              className="h-36 w-36 object-cover rounded-2xl border border-ivory-dark"
            />
            <button
              onClick={clearImage}
              className="absolute -top-2 -right-2 w-6 h-6 bg-noir text-white rounded-full flex items-center justify-center hover:bg-red-600 transition-colors shadow-sm"
            >
              <X className="h-3 w-3" />
            </button>
            <p className="text-xs text-noir/40 mt-2 truncate max-w-[144px]">{pendingImage.name}</p>
          </div>
        )}

        <input
          ref={fileInputRef}
          type="file"
          accept="image/jpeg,image/png,image/webp"
          className="hidden"
          onChange={(e) => { const f = e.target.files?.[0]; if (f) handleFileSelect(f) }}
        />

        {/* Analyse button */}
        <button
          onClick={handleAnalyse}
          disabled={!hasInput || isLoading}
          className="w-full py-3 bg-noir text-white rounded-2xl text-sm font-medium tracking-wide hover:bg-noir/90 disabled:opacity-30 disabled:cursor-not-allowed transition-all flex items-center justify-center gap-2"
        >
          {isLoading ? (
            <>
              <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
              Analysing with Gemini Vision...
            </>
          ) : (
            <>
              <Search className="h-4 w-4" />
              Find This Look
            </>
          )}
        </button>

        {/* Tips */}
        <div className="flex flex-wrap gap-2">
          {[
            '📸 Screenshot from Instagram',
            '🛍️ Product page image',
            '📌 Pinterest pin URL',
            '🔗 Direct .jpg / .png URL',
          ].map((tip) => (
            <span key={tip} className="text-[11px] px-2.5 py-1 bg-ivory rounded-full text-noir/40 border border-ivory-dark">
              {tip}
            </span>
          ))}
        </div>
      </div>

      {/* Error */}
      {error && (
        <div className="bg-red-50 border border-red-200 rounded-2xl px-5 py-4 text-sm text-red-700">
          {error}
        </div>
      )}

      {/* Results */}
      {result && (
        <div className="space-y-5">
          {/* AI message */}
          <div className="bg-white rounded-2xl border border-ivory-dark shadow-sm p-4 flex gap-3">
            <div className="w-7 h-7 rounded-full bg-noir flex items-center justify-center flex-shrink-0 mt-0.5">
              <Sparkles className="h-3.5 w-3.5 text-gold" />
            </div>
            <p className="text-sm text-noir leading-relaxed whitespace-pre-line">{result.message}</p>
          </div>

          {/* Product cards */}
          {result.products.length > 0 && (
            <div>
              <div className="flex items-center gap-2 mb-3">
                <span className="text-[10px] tracking-[0.2em] uppercase text-noir/40">Similar Products</span>
                <span className="inline-flex items-center px-2 py-0.5 rounded-full bg-gold/10 text-amber-700 border border-gold/30 text-[10px] font-semibold">
                  📦 {result.products.length} found
                </span>
              </div>
              <div className="flex gap-3 overflow-x-auto pb-2 scrollbar-hide">
                {result.products.map((product) => (
                  <FindLookProductCard
                    key={product.id}
                    product={product}
                    onProductClick={onProductClick}
                    onTryOn={(url, title) => setTryOnGarment({ imageUrl: url, title })}
                    onWishlistToggle={onWishlistToggle}
                    wishlisted={isWishlisted(product.id)}
                  />
                ))}
              </div>
            </div>
          )}

          {/* Web links */}
          {result.webLinks.length > 0 && (
            <div className="space-y-2">
              <div className="flex items-center gap-2 mb-1">
                <span className="text-[10px] tracking-[0.2em] uppercase text-noir/40">Online Finds</span>
                <span className="text-[10px] text-noir/30">{result.webLinks.length} products</span>
              </div>
              {result.webLinks.map((link, i) => (
                <div key={i} className="flex items-start gap-3 p-3.5 bg-white rounded-2xl border border-ivory-dark hover:border-gold/30 hover:shadow-sm transition-all">
                  {link.image_url && (
                    <a href={link.url} target="_blank" rel="noopener noreferrer"
                      className="w-20 h-20 relative flex-shrink-0 rounded-xl overflow-hidden bg-ivory border border-ivory-dark">
                      <Image src={link.image_url} alt={link.title} fill className="object-cover" sizes="80px" />
                    </a>
                  )}
                  <div className="min-w-0 flex-1">
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
                    <div className="flex items-center gap-3 mt-2">
                      <a href={link.url} target="_blank" rel="noopener noreferrer"
                        className="flex items-center gap-1 text-[10px] text-noir/50 hover:text-gold transition-colors">
                        <ExternalLink className="h-2.5 w-2.5" /> View
                      </a>
                      {link.image_url && (
                        <button
                          onClick={() => setTryOnGarment({ imageUrl: link.image_url!, title: link.title })}
                          className="flex items-center gap-1 text-[10px] text-noir/50 hover:text-gold transition-colors">
                          <Shirt className="h-2.5 w-2.5" /> Try
                        </button>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

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

// ── Inline product card with heart ─────────────────────────────────────────

function FindLookProductCard({
  product,
  onProductClick,
  onTryOn,
  onWishlistToggle,
  wishlisted,
}: {
  product: SearchResult
  onProductClick: (p: SearchResult) => void
  onTryOn: (url: string, title: string) => void
  onWishlistToggle: (p: SearchResult) => void
  wishlisted: boolean
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
        <button
          onClick={(e) => { e.stopPropagation(); onWishlistToggle(product) }}
          className="absolute top-1.5 right-1.5 w-6 h-6 rounded-full bg-white/90 flex items-center justify-center shadow-sm hover:scale-110 transition-transform"
        >
          <Heart className={`h-3 w-3 ${wishlisted ? 'fill-red-500 text-red-500' : 'text-noir/40'}`} />
        </button>
      </div>
      <div className="p-2.5">
        <p className="text-[11px] font-medium text-noir leading-tight line-clamp-2 mb-1.5">{product.title}</p>
        {product.price && (
          <p className="text-xs font-bold text-noir">{formatPrice(product.price, product.currency)}</p>
        )}
        <div className="mt-2 flex items-center gap-2">
          {product.product_url && (
            <a href={product.product_url} target="_blank" rel="noopener noreferrer"
              onClick={(e) => e.stopPropagation()}
              className="flex items-center gap-0.5 text-[10px] text-noir/50 hover:text-gold transition-colors">
              <ExternalLink className="h-2.5 w-2.5" /> View
            </a>
          )}
          <button
            onClick={(e) => { e.stopPropagation(); onTryOn(product.image_url, product.title) }}
            className="flex items-center gap-0.5 text-[10px] text-noir/50 hover:text-gold transition-colors">
            <Shirt className="h-2.5 w-2.5" /> Try
          </button>
        </div>
      </div>
    </div>
  )
}
