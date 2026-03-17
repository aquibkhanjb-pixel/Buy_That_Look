'use client'

import { useState } from 'react'
import { useSession } from 'next-auth/react'
import {
  Sparkles, Crown, Loader2, RefreshCw, ShoppingBag,
  ChevronRight, Plus, X, Star, ExternalLink, Heart,
  AlertTriangle, CheckCircle2, MinusCircle,
} from 'lucide-react'
import Link from 'next/link'
import {
  getOccasionCategories, planOccasionOutfit, swapOccasionPiece,
  OccasionCategory, OccasionContext, OutfitPiece, OccasionPlanResponse,
  CompatibilityEdge, CompatibilityConflict,
} from '@/lib/api'
import { SearchResult } from '@/types'

interface OccasionPlannerProps {
  onWishlistToggle: (p: SearchResult) => void
  isWishlisted: (id: string) => boolean
}

type Step = 'input' | 'categories' | 'loading' | 'result'
type BrandTier = 'budget' | 'midrange' | 'premium'

const LOADING_STEPS = [
  'Understanding your occasion…',
  'Searching for outfit pieces…',
  'Building pairwise compatibility graph…',
  'Running ReAct style judge…',
  'Finalising your perfect look…',
]

const TIER_CONFIG: Record<BrandTier, { label: string; desc: string; color: string }> = {
  budget:   { label: 'Budget',   desc: 'Best value picks',       color: 'border-emerald-400 bg-emerald-50 text-emerald-700' },
  midrange: { label: 'Midrange', desc: 'Quality & affordability', color: 'border-noir bg-noir text-white' },
  premium:  { label: 'Premium',  desc: 'Designer & luxury',       color: 'border-gold bg-gold/10 text-gold' },
}

// ── Compatibility graph visualisation ────────────────────────────────────────
function CompatibilityGraph({ edges, pieces }: { edges: CompatibilityEdge[]; pieces: OutfitPiece[] }) {
  if (!edges.length || pieces.length < 2) return null

  const scoreColor = (s: number) =>
    s === 2 ? 'bg-emerald-100 text-emerald-700 border-emerald-200'
    : s === 1 ? 'bg-amber-50 text-amber-600 border-amber-200'
    : 'bg-red-50 text-red-600 border-red-200'

  const scoreIcon = (s: number) =>
    s === 2 ? <CheckCircle2 className="h-3 w-3" />
    : s === 1 ? <MinusCircle className="h-3 w-3" />
    : <AlertTriangle className="h-3 w-3" />

  const scoreLabel = (s: number) => s === 2 ? 'Compatible' : s === 1 ? 'Neutral' : 'Clashes'

  return (
    <div className="bg-white border border-ivory-dark rounded-2xl p-4 space-y-2">
      <p className="text-xs font-medium text-noir/60 uppercase tracking-wider">Outfit Compatibility</p>
      <div className="space-y-1.5">
        {edges.map((e, i) => (
          <div key={i} className="flex items-center gap-2 text-xs">
            <span className="text-noir/50 flex-shrink-0 w-28 truncate">{e.a_label}</span>
            <span className="text-noir/30 flex-shrink-0">↔</span>
            <span className="text-noir/50 flex-shrink-0 w-28 truncate">{e.b_label}</span>
            <span className={`ml-auto flex items-center gap-1 px-2 py-0.5 rounded-full border text-[10px] font-medium flex-shrink-0 ${scoreColor(e.score)}`}>
              {scoreIcon(e.score)} {scoreLabel(e.score)}
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}

// ── Conflict banner ───────────────────────────────────────────────────────────
function ConflictBanner({ conflicts, onDismiss }: {
  conflicts: CompatibilityConflict[]
  onDismiss: () => void
}) {
  return (
    <div className="bg-amber-50 border border-amber-200 rounded-2xl p-4 space-y-2">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 text-amber-700">
          <AlertTriangle className="h-4 w-4 flex-shrink-0" />
          <p className="text-sm font-medium">Style conflict detected after swap</p>
        </div>
        <button onClick={onDismiss} className="text-amber-400 hover:text-amber-600">
          <X className="h-4 w-4" />
        </button>
      </div>
      {conflicts.map((c, i) => (
        <div key={i} className="text-xs text-amber-700 pl-6">
          <span className="font-medium">{c.piece_a_label} ↔ {c.piece_b_label}:</span>{' '}
          {c.reason || 'These pieces may clash.'}{' '}
          <span className="text-amber-600 font-medium">{c.suggestion}</span>
        </div>
      ))}
    </div>
  )
}

// ── Swap panel (inline per card) ──────────────────────────────────────────────
function SwapPanel({ onSwap, onCancel }: {
  onSwap: (hint: string) => void
  onCancel: () => void
}) {
  const [hint, setHint] = useState('')
  return (
    <div className="p-3 border-t border-ivory-dark bg-ivory/40 space-y-2">
      <p className="text-[10px] text-noir/50 font-medium">SWAP OPTIONS</p>
      <input
        value={hint}
        onChange={e => setHint(e.target.value)}
        onKeyDown={e => { if (e.key === 'Enter') onSwap(hint) }}
        placeholder="Optional: what would you prefer? e.g. 'more traditional' 'dark blue'"
        className="w-full px-2.5 py-1.5 text-xs border border-ivory-dark rounded-lg focus:outline-none focus:border-noir/30 bg-white"
      />
      <div className="flex gap-2">
        <button
          onClick={() => onSwap(hint)}
          className="flex-1 flex items-center justify-center gap-1 bg-noir text-white text-xs py-1.5 rounded-lg hover:bg-noir/80 transition-colors"
        >
          <RefreshCw className="h-3 w-3" /> Find alternative
        </button>
        <button
          onClick={onCancel}
          className="px-3 py-1.5 border border-ivory-dark text-xs text-noir rounded-lg hover:bg-ivory transition-colors"
        >
          Cancel
        </button>
      </div>
    </div>
  )
}

// ── Product card ──────────────────────────────────────────────────────────────
function OutfitPieceCard({
  piece, swapping, wishlisted,
  showSwapPanel, onSwapToggle, onSwap, onWishlist,
}: {
  piece: OutfitPiece
  swapping: boolean
  wishlisted: boolean
  showSwapPanel: boolean
  onSwapToggle: () => void
  onSwap: (hint: string) => void
  onWishlist: () => void
}) {
  const savings = piece.budget - piece.price_num
  const over = savings < 0

  return (
    <div className="bg-white rounded-2xl border border-ivory-dark overflow-hidden flex flex-col group">
      {/* Image */}
      <div className="relative aspect-[3/4] bg-gray-50 overflow-hidden">
        {piece.image_url ? (
          <img
            src={piece.image_url}
            alt={piece.title}
            className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500"
            onError={e => { (e.target as HTMLImageElement).style.display = 'none' }}
          />
        ) : (
          <div className="w-full h-full flex items-center justify-center text-3xl">🛍️</div>
        )}
        <div className="absolute top-2 left-2 bg-noir/80 text-white text-[10px] px-2 py-0.5 rounded-full backdrop-blur-sm">
          {piece.category_label}
        </div>
        <button
          onClick={onWishlist}
          className="absolute top-2 right-2 p-1.5 rounded-full bg-white/90 hover:bg-white shadow-sm transition-colors"
        >
          <Heart className={`h-3.5 w-3.5 ${wishlisted ? 'fill-red-500 text-red-500' : 'text-gray-400'}`} />
        </button>
        {swapping && (
          <div className="absolute inset-0 bg-white/70 flex items-center justify-center backdrop-blur-sm">
            <Loader2 className="h-6 w-6 text-noir animate-spin" />
          </div>
        )}
      </div>

      {/* Info */}
      <div className="p-3 flex flex-col gap-1.5 flex-1">
        <p className="text-xs text-noir font-medium line-clamp-2 leading-snug">{piece.title}</p>
        <div className="flex items-center justify-between mt-auto">
          <div>
            <p className="text-sm font-bold text-noir">{piece.price || '—'}</p>
            {piece.price_num > 0 && (
              <p className={`text-[10px] ${over ? 'text-amber-600' : 'text-emerald-600'}`}>
                {over ? `₹${Math.abs(savings).toFixed(0)} over` : `₹${savings.toFixed(0)} saved`}
              </p>
            )}
          </div>
          {piece.rating && (
            <div className="flex items-center gap-0.5 text-[10px] text-amber-500">
              <Star className="h-3 w-3 fill-amber-400" />{piece.rating.toFixed(1)}
            </div>
          )}
        </div>
        {piece.source_site && <p className="text-[10px] text-noir/40 truncate">{piece.source_site}</p>}

        <div className="flex gap-2 mt-1">
          <a
            href={piece.url} target="_blank" rel="noopener noreferrer"
            className="flex-1 flex items-center justify-center gap-1 bg-noir text-white text-[11px] font-medium py-2 rounded-lg hover:bg-noir/80 transition-colors"
          >
            <ExternalLink className="h-3 w-3" /> Buy
          </a>
          <button
            onClick={onSwapToggle}
            disabled={swapping}
            className={`flex-1 flex items-center justify-center gap-1 text-[11px] font-medium py-2 rounded-lg transition-colors disabled:opacity-50 border ${showSwapPanel ? 'bg-noir text-white border-noir' : 'border-ivory-dark text-noir hover:bg-ivory'}`}
          >
            <RefreshCw className="h-3 w-3" /> Swap
          </button>
        </div>
      </div>

      {/* Inline swap panel */}
      {showSwapPanel && !swapping && (
        <SwapPanel onSwap={onSwap} onCancel={onSwapToggle} />
      )}
    </div>
  )
}

// ── Main Component ────────────────────────────────────────────────────────────
export default function OccasionPlanner({ onWishlistToggle, isWishlisted }: OccasionPlannerProps) {
  const { data: session } = useSession()
  const token    = session?.backendToken
  const userTier = session?.user?.tier ?? 'free'

  const [step, setStep]             = useState<Step>('input')
  const [description, setDescription] = useState('')
  const [context, setContext]       = useState<OccasionContext | null>(null)
  const [categories, setCategories] = useState<OccasionCategory[]>([])
  const [selectedIds, setSelectedIds] = useState<string[]>([])
  const [customInput, setCustomInput] = useState('')
  const [customItems, setCustomItems] = useState<string[]>([])
  const [brandTier, setBrandTier]   = useState<BrandTier>('midrange')
  const [outfit, setOutfit]         = useState<OccasionPlanResponse | null>(null)
  const [loadingStep, setLoadingStep] = useState(0)
  const [error, setError]           = useState('')
  const [swappingId, setSwappingId] = useState<string | null>(null)
  const [openSwapId, setOpenSwapId] = useState<string | null>(null)
  const [conflicts, setConflicts]   = useState<CompatibilityConflict[] | null>(null)

  // ── Step 1 ─────────────────────────────────────────────────────────────────
  async function handleDescriptionSubmit() {
    if (!description.trim()) return
    setError('')
    setStep('loading')
    setLoadingStep(0)
    try {
      const data = await getOccasionCategories(description.trim(), token || undefined)
      setContext(data.context)
      setCategories(data.categories)
      setSelectedIds(data.categories.filter(c => c.default).map(c => c.id))
      setStep('categories')
    } catch {
      setError('Could not analyse your occasion. Please try again.')
      setStep('input')
    }
  }

  // ── Step 2: build ──────────────────────────────────────────────────────────
  async function handleBuildOutfit() {
    if (!context) return
    setError('')
    setConflicts(null)
    setStep('loading')
    setLoadingStep(0)

    const timer = setInterval(() =>
      setLoadingStep(p => Math.min(p + 1, LOADING_STEPS.length - 1)), 2000)

    try {
      const data = await planOccasionOutfit(
        context, selectedIds, customItems, brandTier, token || undefined)
      setOutfit(data)
      if (data.conflicts?.has_conflicts) {
        setConflicts(data.conflicts.conflicts)
      }
      setStep('result')
    } catch (err: unknown) {
      const status = (err as { response?: { status?: number; data?: { detail?: string } } })?.response?.status
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setError(status === 403
        ? detail || 'Daily limit reached. Upgrade to Premium for unlimited outfit planning.'
        : 'Could not build your outfit. Please try again.')
      setStep('categories')
    } finally {
      clearInterval(timer)
    }
  }

  // ── Swap ────────────────────────────────────────────────────────────────────
  async function handleSwap(piece: OutfitPiece, hint: string) {
    if (!context || !outfit) return
    setSwappingId(piece.category_id)
    setOpenSwapId(null)
    setConflicts(null)

    const locked = outfit.pieces.filter(p => p.category_id !== piece.category_id)
    try {
      const data = await swapOccasionPiece(
        context, piece.category_id, piece.category_label,
        piece.budget, locked, brandTier, hint,
        piece.category_id.startsWith('custom_') ? piece.category_label : undefined,
        token || undefined,
      )
      setOutfit(prev => {
        if (!prev) return prev
        // Replace swapped piece, then append any gap pieces that were auto-added
        let pieces = prev.pieces.map(p =>
          p.category_id === piece.category_id ? data.piece : p
        )
        // Add newly detected gap pieces (e.g. trousers added when only shirt was swapped in)
        const existingIds = new Set(pieces.map(p => p.category_id))
        const newGaps = (data.gap_pieces ?? []).filter(g => !existingIds.has(g.category_id))
        if (newGaps.length > 0) pieces = [...pieces, ...newGaps]

        return {
          ...prev,
          pieces,
          total_price: pieces.reduce((s, p) => s + (p.price_num || 0), 0),
          compatibility_graph: data.compatibility_graph?.length
            ? data.compatibility_graph
            : prev.compatibility_graph,
        }
      })
      if (data.conflicts?.has_conflicts) {
        setConflicts(data.conflicts.conflicts)
      } else {
        setConflicts(null)
      }
    } catch {
      setError('Swap timed out or failed. Please try again.')
    } finally {
      setSwappingId(null)
    }
  }

  function toggleCategory(id: string) {
    setSelectedIds(p => p.includes(id) ? p.filter(x => x !== id) : [...p, id])
  }

  function addCustomItem() {
    const v = customInput.trim()
    if (!v || customItems.includes(v)) return
    setCustomItems(p => [...p, v])
    setCustomInput('')
  }

  function handleWishlist(piece: OutfitPiece) {
    onWishlistToggle({
      id: piece.url, title: piece.title,
      product_url: piece.url, image_url: piece.image_url,
      price: piece.price_num, source_site: piece.source_site,
    } as SearchResult)
  }

  const totalPieces = selectedIds.length + customItems.length

  // ── Budget bar ─────────────────────────────────────────────────────────────
  function BudgetBar() {
    if (!outfit) return null
    const pct  = Math.min((outfit.total_price / outfit.budget) * 100, 120)
    const over = outfit.total_price > outfit.budget * 1.15
    return (
      <div className="bg-white rounded-2xl border border-ivory-dark p-4">
        <div className="flex justify-between items-center mb-2 text-sm">
          <span className="text-noir/60">Total spent</span>
          <span className={`font-bold ${over ? 'text-amber-600' : 'text-emerald-600'}`}>
            ₹{outfit.total_price.toLocaleString('en-IN')}
            <span className="text-noir/40 font-normal"> / ₹{outfit.budget.toLocaleString('en-IN')}</span>
          </span>
        </div>
        <div className="h-2 bg-ivory rounded-full overflow-hidden">
          <div
            className={`h-full rounded-full transition-all duration-700 ${over ? 'bg-amber-400' : 'bg-emerald-400'}`}
            style={{ width: `${Math.min(pct, 100)}%` }}
          />
        </div>
        {over && <p className="text-[11px] text-amber-600 mt-1">Slightly over budget — try swapping some pieces</p>}
      </div>
    )
  }

  // ── Loading ─────────────────────────────────────────────────────────────────
  if (step === 'loading') return (
    <div className="min-h-[420px] flex flex-col items-center justify-center gap-6 py-16">
      <div className="relative">
        <div className="w-16 h-16 rounded-full border-2 border-gold/30 border-t-gold animate-spin" />
        <Sparkles className="absolute inset-0 m-auto h-6 w-6 text-gold" />
      </div>
      <div className="text-center space-y-2">
        <p className="text-sm font-medium text-noir">{LOADING_STEPS[loadingStep]}</p>
        <div className="flex gap-1.5 justify-center">
          {LOADING_STEPS.map((_, i) => (
            <div key={i} className={`h-1 w-6 rounded-full transition-all duration-500 ${i <= loadingStep ? 'bg-gold' : 'bg-ivory-dark'}`} />
          ))}
        </div>
      </div>
      <p className="text-xs text-noir/40 max-w-xs text-center">
        AI is searching, judging pairwise compatibility, and picking the most cohesive look — ~30 seconds
      </p>
    </div>
  )

  // ── Result ──────────────────────────────────────────────────────────────────
  if (step === 'result' && outfit) return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="font-serif text-2xl text-noir">Your Outfit</h2>
          <p className="text-xs text-noir/50 mt-0.5 capitalize">
            {context?.occasion_type === 'party' && context?.party_subtype && context.party_subtype !== 'other'
              ? `${context.party_subtype} party`
              : context?.occasion_type === 'festival'
              ? `${context.special_notes?.split(' ')[0] || 'Festival'} · ethnic`
              : context?.occasion_type
            } · {context?.gender} · {context?.role} ·{' '}
            <span className="font-medium">{brandTier}</span> tier
          </p>
        </div>
        <button
          onClick={() => { setStep('categories'); setOutfit(null); setConflicts(null) }}
          className="text-xs text-noir/40 hover:text-noir underline underline-offset-2"
        >
          ← Back
        </button>
      </div>

      {/* Swap error */}
      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 text-sm px-4 py-3 rounded-xl flex items-center justify-between">
          {error}
          <button onClick={() => setError('')} className="ml-3 text-red-400 hover:text-red-600"><X className="h-4 w-4" /></button>
        </div>
      )}

      {/* Conflict banner */}
      {conflicts && conflicts.length > 0 && (
        <ConflictBanner conflicts={conflicts} onDismiss={() => setConflicts(null)} />
      )}

      {/* Outfit story */}
      {outfit.outfit_story && (
        <div className="bg-noir/[0.03] border border-ivory-dark rounded-2xl p-4">
          <p className="text-sm text-noir/70 leading-relaxed italic">"{outfit.outfit_story}"</p>
        </div>
      )}

      <BudgetBar />

      {/* Compatibility graph */}
      {outfit.compatibility_graph?.length > 0 && (
        <CompatibilityGraph edges={outfit.compatibility_graph} pieces={outfit.pieces} />
      )}

      {/* Product grid */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
        {outfit.pieces.map(piece => (
          <OutfitPieceCard
            key={piece.category_id}
            piece={piece}
            swapping={swappingId === piece.category_id}
            wishlisted={isWishlisted(piece.url)}
            showSwapPanel={openSwapId === piece.category_id}
            onSwapToggle={() => setOpenSwapId(p => p === piece.category_id ? null : piece.category_id)}
            onSwap={hint => handleSwap(piece, hint)}
            onWishlist={() => handleWishlist(piece)}
          />
        ))}
      </div>

      <div className="flex gap-3">
        <button
          onClick={() => { setStep('input'); setOutfit(null); setDescription(''); setCustomItems([]); setConflicts(null) }}
          className="flex items-center gap-2 px-4 py-2.5 border border-ivory-dark rounded-xl text-sm text-noir hover:bg-ivory transition-colors"
        >
          <RefreshCw className="h-4 w-4" /> New occasion
        </button>
        <button
          onClick={handleBuildOutfit}
          className="flex items-center gap-2 px-4 py-2.5 bg-noir text-white rounded-xl text-sm hover:bg-noir/80 transition-colors"
        >
          <Sparkles className="h-4 w-4" /> Regenerate all
        </button>
      </div>
    </div>
  )

  // ── Category selection ──────────────────────────────────────────────────────
  if (step === 'categories' && context) return (
    <div className="space-y-5 max-w-2xl mx-auto">
      <div>
        <h2 className="font-serif text-2xl text-noir">What do you need?</h2>
        <p className="text-sm text-noir/50 mt-1 capitalize">
          {context.occasion_type === 'party' && context.party_subtype && context.party_subtype !== 'other'
            ? `${context.party_subtype} party`
            : context.occasion_type
          } · {context.gender} · ₹{context.budget.toLocaleString('en-IN')}
        </p>
      </div>

      {error && <div className="bg-red-50 border border-red-200 text-red-700 text-sm px-4 py-3 rounded-xl">{error}</div>}

      {/* Brand tier filter */}
      <div className="space-y-2">
        <p className="text-xs font-medium text-noir/60 uppercase tracking-wider">Budget tier</p>
        <div className="flex gap-2">
          {(Object.keys(TIER_CONFIG) as BrandTier[]).map(tier => {
            const cfg = TIER_CONFIG[tier]
            const active = brandTier === tier
            return (
              <button
                key={tier}
                onClick={() => setBrandTier(tier)}
                className={`flex-1 py-2.5 px-3 rounded-xl border-2 text-center transition-all ${active ? cfg.color : 'border-ivory-dark text-noir/50 hover:border-noir/20'}`}
              >
                <p className="text-xs font-semibold">{cfg.label}</p>
                <p className="text-[10px] opacity-70">{cfg.desc}</p>
              </button>
            )
          })}
        </div>
      </div>

      {/* Category checkboxes */}
      <div className="space-y-2">
        <p className="text-xs font-medium text-noir/60 uppercase tracking-wider">Select pieces</p>
        {categories.map(cat => {
          const sel = selectedIds.includes(cat.id)
          return (
            <button
              key={cat.id}
              onClick={() => toggleCategory(cat.id)}
              className={`w-full flex items-center gap-4 px-4 py-3.5 rounded-2xl border transition-all text-left ${sel ? 'border-noir bg-noir text-white' : 'border-ivory-dark bg-white text-noir hover:border-noir/30'}`}
            >
              <span className="text-xl">{cat.emoji}</span>
              <div className="flex-1">
                <p className="text-sm font-medium">{cat.label}</p>
                <p className={`text-[11px] ${sel ? 'text-white/60' : 'text-noir/40'}`}>{cat.sublabel}</p>
              </div>
              <div className={`w-5 h-5 rounded-full border-2 flex items-center justify-center flex-shrink-0 ${sel ? 'border-white bg-white' : 'border-noir/20'}`}>
                {sel && <div className="w-2.5 h-2.5 rounded-full bg-noir" />}
              </div>
            </button>
          )
        })}
      </div>

      {/* Custom items */}
      <div className="border border-ivory-dark rounded-2xl p-4 space-y-3">
        <p className="text-sm font-medium text-noir flex items-center gap-2">
          <Plus className="h-4 w-4" /> Other items
          <span className="text-[11px] text-noir/40 font-normal">(anything not listed above)</span>
        </p>
        <div className="flex gap-2">
          <input
            value={customInput}
            onChange={e => setCustomInput(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); addCustomItem() } }}
            placeholder="e.g. hair flowers, bindi, necklace…"
            className="flex-1 px-3 py-2 text-sm border border-ivory-dark rounded-xl focus:outline-none focus:border-noir/40 bg-ivory/30"
          />
          <button onClick={addCustomItem} className="px-4 py-2 bg-noir text-white text-sm rounded-xl hover:bg-noir/80 transition-colors">
            Add
          </button>
        </div>
        {customItems.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {customItems.map(item => (
              <span key={item} className="inline-flex items-center gap-1.5 bg-gold/10 text-noir text-xs px-3 py-1.5 rounded-full">
                {item}
                <button onClick={() => setCustomItems(p => p.filter(x => x !== item))}>
                  <X className="h-3 w-3 hover:text-red-500 transition-colors" />
                </button>
              </span>
            ))}
          </div>
        )}
      </div>

      {userTier !== 'premium' && (
        <div className="bg-amber-50 border border-amber-200 rounded-xl px-4 py-3 flex items-center justify-between">
          <p className="text-xs text-amber-700">Free plan: 2 outfit plans per day</p>
          <Link href="/pricing" target="_blank" className="text-xs text-amber-700 font-medium underline underline-offset-2">Upgrade →</Link>
        </div>
      )}

      <button
        onClick={handleBuildOutfit}
        disabled={totalPieces === 0}
        className="w-full flex items-center justify-center gap-2 bg-noir text-white py-4 rounded-2xl text-sm font-medium hover:bg-noir/80 transition-colors disabled:opacity-40"
      >
        <ShoppingBag className="h-4 w-4" />
        Find my outfit — {totalPieces} {totalPieces === 1 ? 'piece' : 'pieces'} · {TIER_CONFIG[brandTier].label}
        <ChevronRight className="h-4 w-4" />
      </button>
    </div>
  )

  // ── Input (default) ─────────────────────────────────────────────────────────
  return (
    <div className="max-w-2xl mx-auto space-y-8">
      <div className="text-center space-y-3 pt-4">
        <div className="inline-flex items-center gap-2 bg-gold/10 text-gold text-xs px-3 py-1.5 rounded-full font-medium">
          <Crown className="h-3.5 w-3.5" /> AI Outfit Planner
        </div>
        <h2 className="font-serif text-3xl text-noir">Plan the perfect outfit</h2>
        <p className="text-sm text-noir/50 max-w-sm mx-auto">
          Describe your occasion — AI builds a complete, pairwise-compatible look within your budget.
        </p>
      </div>

      <div className="flex flex-wrap gap-2 justify-center">
        {[
          "Cousin's wedding, guest, ₹4000, women",
          "Office presentation, men, ₹3000",
          "Friend's birthday party, women, ₹2500",
          "Eid celebration, men, ₹3500",
          "Diwali family gathering, women, ₹5000",
          "Farewell party for colleague, men, ₹2000",
        ].map(ex => (
          <button
            key={ex}
            onClick={() => setDescription(ex)}
            className="text-xs text-noir/50 border border-ivory-dark px-3 py-1.5 rounded-full hover:border-noir/40 hover:text-noir transition-all"
          >
            {ex}
          </button>
        ))}
      </div>

      <div className="space-y-3">
        <textarea
          value={description}
          onChange={e => setDescription(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleDescriptionSubmit() } }}
          placeholder="Describe your occasion… e.g. 'Attending a cousin's wedding this Saturday as a guest, women, budget ₹4000'"
          rows={3}
          className="w-full px-4 py-3.5 text-sm border border-ivory-dark rounded-2xl focus:outline-none focus:border-noir/40 resize-none bg-white text-noir placeholder-noir/30"
        />
        {error && <p className="text-sm text-red-500">{error}</p>}
        <button
          onClick={handleDescriptionSubmit}
          disabled={!description.trim()}
          className="w-full flex items-center justify-center gap-2 bg-noir text-white py-4 rounded-2xl text-sm font-medium hover:bg-noir/80 transition-colors disabled:opacity-40"
        >
          <Sparkles className="h-4 w-4" /> Plan my outfit <ChevronRight className="h-4 w-4" />
        </button>
      </div>

      <div className="grid grid-cols-3 gap-4 text-center">
        {[
          { emoji: '💬', title: 'Describe', desc: 'Occasion, role & budget' },
          { emoji: '✅', title: 'Select',   desc: 'Choose pieces & tier' },
          { emoji: '✨', title: 'Outfit',   desc: 'AI judges compatibility' },
        ].map(s => (
          <div key={s.title} className="space-y-2">
            <div className="text-2xl">{s.emoji}</div>
            <p className="text-xs font-medium text-noir">{s.title}</p>
            <p className="text-[11px] text-noir/40">{s.desc}</p>
          </div>
        ))}
      </div>
    </div>
  )
}
