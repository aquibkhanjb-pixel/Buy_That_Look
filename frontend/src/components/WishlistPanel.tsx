'use client'

import { useState, useEffect } from 'react'
import {
  X, ExternalLink, ShoppingBag, Trash2,
  Bell, BellOff, CheckCircle2, Loader2,
  AlertCircle, RefreshCw,
} from 'lucide-react'
import Image from 'next/image'
import { SearchResult } from '@/types'
import { formatPrice } from '@/lib/utils'
import {
  registerPriceAlerts,
  getTrackedAlerts,
  removeTrackedAlert,
  TrackedAlert,
} from '@/lib/api'

type Tab = 'wishlist' | 'tracking'

interface WishlistPanelProps {
  wishlist: SearchResult[]
  onRemove: (id: string) => void
  onClose: () => void
  onProductClick: (product: SearchResult) => void
  limitError?: string | null
  onClearLimitError?: () => void
}

const EMAIL_KEY = 'fashionai_alert_email'

export default function WishlistPanel({
  wishlist,
  onRemove,
  onClose,
  onProductClick,
  limitError,
  onClearLimitError,
}: WishlistPanelProps) {
  const [tab, setTab] = useState<Tab>('wishlist')

  // ── Wishlist tab state ──────────────────────────────────────────────────
  const [selected, setSelected]   = useState<Set<string>>(new Set())
  const [email, setEmail]         = useState('')
  const [tracking, setTracking]   = useState(false)
  const [trackError, setTrackError] = useState('')
  const [justTracked, setJustTracked] = useState<string[]>([])  // titles of newly tracked

  // ── Tracking tab state ──────────────────────────────────────────────────
  const [lookupEmail, setLookupEmail] = useState('')
  const [loadingAlerts, setLoadingAlerts] = useState(false)
  const [trackedAlerts, setTrackedAlerts] = useState<TrackedAlert[] | null>(null)
  const [alertsError, setAlertsError]     = useState('')
  const [removing, setRemoving]           = useState<number | null>(null)

  // Restore saved email from localStorage
  useEffect(() => {
    const saved = localStorage.getItem(EMAIL_KEY) ?? ''
    if (saved) { setEmail(saved); setLookupEmail(saved) }
  }, [])

  // ── Wishlist helpers ────────────────────────────────────────────────────

  function toggleSelect(id: string) {
    setSelected((prev) => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })
  }

  function toggleAll() {
    if (selected.size === wishlist.length) {
      setSelected(new Set())
    } else {
      setSelected(new Set(wishlist.map((p) => p.id)))
    }
  }

  async function handleTrack() {
    if (!email.trim() || !email.includes('@')) {
      setTrackError('Enter a valid email address.')
      return
    }
    if (selected.size === 0) {
      setTrackError('Select at least one item to track.')
      return
    }
    setTracking(true)
    setTrackError('')
    const selectedProducts = wishlist.filter((p) => selected.has(p.id))
    try {
      await registerPriceAlerts(email.trim(), selectedProducts)
      localStorage.setItem(EMAIL_KEY, email.trim())
      setLookupEmail(email.trim())
      setJustTracked(selectedProducts.map((p) => p.title))
      setSelected(new Set())
      // Refresh tracking tab data if already loaded
      if (trackedAlerts !== null) fetchAlerts(email.trim())
    } catch {
      setTrackError('Could not register alerts — please try again.')
    } finally {
      setTracking(false)
    }
  }

  // ── Tracking tab helpers ────────────────────────────────────────────────

  async function fetchAlerts(em?: string) {
    const target = (em ?? lookupEmail).trim()
    if (!target || !target.includes('@')) {
      setAlertsError('Enter a valid email to view your tracked items.')
      return
    }
    setLoadingAlerts(true)
    setAlertsError('')
    setTrackedAlerts(null)
    try {
      const data = await getTrackedAlerts(target)
      setTrackedAlerts(data.alerts)
      localStorage.setItem(EMAIL_KEY, target)
    } catch {
      setAlertsError('Could not load tracked alerts. Check your email and try again.')
    } finally {
      setLoadingAlerts(false)
    }
  }

  async function handleRemoveAlert(alert: TrackedAlert) {
    setRemoving(alert.id)
    try {
      await removeTrackedAlert(alert.email, alert.product_url)
      setTrackedAlerts((prev) => (prev ? prev.filter((a) => a.id !== alert.id) : prev))
    } catch {
      // silent — alert stays in list
    } finally {
      setRemoving(null)
    }
  }

  function fmtPrice(price: number | null, currency: string) {
    if (!price) return null
    const sym = currency === 'INR' ? '₹' : '$'
    return `${sym}${price.toLocaleString('en-IN', { maximumFractionDigits: 0 })}`
  }

  function fmtDate(iso: string | null) {
    if (!iso) return 'Not yet'
    return new Date(iso).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' })
  }

  // ── Render ──────────────────────────────────────────────────────────────

  return (
    <>
      {/* Backdrop */}
      <div className="fixed inset-0 bg-noir/30 backdrop-blur-sm z-40" onClick={onClose} />

      {/* Panel */}
      <div className="fixed top-0 right-0 h-full w-full max-w-sm bg-white shadow-2xl z-50 flex flex-col">

        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-ivory-dark">
          <div className="flex items-center gap-2.5">
            <ShoppingBag className="h-5 w-5 text-noir" />
            <h2 className="font-serif text-lg text-noir">Saved Items</h2>
            {wishlist.length > 0 && (
              <span className="text-xs bg-gold/20 text-amber-800 px-2 py-0.5 rounded-full font-medium">
                {wishlist.length}
              </span>
            )}
          </div>
          <button onClick={onClose} className="p-1.5 hover:bg-ivory rounded-xl transition-colors">
            <X className="h-4 w-4 text-noir/60" />
          </button>
        </div>

        {/* Tabs */}
        <div className="flex border-b border-ivory-dark">
          {(['wishlist', 'tracking'] as Tab[]).map((t) => (
            <button
              key={t}
              onClick={() => { setTab(t); setJustTracked([]) }}
              className={`flex-1 py-2.5 text-xs font-medium tracking-wide transition-colors ${
                tab === t
                  ? 'text-noir border-b-2 border-noir'
                  : 'text-noir/40 hover:text-noir/60'
              }`}
            >
              {t === 'wishlist' ? 'My Wishlist' : 'Price Tracking'}
            </button>
          ))}
        </div>

        {/* ── WISHLIST TAB ─────────────────────────────────────────────── */}
        {tab === 'wishlist' && (
          <>
            {/* Wishlist limit error banner */}
            {limitError && (
              <div className="mx-5 mt-3 flex items-start gap-2 bg-amber-50 border border-amber-200 rounded-xl px-3.5 py-2.5">
                <AlertCircle className="h-4 w-4 text-amber-600 flex-shrink-0 mt-0.5" />
                <div className="flex-1 min-w-0">
                  <p className="text-xs font-medium text-amber-800">Wishlist limit reached</p>
                  <p className="text-[11px] text-amber-600 mt-0.5">{limitError}</p>
                  <a href="/pricing" className="text-[11px] text-amber-700 underline font-medium">Upgrade to Premium →</a>
                </div>
                <button onClick={onClearLimitError} className="text-amber-400 hover:text-amber-600">
                  <X className="h-3.5 w-3.5" />
                </button>
              </div>
            )}
            <div className="flex-1 overflow-y-auto">
              {wishlist.length === 0 ? (
                <div className="flex flex-col items-center justify-center h-full gap-4 text-center px-8">
                  <div className="w-16 h-16 rounded-full bg-ivory flex items-center justify-center">
                    <ShoppingBag className="h-7 w-7 text-noir/20" />
                  </div>
                  <div>
                    <p className="font-serif text-lg text-noir/60">Your wishlist is empty</p>
                    <p className="text-sm text-noir/40 mt-1">
                      Tap the heart icon on any product to save it here.
                    </p>
                  </div>
                </div>
              ) : (
                <>
                  {/* Select-all bar */}
                  <div className="flex items-center justify-between px-4 py-2 bg-ivory/60 border-b border-ivory-dark">
                    <p className="text-[11px] text-noir/50">
                      {selected.size > 0
                        ? `${selected.size} selected for tracking`
                        : 'Tap 🔔 to select items for price tracking'}
                    </p>
                    <button
                      onClick={toggleAll}
                      className="text-[11px] font-medium text-gold hover:text-amber-700 transition-colors"
                    >
                      {selected.size === wishlist.length ? 'Deselect all' : 'Select all'}
                    </button>
                  </div>

                  <div className="divide-y divide-ivory-dark">
                    {wishlist.map((product) => {
                      const isSel = selected.has(product.id)
                      return (
                        <div
                          key={product.id}
                          className={`flex gap-3 p-4 transition-colors ${isSel ? 'bg-amber-50/60' : 'hover:bg-ivory/50'}`}
                        >
                          {/* Thumbnail */}
                          <div
                            onClick={() => { onProductClick(product); onClose() }}
                            className="w-20 h-24 relative flex-shrink-0 rounded-xl overflow-hidden bg-ivory border border-ivory-dark cursor-pointer"
                          >
                            <Image
                              src={product.image_url}
                              alt={product.title}
                              fill
                              className="object-cover"
                              sizes="80px"
                            />
                          </div>

                          {/* Info */}
                          <div className="flex-1 min-w-0 py-0.5">
                            <p
                              onClick={() => { onProductClick(product); onClose() }}
                              className="text-sm font-medium text-noir line-clamp-2 leading-snug cursor-pointer hover:text-gold transition-colors"
                            >
                              {product.title}
                            </p>
                            {product.brand && (
                              <p className="text-xs text-noir/40 mt-0.5">{product.brand}</p>
                            )}
                            {product.price && (
                              <p className="text-sm font-bold text-noir mt-1.5">
                                {formatPrice(product.price, product.currency)}
                              </p>
                            )}
                            <div className="flex items-center gap-3 mt-2">
                              <a
                                href={product.product_url}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="flex items-center gap-1 text-[11px] text-noir/50 hover:text-gold transition-colors"
                              >
                                <ExternalLink className="h-3 w-3" /> Shop
                              </a>
                              <button
                                onClick={() => onRemove(product.id)}
                                className="flex items-center gap-1 text-[11px] text-noir/40 hover:text-red-500 transition-colors"
                              >
                                <Trash2 className="h-3 w-3" /> Remove
                              </button>
                            </div>
                          </div>

                          {/* Bell toggle */}
                          <button
                            onClick={() => toggleSelect(product.id)}
                            className={`flex-shrink-0 self-center p-2 rounded-full transition-colors ${
                              isSel
                                ? 'bg-gold/20 text-amber-700'
                                : 'text-noir/25 hover:text-noir/50 hover:bg-ivory'
                            }`}
                            title={isSel ? 'Remove from tracking selection' : 'Select for price tracking'}
                          >
                            {isSel
                              ? <Bell className="h-4 w-4 fill-current" />
                              : <BellOff className="h-4 w-4" />
                            }
                          </button>
                        </div>
                      )
                    })}
                  </div>
                </>
              )}
            </div>

            {/* Footer — email + track */}
            {wishlist.length > 0 && (
              <div className="px-5 py-4 border-t border-ivory-dark space-y-2.5">
                {justTracked.length > 0 && (
                  <div className="flex items-start gap-2 bg-emerald-50 border border-emerald-200 rounded-xl px-3.5 py-2.5">
                    <CheckCircle2 className="h-4 w-4 text-emerald-600 flex-shrink-0 mt-0.5" />
                    <div>
                      <p className="text-xs font-medium text-emerald-800">Alerts registered!</p>
                      <p className="text-[11px] text-emerald-600 mt-0.5 line-clamp-2">
                        Tracking: {justTracked.slice(0, 2).join(', ')}
                        {justTracked.length > 2 && ` +${justTracked.length - 2} more`}
                      </p>
                    </div>
                  </div>
                )}

                <div className="flex items-center gap-1.5">
                  <Bell className="h-3.5 w-3.5 text-gold" />
                  <p className="text-xs font-medium text-noir">Email for price drop alerts</p>
                </div>

                <input
                  type="email"
                  value={email}
                  onChange={(e) => { setEmail(e.target.value); setTrackError('') }}
                  placeholder="your@email.com"
                  className="w-full text-sm border border-ivory-dark rounded-xl px-3 py-2 focus:outline-none focus:border-gold bg-ivory/50 placeholder:text-noir/30"
                />

                {trackError && (
                  <p className="text-[11px] text-red-500 flex items-center gap-1">
                    <AlertCircle className="h-3 w-3" /> {trackError}
                  </p>
                )}

                <button
                  onClick={handleTrack}
                  disabled={tracking || selected.size === 0}
                  className="w-full flex items-center justify-center gap-2 bg-noir text-ivory text-xs font-medium tracking-wider py-2.5 rounded-xl hover:bg-noir/80 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  {tracking
                    ? <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    : <Bell className="h-3.5 w-3.5" />
                  }
                  {tracking
                    ? 'Registering…'
                    : selected.size === 0
                      ? 'Select items above to track'
                      : `Track ${selected.size} selected item${selected.size !== 1 ? 's' : ''}`
                  }
                </button>

                <p className="text-[10px] text-center text-noir/25 tracking-wide">
                  Saved locally · {wishlist.length} item{wishlist.length !== 1 ? 's' : ''} · Prices checked daily
                </p>
              </div>
            )}
          </>
        )}

        {/* ── TRACKING TAB ─────────────────────────────────────────────── */}
        {tab === 'tracking' && (
          <>
            <div className="flex-1 overflow-y-auto">
              <div className="px-5 pt-4 pb-3 space-y-2 border-b border-ivory-dark">
                <p className="text-xs text-noir/50">Enter your email to view all items you're tracking for price drops.</p>
                <div className="flex gap-2">
                  <input
                    type="email"
                    value={lookupEmail}
                    onChange={(e) => { setLookupEmail(e.target.value); setAlertsError('') }}
                    placeholder="your@email.com"
                    className="flex-1 text-sm border border-ivory-dark rounded-xl px-3 py-2 focus:outline-none focus:border-gold bg-ivory/50 placeholder:text-noir/30"
                    onKeyDown={(e) => e.key === 'Enter' && fetchAlerts()}
                  />
                  <button
                    onClick={() => fetchAlerts()}
                    disabled={loadingAlerts}
                    className="px-3 py-2 bg-noir text-ivory rounded-xl hover:bg-noir/80 transition-colors disabled:opacity-50"
                  >
                    {loadingAlerts
                      ? <Loader2 className="h-4 w-4 animate-spin" />
                      : <RefreshCw className="h-4 w-4" />
                    }
                  </button>
                </div>
                {alertsError && (
                  <p className="text-[11px] text-red-500 flex items-center gap-1">
                    <AlertCircle className="h-3 w-3" /> {alertsError}
                  </p>
                )}
              </div>

              {/* Tracked list */}
              {trackedAlerts === null && !loadingAlerts && (
                <div className="flex flex-col items-center justify-center h-48 gap-3 text-center px-8">
                  <Bell className="h-8 w-8 text-noir/15" />
                  <p className="text-sm text-noir/40">Enter your email above to see tracked items.</p>
                </div>
              )}

              {loadingAlerts && (
                <div className="flex items-center justify-center h-32">
                  <Loader2 className="h-5 w-5 animate-spin text-noir/30" />
                </div>
              )}

              {trackedAlerts !== null && !loadingAlerts && (
                trackedAlerts.length === 0 ? (
                  <div className="flex flex-col items-center justify-center h-48 gap-3 text-center px-8">
                    <BellOff className="h-8 w-8 text-noir/15" />
                    <p className="text-sm text-noir/40 font-serif">No active price alerts</p>
                    <p className="text-xs text-noir/30">
                      Go to the Wishlist tab, select items, and register your email.
                    </p>
                  </div>
                ) : (
                  <div className="divide-y divide-ivory-dark">
                    {trackedAlerts.map((alert) => (
                      <div key={alert.id} className="flex gap-3 p-4 hover:bg-ivory/50 transition-colors">
                        {/* Thumbnail */}
                        <a
                          href={alert.product_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="w-16 h-20 relative flex-shrink-0 rounded-lg overflow-hidden bg-ivory border border-ivory-dark"
                        >
                          {alert.image_url ? (
                            <Image
                              src={alert.image_url}
                              alt={alert.title}
                              fill
                              className="object-cover"
                              sizes="64px"
                            />
                          ) : (
                            <div className="w-full h-full flex items-center justify-center">
                              <ShoppingBag className="h-5 w-5 text-noir/20" />
                            </div>
                          )}
                        </a>

                        {/* Info */}
                        <div className="flex-1 min-w-0 py-0.5">
                          <a
                            href={alert.product_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-sm font-medium text-noir line-clamp-2 leading-snug hover:text-gold transition-colors"
                          >
                            {alert.title}
                          </a>

                          {alert.last_price && (
                            <div className="flex items-center gap-1.5 mt-1.5">
                              <Bell className="h-3 w-3 text-gold" />
                              <p className="text-xs font-bold text-noir">
                                {fmtPrice(alert.last_price, alert.currency)}
                              </p>
                            </div>
                          )}

                          <p className="text-[10px] text-noir/35 mt-1">
                            Last checked: {fmtDate(alert.last_checked)}
                          </p>

                          <button
                            onClick={() => handleRemoveAlert(alert)}
                            disabled={removing === alert.id}
                            className="flex items-center gap-1 mt-1.5 text-[11px] text-noir/40 hover:text-red-500 transition-colors disabled:opacity-50"
                          >
                            {removing === alert.id
                              ? <Loader2 className="h-3 w-3 animate-spin" />
                              : <Trash2 className="h-3 w-3" />
                            }
                            Remove alert
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                )
              )}
            </div>

            {/* Footer */}
            {trackedAlerts !== null && trackedAlerts.length > 0 && (
              <div className="px-5 py-3 border-t border-ivory-dark">
                <p className="text-[10px] text-center text-noir/30 tracking-wide">
                  {trackedAlerts.length} item{trackedAlerts.length !== 1 ? 's' : ''} tracked · Prices checked daily at 09:00
                </p>
              </div>
            )}
          </>
        )}
      </div>
    </>
  )
}
