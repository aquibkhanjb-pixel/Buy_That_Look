'use client'

import { useState, useEffect, useCallback, useRef } from 'react'
import { useSession } from 'next-auth/react'
import { SearchResult } from '@/types'
import { getWishlist, addToWishlist, removeFromWishlist, WishlistItemDB } from '@/lib/api'

function dbItemToSearchResult(item: WishlistItemDB): SearchResult {
  return {
    id: item.product_id,
    product_id: item.product_id,
    title: item.title,
    product_url: item.product_url,
    image_url: item.image_url,
    price: item.price ?? undefined,
    currency: item.currency,
    source_site: item.source_site,
    description: item.description ?? undefined,
    brand: item.brand ?? undefined,
    similarity: 0,
  }
}

export type WishlistLimitError = { type: 'limit'; message: string }

export function useWishlist() {
  const { data: session } = useSession()
  const token = session?.backendToken
  const [wishlist, setWishlist] = useState<SearchResult[]>([])
  const [limitError, setLimitError] = useState<string | null>(null)
  const loadedRef = useRef(false)

  // Load from DB when authenticated
  useEffect(() => {
    if (!token) {
      loadedRef.current = false
      return
    }
    if (loadedRef.current) return
    loadedRef.current = true

    getWishlist(token)
      .then((items) => setWishlist(items.map(dbItemToSearchResult)))
      .catch(() => {
        // Silently fall back to empty
      })
  }, [token])

  const toggle = useCallback(
    async (product: SearchResult) => {
      setLimitError(null)
      if (!token) return

      const exists = wishlist.some((p) => p.id === product.id)
      if (exists) {
        // Optimistic remove
        setWishlist((prev) => prev.filter((p) => p.id !== product.id))
        try {
          await removeFromWishlist(token, product.id)
        } catch {
          // Rollback on failure
          setWishlist((prev) => [...prev, product])
        }
      } else {
        // Optimistic add
        setWishlist((prev) => [...prev, product])
        try {
          await addToWishlist(token, {
            product_id: product.id,
            title: product.title,
            product_url: product.product_url ?? '',
            image_url: product.image_url ?? '',
            price: product.price ?? null,
            currency: product.currency ?? 'INR',
            source_site: product.source_site ?? '',
            description: product.description ?? null,
            brand: product.brand ?? null,
          })
        } catch (err: unknown) {
          // Rollback
          setWishlist((prev) => prev.filter((p) => p.id !== product.id))
          const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
          if (detail?.includes('Free tier')) {
            setLimitError(detail)
          }
        }
      }
    },
    [token, wishlist],
  )

  const remove = useCallback(
    async (id: string) => {
      if (!token) return
      setWishlist((prev) => prev.filter((p) => p.id !== id))
      try {
        await removeFromWishlist(token, id)
      } catch {
        // Silent failure — item already removed from UI
      }
    },
    [token],
  )

  const isWishlisted = useCallback((id: string) => wishlist.some((p) => p.id === id), [wishlist])

  return { wishlist, toggle, remove, isWishlisted, count: wishlist.length, limitError, clearLimitError: () => setLimitError(null) }
}
