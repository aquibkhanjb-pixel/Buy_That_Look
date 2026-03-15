'use client'

import { useEffect, useState, useCallback } from 'react'
import { useSession } from 'next-auth/react'
import { useSearchParams } from 'next/navigation'
import { Check, Crown, Sparkles, Loader2, X } from 'lucide-react'
import Link from 'next/link'
import {
  createCheckoutSession,
  verifyPayment,
  cancelSubscription,
  refreshBackendToken,
} from '@/lib/api'

// Razorpay types
declare global {
  interface Window {
    Razorpay: new (options: RazorpayOptions) => RazorpayInstance
  }
}
interface RazorpayOptions {
  key: string
  subscription_id: string
  name: string
  description: string
  image?: string
  prefill: { name: string; email: string }
  theme: { color: string }
  handler: (response: RazorpayResponse) => void
  modal: { ondismiss: () => void }
}
interface RazorpayResponse {
  razorpay_payment_id: string
  razorpay_subscription_id: string
  razorpay_signature: string
}
interface RazorpayInstance {
  open(): void
}

const FREE_FEATURES = [
  '15 AI chat messages / day',
  'Wishlist — up to 20 items',
  '3 price drop alerts',
  'Fashion trend discovery',
  'Basic web product search',
]

const PREMIUM_FEATURES = [
  'Unlimited AI chat messages',
  'Unlimited wishlist items',
  'Unlimited price drop alerts',
  'Virtual try-on',
  'Outfit completion',
  'Style memory across sessions',
  'Priority product results',
  '30-day chat history',
]

function loadRazorpayScript(): Promise<boolean> {
  return new Promise((resolve) => {
    if (typeof window !== 'undefined' && window.Razorpay) {
      resolve(true)
      return
    }
    const script = document.createElement('script')
    script.src = 'https://checkout.razorpay.com/v1/checkout.js'
    script.onload  = () => resolve(true)
    script.onerror = () => resolve(false)
    document.body.appendChild(script)
  })
}

export default function PricingPage() {
  const { data: session, update: updateSession } = useSession()
  const searchParams = useSearchParams()
  const success = searchParams.get('success') === 'true'

  const [userTier, setUserTier]         = useState<string>('free')
  const [loading, setLoading]           = useState(false)
  const [cancelling, setCancelling]     = useState(false)
  const [showConfirm, setShowConfirm]   = useState(false)
  const [successMsg, setSuccessMsg]     = useState(success)
  const [errorMsg, setErrorMsg]         = useState('')

  const isPremium = userTier === 'premium'

  // Fetch fresh tier from DB on load
  useEffect(() => {
    if (session?.backendToken) {
      refreshBackendToken(session.backendToken)
        .then((d) => setUserTier(d.tier))
        .catch(() => setUserTier(session.user?.tier ?? 'free'))
    }
  }, [session])

  const applyNewToken = useCallback(async (token: string, tier: string) => {
    setUserTier(tier)
    await updateSession({ backendToken: token })
  }, [updateSession])

  // ── Upgrade ──────────────────────────────────────────────────────────────

  async function handleUpgrade() {
    setErrorMsg('')
    if (!session?.backendToken) {
      setErrorMsg('Session expired — please sign out and sign back in.')
      return
    }
    setLoading(true)
    try {
      const loaded = await loadRazorpayScript()
      if (!loaded) throw new Error('Razorpay script failed to load')

      const checkout = await createCheckoutSession(session.backendToken)

      const rzp = new window.Razorpay({
        key:             checkout.key_id,
        subscription_id: checkout.subscription_id,
        name:            'FashionAI',
        description:     'Premium — ₹99/month',
        prefill: {
          name:  checkout.user_name,
          email: checkout.user_email,
        },
        theme: { color: '#C9A84C' },

        handler: async (response: RazorpayResponse) => {
          try {
            const result = await verifyPayment(session.backendToken, response)
            await applyNewToken(result.access_token, result.tier)
            setSuccessMsg(true)
          } catch {
            alert('Payment verification failed. Please contact support.')
          } finally {
            setLoading(false)
          }
        },

        modal: {
          ondismiss: () => setLoading(false),
        },
      })

      rzp.open()
    } catch (e: unknown) {
      const msg = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setErrorMsg(msg ?? 'Could not open payment — please try again.')
      setLoading(false)
    }
  }

  // ── Cancel ───────────────────────────────────────────────────────────────

  async function handleCancel() {
    if (!session?.backendToken) return
    setCancelling(true)
    try {
      const result = await cancelSubscription(session.backendToken)
      await applyNewToken(result.access_token, result.tier)
      setShowConfirm(false)
    } catch {
      alert('Could not cancel subscription. Please try again.')
    } finally {
      setCancelling(false)
    }
  }

  // ── Render ───────────────────────────────────────────────────────────────

  return (
    <div className="min-h-screen bg-ivory px-4 py-16">
      <div className="max-w-4xl mx-auto mb-10">
        <Link href="/" className="text-sm text-noir/40 hover:text-noir transition-colors">
          ← Back to discover
        </Link>
      </div>

      {/* Header */}
      <div className="max-w-4xl mx-auto text-center mb-14">
        {successMsg && (
          <div className="inline-flex items-center gap-2 bg-emerald-50 border border-emerald-200 text-emerald-800 text-sm px-5 py-2.5 rounded-full mb-8">
            <Check className="h-4 w-4" />
            Payment successful — Premium is now active!
          </div>
        )}
        <h1 className="font-serif text-4xl md:text-5xl text-noir mb-4">Simple pricing</h1>
        <p className="text-noir/50 text-lg">Everything you need to discover your perfect style.</p>
      </div>

      {/* Cards */}
      <div className="max-w-3xl mx-auto grid md:grid-cols-2 gap-6">

        {/* Free */}
        <div className="bg-white rounded-2xl border border-ivory-dark p-8">
          <div className="flex items-center gap-2 mb-1">
            <Sparkles className="h-4 w-4 text-noir/40" />
            <h2 className="font-serif text-xl text-noir">Free</h2>
          </div>
          <p className="text-3xl font-bold text-noir mt-3">₹0</p>
          <p className="text-xs text-noir/40 mt-0.5">forever</p>
          <ul className="mt-8 space-y-3">
            {FREE_FEATURES.map((f) => (
              <li key={f} className="flex items-start gap-2.5 text-sm text-noir/70">
                <Check className="h-4 w-4 text-noir/30 flex-shrink-0 mt-0.5" /> {f}
              </li>
            ))}
          </ul>
          <div className="mt-8 py-2.5 px-4 rounded-xl bg-ivory text-center text-sm text-noir/50 font-medium">
            {isPremium ? 'Your previous plan' : 'Current plan'}
          </div>
        </div>

        {/* Premium */}
        <div className="bg-noir rounded-2xl p-8 relative overflow-hidden">
          <div className="absolute top-0 right-0 w-32 h-32 bg-gold/10 rounded-full blur-3xl" />
          <div className="flex items-center gap-2 mb-1">
            <Crown className="h-4 w-4 text-gold" />
            <h2 className="font-serif text-xl text-ivory">Premium</h2>
            {isPremium && (
              <span className="ml-auto text-[10px] bg-gold/20 text-gold px-2 py-0.5 rounded-full font-medium tracking-wide">
                ACTIVE
              </span>
            )}
          </div>
          <p className="text-3xl font-bold text-ivory mt-3">₹99</p>
          <p className="text-xs text-ivory/40 mt-0.5">per month · Card, UPI, Netbanking</p>
          <ul className="mt-8 space-y-3">
            {PREMIUM_FEATURES.map((f) => (
              <li key={f} className="flex items-start gap-2.5 text-sm text-ivory/80">
                <Check className="h-4 w-4 text-gold flex-shrink-0 mt-0.5" /> {f}
              </li>
            ))}
          </ul>

          <div className="mt-8 space-y-2">
            {errorMsg && (
              <p className="text-xs text-red-400 text-center pb-1">{errorMsg}</p>
            )}
            {isPremium ? (
              <button
                onClick={() => setShowConfirm(true)}
                className="w-full flex items-center justify-center gap-2 bg-white/10 text-ivory/70 text-sm font-medium py-3 rounded-xl hover:bg-white/15 transition-colors border border-white/10"
              >
                <X className="h-4 w-4" /> Cancel Subscription
              </button>
            ) : (
              <button
                onClick={handleUpgrade}
                disabled={loading}
                className="w-full flex items-center justify-center gap-2 bg-gold text-white text-sm font-medium py-3 rounded-xl hover:bg-amber-600 transition-colors disabled:opacity-50"
              >
                {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Crown className="h-4 w-4" />}
                {loading ? 'Opening payment…' : 'Upgrade to Premium'}
              </button>
            )}
          </div>
        </div>
      </div>

      <p className="text-center text-xs text-noir/30 mt-10">
        Cancel anytime · Powered by Razorpay · Secure payments
      </p>

      {/* Cancel confirm dialog */}
      {showConfirm && (
        <div className="fixed inset-0 bg-noir/50 backdrop-blur-sm z-50 flex items-center justify-center px-4">
          <div className="bg-white rounded-2xl p-8 max-w-sm w-full shadow-2xl">
            <h3 className="font-serif text-xl text-noir mb-2">Cancel subscription?</h3>
            <p className="text-sm text-noir/60 mb-6">
              You'll lose access to Premium features immediately. You can resubscribe anytime.
            </p>
            <div className="flex gap-3">
              <button
                onClick={() => setShowConfirm(false)}
                className="flex-1 py-2.5 rounded-xl border border-ivory-dark text-sm text-noir hover:bg-ivory transition-colors"
              >
                Keep Premium
              </button>
              <button
                onClick={handleCancel}
                disabled={cancelling}
                className="flex-1 py-2.5 rounded-xl bg-red-500 text-white text-sm font-medium hover:bg-red-600 transition-colors disabled:opacity-50 flex items-center justify-center gap-2"
              >
                {cancelling && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
                {cancelling ? 'Cancelling…' : 'Yes, Cancel'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
