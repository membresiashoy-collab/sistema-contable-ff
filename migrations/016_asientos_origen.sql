-- ======================================================
-- CONTABILIDAD PRO - ASIENTOS DE ORIGEN + INICIO CONTABLE
-- Asientos de apertura, capital social, socios, suscripciones,
-- integraciones y base central para futura bandeja de asientos propuestos.
-- ======================================================

CREATE TABLE IF NOT EXISTS asientos_origen (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    empresa_id INTEGER NOT NULL DEFAULT 1,
    ejercicio_id INTEGER,
    fecha TEXT NOT NULL,
    tipo_origen TEXT NOT NULL,
    descripcion TEXT NOT NULL,
    referencia TEXT,
    observaciones TEXT,
    estado TEXT NOT NULL DEFAULT 'PROPUESTO',
    total_debe REAL NOT NULL DEFAULT 0,
    total_haber REAL NOT NULL DEFAULT 0,
    diferencia REAL NOT NULL DEFAULT 0,
    asiento_propuesto_id INTEGER,
    usuario_creacion TEXT,
    fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    usuario_anulacion TEXT,
    fecha_anulacion TIMESTAMP,
    motivo_anulacion TEXT,
    fecha_actualizacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_asientos_origen_empresa ON asientos_origen (empresa_id, estado);
CREATE INDEX IF NOT EXISTS idx_asientos_origen_ejercicio ON asientos_origen (empresa_id, ejercicio_id, estado);
CREATE INDEX IF NOT EXISTS idx_asientos_origen_fecha ON asientos_origen (empresa_id, fecha);
CREATE INDEX IF NOT EXISTS idx_asientos_origen_tipo ON asientos_origen (empresa_id, tipo_origen, estado);

CREATE TABLE IF NOT EXISTS asientos_origen_detalle (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    asiento_origen_id INTEGER NOT NULL,
    renglon INTEGER NOT NULL,
    cuenta_codigo TEXT,
    cuenta_nombre TEXT NOT NULL,
    debe REAL NOT NULL DEFAULT 0,
    haber REAL NOT NULL DEFAULT 0,
    glosa TEXT
);

CREATE INDEX IF NOT EXISTS idx_asientos_origen_detalle_cabecera ON asientos_origen_detalle (asiento_origen_id, renglon);

CREATE TABLE IF NOT EXISTS asientos_origen_eventos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    asiento_origen_id INTEGER,
    empresa_id INTEGER NOT NULL DEFAULT 1,
    evento TEXT NOT NULL,
    detalle TEXT,
    usuario TEXT,
    fecha_evento TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_asientos_origen_eventos ON asientos_origen_eventos (asiento_origen_id, fecha_evento);

-- ------------------------------------------------------
-- Bandeja central futura.
-- En esta etapa se usa para que apertura/capital/aportes
-- NO impacten directamente en Libro Diario.
-- ------------------------------------------------------

CREATE TABLE IF NOT EXISTS asientos_propuestos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    empresa_id INTEGER NOT NULL DEFAULT 1,
    ejercicio_id INTEGER,
    fecha TEXT NOT NULL,
    origen TEXT NOT NULL,
    origen_tabla TEXT,
    origen_id INTEGER,
    tipo_asiento TEXT NOT NULL,
    referencia TEXT,
    descripcion TEXT NOT NULL,
    estado TEXT NOT NULL DEFAULT 'PROPUESTO',
    total_debe REAL NOT NULL DEFAULT 0,
    total_haber REAL NOT NULL DEFAULT 0,
    diferencia REAL NOT NULL DEFAULT 0,
    id_asiento_libro_diario INTEGER,
    fecha_contabilizacion TIMESTAMP,
    usuario_contabilizacion TEXT,
    usuario_creacion TEXT,
    fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    usuario_anulacion TEXT,
    fecha_anulacion TIMESTAMP,
    motivo_anulacion TEXT,
    fecha_actualizacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_asientos_propuestos_empresa_estado ON asientos_propuestos (empresa_id, estado);
CREATE INDEX IF NOT EXISTS idx_asientos_propuestos_origen ON asientos_propuestos (empresa_id, origen, estado);
CREATE INDEX IF NOT EXISTS idx_asientos_propuestos_fecha ON asientos_propuestos (empresa_id, fecha);
CREATE INDEX IF NOT EXISTS idx_asientos_propuestos_origen_id ON asientos_propuestos (origen_tabla, origen_id);

CREATE TABLE IF NOT EXISTS asientos_propuestos_detalle (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    asiento_propuesto_id INTEGER NOT NULL,
    renglon INTEGER NOT NULL,
    cuenta_codigo TEXT,
    cuenta_nombre TEXT NOT NULL,
    debe REAL NOT NULL DEFAULT 0,
    haber REAL NOT NULL DEFAULT 0,
    glosa TEXT
);

CREATE INDEX IF NOT EXISTS idx_asientos_propuestos_detalle_cabecera ON asientos_propuestos_detalle (asiento_propuesto_id, renglon);

CREATE TABLE IF NOT EXISTS asientos_propuestos_eventos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    asiento_propuesto_id INTEGER,
    empresa_id INTEGER NOT NULL DEFAULT 1,
    evento TEXT NOT NULL,
    detalle TEXT,
    usuario TEXT,
    fecha_evento TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_asientos_propuestos_eventos ON asientos_propuestos_eventos (asiento_propuesto_id, fecha_evento);

-- ------------------------------------------------------
-- Inicio contable asistido: socios, capital suscripto e integrado.
-- ------------------------------------------------------

CREATE TABLE IF NOT EXISTS socios_empresa (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    empresa_id INTEGER NOT NULL DEFAULT 1,
    nombre TEXT NOT NULL,
    cuit TEXT,
    tipo_socio TEXT NOT NULL DEFAULT 'SOCIO',
    porcentaje_participacion REAL NOT NULL DEFAULT 0,
    observaciones TEXT,
    estado TEXT NOT NULL DEFAULT 'ACTIVO',
    usuario_creacion TEXT,
    fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    usuario_actualizacion TEXT,
    fecha_actualizacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    usuario_baja TEXT,
    fecha_baja TIMESTAMP,
    motivo_baja TEXT
);

CREATE INDEX IF NOT EXISTS idx_socios_empresa_estado ON socios_empresa (empresa_id, estado);
CREATE INDEX IF NOT EXISTS idx_socios_empresa_nombre ON socios_empresa (empresa_id, nombre);

CREATE TABLE IF NOT EXISTS capital_social_empresa (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    empresa_id INTEGER NOT NULL DEFAULT 1,
    ejercicio_id INTEGER,
    fecha_instrumento TEXT NOT NULL,
    tipo_instrumento TEXT NOT NULL DEFAULT 'INICIO_CONTABLE',
    referencia TEXT,
    descripcion TEXT NOT NULL DEFAULT 'Capital social inicial',
    capital_social_total REAL NOT NULL DEFAULT 0,
    total_suscripto REAL NOT NULL DEFAULT 0,
    total_integrado REAL NOT NULL DEFAULT 0,
    total_pendiente_integracion REAL NOT NULL DEFAULT 0,
    cuenta_socios_integracion_codigo TEXT,
    cuenta_socios_integracion_nombre TEXT,
    cuenta_capital_codigo TEXT,
    cuenta_capital_nombre TEXT,
    estado TEXT NOT NULL DEFAULT 'PROPUESTO',
    asiento_suscripcion_origen_id INTEGER,
    asiento_suscripcion_propuesto_id INTEGER,
    asiento_integracion_origen_id INTEGER,
    asiento_integracion_propuesto_id INTEGER,
    usuario_creacion TEXT,
    fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    usuario_anulacion TEXT,
    fecha_anulacion TIMESTAMP,
    motivo_anulacion TEXT,
    fecha_actualizacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_capital_social_empresa_estado ON capital_social_empresa (empresa_id, estado);
CREATE INDEX IF NOT EXISTS idx_capital_social_empresa_ejercicio ON capital_social_empresa (empresa_id, ejercicio_id, estado);

CREATE TABLE IF NOT EXISTS capital_suscripciones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    capital_id INTEGER NOT NULL,
    empresa_id INTEGER NOT NULL DEFAULT 1,
    socio_id INTEGER NOT NULL,
    porcentaje REAL NOT NULL DEFAULT 0,
    importe_suscripto REAL NOT NULL DEFAULT 0,
    importe_integrado REAL NOT NULL DEFAULT 0,
    importe_pendiente REAL NOT NULL DEFAULT 0,
    observaciones TEXT,
    estado TEXT NOT NULL DEFAULT 'ACTIVO',
    fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_capital_suscripciones_capital ON capital_suscripciones (capital_id, estado);
CREATE INDEX IF NOT EXISTS idx_capital_suscripciones_socio ON capital_suscripciones (empresa_id, socio_id, estado);

CREATE TABLE IF NOT EXISTS capital_integraciones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    capital_id INTEGER NOT NULL,
    suscripcion_id INTEGER,
    empresa_id INTEGER NOT NULL DEFAULT 1,
    socio_id INTEGER NOT NULL,
    fecha TEXT NOT NULL,
    importe REAL NOT NULL DEFAULT 0,
    medio_integracion TEXT NOT NULL DEFAULT 'NO_INTEGRADO',
    cuenta_destino_codigo TEXT,
    cuenta_destino_nombre TEXT,
    referencia TEXT,
    observaciones TEXT,
    asiento_origen_id INTEGER,
    asiento_propuesto_id INTEGER,
    estado TEXT NOT NULL DEFAULT 'PROPUESTO',
    usuario_creacion TEXT,
    fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    usuario_anulacion TEXT,
    fecha_anulacion TIMESTAMP,
    motivo_anulacion TEXT
);

CREATE INDEX IF NOT EXISTS idx_capital_integraciones_capital ON capital_integraciones (capital_id, estado);
CREATE INDEX IF NOT EXISTS idx_capital_integraciones_socio ON capital_integraciones (empresa_id, socio_id, estado);

CREATE TABLE IF NOT EXISTS capital_social_eventos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    capital_id INTEGER,
    socio_id INTEGER,
    empresa_id INTEGER NOT NULL DEFAULT 1,
    evento TEXT NOT NULL,
    detalle TEXT,
    usuario TEXT,
    fecha_evento TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_capital_social_eventos_capital ON capital_social_eventos (capital_id, fecha_evento);
CREATE INDEX IF NOT EXISTS idx_capital_social_eventos_empresa ON capital_social_eventos (empresa_id, fecha_evento);