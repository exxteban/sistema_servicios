import { useEffect, useLayoutEffect, useRef, useState } from 'react'

export default function SearchBar({ value, onChange }) {
  const [local, setLocal] = useState(value || '')
  const inputRef = useRef(null)
  const shouldRestoreFocusRef = useRef(false)
  const selectionRef = useRef({ start: null, end: null })

  useEffect(() => {
    const nextValue = value || ''
    if (nextValue === local) return
    if (document.activeElement === inputRef.current) {
      shouldRestoreFocusRef.current = true
      selectionRef.current = {
        start: inputRef.current.selectionStart,
        end: inputRef.current.selectionEnd
      }
    }
    setLocal(nextValue)
  }, [value, local])

  useEffect(() => {
    const t = setTimeout(() => onChange(local), 250)
    return () => clearTimeout(t)
  }, [local, onChange])

  useLayoutEffect(() => {
    if (!shouldRestoreFocusRef.current || !inputRef.current) return
    inputRef.current.focus({ preventScroll: true })
    const { start, end } = selectionRef.current
    if (typeof start === 'number' && typeof end === 'number') {
      inputRef.current.setSelectionRange(start, end)
    }
    shouldRestoreFocusRef.current = false
  }, [value])

  return (
    <div className="relative w-full">
      <div className="absolute inset-y-0 left-0 flex items-center pl-3 pointer-events-none">
        <svg className="w-5 h-5 text-gray-400" fill="none" strokeWidth="2" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
          <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-4.35-4.35M16.65 10.65a6 6 0 11-12 0 6 6 0 0112 0z"></path>
        </svg>
      </div>
      <input
        ref={inputRef}
        type="search"
        className="w-full pl-10 pr-4 py-2.5 bg-gray-50 border border-gray-200 text-gray-900 text-sm rounded-full focus:ring-blue-500 focus:border-blue-500 focus:bg-white transition-all shadow-sm"
        value={local}
        onChange={(e) => setLocal(e.target.value)}
        placeholder="Buscar productos..."
        aria-label="Buscar productos en la tienda"
        autoComplete="off"
      />
    </div>
  )
}
