-- ======================================================
-- 009_tesoreria_base.sql
-- Base común de Tesorería
--
-- Objetivo:
-- - Unificar Banco, Caja, Cobranzas, Pagos y Conciliación.
-- - Evitar que Banco/Caja sea el único origen de operaciones.
-- - Permitir registrar operaciones del sistema antes de conciliarlas.
-- ======================================================

CREATE TABLE IF NOT EXISTS tesoreria_cuentas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    empresa_id INTEGER DEFAULT 1,
    tipo_cuenta TEXT NOT NULL,
    nombre TEXT NOT NULL,
    entidad TEXT,
    numero_cuenta TEXT,
    moneda TEXT DEFAULT 'ARS',
    cuenta_contable_codigo TEXT,
    cuenta_contable_nombre TEXT,
    activo INTEGER DEFAULT 1,
    observacion TEXT,
    fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    fecha_actualizacion TIMESTAMP,
    UNIQUE(empresa_id, tipo_cuenta, nombre)
);

CREATE TABLE IF NOT EXISTS tesoreria_medios_pago (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    empresa_id INTEGER DEFAULT 1,
    codigo TEXT NOT NULL,
    nombre TEXT NOT NULL,
    tipo TEXT,
    requiere_referencia INTEGER DEFAULT 0,
    activo INTEGER DEFAULT 1,
    fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(empresa_id, codigo)
);

CREATE TABLE IF NOT EXISTS tesoreria_operaciones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    empresa_id INTEGER DEFAULT 1,

    tipo_operacion TEXT NOT NULL,
    subtipo TEXT,

    fecha_operacion TEXT NOT NULL,
    fecha_contable TEXT,

    cuenta_tesoreria_id INTEGER,
    medio_pago_id INTEGER,

    tercero_tipo TEXT,
    tercero_id INTEGER,
    tercero_nombre TEXT,
    tercero_cuit TEXT,

    descripcion TEXT,
    referencia_externa TEXT,

    importe REAL NOT NULL DEFAULT 0,
    moneda TEXT DEFAULT 'ARS',

    estado TEXT DEFAULT 'CONFIRMADA',
    estado_conciliacion TEXT DEFAULT 'PENDIENTE',

    importe_conciliado REAL DEFAULT 0,
    importe_pendiente REAL DEFAULT 0,

    asiento_id INTEGER,

    origen_modulo TEXT,
    origen_tabla TEXT,
    origen_id INTEGER,

    fingerprint TEXT,

    usuario_id INTEGER,
    motivo_anulacion TEXT,
    fecha_anulacion TIMESTAMP,

    fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    fecha_actualizacion TIMESTAMP,

    FOREIGN KEY(cuenta_tesoreria_id) REFERENCES tesoreria_cuentas(id),
    FOREIGN KEY(medio_pago_id) REFERENCES tesoreria_medios_pago(id),
    UNIQUE(empresa_id, fingerprint)
);

CREATE TABLE IF NOT EXISTS tesoreria_operaciones_componentes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    empresa_id INTEGER DEFAULT 1,
    operacion_id INTEGER NOT NULL,

    tipo_componente TEXT NOT NULL,
    cuenta_contable_codigo TEXT,
    cuenta_contable_nombre TEXT,

    importe REAL NOT NULL DEFAULT 0,
    descripcion TEXT,

    fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY(operacion_id) REFERENCES tesoreria_operaciones(id)
);

CREATE TABLE IF NOT EXISTS tesoreria_operaciones_vinculos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    empresa_id INTEGER DEFAULT 1,

    operacion_origen_id INTEGER NOT NULL,
    operacion_destino_id INTEGER NOT NULL,

    tipo_vinculo TEXT NOT NULL,
    descripcion TEXT,

    fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY(operacion_origen_id) REFERENCES tesoreria_operaciones(id),
    FOREIGN KEY(operacion_destino_id) REFERENCES tesoreria_operaciones(id),
    UNIQUE(empresa_id, operacion_origen_id, operacion_destino_id, tipo_vinculo)
);

CREATE TABLE IF NOT EXISTS tesoreria_auditoria (
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

CREATE INDEX IF NOT EXISTS idx_tesoreria_cuentas_empresa
ON tesoreria_cuentas(empresa_id, activo);

CREATE INDEX IF NOT EXISTS idx_tesoreria_medios_empresa
ON tesoreria_medios_pago(empresa_id, activo);

CREATE INDEX IF NOT EXISTS idx_tesoreria_operaciones_empresa_estado
ON tesoreria_operaciones(empresa_id, estado, estado_conciliacion);

CREATE INDEX IF NOT EXISTS idx_tesoreria_operaciones_fecha
ON tesoreria_operaciones(empresa_id, fecha_operacion);

CREATE INDEX IF NOT EXISTS idx_tesoreria_operaciones_cuenta
ON tesoreria_operaciones(empresa_id, cuenta_tesoreria_id, estado_conciliacion);

CREATE INDEX IF NOT EXISTS idx_tesoreria_operaciones_tipo
ON tesoreria_operaciones(empresa_id, tipo_operacion);

CREATE INDEX IF NOT EXISTS idx_tesoreria_operaciones_tercero
ON tesoreria_operaciones(empresa_id, tercero_tipo, tercero_id, tercero_cuit);

CREATE INDEX IF NOT EXISTS idx_tesoreria_operaciones_referencia
ON tesoreria_operaciones(empresa_id, referencia_externa);

CREATE INDEX IF NOT EXISTS idx_tesoreria_operaciones_fingerprint
ON tesoreria_operaciones(empresa_id, fingerprint);

CREATE INDEX IF NOT EXISTS idx_tesoreria_operaciones_importe
ON tesoreria_operaciones(empresa_id, importe);

CREATE INDEX IF NOT EXISTS idx_tesoreria_componentes_operacion
ON tesoreria_operaciones_componentes(empresa_id, operacion_id);

CREATE INDEX IF NOT EXISTS idx_tesoreria_vinculos_origen
ON tesoreria_operaciones_vinculos(empresa_id, operacion_origen_id);

CREATE INDEX IF NOT EXISTS idx_tesoreria_vinculos_destino
ON tesoreria_operaciones_vinculos(empresa_id, operacion_destino_id);

INSERT OR IGNORE INTO tesoreria_medios_pago
(empresa_id, codigo, nombre, tipo, requiere_referencia, activo)
VALUES
(1, 'EFECTIVO', 'Efectivo', 'EFECTIVO', 0, 1),
(1, 'TRANSFERENCIA', 'Transferencia bancaria', 'BANCO', 1, 1),
(1, 'CHEQUE', 'Cheque', 'VALORES', 1, 1),
(1, 'ECHEQ', 'E-Cheq', 'VALORES', 1, 1),
(1, 'TARJETA', 'Tarjeta', 'TARJETA', 1, 1),
(1, 'BILLETERA', 'Billetera virtual', 'BILLETERA', 1, 1),
(1, 'DEBITO_AUTOMATICO', 'Débito automático', 'BANCO', 1, 1),
(1, 'OTRO', 'Otro medio de pago', 'OTRO', 0, 1);