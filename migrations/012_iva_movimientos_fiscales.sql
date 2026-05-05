-- ======================================================
-- MIGRACIÓN 012 - IVA MOVIMIENTOS FISCALES
-- Sistema Contable FF
-- ======================================================
--
-- Objetivo:
-- Crear una estructura fiscal propia para conceptos de IVA
-- que no nacen directamente de ventas_comprobantes ni compras_comprobantes.
--
-- Esta tabla NO reemplaza Ventas.
-- Esta tabla NO reemplaza Compras.
-- Esta tabla NO reemplaza Banco/Tesorería.
--
-- Sirve para registrar conceptos fiscales adicionales como:
-- - IVA crédito fiscal por comisiones/gastos bancarios.
-- - Percepciones IVA sufridas.
-- - Retenciones IVA sufridas.
-- - Saldos técnicos anteriores.
-- - Saldos de libre disponibilidad aplicados.
-- - Pagos a cuenta.
-- - Ajustes técnicos controlados.
-- - Futuras liquidaciones de tarjetas/acreditadoras.
--
-- Regla de diseño:
-- Si el concepto nace del banco, se vinculará luego por origen_tabla/origen_id,
-- pero el extracto bancario no debe cargarse como compra manual.

CREATE TABLE IF NOT EXISTS iva_movimientos_fiscales (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    empresa_id INTEGER NOT NULL DEFAULT 1,

    anio INTEGER NOT NULL,
    mes INTEGER NOT NULL,
    periodo TEXT,

    fecha TEXT NOT NULL,

    origen TEXT NOT NULL DEFAULT 'MANUAL',
    tipo_concepto TEXT NOT NULL,

    descripcion TEXT NOT NULL,

    contraparte TEXT,
    cuit TEXT,

    comprobante_codigo TEXT,
    comprobante_tipo TEXT,
    punto_venta TEXT,
    numero TEXT,

    neto_gravado REAL NOT NULL DEFAULT 0,
    iva_debito REAL NOT NULL DEFAULT 0,
    credito_fiscal_computable REAL NOT NULL DEFAULT 0,
    iva_no_computable REAL NOT NULL DEFAULT 0,

    percepcion_iva REAL NOT NULL DEFAULT 0,
    retencion_iva REAL NOT NULL DEFAULT 0,
    percepcion_iibb_informativa REAL NOT NULL DEFAULT 0,

    saldo_tecnico_anterior REAL NOT NULL DEFAULT 0,
    saldo_libre_disponibilidad REAL NOT NULL DEFAULT 0,
    pago_a_cuenta REAL NOT NULL DEFAULT 0,

    otros_tributos REAL NOT NULL DEFAULT 0,
    total REAL NOT NULL DEFAULT 0,

    estado TEXT NOT NULL DEFAULT 'CONFIRMADO',

    origen_tabla TEXT,
    origen_id INTEGER,

    observacion TEXT,
    usuario TEXT,

    fecha_carga TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    fecha_confirmacion TIMESTAMP,
    fecha_anulacion TIMESTAMP,
    motivo_anulacion TEXT,

    CHECK (mes BETWEEN 1 AND 12),
    CHECK (estado IN ('BORRADOR', 'CONFIRMADO', 'ANULADO')),
    CHECK (
        origen IN (
            'MANUAL',
            'BANCO',
            'TARJETA',
            'ACREDITADORA',
            'SALDO_ANTERIOR',
            'RETENCION',
            'PERCEPCION',
            'AJUSTE_TECNICO',
            'OTRO'
        )
    ),
    CHECK (
        tipo_concepto IN (
            'IVA_DEBITO',
            'IVA_CREDITO',
            'IVA_NO_COMPUTABLE',
            'PERCEPCION_IVA',
            'RETENCION_IVA',
            'PERCEPCION_IIBB_INFORMATIVA',
            'SALDO_TECNICO_ANTERIOR',
            'SALDO_LIBRE_DISPONIBILIDAD',
            'PAGO_A_CUENTA',
            'AJUSTE_SALDO',
            'OTRO'
        )
    )
);

CREATE INDEX IF NOT EXISTS idx_iva_mov_fiscales_empresa_periodo
ON iva_movimientos_fiscales (empresa_id, anio, mes);

CREATE INDEX IF NOT EXISTS idx_iva_mov_fiscales_estado
ON iva_movimientos_fiscales (estado);

CREATE INDEX IF NOT EXISTS idx_iva_mov_fiscales_origen
ON iva_movimientos_fiscales (origen);

CREATE INDEX IF NOT EXISTS idx_iva_mov_fiscales_tipo
ON iva_movimientos_fiscales (tipo_concepto);

CREATE INDEX IF NOT EXISTS idx_iva_mov_fiscales_origen_vinculo
ON iva_movimientos_fiscales (origen_tabla, origen_id);

CREATE INDEX IF NOT EXISTS idx_iva_mov_fiscales_cuit
ON iva_movimientos_fiscales (cuit);


-- ======================================================
-- AUDITORÍA ESPECÍFICA DE MOVIMIENTOS FISCALES IVA
-- ======================================================
--
-- Esta tabla registra eventos relevantes:
-- - creación
-- - confirmación
-- - anulación
-- - edición futura controlada
--
-- No reemplaza auditoria_cambios general del sistema.
-- Es trazabilidad funcional específica del módulo IVA.

CREATE TABLE IF NOT EXISTS iva_movimientos_fiscales_eventos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    movimiento_id INTEGER,
    empresa_id INTEGER NOT NULL DEFAULT 1,

    evento TEXT NOT NULL,
    detalle TEXT,

    usuario TEXT,
    fecha_evento TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (movimiento_id)
        REFERENCES iva_movimientos_fiscales(id)
        ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_iva_mov_fiscales_eventos_movimiento
ON iva_movimientos_fiscales_eventos (movimiento_id);

CREATE INDEX IF NOT EXISTS idx_iva_mov_fiscales_eventos_empresa
ON iva_movimientos_fiscales_eventos (empresa_id);

CREATE INDEX IF NOT EXISTS idx_iva_mov_fiscales_eventos_fecha
ON iva_movimientos_fiscales_eventos (fecha_evento);