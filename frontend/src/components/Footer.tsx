import Link from 'next/link'
import { Crown, Shield, Sparkles, Shirt, Camera, Calendar } from 'lucide-react'

const FEATURES = [
  { label: 'AI Style Discovery',   icon: Sparkles,  href: '/?tab=discover'  },
  { label: 'Find This Look',       icon: Camera,    href: '/?tab=findlook'  },
  { label: 'Occasion Planner',     icon: Calendar,  href: '/?tab=occasion'  },
  { label: 'Virtual Try-On',       icon: Shirt,     href: '/pricing'        },
  { label: 'Premium Plan',         icon: Crown,     href: '/pricing'        },
]

const LEGAL = [
  { label: 'Privacy Policy',    href: '/privacy'    },
  { label: 'Terms of Service',  href: '/terms'      },
  { label: 'Refund Policy',     href: '/refund'     },
  { label: 'Contact Us',        href: '/contact'    },
]

export default function Footer() {
  const year = new Date().getFullYear()

  return (
    <footer className="bg-noir text-white mt-20">

      {/* Top divider */}
      <div className="h-px bg-gradient-to-r from-transparent via-gold/30 to-transparent" />

      <div className="max-w-5xl mx-auto px-6 lg:px-8 py-14">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-12">

          {/* Brand column */}
          <div className="space-y-5">
            <div>
              <h2 className="font-serif text-3xl font-light tracking-tight text-white leading-none">
                Fashion<span className="text-gold italic"> Finder</span>
              </h2>
              <p className="mt-2 text-xs tracking-[0.2em] uppercase text-white/40">
                Your Personal AI Stylist
              </p>
            </div>
            <p className="text-sm text-white/50 leading-relaxed max-w-xs">
              Discover your perfect style with AI-powered recommendations, visual search, and personalised outfit planning — all in one place.
            </p>
            <div className="flex items-center gap-2 pt-1">
              <Shield className="h-3.5 w-3.5 text-gold/70 flex-shrink-0" />
              <span className="text-[11px] text-white/35 tracking-wide">
                Secure payments · SSL encrypted · Privacy first
              </span>
            </div>
          </div>

          {/* Features column */}
          <div>
            <p className="text-[10px] tracking-[0.25em] uppercase text-white/30 mb-5">Features</p>
            <ul className="space-y-3">
              {FEATURES.map(({ label, icon: Icon, href }) => (
                <li key={label}>
                  <Link
                    href={href}
                    className="flex items-center gap-2.5 text-sm text-white/55 hover:text-gold transition-colors group"
                  >
                    <Icon className="h-3.5 w-3.5 text-white/25 group-hover:text-gold/70 transition-colors flex-shrink-0" />
                    {label}
                  </Link>
                </li>
              ))}
            </ul>
          </div>

          {/* Legal + CTA column */}
          <div>
            <p className="text-[10px] tracking-[0.25em] uppercase text-white/30 mb-5">Company</p>
            <ul className="space-y-3 mb-8">
              {LEGAL.map(({ label, href }) => (
                <li key={label}>
                  <Link
                    href={href}
                    className="text-sm text-white/55 hover:text-gold transition-colors"
                  >
                    {label}
                  </Link>
                </li>
              ))}
            </ul>

            {/* Upgrade CTA */}
            <div className="rounded-xl border border-gold/20 bg-white/5 p-4 space-y-2">
              <div className="flex items-center gap-2">
                <Crown className="h-4 w-4 text-gold" />
                <span className="text-sm font-semibold text-white">Go Premium</span>
              </div>
              <p className="text-xs text-white/45 leading-relaxed">
                Unlimited styling, virtual try-on, chat history and more.
              </p>
              <Link
                href="/pricing"
                className="inline-block mt-1 text-xs font-medium text-gold hover:text-amber-400 transition-colors tracking-wide"
              >
                See plans →
              </Link>
            </div>
          </div>

        </div>
      </div>

      {/* Bottom bar */}
      <div className="border-t border-white/8">
        <div className="max-w-5xl mx-auto px-6 lg:px-8 py-5 flex flex-col sm:flex-row items-center justify-between gap-3">
          <p className="text-[11px] text-white/25">
            © {year} Fashion Finder. All rights reserved.
          </p>
          <div className="flex items-center gap-1.5 text-[11px] text-white/25">
            <span>Secure payments by</span>
            <span className="text-white/40 font-semibold">Razorpay</span>
            <span className="mx-1">·</span>
            <span>Made in India 🇮🇳</span>
          </div>
        </div>
      </div>

    </footer>
  )
}
