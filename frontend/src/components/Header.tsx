'use client'

export default function Header() {
  return (
    <header className="bg-noir text-white">
      <div className="max-w-5xl mx-auto px-6 lg:px-8">
        {/* Top strip */}
        <div className="border-b border-white/10 py-2 flex items-center justify-between">
          <p className="text-[10px] tracking-[0.3em] uppercase text-white/40">
            AI-Powered Style Intelligence
          </p>
          <p className="text-[10px] tracking-[0.2em] uppercase text-gold/70">
            ✦ Powered by Gemini · CLIP · LangGraph
          </p>
        </div>

        {/* Main masthead */}
        <div className="py-6 flex items-end justify-between gap-6">
          <div>
            <h1 className="font-serif text-5xl md:text-6xl font-light tracking-tight text-white leading-none">
              Fashion<span className="text-gold italic"> Finder</span>
            </h1>
            <p className="mt-1 text-xs tracking-[0.25em] uppercase text-white/50">
              Your Personal AI Stylist
            </p>
          </div>

          <nav className="hidden md:flex items-center gap-6 pb-1">
            {['Discover', 'Trends', 'Try‑On'].map((item) => (
              <span
                key={item}
                className="text-xs tracking-[0.2em] uppercase text-white/50 hover:text-gold transition-colors cursor-pointer"
              >
                {item}
              </span>
            ))}
          </nav>
        </div>

        {/* Gold rule */}
        <div className="h-px bg-gradient-to-r from-gold/60 via-gold/20 to-transparent" />
      </div>
    </header>
  )
}
