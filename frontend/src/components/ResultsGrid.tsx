'use client'

import Image from 'next/image'
import { ExternalLink } from 'lucide-react'
import { SearchResult } from '@/types'
import { formatPrice, formatSimilarity, truncate } from '@/lib/utils'

interface ResultsGridProps {
  results: SearchResult[]
  isLoading: boolean
  onProductClick: (product: SearchResult) => void
}

function SkeletonCard() {
  return (
    <div className="card overflow-hidden animate-pulse">
      <div className="aspect-[3/4] bg-gray-200" />
      <div className="p-4 space-y-3">
        <div className="h-4 bg-gray-200 rounded w-3/4" />
        <div className="h-3 bg-gray-200 rounded w-1/2" />
        <div className="h-5 bg-gray-200 rounded w-1/4" />
      </div>
    </div>
  )
}

function ProductCard({
  product,
  onClick,
}: {
  product: SearchResult
  onClick: () => void
}) {
  return (
    <div
      onClick={onClick}
      className="card overflow-hidden cursor-pointer group"
    >
      {/* Image */}
      <div className="aspect-[3/4] relative bg-gray-100 overflow-hidden">
        <Image
          src={product.image_url}
          alt={product.title}
          fill
          className="object-cover group-hover:scale-105 transition-transform duration-300"
          sizes="(max-width: 640px) 100vw, (max-width: 1024px) 50vw, 25vw"
        />

        {/* Similarity Badge */}
        <div className="absolute top-2 left-2 px-2 py-1 bg-white/90 backdrop-blur-sm rounded-full text-xs font-medium text-primary-700">
          {formatSimilarity(product.similarity)} match
        </div>

        {/* Quick Actions */}
        <div className="absolute bottom-0 left-0 right-0 p-3 bg-gradient-to-t from-black/60 to-transparent opacity-0 group-hover:opacity-100 transition-opacity">
          <a
            href={product.product_url}
            target="_blank"
            rel="noopener noreferrer"
            onClick={(e) => e.stopPropagation()}
            className="flex items-center justify-center gap-2 w-full py-2 bg-white rounded-lg text-sm font-medium text-gray-900 hover:bg-gray-100"
          >
            <ExternalLink className="h-4 w-4" />
            View on {product.source_site}
          </a>
        </div>
      </div>

      {/* Details */}
      <div className="p-4">
        {/* Brand */}
        {product.brand && (
          <p className="text-xs font-medium text-primary-600 uppercase tracking-wide mb-1">
            {product.brand}
          </p>
        )}

        {/* Title */}
        <h3 className="font-medium text-gray-900 line-clamp-2 mb-2">
          {truncate(product.title, 60)}
        </h3>

        {/* Category */}
        {product.category && (
          <p className="text-xs text-gray-500 mb-2">
            {product.category}
          </p>
        )}

        {/* Price */}
        <div className="flex items-center gap-2">
          {product.price && (
            <span className="text-lg font-bold text-gray-900">
              {formatPrice(product.price, product.currency)}
            </span>
          )}
          {product.original_price && product.original_price > (product.price || 0) && (
            <span className="text-sm text-gray-400 line-through">
              {formatPrice(product.original_price, product.currency)}
            </span>
          )}
        </div>
      </div>
    </div>
  )
}

export default function ResultsGrid({
  results,
  isLoading,
  onProductClick,
}: ResultsGridProps) {
  if (isLoading) {
    return (
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
        {Array.from({ length: 8 }).map((_, i) => (
          <SkeletonCard key={i} />
        ))}
      </div>
    )
  }

  if (results.length === 0) {
    return null
  }

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
      {results.map((product) => (
        <ProductCard
          key={product.id}
          product={product}
          onClick={() => onProductClick(product)}
        />
      ))}
    </div>
  )
}
