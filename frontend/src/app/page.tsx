'use client'

import { useState, useRef } from 'react'
import Header, { ActiveTab } from '@/components/Header'
import ChatAssistant from '@/components/ChatAssistant'
import TrendAnalyzer from '@/components/TrendAnalyzer'
import ProductModal from '@/components/ProductModal'
import WishlistPanel from '@/components/WishlistPanel'
import FindThisLook from '@/components/FindThisLook'
import OccasionPlanner from '@/components/OccasionPlanner'
import Footer from '@/components/Footer'
import { useWishlist } from '@/lib/useWishlist'
import { Product, SearchResult } from '@/types'

export default function Home() {
  const [activeTab, setActiveTab] = useState<ActiveTab>('discover')
  const [selectedProduct, setSelectedProduct] = useState<Product | null>(null)
  const [wishlistOpen, setWishlistOpen] = useState(false)
  const chatTriggerRef = useRef<((query: string) => void) | null>(null)

  const { wishlist, toggle, remove, isWishlisted, count, limitError, clearLimitError } = useWishlist()

  return (
    <main className="min-h-screen bg-ivory">
<Header
        activeTab={activeTab}
        onTabChange={setActiveTab}
        wishlistCount={count}
        onWishlistOpen={() => setWishlistOpen(true)}
      />

      <div className="max-w-5xl mx-auto px-6 lg:px-8 py-10">

        {/* ── Discover tab ── */}
        {activeTab === 'discover' && (
          <>
            <TrendAnalyzer onSearch={(q) => {
              chatTriggerRef.current?.(q)
            }} />

            <div className="flex items-center gap-4 mb-8">
              <div className="flex-1 h-px bg-ivory-dark" />
              <p className="text-[10px] tracking-[0.3em] uppercase text-noir/30">Your AI Stylist</p>
              <div className="flex-1 h-px bg-ivory-dark" />
            </div>

            <div className="rounded-3xl border border-ivory-dark bg-white shadow-sm overflow-hidden">
              <ChatAssistant
                onProductClick={(p) => setSelectedProduct(p as Product)}
                triggerRef={chatTriggerRef}
                onWishlistToggle={toggle}
                isWishlisted={isWishlisted}
              />
            </div>
          </>
        )}

        {/* ── Find This Look tab ── */}
        {activeTab === 'findlook' && (
          <FindThisLook
            onProductClick={(p) => setSelectedProduct(p as Product)}
            onWishlistToggle={toggle}
            isWishlisted={isWishlisted}
          />
        )}

        {/* ── Occasion Planner tab ── */}
        {activeTab === 'occasion' && (
          <div className="rounded-3xl border border-ivory-dark bg-white shadow-sm p-8">
            <OccasionPlanner
              onWishlistToggle={toggle}
              isWishlisted={isWishlisted}
            />
          </div>
        )}
      </div>

      {/* Product detail modal */}
      {selectedProduct && (
        <ProductModal product={selectedProduct} onClose={() => setSelectedProduct(null)} />
      )}

      {/* Wishlist panel */}
      {wishlistOpen && (
        <WishlistPanel
          wishlist={wishlist}
          onRemove={remove}
          onClose={() => setWishlistOpen(false)}
          onProductClick={(p) => setSelectedProduct(p as Product)}
          limitError={limitError}
          onClearLimitError={clearLimitError}
        />
      )}

      <Footer />
    </main>
  )
}
