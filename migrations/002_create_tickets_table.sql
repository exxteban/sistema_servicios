-- Migración: Crear tabla tickets para auditoría de impresiones
-- Fecha: 2025-12-30
-- Descripción: Tabla para registrar emisión y reimpresiones de tickets

CREATE TABLE tickets (
    id_ticket INTEGER PRIMARY KEY AUTOINCREMENT,
    id_venta INTEGER NOT NULL,
    numero_ticket VARCHAR(20) UNIQUE NOT NULL,
    fecha_emision DATETIME DEFAULT CURRENT_TIMESTAMP,
    fecha_ultima_impresion DATETIME,
    cantidad_impresiones INTEGER DEFAULT 1,
    formato VARCHAR(30) DEFAULT 'thermal_80mm',
    id_usuario_emision INTEGER,
    FOREIGN KEY (id_venta) REFERENCES ventas(id_venta),
    FOREIGN KEY (id_usuario_emision) REFERENCES usuarios(id_usuario)
);

-- Índices para mejorar rendimiento
CREATE INDEX idx_tickets_venta ON tickets(id_venta);
CREATE INDEX idx_tickets_numero ON tickets(numero_ticket);
