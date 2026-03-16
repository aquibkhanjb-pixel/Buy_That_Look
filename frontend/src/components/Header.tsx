'use client'

import { Heart } from 'lucide-react'
import UserMenu from '@/components/UserMenu'

export type ActiveTab = 'discover' | 'findlook' | 'occasion'

interface HeaderProps {
  activeTab: ActiveTab
  onTabChange: (tab: ActiveTab) => void
  wishlistCount: number
  onWishlistOpen: () => void
}

const TABS: { id: ActiveTab; label: string }[] = [
  { id: 'discover',  label: 'Discover'         },
  { id: 'findlook',  label: 'Find This Look'    },
  { id: 'occasion',  label: 'Occasion Planner'  },
]

export default function Header({
  activeTab,
  onTabChange,
  wishlistCount,
  onWishlistOpen,
}: HeaderProps) {
  return (
    <header className="bg-noir text-white">
      <div className="max-w-5xl mx-auto px-6 lg:px-8">
        {/* Top strip */}
        <div className="border-b border-white/10 py-2 flex items-center justify-between">
          <p className="text-[10px] tracking-[0.3em] uppercase text-white/40">
            AI-Powered Style Intelligence
          </p>
          <p className="text-[10px] tracking-[0.2em] uppercase text-gold/70">
            ✦ Powered by Gemini · Serper · LangGraph
          </p>
        </div>

        {/* Main masthead */}
        <div className="py-5 flex items-center justify-between gap-6">
          <div>
            <h1 className="font-serif text-5xl md:text-6xl font-light tracking-tight text-white leading-none">
              Fashion<span className="text-gold italic"> Finder</span>
            </h1>
            <p className="mt-1 text-xs tracking-[0.25em] uppercase text-white/50">
              Your Personal AI Stylist
            </p>
          </div>

          {/* Nav — tabs + wishlist */}
          <nav className="hidden md:flex items-center gap-1 pb-1">
            {TABS.map((tab) => (
              <button
                key={tab.id}
                onClick={() => onTabChange(tab.id)}
                className={`
                  px-4 py-2 rounded-xl text-xs tracking-[0.15em] uppercase transition-all
                  ${activeTab === tab.id
                    ? 'bg-white/10 text-gold font-semibold'
                    : 'text-white/50 hover:text-white hover:bg-white/5'
                  }
                `}
              >
                {tab.label}
              </button>
            ))}

            {/* Divider */}
            <div className="w-px h-4 bg-white/20 mx-2" />

            {/* User menu */}
            <UserMenu />

            {/* Divider */}
            <div className="w-px h-4 bg-white/20 mx-2" />

            {/* Wishlist icon */}
            <button
              onClick={onWishlistOpen}
              className="relative p-2 rounded-xl text-white/50 hover:text-gold hover:bg-white/5 transition-all"
              title="My Wishlist"
            >
              <Heart className="h-4 w-4" />
              {wishlistCount > 0 && (
                <span className="absolute -top-0.5 -right-0.5 w-4 h-4 bg-gold text-noir text-[9px] font-bold rounded-full flex items-center justify-center leading-none">
                  {wishlistCount > 9 ? '9+' : wishlistCount}
                </span>
              )}
            </button>
          </nav>
        </div>

        {/* Gold rule */}
        <div className="h-px bg-gradient-to-r from-gold/60 via-gold/20 to-transparent" />
      </div>
    </header>
  )
}
