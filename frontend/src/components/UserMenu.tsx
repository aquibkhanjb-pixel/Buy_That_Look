'use client'

import { useState, useRef, useEffect } from 'react'
import { useSession, signOut } from 'next-auth/react'
import Image from 'next/image'
import Link from 'next/link'
import { Crown, LogOut, ChevronDown, Sparkles } from 'lucide-react'
import { useSettings } from '@/contexts/SettingsContext'

export default function UserMenu() {
  const { data: session } = useSession()
  const { subscriptionPrice } = useSettings()
  const [open, setOpen]   = useState(false)
  const ref               = useRef<HTMLDivElement>(null)

  // Close on outside click
  useEffect(() => {
    function handler(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  if (!session?.user) return null

  const { name, email, image, tier } = session.user as {
    name?: string | null
    email?: string | null
    image?: string | null
    tier: string
  }
  const isPremium = tier === 'premium'

  return (
    <div ref={ref} className="relative">
      {/* Avatar trigger */}
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-2 hover:opacity-80 transition-opacity"
      >
        <div className="relative">
          {image ? (
            <Image
              src={image}
              alt={name ?? 'User'}
              width={32}
              height={32}
              className="rounded-full ring-2 ring-white/20"
            />
          ) : (
            <div className="w-8 h-8 rounded-full bg-gold/30 flex items-center justify-center">
              <span className="text-sm font-medium text-gold">
                {name?.[0]?.toUpperCase() ?? 'U'}
              </span>
            </div>
          )}
          {/* Premium crown badge */}
          {isPremium && (
            <div className="absolute -top-1 -right-1 w-4 h-4 bg-gold rounded-full flex items-center justify-center">
              <Crown className="h-2.5 w-2.5 text-white" />
            </div>
          )}
        </div>
        <ChevronDown className={`h-3.5 w-3.5 text-ivory/60 transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>

      {/* Dropdown */}
      {open && (
        <div className="absolute right-0 top-10 w-56 bg-white rounded-2xl shadow-2xl border border-ivory-dark z-50 overflow-hidden">
          {/* User info */}
          <div className="px-4 py-3 border-b border-ivory-dark">
            <p className="text-sm font-medium text-noir truncate">{name}</p>
            <p className="text-xs text-noir/40 truncate">{email}</p>
            <div className={`inline-flex items-center gap-1 mt-1.5 px-2 py-0.5 rounded-full text-[10px] font-medium tracking-wide ${
              isPremium
                ? 'bg-gold/15 text-amber-700'
                : 'bg-ivory text-noir/50'
            }`}>
              {isPremium ? <Crown className="h-2.5 w-2.5" /> : <Sparkles className="h-2.5 w-2.5" />}
              {isPremium ? 'Premium' : 'Free Plan'}
            </div>
          </div>

          {/* Actions */}
          <div className="py-1">
            {isPremium ? (
              <Link
                href="/pricing"
                onClick={() => setOpen(false)}
                className="flex items-center gap-2.5 px-4 py-2.5 text-sm text-noir hover:bg-ivory transition-colors"
              >
                <Crown className="h-4 w-4 text-gold" />
                Premium — Manage Plan
              </Link>
            ) : (
              <Link
                href="/pricing"
                onClick={() => setOpen(false)}
                className="flex items-center gap-2.5 px-4 py-2.5 text-sm text-noir hover:bg-ivory transition-colors"
              >
                <Crown className="h-4 w-4 text-gold" />
                <span>
                  Upgrade to Premium
                  <span className="ml-1.5 text-[10px] bg-gold text-white px-1.5 py-0.5 rounded-full">₹{subscriptionPrice}/mo</span>
                </span>
              </Link>
            )}

            <button
              onClick={() => signOut({ callbackUrl: '/login' })}
              className="w-full flex items-center gap-2.5 px-4 py-2.5 text-sm text-noir/60 hover:text-rouge hover:bg-red-50 transition-colors"
            >
              <LogOut className="h-4 w-4" />
              Sign out
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
