'use client'

import { useState, useRef } from 'react'
import Header from '@/components/Header'
import ChatAssistant from '@/components/ChatAssistant'
import TrendAnalyzer from '@/components/TrendAnalyzer'
import ProductModal from '@/components/ProductModal'
import { Product, SearchResult } from '@/types'

export default function Home() {
  const [selectedProduct, setSelectedProduct] = useState<Product | null>(null)
  const chatTriggerRef = useRef<((query: string) => void) | null>(null)

  return (
    <main className="min-h-screen bg-ivory">
      <Header />

      <div className="max-w-5xl mx-auto px-6 lg:px-8 py-10">
        <TrendAnalyzer onSearch={(q) => chatTriggerRef.current?.(q)} />

        {/* Divider */}
        <div className="flex items-center gap-4 mb-8">
          <div className="flex-1 h-px bg-ivory-dark" />
          <p className="text-[10px] tracking-[0.3em] uppercase text-noir/30">Your AI Stylist</p>
          <div className="flex-1 h-px bg-ivory-dark" />
        </div>

        {/* Chat */}
        <div className="rounded-3xl border border-ivory-dark bg-white shadow-sm overflow-hidden">
          <ChatAssistant
            onProductClick={(p) => setSelectedProduct(p as Product)}
            triggerRef={chatTriggerRef}
          />
        </div>
      </div>

      {selectedProduct && (
        <ProductModal product={selectedProduct} onClose={() => setSelectedProduct(null)} />
      )}
    </main>
  )
}
