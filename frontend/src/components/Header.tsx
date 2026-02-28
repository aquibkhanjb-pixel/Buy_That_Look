'use client'

import { Sparkles } from 'lucide-react'

export default function Header() {
  return (
    <header className="bg-white border-b border-gray-100">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">
          <div className="flex items-center space-x-3">
            <div className="bg-gradient-to-r from-primary-500 to-purple-600 p-2 rounded-lg">
              <Sparkles className="h-6 w-6 text-white" />
            </div>
            <div>
              <h1 className="text-xl font-bold text-gray-900">
                Fashion Finder
              </h1>
              <p className="text-xs text-gray-500">AI-Powered Visual Search</p>
            </div>
          </div>

          <nav className="hidden md:flex items-center space-x-6">
            <a href="#" className="text-sm text-gray-600 hover:text-gray-900">
              How it works
            </a>
            <a href="#" className="text-sm text-gray-600 hover:text-gray-900">
              API Docs
            </a>
            <a
              href="https://github.com"
              target="_blank"
              rel="noopener noreferrer"
              className="text-sm text-gray-600 hover:text-gray-900"
            >
              GitHub
            </a>
          </nav>
        </div>
      </div>
    </header>
  )
}
