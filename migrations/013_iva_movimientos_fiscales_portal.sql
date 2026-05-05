-- =====================================================
-- IVA PRO - Portal IVA / inclusión declarable
-- Migración 013
-- =====================================================
-- Objetivo:
-- Separar la existencia contable/fiscal del crédito de su inclusión
-- en la posición IVA declarable del período.
--
-- Reglas:
-- - BORRADOR no impacta IVA.
-- - ANULADO no impacta IVA.
-- - CONFIRMADO impacta IVA solo si incluido_en_posicion = 1.
-- - CONFIRMADO con incluido_en_posicion = 0 queda como crédito/control pendiente.
--
-- Migración no destructiva: no borra datos ni recrea tablas.

ALTER TABLE iva_movimientos_fiscales
ADD COLUMN incluido_en_posicion INTEGER NOT NULL DEFAULT 1;

ALTER TABLE iva_movimientos_fiscales
ADD COLUMN incluido_en_portal_iva INTEGER NOT NULL DEFAULT 0;

ALTER TABLE iva_movimientos_fiscales
ADD COLUMN periodo_declaracion TEXT;

ALTER TABLE iva_movimientos_fiscales
ADD COLUMN motivo_no_inclusion TEXT;

ALTER TABLE iva_movimientos_fiscales
ADD COLUMN fecha_inclusion_posicion TIMESTAMP;

ALTER TABLE iva_movimientos_fiscales
ADD COLUMN usuario_inclusion_posicion TEXT;

ALTER TABLE iva_movimientos_fiscales
ADD COLUMN fecha_declaracion_portal TIMESTAMP;

ALTER TABLE iva_movimientos_fiscales
ADD COLUMN usuario_declaracion_portal TEXT;

UPDATE iva_movimientos_fiscales
SET incluido_en_posicion = CASE
        WHEN estado = 'CONFIRMADO' THEN 1
        ELSE 0
    END,
    incluido_en_portal_iva = 0,
    fecha_inclusion_posicion = CASE
        WHEN estado = 'CONFIRMADO' THEN COALESCE(fecha_confirmacion, fecha_carga, CURRENT_TIMESTAMP)
        ELSE NULL
    END
WHERE incluido_en_posicion IS NULL
   OR incluido_en_posicion NOT IN (0, 1)
   OR incluido_en_portal_iva IS NULL
   OR incluido_en_portal_iva NOT IN (0, 1);

CREATE INDEX IF NOT EXISTS idx_iva_mov_fiscales_inclusion
ON iva_movimientos_fiscales (empresa_id, anio, mes, estado, incluido_en_posicion);

CREATE UNIQUE INDEX IF NOT EXISTS idx_iva_mov_fiscales_origen_concepto_activo
ON iva_movimientos_fiscales (empresa_id, origen, origen_tabla, origen_id, tipo_concepto)
WHERE origen_id IS NOT NULL AND estado <> 'ANULADO';