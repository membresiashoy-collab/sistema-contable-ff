-- ======================================================
-- 011_pagos.sql
-- Módulo Pagos MVP
--
-- Objetivo:
-- - Registrar pagos a proveedores.
-- - Imputar contra cuenta corriente proveedores.
-- - Registrar retenciones practicadas.
-- - Crear asiento contable.
-- - Crear operación conciliable en Tesorería.
-- ======================================================

CREATE TABLE IF NOT EXISTS pagos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    empresa_id INTEGER DEFAULT 1,

    numero_orden_pago TEXT,
    fecha_pago TEXT NOT NULL,
    fecha_contable TEXT,

    proveedor TEXT,
    cuit TEXT,

    cuenta_tesoreria_id INTEGER,
    medio_pago_id INTEGER,

    importe_pagado REAL DEFAULT 0,
    importe_retenciones REAL DEFAULT 0,
    importe_total_aplicado REAL DEFAULT 0,
    importe_imputado REAL DEFAULT 0,
    importe_a_cuenta REAL DEFAULT 0,

    referencia_externa TEXT,
    descripcion TEXT,

    estado TEXT DEFAULT 'CONFIRMADO',

    asiento_id INTEGER,
    tesoreria_operacion_id INTEGER,

    usuario_id INTEGER,
    motivo_anulacion TEXT,
    fecha_anulacion TIMESTAMP,

    fingerprint TEXT,

    fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    fecha_actualizacion TIMESTAMP,

    UNIQUE(empresa_id, fingerprint)
);

CREATE TABLE IF NOT EXISTS pagos_imputaciones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    empresa_id INTEGER DEFAULT 1,
    pago_id INTEGER NOT NULL,

    cuenta_corriente_id INTEGER,
    tipo_comprobante TEXT,
    numero_comprobante TEXT,

    importe_imputado REAL DEFAULT 0,

    fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY(pago_id) REFERENCES pagos(id)
);

CREATE TABLE IF NOT EXISTS pagos_retenciones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    empresa_id INTEGER DEFAULT 1,
    pago_id INTEGER NOT NULL,

    tipo_retencion TEXT NOT NULL,
    descripcion TEXT,

    cuenta_contable_codigo TEXT,
    cuenta_contable_nombre TEXT,

    importe REAL DEFAULT 0,

    fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY(pago_id) REFERENCES pagos(id)
);

CREATE TABLE IF NOT EXISTS pagos_auditoria (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    empresa_id INTEGER DEFAULT 1,
    usuario_id INTEGER,
    accion TEXT NOT NULL,
    entidad TEXT NOT NULL,
    entidad_id TEXT,
    valor_anterior TEXT,
    valor_nuevo TEXT,
    motivo TEXT
);

CREATE INDEX IF NOT EXISTS idx_pagos_empresa_fecha
ON pagos(empresa_id, fecha_pago);

CREATE INDEX IF NOT EXISTS idx_pagos_proveedor
ON pagos(empresa_id, proveedor, cuit);

CREATE INDEX IF NOT EXISTS idx_pagos_estado
ON pagos(empresa_id, estado);

CREATE INDEX IF NOT EXISTS idx_pagos_fingerprint
ON pagos(empresa_id, fingerprint);

CREATE INDEX IF NOT EXISTS idx_pagos_tesoreria
ON pagos(empresa_id, tesoreria_operacion_id);

CREATE INDEX IF NOT EXISTS idx_pagos_imputaciones_pago
ON pagos_imputaciones(empresa_id, pago_id);

CREATE INDEX IF NOT EXISTS idx_pagos_retenciones_pago
ON pagos_retenciones(empresa_id, pago_id);