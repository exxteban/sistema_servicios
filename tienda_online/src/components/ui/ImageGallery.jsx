import { useState } from 'react';
import StoreImage from './StoreImage';

export default function ImageGallery({ imagenes, nombre }) {
  const [currentIndex, setCurrentIndex] = useState(0);

  if (!imagenes || imagenes.length === 0) {
    return (
      <div style={{ width: '100%', height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <svg style={{ width: 64, height: 64, color: '#e2e8f0' }} fill="none" strokeWidth="1.5" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" d="M2.25 15.75l5.159-5.159a2.25 2.25 0 013.182 0l5.159 5.159m-1.5-1.5l1.409-1.409a2.25 2.25 0 013.182 0l..."></path>
        </svg>
      </div>
    );
  }

  return (
    <div style={{ width: '100%', height: '100%', display: 'flex', flexDirection: 'column' }}>
      <div style={{ position: 'relative', width: '100%', flex: 1, overflow: 'hidden' }}>
        <StoreImage
          src={imagenes[currentIndex].url}
          fallbackSources={imagenes[currentIndex].fallback_urls}
          alt={`${nombre} - imagen ${currentIndex + 1}`}
          width={imagenes[currentIndex].width || undefined}
          height={imagenes[currentIndex].height || undefined}
          loading="eager"
          fetchPriority="high"
          decoding="async"
          sizes="(max-width: 768px) 92vw, 48vw"
          style={{ width: '100%', height: '100%', objectFit: 'cover', transition: 'opacity 0.3s' }}
        />
        
        {imagenes.length > 1 && (
          <>
            <button 
              type="button"
              onClick={() => setCurrentIndex(prev => prev === 0 ? imagenes.length - 1 : prev - 1)}
              aria-label={`Ver imagen anterior de ${nombre}`}
              style={{ position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)', background: 'rgba(255,255,255,0.8)', border: 'none', borderRadius: '50%', width: 40, height: 40, display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer', boxShadow: '0 2px 5px rgba(0,0,0,0.1)' }}
            >
              <svg width="24" height="24" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" /></svg>
            </button>
            <button 
              type="button"
              onClick={() => setCurrentIndex(prev => prev === imagenes.length - 1 ? 0 : prev + 1)}
              aria-label={`Ver imagen siguiente de ${nombre}`}
              style={{ position: 'absolute', right: 10, top: '50%', transform: 'translateY(-50%)', background: 'rgba(255,255,255,0.8)', border: 'none', borderRadius: '50%', width: 40, height: 40, display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer', boxShadow: '0 2px 5px rgba(0,0,0,0.1)' }}
            >
              <svg width="24" height="24" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" /></svg>
            </button>
          </>
        )}
      </div>
      
      {imagenes.length > 1 && (
        <div style={{ display: 'flex', gap: 8, padding: '12px 16px', overflowX: 'auto', background: '#f8fafc', borderTop: '1px solid var(--border-color)' }}>
          {imagenes.map((img, index) => (
            <button
              type="button"
              key={index}
              onClick={() => setCurrentIndex(index)}
              aria-label={`Ver imagen ${index + 1} de ${nombre}`}
              aria-pressed={currentIndex === index}
              style={{ 
                flexShrink: 0, 
                width: 60, 
                height: 60, 
                padding: 0, 
                border: currentIndex === index ? '2px solid var(--brand)' : '2px solid transparent', 
                borderRadius: 8, 
                overflow: 'hidden', 
                cursor: 'pointer',
                opacity: currentIndex === index ? 1 : 0.6,
                transition: 'all 0.2s'
              }}
            >
              <StoreImage
                src={img.card_url || img.url}
                fallbackSources={img.card_fallback_urls || img.fallback_urls}
                alt={`${nombre} miniatura ${index + 1}`}
                width={img.width || undefined}
                height={img.height || undefined}
                loading="lazy"
                decoding="async"
                sizes="60px"
                style={{ width: '100%', height: '100%', objectFit: 'cover' }}
              />
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
