/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './src/pages/**/*.{js,ts,jsx,tsx,mdx}',
    './src/components/**/*.{js,ts,jsx,tsx,mdx}',
    './src/app/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      fontFamily: {
        sans:  ['var(--font-dm-sans)', 'sans-serif'],
        serif: ['var(--font-cormorant)', 'Georgia', 'serif'],
      },
      colors: {
        ivory: { DEFAULT: '#F7F5F0', dark: '#EDE9E1' },
        noir:  { DEFAULT: '#0A0A0A', soft: '#1C1C1C', muted: '#3A3A3A' },
        gold:  { DEFAULT: '#C9A84C', light: '#E8D5A0', pale: '#F5EDD6' },
        blush: { DEFAULT: '#E8C4C4', soft: '#F5E6E6' },
        primary: {
          50: '#fdf4ff', 100: '#fae8ff', 200: '#f5d0fe', 300: '#f0abfc',
          400: '#e879f9', 500: '#d946ef', 600: '#c026d3', 700: '#a21caf',
          800: '#86198f', 900: '#701a75',
        },
      },
      animation: {
        'fade-in':  'fadeIn 0.4s ease-out',
        'slide-up': 'slideUp 0.3s ease-out',
        'shimmer':  'shimmer 1.5s infinite',
      },
      keyframes: {
        fadeIn:  { from: { opacity: '0' },                             to: { opacity: '1' } },
        slideUp: { from: { opacity: '0', transform: 'translateY(8px)' }, to: { opacity: '1', transform: 'translateY(0)' } },
        shimmer: { '0%': { backgroundPosition: '-200% 0' },           '100%': { backgroundPosition: '200% 0' } },
      },
    },
  },
  plugins: [],
}
