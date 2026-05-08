-- ======================================================
-- CONTABILIDAD PRO - BANDEJA DE ASIENTOS PROPUESTOS
-- Pase controlado al Libro Diario, rechazo y reverso.
-- ======================================================
--
-- Esta migración es idempotente.
-- No borra datos.
-- No convierte asientos existentes.
-- Solo crea la auditoría común de la bandeja.
--
-- Las columnas adicionales de trazabilidad sobre:
--   asientos_propuestos
--   iva_cierres_asientos_propuestos
-- se agregan desde services/asientos_propuestos_service.py,
-- porque SQLite no soporta ALTER TABLE ADD COLUMN IF NOT EXISTS
-- de manera portable en todos los entornos.
-- ======================================================

CREATE TABLE IF NOT EXISTS asientos_bandeja_eventos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    empresa_id INTEGER NOT NULL DEFAULT 1,
    fuente TEXT NOT NULL,
    fuente_id INTEGER,
    fuente_clave TEXT NOT NULL,
    evento TEXT NOT NULL,
    detalle TEXT,
    usuario TEXT,
    fecha_evento TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_asientos_bandeja_eventos_empresa
ON asientos_bandeja_eventos (empresa_id, fecha_evento);

CREATE INDEX IF NOT EXISTS idx_asientos_bandeja_eventos_fuente
ON asientos_bandeja_eventos (fuente, fuente_clave, fecha_evento);

CREATE INDEX IF NOT EXISTS idx_asientos_bandeja_eventos_evento
ON asientos_bandeja_eventos (empresa_id, evento, fecha_evento);