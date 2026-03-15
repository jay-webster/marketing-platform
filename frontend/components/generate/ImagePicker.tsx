"use client"

import { useEffect, useState } from "react"
import type { BrandImage } from "@/lib/types"

interface ImagePickerProps {
  selectedIds: string[]
  onSelectionChange: (ids: string[]) => void
}

export function ImagePicker({ selectedIds, onSelectionChange }: ImagePickerProps) {
  const [images, setImages] = useState<BrandImage[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    async function fetchImages() {
      try {
        const res = await fetch("/api/v1/images/?limit=200")
        if (!res.ok) throw new Error(`Failed to load images (${res.status})`)
        const json = await res.json()
        setImages(json.data)
      } catch (err) {
        setError("Could not load brand images.")
      } finally {
        setIsLoading(false)
      }
    }
    fetchImages()
  }, [])

  function toggleImage(id: string) {
    if (selectedIds.includes(id)) {
      onSelectionChange(selectedIds.filter((s) => s !== id))
    } else {
      onSelectionChange([...selectedIds, id])
    }
  }

  if (isLoading) {
    return <div className="text-sm text-gray-500">Loading images…</div>
  }

  if (error) {
    return <div className="text-sm text-red-600">{error}</div>
  }

  if (images.length === 0) {
    return (
      <div className="rounded-md border border-dashed border-gray-300 p-6 text-center text-sm text-gray-500">
        No brand images available — images will appear here after the next GitHub sync or an admin upload.
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-2">
      {selectedIds.length > 0 && (
        <p className="text-xs text-gray-500">
          {selectedIds.length} image{selectedIds.length !== 1 ? "s" : ""} selected
        </p>
      )}
      <div className="grid grid-cols-3 gap-2 sm:grid-cols-4">
        {images.map((img) => {
          const isSelected = selectedIds.includes(img.id)
          return (
            <button
              key={img.id}
              onClick={() => toggleImage(img.id)}
              title={img.display_title}
              className={`relative rounded-md overflow-hidden border-2 transition-all aspect-square ${
                isSelected
                  ? "border-gray-900 ring-2 ring-gray-900 ring-offset-1"
                  : "border-gray-200 hover:border-gray-400"
              }`}
            >
              {img.thumbnail_url ? (
                <img
                  src={img.thumbnail_url}
                  alt={img.display_title}
                  className="w-full h-full object-cover"
                />
              ) : (
                <div className="w-full h-full bg-gray-100 flex items-center justify-center text-xs text-gray-400">
                  {img.filename.split(".")[0].slice(0, 8)}
                </div>
              )}
              {isSelected && (
                <div className="absolute inset-0 bg-gray-900/20 flex items-center justify-center">
                  <span className="rounded-full bg-gray-900 text-white text-xs px-1.5 py-0.5">✓</span>
                </div>
              )}
            </button>
          )
        })}
      </div>
    </div>
  )
}
