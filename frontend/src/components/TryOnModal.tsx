'use client'

import { useRef, useState } from 'react'
import Image from 'next/image'
import Link from 'next/link'
import { X, Upload, Loader2, Shirt, Crown } from 'lucide-react'
import { useSession } from 'next-auth/react'
import { virtualTryOnAuth } from '@/lib/api'

interface TryOnModalProps {
  garmentImageUrl: string
  garmentTitle: string
  onClose: () => void
}

export default function TryOnModal({ garmentImageUrl, garmentTitle, onClose }: TryOnModalProps) {
  const { data: session } = useSession()
  const token = session?.backendToken
  const userTier = session?.user?.tier ?? 'free'

  const [personFile, setPersonFile] = useState<File | null>(null)
  const [personPreview, setPersonPreview] = useState<string | null>(null)
  const [resultImage, setResultImage] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const handleFileSelect = (file: File) => {
    setPersonFile(file)
    setResultImage(null)
    setError(null)
    const reader = new FileReader()
    reader.onload = (e) => setPersonPreview(e.target?.result as string)
    reader.readAsDataURL(file)
  }

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    const file = e.dataTransfer.files[0]
    if (file && file.type.startsWith('image/')) handleFileSelect(file)
  }

  const handleGenerate = async () => {
    if (!personFile || !token) return
    setLoading(true)
    setError(null)
    try {
      const response = await virtualTryOnAuth(token, personFile, garmentImageUrl, garmentTitle)
      setResultImage(`data:image/jpeg;base64,${response.result_image}`)
    } catch (err: unknown) {
      const status = (err as { response?: { status?: number; data?: { detail?: string } } })?.response?.status
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      if (status === 403) {
        setError('premium_required')
      } else if (status === 502 || status === 503) {
        setError('The AI model is waking up — HuggingFace spaces sleep when idle. Wait 30 seconds and try again.')
      } else if (detail?.includes('timeout') || String(err).includes('408')) {
        setError('Request timed out. The model may be overloaded. Please try again.')
      } else {
        setError('Try-on failed. Please ensure your photo shows your full body and try again.')
      }
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-2xl max-h-[90vh] overflow-y-auto">

        {/* Header */}
        <div className="flex items-center justify-between p-5 border-b">
          <div className="flex items-center gap-2">
            <Shirt className="h-5 w-5 text-purple-600" />
            <h2 className="text-lg font-semibold text-gray-900">Virtual Try-On</h2>
            {userTier !== 'premium' && (
              <span className="ml-1 flex items-center gap-1 text-[10px] bg-amber-100 text-amber-700 px-2 py-0.5 rounded-full font-medium">
                <Crown className="h-3 w-3" /> Premium
              </span>
            )}
          </div>
          <button onClick={onClose} className="p-1 rounded-lg hover:bg-gray-100">
            <X className="h-5 w-5 text-gray-500" />
          </button>
        </div>

        <div className="p-5 space-y-5">

          {/* Premium gate for free users */}
          {userTier !== 'premium' && (
            <div className="rounded-xl bg-noir text-ivory p-6 text-center space-y-3">
              <Crown className="h-8 w-8 text-gold mx-auto" />
              <p className="font-serif text-lg">Virtual Try-On is a Premium feature</p>
              <p className="text-sm text-ivory/60">Upgrade to see how clothes look on you before buying.</p>
              <Link
                href="/pricing"
                className="inline-block mt-2 bg-gold text-white text-sm font-medium px-6 py-2.5 rounded-xl hover:bg-amber-600 transition-colors"
              >
                Upgrade to Premium — ₹99/mo
              </Link>
            </div>
          )}

          {/* Only show controls for premium users */}
          {userTier === 'premium' && (
            <>
              {/* Garment preview */}
              <div className="flex items-center gap-3 p-3 bg-purple-50 rounded-xl border border-purple-100">
                <div className="w-14 h-14 relative rounded-lg overflow-hidden flex-shrink-0 bg-gray-100">
                  <Image src={garmentImageUrl} alt={garmentTitle} fill className="object-cover" sizes="56px" />
                </div>
                <div className="min-w-0">
                  <p className="text-xs text-purple-600 font-medium">Selected garment</p>
                  <p className="text-sm font-medium text-gray-900 line-clamp-2">{garmentTitle}</p>
                </div>
              </div>

              {!resultImage ? (
                <>
                  {/* Upload area */}
                  <div>
                    <p className="text-sm font-medium text-gray-700 mb-2">
                      Upload your full-body photo
                    </p>
                    <p className="text-xs text-gray-500 mb-3">
                      For best results: stand straight, front-facing, full body visible, good lighting.
                    </p>

                    {personPreview ? (
                      <div className="relative">
                        <div className="w-full h-64 relative rounded-xl overflow-hidden bg-gray-100">
                          <Image src={personPreview} alt="Your photo" fill className="object-contain" sizes="600px" />
                        </div>
                        <button
                          onClick={() => { setPersonFile(null); setPersonPreview(null) }}
                          className="absolute top-2 right-2 w-7 h-7 bg-red-500 text-white rounded-full flex items-center justify-center"
                        >
                          <X className="h-4 w-4" />
                        </button>
                      </div>
                    ) : (
                      <div
                        onDrop={handleDrop}
                        onDragOver={(e) => e.preventDefault()}
                        onClick={() => fileInputRef.current?.click()}
                        className="border-2 border-dashed border-purple-200 rounded-xl p-8 text-center cursor-pointer hover:border-purple-400 hover:bg-purple-50/50 transition-colors"
                      >
                        <Upload className="h-8 w-8 text-purple-400 mx-auto mb-2" />
                        <p className="text-sm font-medium text-gray-700">Click or drag & drop your photo</p>
                        <p className="text-xs text-gray-400 mt-1">JPEG, PNG or WebP · max 10 MB</p>
                      </div>
                    )}
                    <input
                      ref={fileInputRef}
                      type="file"
                      accept="image/jpeg,image/png,image/webp"
                      className="hidden"
                      onChange={(e) => e.target.files?.[0] && handleFileSelect(e.target.files[0])}
                    />
                  </div>

                  {error && error !== 'premium_required' && (
                    <p className="text-sm text-red-600 bg-red-50 rounded-lg px-3 py-2">{error}</p>
                  )}

                  <button
                    onClick={handleGenerate}
                    disabled={!personFile || loading}
                    className="w-full py-3 rounded-xl bg-purple-600 text-white font-medium text-sm hover:bg-purple-700 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2 transition-colors"
                  >
                    {loading ? (
                      <>
                        <Loader2 className="h-4 w-4 animate-spin" />
                        Generating try-on... (30–120 seconds)
                      </>
                    ) : (
                      <>
                        <Shirt className="h-4 w-4" />
                        Try It On
                      </>
                    )}
                  </button>

                  {loading && (
                    <p className="text-xs text-center text-gray-500">
                      HuggingFace is processing your request. Please wait — do not close this window.
                    </p>
                  )}
                </>
              ) : (
                /* Result view */
                <div className="space-y-4">
                  <p className="text-sm font-medium text-gray-700 text-center">Here&apos;s how it looks on you!</p>
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <p className="text-xs text-gray-500 text-center mb-1">Your photo</p>
                      <div className="w-full aspect-[3/4] relative rounded-xl overflow-hidden bg-gray-100">
                        {personPreview && (
                          <Image src={personPreview} alt="Your photo" fill className="object-contain" sizes="300px" />
                        )}
                      </div>
                    </div>
                    <div>
                      <p className="text-xs text-purple-600 font-medium text-center mb-1">Virtual try-on</p>
                      <div className="w-full aspect-[3/4] relative rounded-xl overflow-hidden bg-gray-100">
                        <Image src={resultImage} alt="Try-on result" fill className="object-contain" sizes="300px" />
                      </div>
                    </div>
                  </div>

                  <div className="flex gap-3">
                    <button
                      onClick={() => setResultImage(null)}
                      className="flex-1 py-2.5 rounded-xl border border-gray-300 text-sm font-medium text-gray-700 hover:bg-gray-50 transition-colors"
                    >
                      Try Again
                    </button>
                    <a
                      href={resultImage}
                      download="tryon-result.jpg"
                      className="flex-1 py-2.5 rounded-xl bg-purple-600 text-white text-sm font-medium text-center hover:bg-purple-700 transition-colors"
                    >
                      Save Image
                    </a>
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  )
}
