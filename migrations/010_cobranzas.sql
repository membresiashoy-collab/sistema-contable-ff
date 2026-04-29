-- ======================================================
-- 010_cobranzas.sql
-- Módulo Cobranzas MVP
--
-- Objetivo:
-- - Registrar cobranzas de clientes.
-- - Imputar contra cuenta corriente clientes.
-- - Registrar retenciones sufridas.
-- - Crear asiento contable.
-- - Crear operación conciliable en Tesorería.
-- ======================================================

CREATE TABLE IF NOT EXISTS cobranzas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    empresa_id INTEGER DEFAULT 1,

    numero_recibo TEXT,
    fecha_cobranza TEXT NOT NULL,
    fecha_contable TEXT,

    cliente TEXT,
    cuit TEXT,

    cuenta_tesoreria_id INTEGER,
    medio_pago_id INTEGER,

    importe_recibido REAL DEFAULT 0,
    importe_retenciones REAL DEFAULT 0,
    importe_total_aplicado REAL DEFAULT 0,
    importe_imputado REAL DEFAULT 0,
    importe_a_cuenta REAL DEFAULT 0,

    referencia_externa TEXT,
    descripcion TEXT,

    estado TEXT DEFAULT 'CONFIRMADA',

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

CREATE TABLE IF NOT EXISTS cobranzas_imputaciones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    empresa_id INTEGER DEFAULT 1,
    cobranza_id INTEGER NOT NULL,

    cuenta_corriente_id INTEGER,
    tipo_comprobante TEXT,
    numero_comprobante TEXT,

    importe_imputado REAL DEFAULT 0,

    fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY(cobranza_id) REFERENCES cobranzas(id)
);

CREATE TABLE IF NOT EXISTS cobranzas_retenciones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    empresa_id INTEGER DEFAULT 1,
    cobranza_id INTEGER NOT NULL,

    tipo_retencion TEXT NOT NULL,
    descripcion TEXT,

    cuenta_contable_codigo TEXT,
    cuenta_contable_nombre TEXT,

    importe REAL DEFAULT 0,

    fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY(cobranza_id) REFERENCES cobranzas(id)
);

CREATE TABLE IF NOT EXISTS cobranzas_auditoria (
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

CREATE INDEX IF NOT EXISTS idx_cobranzas_empresa_fecha
ON cobranzas(empresa_id, fecha_cobranza);

CREATE INDEX IF NOT EXISTS idx_cobranzas_cliente
ON cobranzas(empresa_id, cliente, cuit);

CREATE INDEX IF NOT EXISTS idx_cobranzas_estado
ON cobranzas(empresa_id, estado);

CREATE INDEX IF NOT EXISTS idx_cobranzas_fingerprint
ON cobranzas(empresa_id, fingerprint);

CREATE INDEX IF NOT EXISTS idx_cobranzas_tesoreria
ON cobranzas(empresa_id, tesoreria_operacion_id);

CREATE INDEX IF NOT EXISTS idx_cobranzas_imputaciones_cobranza
ON cobranzas_imputaciones(empresa_id, cobranza_id);

CREATE INDEX IF NOT EXISTS idx_cobranzas_retenciones_cobranza
ON cobranzas_retenciones(empresa_id, cobranza_id);