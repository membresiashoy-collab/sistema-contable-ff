CREATE TABLE IF NOT EXISTS contabilidad_cuentas_comportamiento (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    empresa_id INTEGER,
    cuenta_id INTEGER,
    codigo_cuenta TEXT,
    comportamiento TEXT NOT NULL,
    activo INTEGER NOT NULL DEFAULT 1,
    origen TEXT NOT NULL DEFAULT 'MANUAL',
    observaciones TEXT,
    creado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    actualizado_en TEXT
);

CREATE INDEX IF NOT EXISTS idx_contabilidad_cuentas_comportamiento_empresa
ON contabilidad_cuentas_comportamiento(empresa_id, comportamiento, activo);

CREATE INDEX IF NOT EXISTS idx_contabilidad_cuentas_comportamiento_cuenta
ON contabilidad_cuentas_comportamiento(cuenta_id, codigo_cuenta);

CREATE TABLE IF NOT EXISTS contabilidad_origenes_economicos (
    codigo TEXT PRIMARY KEY,
    nombre TEXT NOT NULL,
    modulo TEXT,
    descripcion TEXT,
    activo INTEGER NOT NULL DEFAULT 1,
    creado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS contabilidad_diagnosticos_coherencia (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    empresa_id INTEGER,
    fecha_diagnostico TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    area TEXT NOT NULL,
    severidad TEXT NOT NULL,
    codigo TEXT NOT NULL,
    titulo TEXT NOT NULL,
    detalle TEXT,
    referencia_tipo TEXT,
    referencia_id TEXT,
    resuelto INTEGER NOT NULL DEFAULT 0,
    creado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_contabilidad_diagnosticos_empresa
ON contabilidad_diagnosticos_coherencia(empresa_id, resuelto, severidad, area);

INSERT OR IGNORE INTO contabilidad_origenes_economicos (codigo, nombre, modulo, descripcion, activo)
VALUES
('COBRANZA_CLIENTE', 'Cobranza de cliente', 'Cobranzas/Banco/Caja', 'Ingreso por cancelación total o parcial de deuda de cliente.', 1),
('PAGO_PROVEEDOR', 'Pago a proveedor', 'Pagos/Banco/Caja', 'Egreso por cancelación total o parcial de deuda con proveedor.', 1),
('APORTE_SOCIO', 'Aporte de socio', 'Capital/Banco/Caja', 'Ingreso patrimonial aportado por socio sin tratarlo como venta ni cobranza.', 1),
('INTEGRACION_CAPITAL', 'Integración de capital', 'Inicio contable/Capital/Banco/Caja', 'Ingreso que cancela capital suscripto pendiente de integración.', 1),
('PRESTAMO_SOCIO', 'Préstamo de socio', 'Banco/Caja', 'Ingreso de fondos de socio con naturaleza de pasivo.', 1),
('RETIRO_SOCIO', 'Retiro de socio', 'Banco/Caja', 'Egreso hacia socio que debe clasificarse contablemente.', 1),
('GASTO_MENOR', 'Gasto menor', 'Caja', 'Egreso operativo de caja pendiente de imputación contable específica.', 1),
('TRANSFERENCIA_INTERNA', 'Transferencia interna', 'Banco/Caja/Tesorería', 'Movimiento entre cuentas propias sin generar ingreso ni gasto.', 1),
('DEPOSITO_CAJA_A_BANCO', 'Depósito de caja a banco', 'Caja/Banco', 'Traslado de efectivo a una cuenta bancaria propia.', 1),
('RETIRO_BANCO_A_CAJA', 'Retiro desde banco a caja', 'Banco/Caja', 'Extracción de fondos bancarios para disponibilidad en caja.', 1),
('PAGO_FISCAL', 'Pago fiscal', 'Banco/Caja/IVA', 'Egreso aplicado a obligaciones impositivas.', 1),
('PAGO_SUELDO', 'Pago de sueldo', 'Sueldos/Banco/Caja', 'Cancelación de remuneraciones liquidadas externamente.', 1),
('PAGO_CARGAS_SOCIALES', 'Pago de cargas sociales', 'Sueldos/Banco/Caja', 'Cancelación de obligaciones laborales y de seguridad social.', 1),
('AJUSTE_CAJA', 'Ajuste de caja', 'Caja', 'Diferencia de arqueo o ajuste operativo con trazabilidad.', 1);
