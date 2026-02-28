'use client'

import { useState } from 'react'
import { Filter, ChevronDown, X } from 'lucide-react'
import { SearchFilters } from '@/types'
import { cn } from '@/lib/utils'

interface FiltersProps {
  filters: SearchFilters
  onChange: (filters: SearchFilters) => void
}

const categories = [
  'Women > Dresses',
  'Women > Tops',
  'Women > Pants',
  'Men > Shirts',
  'Men > Pants',
  'Men > Jackets',
  'Accessories > Bags',
  'Accessories > Shoes',
]

const priceRanges = [
  { label: 'Under $25', min: 0, max: 25 },
  { label: '$25 - $50', min: 25, max: 50 },
  { label: '$50 - $100', min: 50, max: 100 },
  { label: '$100 - $200', min: 100, max: 200 },
  { label: 'Over $200', min: 200, max: undefined },
]

export default function Filters({ filters, onChange }: FiltersProps) {
  const [isExpanded, setIsExpanded] = useState(false)

  const hasActiveFilters =
    filters.min_price !== undefined ||
    filters.max_price !== undefined ||
    filters.category ||
    filters.brand

  const clearFilters = () => {
    onChange({})
  }

  const updateFilter = (key: keyof SearchFilters, value: any) => {
    const newFilters = { ...filters }
    if (value === undefined || value === '') {
      delete newFilters[key]
    } else {
      newFilters[key] = value
    }
    onChange(newFilters)
  }

  const setPriceRange = (min?: number, max?: number) => {
    const newFilters = { ...filters }
    if (min !== undefined) {
      newFilters.min_price = min
    } else {
      delete newFilters.min_price
    }
    if (max !== undefined) {
      newFilters.max_price = max
    } else {
      delete newFilters.max_price
    }
    onChange(newFilters)
  }

  return (
    <div className="bg-white rounded-xl border border-gray-100 overflow-hidden">
      {/* Header */}
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="w-full flex items-center justify-between p-4 hover:bg-gray-50"
      >
        <div className="flex items-center gap-2">
          <Filter className="h-5 w-5 text-gray-500" />
          <span className="font-medium text-gray-900">Filters</span>
          {hasActiveFilters && (
            <span className="px-2 py-0.5 text-xs bg-primary-100 text-primary-700 rounded-full">
              Active
            </span>
          )}
        </div>
        <ChevronDown
          className={cn(
            'h-5 w-5 text-gray-400 transition-transform',
            isExpanded && 'rotate-180'
          )}
        />
      </button>

      {/* Filter Options */}
      {isExpanded && (
        <div className="border-t border-gray-100 p-4 space-y-6">
          {/* Price Range */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Price Range
            </label>
            <div className="flex flex-wrap gap-2">
              {priceRanges.map((range) => {
                const isActive =
                  filters.min_price === range.min &&
                  filters.max_price === range.max
                return (
                  <button
                    key={range.label}
                    onClick={() =>
                      isActive
                        ? setPriceRange(undefined, undefined)
                        : setPriceRange(range.min, range.max)
                    }
                    className={cn(
                      'px-3 py-1.5 text-sm rounded-full border transition-colors',
                      isActive
                        ? 'border-primary-500 bg-primary-50 text-primary-700'
                        : 'border-gray-200 text-gray-600 hover:border-gray-300'
                    )}
                  >
                    {range.label}
                  </button>
                )
              })}
            </div>
          </div>

          {/* Category */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Category
            </label>
            <select
              value={filters.category || ''}
              onChange={(e) => updateFilter('category', e.target.value || undefined)}
              className="input-field"
            >
              <option value="">All Categories</option>
              {categories.map((cat) => (
                <option key={cat} value={cat}>
                  {cat}
                </option>
              ))}
            </select>
          </div>

          {/* Brand */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Brand
            </label>
            <input
              type="text"
              value={filters.brand || ''}
              onChange={(e) => updateFilter('brand', e.target.value || undefined)}
              placeholder="Enter brand name"
              className="input-field"
            />
          </div>

          {/* Clear Filters */}
          {hasActiveFilters && (
            <button
              onClick={clearFilters}
              className="flex items-center gap-1 text-sm text-gray-500 hover:text-gray-700"
            >
              <X className="h-4 w-4" />
              Clear all filters
            </button>
          )}
        </div>
      )}
    </div>
  )
}
