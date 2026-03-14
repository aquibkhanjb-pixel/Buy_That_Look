'use client'

import { useEffect, useState } from 'react'
import { TrendItem, TrendsResponse } from '@/types'
import { getTrends } from '@/lib/api'
import { RefreshCw } from 'lucide-react'

const CATEGORY_STYLES: Record<string, { bg: string; text: string; dot: string }> = {
  Women:       { bg: 'bg-blush/40',       text: 'text-rose-800',   dot: 'bg-rose-400' },
  Men:         { bg: 'bg-blue-50',         text: 'text-blue-800',   dot: 'bg-blue-400' },
  Unisex:      { bg: 'bg-gold/10',         text: 'text-amber-800',  dot: 'bg-gold' },
  Accessories: { bg: 'bg-purple-50',       text: 'text-purple-800', dot: 'bg-purple-400' },
}

const BADGE_STYLES: Record<string, string> = {
  '🔥 Hot':       'bg-red-50 text-red-700 border-red-200',
  '📈 Rising':    'bg-emerald-50 text-emerald-700 border-emerald-200',
  '✨ New':       'bg-gold/10 text-amber-700 border-gold/30',
}

function SkeletonCard() {
  return (
    <div className="flex-shrink-0 w-60 rounded-2xl border border-ivory-dark bg-white overflow-hidden">
      <div className="h-1 bg-gradient-to-r from-gray-200 via-gray-100 to-gray-200 animate-shimmer bg-[length:200%_100%]" />
      <div className="p-5 space-y-3">
        <div className="h-4 w-3/4 bg-gray-100 rounded animate-pulse" />
        <div className="h-3 w-1/3 bg-gray-100 rounded animate-pulse" />
        <div className="h-3 w-full bg-gray-100 rounded animate-pulse" />
        <div className="h-3 w-5/6 bg-gray-100 rounded animate-pulse" />
        <div className="flex gap-2 pt-1">
          <div className="h-5 w-16 bg-gray-100 rounded-full animate-pulse" />
          <div className="h-5 w-20 bg-gray-100 rounded-full animate-pulse" />
        </div>
        <div className="h-8 w-full bg-gray-100 rounded-xl animate-pulse mt-2" />
      </div>
    </div>
  )
}

function TrendCard({ trend, onSearch }: { trend: TrendItem; onSearch: (q: string) => void }) {
  const cat = CATEGORY_STYLES[trend.category] ?? { bg: 'bg-gray-50', text: 'text-gray-700', dot: 'bg-gray-400' }
  const badgeStyle = BADGE_STYLES[trend.badge] ?? 'bg-gray-50 text-gray-600 border-gray-200'

  return (
    <div className="flex-shrink-0 w-60 rounded-2xl border border-ivory-dark bg-white overflow-hidden hover:shadow-lg hover:-translate-y-0.5 transition-all duration-300 group flex flex-col">
      {/* Top colour strip by category */}
      <div className={`h-1 w-full ${cat.dot} opacity-70`} />

      <div className="p-5 flex flex-col gap-3 flex-1">
        {/* Badge + category */}
        <div className="flex items-center justify-between">
          <span className={`text-[10px] font-semibold px-2.5 py-0.5 rounded-full border ${badgeStyle}`}>
            {trend.badge}
          </span>
          <span className={`text-[10px] font-semibold px-2.5 py-0.5 rounded-full ${cat.bg} ${cat.text} flex items-center gap-1`}>
            <span className={`inline-block w-1.5 h-1.5 rounded-full ${cat.dot}`} />
            {trend.category}
          </span>
        </div>

        {/* Trend name */}
        <h3 className="font-serif text-xl font-semibold text-noir leading-tight group-hover:text-noir-soft transition-colors">
          {trend.name}
        </h3>

        {/* Description */}
        <p className="text-xs text-noir/50 leading-relaxed line-clamp-3 flex-1">
          {trend.description}
        </p>

        {/* Example tags */}
        <div className="flex flex-wrap gap-1.5">
          {trend.example_items.map((item, i) => (
            <span key={i} className="text-[10px] px-2 py-0.5 bg-ivory text-noir/60 rounded-full border border-ivory-dark">
              {item}
            </span>
          ))}
        </div>

        {/* CTA */}
        <button
          onClick={() => onSearch(trend.search_query)}
          className="mt-auto w-full py-2.5 rounded-xl bg-noir text-white text-xs font-semibold tracking-wide hover:bg-noir-soft transition-colors group-hover:bg-gold group-hover:text-noir"
        >
          Explore trend →
        </button>
      </div>
    </div>
  )
}

export default function TrendAnalyzer({ onSearch }: { onSearch: (query: string) => void }) {
  const [data, setData] = useState<TrendsResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)

  const fetchTrends = async (refresh = false) => {
    try {
      setData(await getTrends(refresh))
    } catch { /* non-critical */ }
    finally { setLoading(false); setRefreshing(false) }
  }

  useEffect(() => { fetchTrends() }, [])

  return (
    <div className="mb-10">
      {/* Section heading */}
      <div className="flex items-end justify-between mb-5">
        <div>
          <p className="text-[10px] tracking-[0.3em] uppercase text-noir/40 mb-1">Curated for you</p>
          <h2 className="font-serif text-3xl font-light text-noir">
            What&apos;s <span className="italic text-gold">Trending</span> Now
          </h2>
        </div>
        {!loading && (
          <button
            onClick={() => { setRefreshing(true); fetchTrends(true) }}
            disabled={refreshing}
            className="flex items-center gap-1.5 text-xs text-noir/40 hover:text-gold transition-colors disabled:opacity-30"
          >
            <RefreshCw className={`h-3 w-3 ${refreshing ? 'animate-spin' : ''}`} />
            Refresh
          </button>
        )}
      </div>

      {/* Cards */}
      <div className="flex gap-4 overflow-x-auto pb-3 scrollbar-hide">
        {loading
          ? [...Array(4)].map((_, i) => <SkeletonCard key={i} />)
          : data?.trends.map((trend, i) => (
              <TrendCard key={i} trend={trend} onSearch={onSearch} />
            ))
        }
      </div>

      {!loading && data && (
        <p className="text-[10px] text-noir/25 mt-2 tracking-wide">
          Updated {data.updated_at} · {data.source}
        </p>
      )}
    </div>
  )
}
