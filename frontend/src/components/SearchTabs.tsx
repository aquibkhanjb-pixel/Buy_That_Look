'use client'

import { Image, Type, Combine } from 'lucide-react'
import { cn } from '@/lib/utils'

type SearchMode = 'image' | 'text' | 'hybrid'

interface SearchTabsProps {
  activeTab: SearchMode
  onTabChange: (tab: SearchMode) => void
}

const tabs = [
  {
    id: 'image' as SearchMode,
    label: 'Image Search',
    icon: Image,
    description: 'Upload a fashion item',
  },
  {
    id: 'text' as SearchMode,
    label: 'Text Search',
    icon: Type,
    description: 'Describe what you want',
  },
  {
    id: 'hybrid' as SearchMode,
    label: 'Hybrid Search',
    icon: Combine,
    description: 'Combine image + text',
  },
]

export default function SearchTabs({ activeTab, onTabChange }: SearchTabsProps) {
  return (
    <div className="flex flex-col sm:flex-row gap-3">
      {tabs.map((tab) => {
        const Icon = tab.icon
        const isActive = activeTab === tab.id

        return (
          <button
            key={tab.id}
            onClick={() => onTabChange(tab.id)}
            className={cn(
              'flex-1 flex items-center gap-3 p-4 rounded-xl border-2 transition-all duration-200',
              isActive
                ? 'border-primary-500 bg-primary-50 text-primary-700'
                : 'border-gray-200 bg-white text-gray-600 hover:border-gray-300 hover:bg-gray-50'
            )}
          >
            <div
              className={cn(
                'p-2 rounded-lg',
                isActive ? 'bg-primary-100' : 'bg-gray-100'
              )}
            >
              <Icon className="h-5 w-5" />
            </div>
            <div className="text-left">
              <div className="font-medium">{tab.label}</div>
              <div className="text-xs opacity-75">{tab.description}</div>
            </div>
          </button>
        )
      })}
    </div>
  )
}
