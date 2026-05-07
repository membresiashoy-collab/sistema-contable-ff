-- ======================================================
-- CONTABILIDAD PRO - EJERCICIOS CONTABLES
-- Ejercicios por empresa, fecha de inicio/cierre,
-- bloqueo contable, reapertura y auditoría.
-- ======================================================

CREATE TABLE IF NOT EXISTS ejercicios_contables (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    empresa_id INTEGER NOT NULL DEFAULT 1,

    nombre TEXT NOT NULL,
    fecha_inicio TEXT NOT NULL,
    fecha_cierre TEXT NOT NULL,

    anio_inicio INTEGER,
    anio_cierre INTEGER,

    estado TEXT NOT NULL DEFAULT 'ABIERTO',
    es_actual INTEGER NOT NULL DEFAULT 0,

    bloqueo_hasta TEXT,
    fecha_bloqueo TIMESTAMP,

    observaciones TEXT,

    usuario_creacion TEXT,
    fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    usuario_cierre TEXT,
    fecha_cierre_operativo TIMESTAMP,
    motivo_cierre TEXT,

    usuario_reapertura TEXT,
    fecha_reapertura TIMESTAMP,
    motivo_reapertura TEXT,

    usuario_anulacion TEXT,
    fecha_anulacion TIMESTAMP,
    motivo_anulacion TEXT,

    fecha_actualizacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    UNIQUE (empresa_id, fecha_inicio, fecha_cierre)
);

CREATE INDEX IF NOT EXISTS idx_ejercicios_empresa_estado
ON ejercicios_contables (empresa_id, estado);

CREATE INDEX IF NOT EXISTS idx_ejercicios_empresa_fechas
ON ejercicios_contables (empresa_id, fecha_inicio, fecha_cierre);

CREATE INDEX IF NOT EXISTS idx_ejercicios_empresa_actual
ON ejercicios_contables (empresa_id, es_actual);

CREATE INDEX IF NOT EXISTS idx_ejercicios_bloqueo
ON ejercicios_contables (empresa_id, bloqueo_hasta);

CREATE TABLE IF NOT EXISTS ejercicios_contables_eventos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    ejercicio_id INTEGER,
    empresa_id INTEGER NOT NULL DEFAULT 1,

    evento TEXT NOT NULL,
    detalle TEXT,
    usuario TEXT,

    fecha_evento TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_ejercicios_eventos_ejercicio
ON ejercicios_contables_eventos (ejercicio_id, fecha_evento);

CREATE INDEX IF NOT EXISTS idx_ejercicios_eventos_empresa
ON ejercicios_contables_eventos (empresa_id, fecha_evento);