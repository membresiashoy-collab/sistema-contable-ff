-- ============================================================
-- 022 - Inicio societario PRO: integraciones reales de capital
-- ============================================================
--
-- Objetivo:
-- - Mantener la estructura histórica de capital social creada en 016.
-- - Agregar una tabla de vínculo auditable entre una integración de capital
--   y el movimiento operativo real que la originó.
-- - Evitar que una misma operación de Tesorería/Caja/Banco sea aplicada
--   dos veces como integración activa de capital.
--
-- Nota técnica:
-- SQLite no permite ADD COLUMN IF NOT EXISTS de forma portable en todos los
-- entornos usados por el proyecto. Por eso las columnas complementarias de
-- capital_integraciones se agregan idempotentemente desde
-- services/capital_social_service.py. Esta migración crea la tabla de vínculos
-- e índices que sí son idempotentes en SQL puro.

CREATE TABLE IF NOT EXISTS capital_integraciones_origenes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    capital_integracion_id INTEGER NOT NULL,
    capital_id INTEGER NOT NULL,
    suscripcion_id INTEGER,
    empresa_id INTEGER NOT NULL DEFAULT 1,
    socio_id INTEGER NOT NULL,

    origen_modulo TEXT NOT NULL,
    origen_tabla TEXT NOT NULL,
    origen_id INTEGER NOT NULL,

    cuenta_tesoreria_id INTEGER,
    tesoreria_operacion_id INTEGER,
    movimiento_caja_id INTEGER,
    movimiento_banco_id INTEGER,

    estado TEXT NOT NULL DEFAULT 'ACTIVO',

    usuario_vinculacion TEXT,
    fecha_vinculacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    usuario_anulacion TEXT,
    fecha_anulacion TIMESTAMP,
    motivo_anulacion TEXT
);

CREATE INDEX IF NOT EXISTS idx_capital_integraciones_origenes_capital
ON capital_integraciones_origenes (empresa_id, capital_id, estado);

CREATE INDEX IF NOT EXISTS idx_capital_integraciones_origenes_socio
ON capital_integraciones_origenes (empresa_id, socio_id, estado);

CREATE INDEX IF NOT EXISTS idx_capital_integraciones_origenes_integracion
ON capital_integraciones_origenes (capital_integracion_id, estado);

CREATE INDEX IF NOT EXISTS idx_capital_integraciones_origenes_tesoreria
ON capital_integraciones_origenes (empresa_id, tesoreria_operacion_id, estado);

CREATE INDEX IF NOT EXISTS idx_capital_integraciones_origenes_origen
ON capital_integraciones_origenes (empresa_id, origen_modulo, origen_tabla, origen_id, estado);

CREATE UNIQUE INDEX IF NOT EXISTS idx_capital_integraciones_origenes_activo
ON capital_integraciones_origenes (empresa_id, origen_modulo, origen_tabla, origen_id)
WHERE estado = 'ACTIVO';