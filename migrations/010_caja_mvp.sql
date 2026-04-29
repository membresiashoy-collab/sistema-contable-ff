-- ======================================================
-- 010_caja_mvp.sql
-- Caja MVP PRO
-- ======================================================
-- Objetivo:
-- - cajas configurables usando tesoreria_cuentas tipo CAJA;
-- - movimientos manuales de caja;
-- - transferencias Caja <-> Banco / Caja <-> Caja;
-- - arqueos y diferencias controladas;
-- - asientos propuestos/controlados propios de Caja;
-- - anulación lógica con motivo;
-- - trazabilidad sin borrar datos.
-- ======================================================

CREATE TABLE IF NOT EXISTS caja_movimientos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    empresa_id INTEGER NOT NULL DEFAULT 1,

    fecha TEXT NOT NULL,
    tipo_movimiento TEXT NOT NULL,
    subtipo TEXT DEFAULT '',

    caja_id_origen INTEGER,
    caja_nombre_origen TEXT DEFAULT '',

    caja_id_destino INTEGER,
    caja_nombre_destino TEXT DEFAULT '',

    cuenta_banco_id INTEGER,
    cuenta_banco_nombre TEXT DEFAULT '',

    concepto TEXT NOT NULL DEFAULT '',
    referencia TEXT DEFAULT '',
    observacion TEXT DEFAULT '',

    importe REAL NOT NULL DEFAULT 0,
    sentido_caja_origen TEXT NOT NULL DEFAULT 'NEUTRO',

    estado TEXT NOT NULL DEFAULT 'CONFIRMADO',
    motivo_anulacion TEXT DEFAULT '',
    fecha_anulacion TEXT,

    usuario_id INTEGER,
    fecha_creacion TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

    tesoreria_operacion_id INTEGER,
    tesoreria_operacion_banco_id INTEGER,

    arqueo_id INTEGER,
    fingerprint TEXT DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_caja_movimientos_empresa
ON caja_movimientos (empresa_id);

CREATE INDEX IF NOT EXISTS idx_caja_movimientos_fecha
ON caja_movimientos (empresa_id, fecha);

CREATE INDEX IF NOT EXISTS idx_caja_movimientos_caja_origen
ON caja_movimientos (empresa_id, caja_id_origen);

CREATE INDEX IF NOT EXISTS idx_caja_movimientos_caja_destino
ON caja_movimientos (empresa_id, caja_id_destino);

CREATE INDEX IF NOT EXISTS idx_caja_movimientos_estado
ON caja_movimientos (empresa_id, estado);

CREATE UNIQUE INDEX IF NOT EXISTS idx_caja_movimientos_fingerprint
ON caja_movimientos (empresa_id, fingerprint)
WHERE fingerprint IS NOT NULL AND fingerprint <> '';

CREATE TABLE IF NOT EXISTS caja_arqueos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    empresa_id INTEGER NOT NULL DEFAULT 1,

    caja_id INTEGER NOT NULL,
    caja_nombre TEXT NOT NULL DEFAULT '',

    fecha TEXT NOT NULL,
    saldo_sistema REAL NOT NULL DEFAULT 0,
    efectivo_contado REAL NOT NULL DEFAULT 0,
    diferencia REAL NOT NULL DEFAULT 0,

    tipo_diferencia TEXT NOT NULL DEFAULT 'SIN_DIFERENCIA',
    estado TEXT NOT NULL DEFAULT 'CONFIRMADO',

    movimiento_ajuste_id INTEGER,

    observacion TEXT DEFAULT '',
    usuario_id INTEGER,

    motivo_anulacion TEXT DEFAULT '',
    fecha_anulacion TEXT,
    fecha_creacion TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_caja_arqueos_empresa
ON caja_arqueos (empresa_id);

CREATE INDEX IF NOT EXISTS idx_caja_arqueos_caja_fecha
ON caja_arqueos (empresa_id, caja_id, fecha);

CREATE TABLE IF NOT EXISTS caja_asientos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    empresa_id INTEGER NOT NULL DEFAULT 1,

    movimiento_caja_id INTEGER,
    arqueo_id INTEGER,

    fecha TEXT NOT NULL,
    cuenta_codigo TEXT NOT NULL DEFAULT '',
    cuenta_nombre TEXT NOT NULL DEFAULT '',

    debe REAL NOT NULL DEFAULT 0,
    haber REAL NOT NULL DEFAULT 0,

    glosa TEXT NOT NULL DEFAULT '',
    estado TEXT NOT NULL DEFAULT 'PROPUESTO',

    fecha_creacion TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_caja_asientos_empresa
ON caja_asientos (empresa_id);

CREATE INDEX IF NOT EXISTS idx_caja_asientos_movimiento
ON caja_asientos (empresa_id, movimiento_caja_id);

CREATE INDEX IF NOT EXISTS idx_caja_asientos_arqueo
ON caja_asientos (empresa_id, arqueo_id);

CREATE TABLE IF NOT EXISTS caja_auditoria (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    empresa_id INTEGER NOT NULL DEFAULT 1,
    usuario_id INTEGER,

    accion TEXT NOT NULL DEFAULT '',
    entidad TEXT NOT NULL DEFAULT '',
    entidad_id TEXT NOT NULL DEFAULT '',

    valor_anterior TEXT DEFAULT '',
    valor_nuevo TEXT DEFAULT '',
    motivo TEXT DEFAULT '',

    fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_caja_auditoria_empresa
ON caja_auditoria (empresa_id, fecha);