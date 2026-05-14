-- Parametrizacion PRO v2B - nucleo auditado de decisiones.
-- Esta migracion crea tablas propias para guardar decisiones sobre parametrizaciones
-- asistidas sin tocar modulos operativos ni generar asientos.

CREATE TABLE IF NOT EXISTS parametrizaciones_asistidas_decisiones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    empresa_id INTEGER NOT NULL,
    modulo TEXT NOT NULL,
    tipo_parametrizacion TEXT NOT NULL DEFAULT 'GENERAL',
    clave_parametrizacion TEXT NOT NULL,
    origen_sugerencia TEXT NOT NULL DEFAULT 'PARAMETRIZACION_ASISTIDA',
    estado_decision TEXT NOT NULL DEFAULT 'ACTIVA',
    accion_ultima TEXT NOT NULL DEFAULT 'ACEPTAR',
    cuenta_codigo TEXT,
    cuenta_nombre TEXT,
    valor_sugerido_json TEXT,
    valor_decidido_json TEXT,
    confianza TEXT,
    requiere_revision INTEGER NOT NULL DEFAULT 0,
    motivo TEXT,
    observacion TEXT,
    usuario_id INTEGER,
    fecha_decision TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    fecha_actualizacion TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    fecha_desactivacion TEXT,
    activo INTEGER NOT NULL DEFAULT 1,
    version INTEGER NOT NULL DEFAULT 1,
    UNIQUE (empresa_id, modulo, clave_parametrizacion)
);

CREATE INDEX IF NOT EXISTS idx_param_decisiones_empresa_modulo
ON parametrizaciones_asistidas_decisiones (empresa_id, modulo);

CREATE INDEX IF NOT EXISTS idx_param_decisiones_estado
ON parametrizaciones_asistidas_decisiones (empresa_id, estado_decision, activo);

CREATE TABLE IF NOT EXISTS parametrizaciones_asistidas_eventos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    decision_id INTEGER NOT NULL,
    empresa_id INTEGER NOT NULL,
    modulo TEXT NOT NULL,
    clave_parametrizacion TEXT NOT NULL,
    accion TEXT NOT NULL,
    estado_anterior TEXT,
    estado_nuevo TEXT NOT NULL,
    valor_anterior_json TEXT,
    valor_nuevo_json TEXT,
    motivo TEXT,
    usuario_id INTEGER,
    fecha_evento TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (decision_id) REFERENCES parametrizaciones_asistidas_decisiones(id)
);

CREATE INDEX IF NOT EXISTS idx_param_eventos_decision
ON parametrizaciones_asistidas_eventos (decision_id, fecha_evento);

CREATE INDEX IF NOT EXISTS idx_param_eventos_empresa_modulo
ON parametrizaciones_asistidas_eventos (empresa_id, modulo, clave_parametrizacion);

