'use client'

import { useCallback, useState } from 'react'
import { useDropzone } from 'react-dropzone'
import { Upload, X, Loader2, Search, Sliders } from 'lucide-react'
import Image from 'next/image'
import { cn } from '@/lib/utils'

interface HybridSearchProps {
  onSearch: (file: File, query: string, alpha: number) => void
  isLoading: boolean
}

export default function HybridSearch({ onSearch, isLoading }: HybridSearchProps) {
  const [preview, setPreview] = useState<string | null>(null)
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [query, setQuery] = useState('')
  const [alpha, setAlpha] = useState(0.5)

  const onDrop = useCallback((acceptedFiles: File[]) => {
    const file = acceptedFiles[0]
    if (file) {
      setSelectedFile(file)
      const reader = new FileReader()
      reader.onload = () => {
        setPreview(reader.result as string)
      }
      reader.readAsDataURL(file)
    }
  }, [])

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      'image/jpeg': ['.jpg', '.jpeg'],
      'image/png': ['.png'],
      'image/webp': ['.webp'],
    },
    maxSize: 10 * 1024 * 1024,
    multiple: false,
  })

  const handleSearch = () => {
    if (selectedFile && query.trim()) {
      onSearch(selectedFile, query.trim(), alpha)
    }
  }

  const clearImage = () => {
    setPreview(null)
    setSelectedFile(null)
  }

  return (
    <div className="space-y-6">
      <div className="grid md:grid-cols-2 gap-6">
        {/* Image Upload */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-2">
            Reference Image
          </label>
          {!preview ? (
            <div
              {...getRootProps()}
              className={cn(
                'border-2 border-dashed rounded-xl p-6 text-center cursor-pointer transition-all duration-200 h-48 flex flex-col items-center justify-center',
                isDragActive
                  ? 'border-primary-500 bg-primary-50'
                  : 'border-gray-300 hover:border-gray-400 hover:bg-gray-50'
              )}
            >
              <input {...getInputProps()} />
              <Upload className="h-8 w-8 text-gray-400 mb-2" />
              <p className="text-sm text-gray-600">
                {isDragActive ? 'Drop here' : 'Upload an image'}
              </p>
            </div>
          ) : (
            <div className="relative h-48 rounded-xl overflow-hidden bg-gray-100">
              <Image
                src={preview}
                alt="Preview"
                fill
                className="object-contain"
              />
              <button
                onClick={clearImage}
                className="absolute top-2 right-2 p-1.5 bg-white rounded-full shadow-md hover:bg-gray-100"
              >
                <X className="h-4 w-4 text-gray-600" />
              </button>
            </div>
          )}
        </div>

        {/* Text Query */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-2">
            Description / Modification
          </label>
          <textarea
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="e.g., 'but in blue color' or 'similar style with floral pattern'"
            className="input-field h-48 resize-none"
          />
        </div>
      </div>

      {/* Alpha Slider */}
      <div className="bg-gray-50 rounded-xl p-4">
        <div className="flex items-center gap-2 mb-3">
          <Sliders className="h-4 w-4 text-gray-500" />
          <span className="text-sm font-medium text-gray-700">
            Search Weight Balance
          </span>
        </div>
        <div className="flex items-center gap-4">
          <span className="text-sm text-gray-500 w-16">Text</span>
          <input
            type="range"
            min="0"
            max="1"
            step="0.1"
            value={alpha}
            onChange={(e) => setAlpha(parseFloat(e.target.value))}
            className="flex-1 h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer accent-primary-600"
          />
          <span className="text-sm text-gray-500 w-16 text-right">Image</span>
        </div>
        <p className="text-xs text-gray-400 mt-2 text-center">
          Image weight: {Math.round(alpha * 100)}% | Text weight: {Math.round((1 - alpha) * 100)}%
        </p>
      </div>

      {/* Search Button */}
      <button
        onClick={handleSearch}
        disabled={isLoading || !selectedFile || !query.trim()}
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
            Search with Image + Text
          </>
        )}
      </button>
    </div>
  )
}
