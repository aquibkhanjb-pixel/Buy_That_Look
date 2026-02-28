'use client'

import { useCallback, useState } from 'react'
import { useDropzone } from 'react-dropzone'
import { Upload, X, Loader2 } from 'lucide-react'
import Image from 'next/image'
import { cn } from '@/lib/utils'

interface ImageUploadProps {
  onUpload: (file: File) => void
  isLoading: boolean
}

export default function ImageUpload({ onUpload, isLoading }: ImageUploadProps) {
  const [preview, setPreview] = useState<string | null>(null)
  const [selectedFile, setSelectedFile] = useState<File | null>(null)

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
    maxSize: 10 * 1024 * 1024, // 10MB
    multiple: false,
  })

  const handleSearch = () => {
    if (selectedFile) {
      onUpload(selectedFile)
    }
  }

  const clearImage = () => {
    setPreview(null)
    setSelectedFile(null)
  }

  return (
    <div className="space-y-4">
      {!preview ? (
        <div
          {...getRootProps()}
          className={cn(
            'border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition-all duration-200',
            isDragActive
              ? 'border-primary-500 bg-primary-50'
              : 'border-gray-300 hover:border-gray-400 hover:bg-gray-50'
          )}
        >
          <input {...getInputProps()} />
          <Upload className="mx-auto h-12 w-12 text-gray-400 mb-4" />
          <p className="text-lg font-medium text-gray-700">
            {isDragActive ? 'Drop the image here' : 'Drag & drop an image here'}
          </p>
          <p className="mt-2 text-sm text-gray-500">
            or click to select a file
          </p>
          <p className="mt-4 text-xs text-gray-400">
            Supports: JPEG, PNG, WebP (max 10MB)
          </p>
        </div>
      ) : (
        <div className="relative">
          <div className="relative w-full h-64 rounded-xl overflow-hidden bg-gray-100">
            <Image
              src={preview}
              alt="Preview"
              fill
              className="object-contain"
            />
          </div>
          <button
            onClick={clearImage}
            className="absolute top-2 right-2 p-2 bg-white rounded-full shadow-md hover:bg-gray-100"
          >
            <X className="h-4 w-4 text-gray-600" />
          </button>
        </div>
      )}

      {preview && (
        <button
          onClick={handleSearch}
          disabled={isLoading}
          className="w-full btn-primary py-3 flex items-center justify-center gap-2"
        >
          {isLoading ? (
            <>
              <Loader2 className="h-5 w-5 animate-spin" />
              Searching...
            </>
          ) : (
            <>
              <Upload className="h-5 w-5" />
              Find Similar Products
            </>
          )}
        </button>
      )}
    </div>
  )
}
