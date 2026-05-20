import React from 'react';

export default function ProductoPageSkeleton() {
  return (
    <div className="container fade-in-up" style={{ padding: '32px 0 90px' }}>
      <div style={{ width: 150, height: 24, background: '#e2e8f0', borderRadius: 4, marginBottom: 24 }} className="skeleton" />
      
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: 32 }}>
        {/* Skeleton Galería */}
        <div style={{ borderRadius: 16, overflow: 'hidden', border: '1px solid var(--border-color)', background: '#fff', aspectRatio: '4/3', display: 'flex', flexDirection: 'column' }}>
          <div style={{ flex: 1, background: '#e2e8f0' }} className="skeleton" />
          <div style={{ display: 'flex', gap: 8, padding: '12px 16px', background: '#f8fafc', borderTop: '1px solid var(--border-color)' }}>
            {[1, 2, 3].map(i => (
              <div key={i} style={{ width: 60, height: 60, borderRadius: 8, background: '#e2e8f0' }} className="skeleton" />
            ))}
          </div>
        </div>
        
        {/* Skeleton Info */}
        <div>
          <div style={{ height: 40, background: '#e2e8f0', borderRadius: 8, marginBottom: 16, width: '80%' }} className="skeleton" />
          <div style={{ height: 32, background: '#e2e8f0', borderRadius: 8, marginBottom: 24, width: '40%' }} className="skeleton" />
          
          <div style={{ background: 'var(--surface-color)', padding: 24, borderRadius: 16, border: '1px solid var(--border-color)', marginBottom: 24 }}>
            <div style={{ height: 16, background: '#e2e8f0', borderRadius: 4, marginBottom: 12, width: '100%' }} className="skeleton" />
            <div style={{ height: 16, background: '#e2e8f0', borderRadius: 4, marginBottom: 12, width: '90%' }} className="skeleton" />
            <div style={{ height: 16, background: '#e2e8f0', borderRadius: 4, width: '95%' }} className="skeleton" />
          </div>
          
          <div style={{ height: 56, background: '#e2e8f0', borderRadius: 8, width: '100%' }} className="skeleton" />
        </div>
      </div>
    </div>
  );
}
