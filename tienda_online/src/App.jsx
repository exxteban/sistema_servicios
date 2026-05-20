import { Suspense, lazy } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'

const CatalogoPage = lazy(() => import('./pages/CatalogoPage'))
const ProductoPage = lazy(() => import('./pages/ProductoPage'))
const WebBotStandalonePage = lazy(() => import('./features/web-bot/pages/WebBotStandalonePage'))

export default function App() {
  return (
    <Suspense fallback={<div style={{ minHeight: '100vh', background: '#f8fafc' }}></div>}>
      <Routes>
        <Route path="/tienda/:slug" element={<CatalogoPage />} />
        <Route path="/tienda/:slug/categoria/:categoryRef" element={<CatalogoPage />} />
        <Route path="/tienda/:slug/producto/:productRef" element={<ProductoPage />} />
        <Route path="/tienda/:slug/asistente" element={<WebBotStandalonePage />} />
        <Route path="/robot/:slug" element={<WebBotStandalonePage />} />
        <Route path="*" element={<Navigate to="/tienda/demo" replace />} />
      </Routes>
    </Suspense>
  )
}
