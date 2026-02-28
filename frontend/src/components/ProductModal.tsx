'use client'

import { useEffect } from 'react'
import Image from 'next/image'
import { X, ExternalLink, Tag, Palette, Store } from 'lucide-react'
import { Product } from '@/types'
import { formatPrice, formatSimilarity } from '@/lib/utils'

interface ProductModalProps {
  product: Product
  onClose: () => void
}

export default function ProductModal({ product, onClose }: ProductModalProps) {
  // Close on escape key
  useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', handleEscape)
    return () => document.removeEventListener('keydown', handleEscape)
  }, [onClose])

  // Prevent body scroll when modal is open
  useEffect(() => {
    document.body.style.overflow = 'hidden'
    return () => {
      document.body.style.overflow = 'unset'
    }
  }, [])

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto">
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black/50 backdrop-blur-sm"
        onClick={onClose}
      />

      {/* Modal */}
      <div className="relative min-h-screen flex items-center justify-center p-4">
        <div className="relative bg-white rounded-2xl shadow-xl max-w-4xl w-full max-h-[90vh] overflow-hidden">
          {/* Close Button */}
          <button
            onClick={onClose}
            className="absolute top-4 right-4 z-10 p-2 bg-white/90 backdrop-blur-sm rounded-full shadow-md hover:bg-gray-100"
          >
            <X className="h-5 w-5 text-gray-600" />
          </button>

          <div className="grid md:grid-cols-2 h-full">
            {/* Image Section */}
            <div className="relative aspect-square md:aspect-auto bg-gray-100">
              <Image
                src={product.image_url}
                alt={product.title}
                fill
                className="object-contain"
              />

              {/* Similarity Badge */}
              {product.similarity && (
                <div className="absolute top-4 left-4 px-3 py-1.5 bg-white/90 backdrop-blur-sm rounded-full text-sm font-medium text-primary-700 shadow-sm">
                  {formatSimilarity(product.similarity)} match
                </div>
              )}
            </div>

            {/* Details Section */}
            <div className="p-6 md:p-8 overflow-y-auto max-h-[50vh] md:max-h-[90vh]">
              {/* Brand */}
              {product.brand && (
                <p className="text-sm font-medium text-primary-600 uppercase tracking-wide mb-2">
                  {product.brand}
                </p>
              )}

              {/* Title */}
              <h2 className="text-2xl font-bold text-gray-900 mb-4">
                {product.title}
              </h2>

              {/* Price */}
              <div className="flex items-center gap-3 mb-6">
                {product.price && (
                  <span className="text-3xl font-bold text-gray-900">
                    {formatPrice(product.price, product.currency)}
                  </span>
                )}
                {product.original_price && product.original_price > (product.price || 0) && (
                  <>
                    <span className="text-lg text-gray-400 line-through">
                      {formatPrice(product.original_price, product.currency)}
                    </span>
                    <span className="px-2 py-1 text-sm bg-green-100 text-green-700 rounded-full">
                      {Math.round((1 - (product.price || 0) / product.original_price) * 100)}% off
                    </span>
                  </>
                )}
              </div>

              {/* Attributes */}
              <div className="space-y-3 mb-6">
                {product.category && (
                  <div className="flex items-center gap-3">
                    <Tag className="h-5 w-5 text-gray-400" />
                    <span className="text-gray-600">{product.category}</span>
                  </div>
                )}
                {product.color && (
                  <div className="flex items-center gap-3">
                    <Palette className="h-5 w-5 text-gray-400" />
                    <span className="text-gray-600">{product.color}</span>
                  </div>
                )}
                <div className="flex items-center gap-3">
                  <Store className="h-5 w-5 text-gray-400" />
                  <span className="text-gray-600 capitalize">{product.source_site}</span>
                </div>
              </div>

              {/* Description */}
              {product.description && (
                <div className="mb-6">
                  <h3 className="text-sm font-medium text-gray-900 mb-2">
                    Description
                  </h3>
                  <p className="text-gray-600 text-sm leading-relaxed">
                    {product.description}
                  </p>
                </div>
              )}

              {/* CTA Button */}
              <a
                href={product.product_url}
                target="_blank"
                rel="noopener noreferrer"
                className="w-full btn-primary py-3 flex items-center justify-center gap-2"
              >
                <ExternalLink className="h-5 w-5" />
                View on {product.source_site}
              </a>

              <p className="text-xs text-gray-400 mt-3 text-center">
                You will be redirected to the retailer&apos;s website
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
