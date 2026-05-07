-- ======================================================
-- IVA PRO - CIERRE MENSUAL OPERATIVO V3
-- Cierre cronológico, versión Original/Rectificativas,
-- saldos trasladados, pagos y asientos propuestos.
-- ======================================================

CREATE TABLE IF NOT EXISTS iva_cierres_periodos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    empresa_id INTEGER NOT NULL,
    anio INTEGER NOT NULL,
    mes INTEGER NOT NULL,
    periodo TEXT NOT NULL,

    estado TEXT NOT NULL DEFAULT 'CERRADO',
    version_tipo TEXT NOT NULL DEFAULT 'ORIGINAL',
    numero_rectificativa INTEGER NOT NULL DEFAULT 0,
    version_etiqueta TEXT NOT NULL DEFAULT 'Original',
    es_version_vigente INTEGER NOT NULL DEFAULT 1,
    cierre_anterior_id INTEGER,
    motivo_rectificativa TEXT,

    requiere_revision_por_rectificativa INTEGER NOT NULL DEFAULT 0,
    cierre_origen_revision_id INTEGER,
    motivo_revision TEXT,

    iva_debito_fiscal REAL NOT NULL DEFAULT 0,
    credito_fiscal_computable REAL NOT NULL DEFAULT 0,
    iva_no_computable REAL NOT NULL DEFAULT 0,
    percepciones_iva_sufridas REAL NOT NULL DEFAULT 0,
    retenciones_iva_sufridas REAL NOT NULL DEFAULT 0,
    saldo_tecnico_anterior REAL NOT NULL DEFAULT 0,
    saldo_libre_disponibilidad REAL NOT NULL DEFAULT 0,
    pago_a_cuenta REAL NOT NULL DEFAULT 0,
    saldo_tecnico_iva REAL NOT NULL DEFAULT 0,
    saldo_preliminar_periodo REAL NOT NULL DEFAULT 0,

    saldo_tecnico_a_favor_trasladable REAL NOT NULL DEFAULT 0,
    saldo_trasladado_al_siguiente REAL NOT NULL DEFAULT 0,
    saldo_trasladado_original REAL NOT NULL DEFAULT 0,
    saldo_trasladado_rectificado REAL NOT NULL DEFAULT 0,
    diferencia_saldo_trasladado REAL NOT NULL DEFAULT 0,
    periodo_siguiente_afectado TEXT,
    impacto_rectificativa_json TEXT,

    resultado_saldo TEXT NOT NULL DEFAULT 'CERO',
    saldo_a_pagar REAL NOT NULL DEFAULT 0,
    saldo_a_favor REAL NOT NULL DEFAULT 0,
    importe_pagado REAL NOT NULL DEFAULT 0,
    saldo_pendiente_pago REAL NOT NULL DEFAULT 0,
    estado_pago TEXT NOT NULL DEFAULT 'NO_APLICA',
    fecha_ultimo_pago TEXT,

    neto_ventas REAL NOT NULL DEFAULT 0,
    total_ventas REAL NOT NULL DEFAULT 0,
    neto_compras REAL NOT NULL DEFAULT 0,
    total_compras REAL NOT NULL DEFAULT 0,
    total_movimientos_fiscales REAL NOT NULL DEFAULT 0,

    cantidad_ventas INTEGER NOT NULL DEFAULT 0,
    cantidad_compras INTEGER NOT NULL DEFAULT 0,
    cantidad_movimientos_fiscales INTEGER NOT NULL DEFAULT 0,

    posicion_json TEXT,
    resumen_origenes_json TEXT,
    alertas_json TEXT,
    indicadores_json TEXT,

    observacion_cierre TEXT,
    usuario_cierre TEXT,
    fecha_cierre TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    motivo_reapertura TEXT,
    usuario_reapertura TEXT,
    fecha_reapertura TIMESTAMP,

    fecha_actualizacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_iva_cierres_empresa_periodo
ON iva_cierres_periodos (empresa_id, anio, mes);

CREATE INDEX IF NOT EXISTS idx_iva_cierres_vigente
ON iva_cierres_periodos (empresa_id, anio, mes, es_version_vigente);

CREATE INDEX IF NOT EXISTS idx_iva_cierres_estado
ON iva_cierres_periodos (empresa_id, estado);

CREATE INDEX IF NOT EXISTS idx_iva_cierres_estado_pago
ON iva_cierres_periodos (empresa_id, estado_pago);

CREATE TABLE IF NOT EXISTS iva_cierres_periodos_eventos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cierre_id INTEGER,
    empresa_id INTEGER NOT NULL,
    anio INTEGER NOT NULL,
    mes INTEGER NOT NULL,
    periodo TEXT NOT NULL,
    evento TEXT NOT NULL,
    detalle TEXT,
    usuario TEXT,
    fecha_evento TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_iva_cierres_eventos_cierre
ON iva_cierres_periodos_eventos (cierre_id, fecha_evento);

CREATE INDEX IF NOT EXISTS idx_iva_cierres_eventos_periodo
ON iva_cierres_periodos_eventos (empresa_id, anio, mes, fecha_evento);

CREATE TABLE IF NOT EXISTS iva_cierres_pagos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cierre_id INTEGER NOT NULL,
    empresa_id INTEGER NOT NULL,
    anio INTEGER NOT NULL,
    mes INTEGER NOT NULL,
    periodo TEXT NOT NULL,
    fecha_pago TEXT NOT NULL,
    importe REAL NOT NULL DEFAULT 0,
    medio_pago TEXT NOT NULL DEFAULT 'MANUAL',
    cuenta_codigo TEXT,
    cuenta_nombre TEXT,
    referencia TEXT,
    observacion TEXT,
    estado TEXT NOT NULL DEFAULT 'REGISTRADO',
    pago_original_id INTEGER,
    motivo_correccion TEXT,
    usuario_correccion TEXT,
    fecha_correccion TIMESTAMP,
    usuario TEXT,
    fecha_carga TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    fecha_anulacion TIMESTAMP,
    motivo_anulacion TEXT,
    fecha_actualizacion TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_iva_cierres_pagos_cierre
ON iva_cierres_pagos (cierre_id, estado);

CREATE INDEX IF NOT EXISTS idx_iva_cierres_pagos_periodo
ON iva_cierres_pagos (empresa_id, anio, mes, fecha_pago);

CREATE INDEX IF NOT EXISTS idx_iva_cierres_pagos_original
ON iva_cierres_pagos (empresa_id, pago_original_id, estado);

CREATE TABLE IF NOT EXISTS iva_cierres_asientos_propuestos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cierre_id INTEGER NOT NULL,
    pago_id INTEGER,
    empresa_id INTEGER NOT NULL,
    anio INTEGER NOT NULL,
    mes INTEGER NOT NULL,
    periodo TEXT NOT NULL,
    fecha TEXT NOT NULL,
    tipo_asiento TEXT NOT NULL,
    cuenta_codigo TEXT NOT NULL,
    cuenta_nombre TEXT NOT NULL,
    debe REAL NOT NULL DEFAULT 0,
    haber REAL NOT NULL DEFAULT 0,
    glosa TEXT,
    estado TEXT NOT NULL DEFAULT 'PROPUESTO',
    usuario TEXT,
    fecha_carga TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_iva_cierres_asientos_cierre
ON iva_cierres_asientos_propuestos (cierre_id, tipo_asiento, estado);

CREATE INDEX IF NOT EXISTS idx_iva_cierres_asientos_periodo
ON iva_cierres_asientos_propuestos (empresa_id, anio, mes, tipo_asiento);