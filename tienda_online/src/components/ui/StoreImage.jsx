import { useEffect, useMemo, useState } from 'react'

function uniqueSources(values) {
  return Array.from(new Set((values || []).filter(Boolean)))
}

export default function StoreImage({ src, fallbackSources = [], fallback = null, ...props }) {
  const sources = useMemo(() => uniqueSources([src, ...fallbackSources]), [src, fallbackSources])
  const [sourceIndex, setSourceIndex] = useState(0)

  useEffect(() => {
    setSourceIndex(0)
  }, [sources])

  if (!sources.length) {
    return fallback
  }

  const currentSource = sources[Math.min(sourceIndex, sources.length - 1)]

  return (
    <img
      {...props}
      src={currentSource}
      onError={() => {
        setSourceIndex((current) => (current < sources.length - 1 ? current + 1 : current))
      }}
    />
  )
}
