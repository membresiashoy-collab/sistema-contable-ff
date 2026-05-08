-- ======================================================
-- CONTABILIDAD PRO - LOTES DE BANDEJA DE ASIENTOS
-- Contabilización masiva controlada y auditada.
-- ======================================================
--
-- Esta migración es idempotente.
-- No borra datos.
-- No contabiliza asientos por sí misma.
-- Solo agrega estructura de trazabilidad para lotes masivos.
-- ======================================================

CREATE TABLE IF NOT EXISTS asientos_bandeja_lotes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    empresa_id INTEGER NOT NULL DEFAULT 1,
    accion TEXT NOT NULL,
    estado TEXT NOT NULL,
    cantidad_solicitada INTEGER NOT NULL DEFAULT 0,
    cantidad_procesada INTEGER NOT NULL DEFAULT 0,
    cantidad_error INTEGER NOT NULL DEFAULT 0,
    total_debe REAL NOT NULL DEFAULT 0,
    total_haber REAL NOT NULL DEFAULT 0,
    diferencia REAL NOT NULL DEFAULT 0,
    detalle TEXT,
    usuario TEXT,
    fecha_lote TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_asientos_bandeja_lotes_empresa
ON asientos_bandeja_lotes (empresa_id, fecha_lote);

CREATE INDEX IF NOT EXISTS idx_asientos_bandeja_lotes_estado
ON asientos_bandeja_lotes (empresa_id, estado, accion);