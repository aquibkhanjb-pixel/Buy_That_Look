'use client'

import { useState } from 'react'
import Header from '@/components/Header'
import SearchTabs from '@/components/SearchTabs'
import ImageUpload from '@/components/ImageUpload'
import TextSearch from '@/components/TextSearch'
import HybridSearch from '@/components/HybridSearch'
import ChatAssistant from '@/components/ChatAssistant'
import ResultsGrid from '@/components/ResultsGrid'
import Filters from '@/components/Filters'
import ProductModal from '@/components/ProductModal'
import { SearchResult, SearchFilters, Product } from '@/types'
import { searchByImage, searchByText, searchHybrid } from '@/lib/api'

type SearchMode = 'image' | 'text' | 'hybrid' | 'chat'

export default function Home() {
  const [searchMode, setSearchMode] = useState<SearchMode>('image')
  const [results, setResults] = useState<SearchResult[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [filters, setFilters] = useState<SearchFilters>({})
  const [selectedProduct, setSelectedProduct] = useState<Product | null>(null)
  const [latencyMs, setLatencyMs] = useState<number | null>(null)
  const [hasSearched, setHasSearched] = useState(false)
  const [llmEnhanced, setLlmEnhanced] = useState(false)
  const [expandedQuery, setExpandedQuery] = useState<string | null>(null)

  const handleImageSearch = async (file: File) => {
    setIsLoading(true)
    setError(null)
    try {
      const response = await searchByImage(file, 20, filters)
      setResults(response.results)
      setLatencyMs(response.latency_ms)
      setHasSearched(true)
      setLlmEnhanced(response.llm_enhanced ?? false)
      setExpandedQuery(null)
    } catch (err) {
      setError('Failed to search. Please try again.')
      console.error(err)
    } finally {
      setIsLoading(false)
    }
  }

  const handleTextSearch = async (query: string) => {
    setIsLoading(true)
    setError(null)
    try {
      const response = await searchByText(query, 20, filters)
      setResults(response.results)
      setLatencyMs(response.latency_ms)
      setHasSearched(true)
      setLlmEnhanced(response.llm_enhanced ?? false)
      setExpandedQuery(response.expanded_query ?? null)
    } catch (err) {
      setError('Failed to search. Please try again.')
      console.error(err)
    } finally {
      setIsLoading(false)
    }
  }

  const handleHybridSearch = async (file: File, query: string, alpha: number) => {
    setIsLoading(true)
    setError(null)
    try {
      const response = await searchHybrid(file, query, alpha, 20, filters)
      setResults(response.results)
      setLatencyMs(response.latency_ms)
      setHasSearched(true)
      setLlmEnhanced(response.llm_enhanced ?? false)
      setExpandedQuery(response.expanded_query ?? null)
    } catch (err) {
      setError('Failed to search. Please try again.')
      console.error(err)
    } finally {
      setIsLoading(false)
    }
  }

  const handleFilterChange = (newFilters: SearchFilters) => {
    setFilters(newFilters)
  }

  const handleProductClick = (product: SearchResult) => {
    setSelectedProduct(product as Product)
  }

  const clearResults = () => {
    setResults([])
    setLatencyMs(null)
    setError(null)
    setHasSearched(false)
    setLlmEnhanced(false)
    setExpandedQuery(null)
  }

  const handleTabChange = (tab: SearchMode) => {
    setSearchMode(tab)
    // Clear results when switching tabs (but not for chat)
    if (tab !== 'chat') {
      clearResults()
    }
  }

  const isSearchMode = searchMode !== 'chat'

  return (
    <main className="min-h-screen">
      <Header />

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Search Section */}
        <div className="mb-8">
          <SearchTabs activeTab={searchMode} onTabChange={handleTabChange} />

          <div className="mt-6 bg-white rounded-xl shadow-sm border border-gray-100 p-6">
            {searchMode === 'image' && (
              <ImageUpload onUpload={handleImageSearch} isLoading={isLoading} />
            )}
            {searchMode === 'text' && (
              <TextSearch onSearch={handleTextSearch} isLoading={isLoading} />
            )}
            {searchMode === 'hybrid' && (
              <HybridSearch onSearch={handleHybridSearch} isLoading={isLoading} />
            )}
            {searchMode === 'chat' && (
              <ChatAssistant onProductClick={handleProductClick} />
            )}
          </div>
        </div>

        {/* Filters — only for non-chat modes */}
        {isSearchMode && (
          <Filters filters={filters} onChange={handleFilterChange} />
        )}

        {/* Error Message */}
        {error && (
          <div className="mb-6 p-4 bg-red-50 border border-red-200 rounded-lg text-red-700">
            {error}
          </div>
        )}

        {/* Results Section — only for non-chat modes */}
        {isSearchMode && (results.length > 0 || isLoading) && (
          <div className="mt-8">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-xl font-semibold text-gray-900">
                {isLoading ? 'Searching...' : `${results.length} Results Found`}
              </h2>
              <div className="flex items-center gap-4">
                {llmEnhanced && !isLoading && (
                  <span className="inline-flex items-center gap-1 px-2 py-1 rounded-full text-xs font-medium bg-purple-100 text-purple-700">
                    ✦ AI Enhanced
                  </span>
                )}
                {latencyMs && !isLoading && (
                  <span className="text-sm text-gray-500">
                    {latencyMs}ms
                  </span>
                )}
                {results.length > 0 && (
                  <button
                    onClick={clearResults}
                    className="text-sm text-gray-500 hover:text-gray-700"
                  >
                    Clear results
                  </button>
                )}
              </div>
            </div>

            {/* Show AI query expansion or image description */}
            {expandedQuery && !isLoading && (
              <div className="mb-4 px-4 py-2 bg-purple-50 border border-purple-100 rounded-lg text-sm text-purple-700">
                <span className="font-medium">
                  {searchMode === 'image' ? 'AI detected: ' : 'AI interpreted your search as: '}
                </span>
                <span className="italic">{expandedQuery}</span>
              </div>
            )}

            <ResultsGrid
              results={results}
              isLoading={isLoading}
              onProductClick={handleProductClick}
              llmEnhanced={llmEnhanced}
            />
          </div>
        )}

        {/* No Results Found — after a completed search */}
        {isSearchMode && !isLoading && hasSearched && results.length === 0 && !error && (
          <div className="mt-12 text-center">
            <div className="text-gray-300 mb-4">
              <svg className="mx-auto h-16 w-16" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} d="M9.172 16.172a4 4 0 015.656 0M9 10h.01M15 10h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
            </div>
            <h3 className="text-lg font-semibold text-gray-800">No matching products found</h3>
            <p className="mt-2 text-gray-500 max-w-sm mx-auto">
              We couldn&apos;t find any products matching your search. Try a different image, adjust your query, or remove some filters.
            </p>
          </div>
        )}

        {/* Initial Empty State — before any search */}
        {isSearchMode && !isLoading && !hasSearched && results.length === 0 && !error && (
          <div className="mt-12 text-center">
            <div className="text-gray-400 mb-4">
              <svg className="mx-auto h-16 w-16" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
              </svg>
            </div>
            <h3 className="text-lg font-medium text-gray-900">Start your search</h3>
            <p className="mt-2 text-gray-500">
              Upload an image or describe what you&apos;re looking for
            </p>
          </div>
        )}
      </div>

      {/* Product Modal */}
      {selectedProduct && (
        <ProductModal
          product={selectedProduct}
          onClose={() => setSelectedProduct(null)}
        />
      )}
    </main>
  )
}
