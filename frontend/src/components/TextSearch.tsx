'use client'

import { useState } from 'react'
import { Search, Loader2 } from 'lucide-react'

interface TextSearchProps {
  onSearch: (query: string) => void
  isLoading: boolean
}

const exampleQueries = [
  'Blue denim jacket with patches',
  'Elegant red evening gown',
  'Casual white sneakers',
  'Floral summer dress',
  'Black leather handbag',
]

export default function TextSearch({ onSearch, isLoading }: TextSearchProps) {
  const [query, setQuery] = useState('')

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (query.trim()) {
      onSearch(query.trim())
    }
  }

  const handleExampleClick = (example: string) => {
    setQuery(example)
    onSearch(example)
  }

  return (
    <div className="space-y-4">
      <form onSubmit={handleSubmit} className="space-y-4">
        <div className="relative">
          <Search className="absolute left-4 top-1/2 -translate-y-1/2 h-5 w-5 text-gray-400" />
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Describe the fashion item you're looking for..."
            className="input-field pl-12 pr-4 py-3 text-lg"
          />
        </div>

        <button
          type="submit"
          disabled={isLoading || !query.trim()}
          className="w-full btn-primary py-3 flex items-center justify-center gap-2"
        >
          {isLoading ? (
            <>
              <Loader2 className="h-5 w-5 animate-spin" />
              Searching...
            </>
          ) : (
            <>
              <Search className="h-5 w-5" />
              Search
            </>
          )}
        </button>
      </form>

      <div>
        <p className="text-sm text-gray-500 mb-2">Try these examples:</p>
        <div className="flex flex-wrap gap-2">
          {exampleQueries.map((example) => (
            <button
              key={example}
              onClick={() => handleExampleClick(example)}
              disabled={isLoading}
              className="px-3 py-1.5 text-sm bg-gray-100 text-gray-700 rounded-full
                         hover:bg-gray-200 transition-colors disabled:opacity-50"
            >
              {example}
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}
