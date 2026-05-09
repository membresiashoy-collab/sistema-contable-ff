CREATE TABLE IF NOT EXISTS contabilidad_cuentas_comportamiento_eventos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    empresa_id INTEGER,
    mapeo_id INTEGER,
    codigo_cuenta TEXT,
    comportamiento TEXT,
    evento TEXT NOT NULL,
    detalle TEXT,
    usuario TEXT,
    fecha_evento TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_contabilidad_comportamientos_eventos_empresa
ON contabilidad_cuentas_comportamiento_eventos(empresa_id, fecha_evento);

CREATE INDEX IF NOT EXISTS idx_contabilidad_comportamientos_eventos_cuenta
ON contabilidad_cuentas_comportamiento_eventos(empresa_id, codigo_cuenta, comportamiento);