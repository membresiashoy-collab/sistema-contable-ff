PRAGMA foreign_keys = ON;

BEGIN;

CREATE TABLE IF NOT EXISTS versiones_plan_cuentas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    version TEXT NOT NULL UNIQUE,
    descripcion TEXT,
    vigencia_desde TEXT,
    vigencia_hasta TEXT,
    estado TEXT NOT NULL DEFAULT 'BORRADOR',
    usuario_aprobacion TEXT,
    fecha_aprobacion TEXT,
    creado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    actualizado_en TEXT,
    CHECK (estado IN ('BORRADOR', 'VIGENTE', 'REEMPLAZADO', 'ANULADO'))
);

CREATE TABLE IF NOT EXISTS versiones_reglas_contables (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    version TEXT NOT NULL UNIQUE,
    descripcion TEXT,
    vigencia_desde TEXT,
    vigencia_hasta TEXT,
    estado TEXT NOT NULL DEFAULT 'BORRADOR',
    usuario_aprobacion TEXT,
    fecha_aprobacion TEXT,
    creado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    actualizado_en TEXT,
    CHECK (estado IN ('BORRADOR', 'VIGENTE', 'REEMPLAZADO', 'ANULADO'))
);

CREATE TABLE IF NOT EXISTS usos_operativos_contables (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo TEXT NOT NULL UNIQUE,
    nombre TEXT NOT NULL,
    descripcion TEXT,
    tipo_uso TEXT,
    modulo_sugerido TEXT,
    requiere_cuenta_imputable INTEGER NOT NULL DEFAULT 1,
    permite_multiples_cuentas_por_empresa INTEGER NOT NULL DEFAULT 0,
    visible_en_ui INTEGER NOT NULL DEFAULT 0,
    activo INTEGER NOT NULL DEFAULT 1,
    creado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    actualizado_en TEXT,
    CHECK (requiere_cuenta_imputable IN (0, 1)),
    CHECK (permite_multiples_cuentas_por_empresa IN (0, 1)),
    CHECK (visible_en_ui IN (0, 1)),
    CHECK (activo IN (0, 1))
);

CREATE TABLE IF NOT EXISTS plan_cuentas_maestro (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    version_plan_id INTEGER,
    codigo TEXT NOT NULL,
    nombre TEXT NOT NULL,
    elemento TEXT NOT NULL,
    clasificacion_corriente_no_corriente TEXT,
    rubro TEXT,
    cuenta TEXT,
    subcuenta TEXT,
    codigo_madre TEXT,
    nivel INTEGER NOT NULL DEFAULT 1,
    orden INTEGER NOT NULL DEFAULT 0,
    imputable INTEGER NOT NULL DEFAULT 0,
    requiere_auxiliar INTEGER NOT NULL DEFAULT 0,
    tipo_auxiliar TEXT,
    es_regularizadora INTEGER NOT NULL DEFAULT 0,
    cuenta_regularizada_codigo TEXT,
    tipo_regularizadora TEXT,
    saldo_normal TEXT NOT NULL DEFAULT 'NO_APLICA',
    significado_saldo_normal TEXT,
    permite_saldo_deudor INTEGER NOT NULL DEFAULT 0,
    significado_saldo_deudor TEXT,
    permite_saldo_acreedor INTEGER NOT NULL DEFAULT 0,
    significado_saldo_acreedor TEXT,
    alertar_saldo_invertido INTEGER NOT NULL DEFAULT 0,
    tratamiento_saldo_invertido TEXT,
    requiere_reclasificacion_saldo_invertido INTEGER NOT NULL DEFAULT 0,
    monetaria_no_monetaria TEXT,
    criterio_medicion TEXT,
    ajustable INTEGER NOT NULL DEFAULT 0,
    participa_recpam INTEGER NOT NULL DEFAULT 0,
    admite_moneda_extranjera INTEGER NOT NULL DEFAULT 0,
    requiere_tipo_cambio INTEGER NOT NULL DEFAULT 0,
    genera_diferencia_cambio INTEGER NOT NULL DEFAULT 0,
    es_cuenta_modelo INTEGER NOT NULL DEFAULT 0,
    permite_copiar_modelo INTEGER NOT NULL DEFAULT 0,
    uso_operativo_sistema TEXT,
    modulo_sugerido TEXT,
    presentacion_estado_contable TEXT,
    orden_presentacion INTEGER NOT NULL DEFAULT 0,
    cuando_debitar TEXT,
    cuando_acreditar TEXT,
    errores_frecuentes TEXT,
    observaciones TEXT,
    estado TEXT NOT NULL DEFAULT 'ACTIVA',
    vigencia_desde TEXT,
    vigencia_hasta TEXT,
    creado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    actualizado_en TEXT,
    FOREIGN KEY (version_plan_id) REFERENCES versiones_plan_cuentas(id),
    CHECK (imputable IN (0, 1)),
    CHECK (requiere_auxiliar IN (0, 1)),
    CHECK (es_regularizadora IN (0, 1)),
    CHECK (saldo_normal IN ('DEUDOR', 'ACREEDOR', 'SEGUN_NATURALEZA', 'NO_APLICA')),
    CHECK (permite_saldo_deudor IN (0, 1)),
    CHECK (permite_saldo_acreedor IN (0, 1)),
    CHECK (alertar_saldo_invertido IN (0, 1)),
    CHECK (requiere_reclasificacion_saldo_invertido IN (0, 1)),
    CHECK (ajustable IN (0, 1)),
    CHECK (participa_recpam IN (0, 1)),
    CHECK (admite_moneda_extranjera IN (0, 1)),
    CHECK (requiere_tipo_cambio IN (0, 1)),
    CHECK (genera_diferencia_cambio IN (0, 1)),
    CHECK (es_cuenta_modelo IN (0, 1)),
    CHECK (permite_copiar_modelo IN (0, 1)),
    CHECK (estado IN ('ACTIVA', 'INACTIVA', 'ANULADA', 'BORRADOR'))
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_plan_cuentas_maestro_version_codigo
ON plan_cuentas_maestro(version_plan_id, codigo);

CREATE INDEX IF NOT EXISTS ix_plan_cuentas_maestro_madre
ON plan_cuentas_maestro(version_plan_id, codigo_madre);

CREATE INDEX IF NOT EXISTS ix_plan_cuentas_maestro_uso_operativo
ON plan_cuentas_maestro(uso_operativo_sistema);

CREATE TABLE IF NOT EXISTS plan_cuentas_empresa (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    empresa_id INTEGER NOT NULL DEFAULT 1,
    cuenta_maestro_id INTEGER,
    codigo TEXT NOT NULL,
    nombre TEXT NOT NULL,
    codigo_madre TEXT,
    nivel INTEGER NOT NULL DEFAULT 1,
    orden INTEGER NOT NULL DEFAULT 0,
    imputable INTEGER NOT NULL DEFAULT 0,
    requiere_auxiliar INTEGER NOT NULL DEFAULT 0,
    tipo_auxiliar TEXT,
    ajustable INTEGER NOT NULL DEFAULT 0,
    estado TEXT NOT NULL DEFAULT 'ACTIVA',
    es_cuenta_modelo INTEGER NOT NULL DEFAULT 0,
    es_cuenta_especifica_empresa INTEGER NOT NULL DEFAULT 0,
    cuenta_modelo_origen_id INTEGER,
    banco_nombre TEXT,
    numero_cuenta TEXT,
    moneda TEXT,
    alias TEXT,
    cbu TEXT,
    uso_operativo_sistema TEXT,
    vigencia_desde TEXT,
    vigencia_hasta TEXT,
    motivo_estado TEXT,
    usuario_ultima_modificacion TEXT,
    fecha_ultima_modificacion TEXT,
    creado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    actualizado_en TEXT,
    FOREIGN KEY (cuenta_maestro_id) REFERENCES plan_cuentas_maestro(id),
    FOREIGN KEY (cuenta_modelo_origen_id) REFERENCES plan_cuentas_empresa(id),
    CHECK (imputable IN (0, 1)),
    CHECK (requiere_auxiliar IN (0, 1)),
    CHECK (ajustable IN (0, 1)),
    CHECK (estado IN ('ACTIVA', 'INACTIVA', 'ANULADA', 'BORRADOR')),
    CHECK (es_cuenta_modelo IN (0, 1)),
    CHECK (es_cuenta_especifica_empresa IN (0, 1))
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_plan_cuentas_empresa_empresa_codigo
ON plan_cuentas_empresa(empresa_id, codigo);

CREATE INDEX IF NOT EXISTS ix_plan_cuentas_empresa_maestro
ON plan_cuentas_empresa(cuenta_maestro_id);

CREATE INDEX IF NOT EXISTS ix_plan_cuentas_empresa_uso_operativo
ON plan_cuentas_empresa(empresa_id, uso_operativo_sistema, estado);

CREATE TABLE IF NOT EXISTS mapeos_contables_empresa (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    empresa_id INTEGER NOT NULL DEFAULT 1,
    uso_operativo_id INTEGER NOT NULL,
    cuenta_empresa_id INTEGER NOT NULL,
    modulo TEXT,
    evento_operativo TEXT,
    vigencia_desde TEXT,
    vigencia_hasta TEXT,
    estado TEXT NOT NULL DEFAULT 'ACTIVO',
    motivo TEXT,
    usuario TEXT,
    fecha_alta TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    fecha_baja TEXT,
    FOREIGN KEY (uso_operativo_id) REFERENCES usos_operativos_contables(id),
    FOREIGN KEY (cuenta_empresa_id) REFERENCES plan_cuentas_empresa(id),
    CHECK (estado IN ('ACTIVO', 'INACTIVO', 'ANULADO'))
);

CREATE INDEX IF NOT EXISTS ix_mapeos_contables_empresa_busqueda
ON mapeos_contables_empresa(empresa_id, uso_operativo_id, modulo, evento_operativo, estado);

CREATE TABLE IF NOT EXISTS eventos_operativos_contables (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo TEXT NOT NULL UNIQUE,
    nombre TEXT NOT NULL,
    modulo_origen TEXT NOT NULL,
    descripcion TEXT,
    genera_asiento INTEGER NOT NULL DEFAULT 1,
    requiere_revision INTEGER NOT NULL DEFAULT 0,
    activo INTEGER NOT NULL DEFAULT 1,
    creado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    actualizado_en TEXT,
    CHECK (genera_asiento IN (0, 1)),
    CHECK (requiere_revision IN (0, 1)),
    CHECK (activo IN (0, 1))
);

CREATE TABLE IF NOT EXISTS plantillas_asientos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    evento_operativo_id INTEGER NOT NULL,
    nombre TEXT NOT NULL,
    descripcion TEXT,
    version TEXT NOT NULL DEFAULT '1.0',
    vigencia_desde TEXT,
    vigencia_hasta TEXT,
    estado TEXT NOT NULL DEFAULT 'BORRADOR',
    requiere_revision INTEGER NOT NULL DEFAULT 1,
    creado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    actualizado_en TEXT,
    FOREIGN KEY (evento_operativo_id) REFERENCES eventos_operativos_contables(id),
    CHECK (estado IN ('BORRADOR', 'VIGENTE', 'REEMPLAZADA', 'ANULADA')),
    CHECK (requiere_revision IN (0, 1))
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_plantillas_asientos_evento_version
ON plantillas_asientos(evento_operativo_id, version);

CREATE TABLE IF NOT EXISTS plantillas_asientos_detalle (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    plantilla_id INTEGER NOT NULL,
    orden INTEGER NOT NULL DEFAULT 0,
    debe_haber TEXT NOT NULL,
    uso_operativo_id INTEGER,
    formula_importe TEXT NOT NULL,
    descripcion_linea TEXT,
    obligatorio INTEGER NOT NULL DEFAULT 1,
    permite_cuenta_principal INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (plantilla_id) REFERENCES plantillas_asientos(id),
    FOREIGN KEY (uso_operativo_id) REFERENCES usos_operativos_contables(id),
    CHECK (debe_haber IN ('DEBE', 'HABER')),
    CHECK (obligatorio IN (0, 1)),
    CHECK (permite_cuenta_principal IN (0, 1))
);

CREATE TABLE IF NOT EXISTS categorias_compra_config (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    empresa_id INTEGER NOT NULL DEFAULT 1,
    categoria TEXT NOT NULL,
    descripcion TEXT,
    tipo_categoria TEXT,
    tratamiento_contable TEXT,
    uso_operativo_principal_id INTEGER,
    uso_operativo_contrapartida_id INTEGER,
    cuenta_sugerida_id INTEGER,
    cuenta_contrapartida_sugerida_id INTEGER,
    requiere_auxiliar INTEGER NOT NULL DEFAULT 0,
    requiere_revision INTEGER NOT NULL DEFAULT 0,
    afecta_inventario INTEGER NOT NULL DEFAULT 0,
    afecta_bienes_uso INTEGER NOT NULL DEFAULT 0,
    afecta_resultado INTEGER NOT NULL DEFAULT 0,
    afecta_iva INTEGER NOT NULL DEFAULT 1,
    estado TEXT NOT NULL DEFAULT 'ACTIVA',
    vigencia_desde TEXT,
    vigencia_hasta TEXT,
    motivo_estado TEXT,
    usuario_ultima_modificacion TEXT,
    fecha_ultima_modificacion TEXT,
    creado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    actualizado_en TEXT,
    FOREIGN KEY (uso_operativo_principal_id) REFERENCES usos_operativos_contables(id),
    FOREIGN KEY (uso_operativo_contrapartida_id) REFERENCES usos_operativos_contables(id),
    FOREIGN KEY (cuenta_sugerida_id) REFERENCES plan_cuentas_empresa(id),
    FOREIGN KEY (cuenta_contrapartida_sugerida_id) REFERENCES plan_cuentas_empresa(id),
    CHECK (requiere_auxiliar IN (0, 1)),
    CHECK (requiere_revision IN (0, 1)),
    CHECK (afecta_inventario IN (0, 1)),
    CHECK (afecta_bienes_uso IN (0, 1)),
    CHECK (afecta_resultado IN (0, 1)),
    CHECK (afecta_iva IN (0, 1)),
    CHECK (estado IN ('ACTIVA', 'INACTIVA', 'ANULADA', 'BORRADOR'))
);

CREATE INDEX IF NOT EXISTS ix_categorias_compra_config_empresa_categoria
ON categorias_compra_config(empresa_id, categoria, estado);

CREATE TABLE IF NOT EXISTS conceptos_fiscales_compra_config (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    empresa_id INTEGER NOT NULL DEFAULT 1,
    concepto TEXT NOT NULL,
    descripcion TEXT,
    tratamiento_fiscal TEXT,
    uso_operativo_id INTEGER,
    cuenta_sugerida_id INTEGER,
    afecta_iva INTEGER NOT NULL DEFAULT 0,
    afecta_iibb INTEGER NOT NULL DEFAULT 0,
    afecta_ganancias INTEGER NOT NULL DEFAULT 0,
    computable INTEGER NOT NULL DEFAULT 0,
    mayor_costo INTEGER NOT NULL DEFAULT 0,
    informativo INTEGER NOT NULL DEFAULT 0,
    requiere_periodo_fiscal INTEGER NOT NULL DEFAULT 0,
    permite_diferir_periodo INTEGER NOT NULL DEFAULT 0,
    estado TEXT NOT NULL DEFAULT 'ACTIVO',
    vigencia_desde TEXT,
    vigencia_hasta TEXT,
    motivo_estado TEXT,
    usuario_ultima_modificacion TEXT,
    fecha_ultima_modificacion TEXT,
    creado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    actualizado_en TEXT,
    FOREIGN KEY (uso_operativo_id) REFERENCES usos_operativos_contables(id),
    FOREIGN KEY (cuenta_sugerida_id) REFERENCES plan_cuentas_empresa(id),
    CHECK (afecta_iva IN (0, 1)),
    CHECK (afecta_iibb IN (0, 1)),
    CHECK (afecta_ganancias IN (0, 1)),
    CHECK (computable IN (0, 1)),
    CHECK (mayor_costo IN (0, 1)),
    CHECK (informativo IN (0, 1)),
    CHECK (requiere_periodo_fiscal IN (0, 1)),
    CHECK (permite_diferir_periodo IN (0, 1)),
    CHECK (estado IN ('ACTIVO', 'INACTIVO', 'ANULADO', 'BORRADOR'))
);

CREATE INDEX IF NOT EXISTS ix_conceptos_fiscales_compra_config_empresa_concepto
ON conceptos_fiscales_compra_config(empresa_id, concepto, estado);

CREATE TABLE IF NOT EXISTS reglas_contables (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo TEXT NOT NULL UNIQUE,
    nombre TEXT NOT NULL,
    descripcion TEXT,
    tipo_regla TEXT,
    aplica_a_elemento TEXT,
    aplica_a_rubro TEXT,
    aplica_a_uso_operativo TEXT,
    severidad TEXT NOT NULL DEFAULT 'INFO',
    accion_sugerida TEXT,
    activo INTEGER NOT NULL DEFAULT 1,
    creado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    actualizado_en TEXT,
    CHECK (severidad IN ('INFO', 'ADVERTENCIA', 'ALTA', 'BLOQUEANTE')),
    CHECK (activo IN (0, 1))
);

CREATE TABLE IF NOT EXISTS reglas_fiscales (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo TEXT NOT NULL UNIQUE,
    impuesto TEXT,
    nombre TEXT NOT NULL,
    descripcion TEXT,
    tratamiento TEXT,
    computable INTEGER NOT NULL DEFAULT 0,
    mayor_costo INTEGER NOT NULL DEFAULT 0,
    informativo INTEGER NOT NULL DEFAULT 0,
    permite_diferir_periodo INTEGER NOT NULL DEFAULT 0,
    activo INTEGER NOT NULL DEFAULT 1,
    creado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    actualizado_en TEXT,
    CHECK (computable IN (0, 1)),
    CHECK (mayor_costo IN (0, 1)),
    CHECK (informativo IN (0, 1)),
    CHECK (permite_diferir_periodo IN (0, 1)),
    CHECK (activo IN (0, 1))
);

CREATE TABLE IF NOT EXISTS reglas_presentacion_contable (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo TEXT NOT NULL UNIQUE,
    nombre TEXT NOT NULL,
    estado_contable TEXT,
    seccion TEXT,
    orden INTEGER NOT NULL DEFAULT 0,
    criterio_presentacion TEXT,
    activo INTEGER NOT NULL DEFAULT 1,
    creado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    actualizado_en TEXT,
    CHECK (activo IN (0, 1))
);

CREATE TABLE IF NOT EXISTS auditoria_plan_cuentas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    empresa_id INTEGER,
    cuenta_empresa_id INTEGER,
    cuenta_maestro_id INTEGER,
    evento TEXT NOT NULL,
    valor_anterior TEXT,
    valor_nuevo TEXT,
    motivo TEXT,
    usuario TEXT,
    fecha_evento TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (cuenta_empresa_id) REFERENCES plan_cuentas_empresa(id),
    FOREIGN KEY (cuenta_maestro_id) REFERENCES plan_cuentas_maestro(id)
);

CREATE INDEX IF NOT EXISTS ix_auditoria_plan_cuentas_cuenta_empresa
ON auditoria_plan_cuentas(empresa_id, cuenta_empresa_id, fecha_evento);

CREATE TABLE IF NOT EXISTS auditoria_configuracion_contable (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    empresa_id INTEGER,
    entidad TEXT NOT NULL,
    entidad_id INTEGER,
    evento TEXT NOT NULL,
    valor_anterior TEXT,
    valor_nuevo TEXT,
    motivo TEXT,
    usuario TEXT,
    fecha_evento TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_auditoria_configuracion_contable_entidad
ON auditoria_configuracion_contable(empresa_id, entidad, entidad_id, fecha_evento);

CREATE TABLE IF NOT EXISTS mapeo_comportamiento_uso_operativo (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    comportamiento_contable TEXT NOT NULL UNIQUE,
    uso_operativo_codigo TEXT NOT NULL,
    observaciones TEXT,
    activo INTEGER NOT NULL DEFAULT 1,
    creado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (activo IN (0, 1))
);

INSERT OR IGNORE INTO versiones_plan_cuentas (version, descripcion, estado)
VALUES ('FF-2026-01', 'Plan de Cuentas Maestro FF base para migración configurable.', 'BORRADOR');

INSERT OR IGNORE INTO usos_operativos_contables (codigo, nombre, descripcion, tipo_uso, modulo_sugerido, requiere_cuenta_imputable, permite_multiples_cuentas_por_empresa, visible_en_ui)
VALUES
('CAJA_GENERAL', 'Caja general', 'Cuenta operativa para dinero físico disponible.', 'TESORERIA', 'Caja', 1, 1, 0),
('FONDO_FIJO', 'Fondo fijo', 'Cuenta operativa para fondos fijos asignados.', 'TESORERIA', 'Caja', 1, 1, 0),
('BANCO_CUENTA_CORRIENTE', 'Banco cuenta corriente', 'Cuenta bancaria operativa de tipo cuenta corriente.', 'TESORERIA', 'Banco/Caja', 1, 1, 0),
('BANCO_CAJA_AHORRO', 'Banco caja de ahorro', 'Cuenta bancaria operativa de tipo caja de ahorro.', 'TESORERIA', 'Banco/Caja', 1, 1, 0),
('BANCO_PLAZO_FIJO', 'Banco plazo fijo', 'Inversión bancaria de corto plazo.', 'INVERSIONES', 'Banco/Caja', 1, 1, 0),
('BILLETERA_VIRTUAL', 'Billetera virtual', 'Cuenta operativa para billeteras virtuales y plataformas de cobro.', 'TESORERIA', 'Banco/Caja', 1, 1, 0),
('VALORES_A_DEPOSITAR', 'Valores a depositar', 'Valores y cheques pendientes de depósito.', 'TESORERIA', 'Banco/Caja', 1, 1, 0),
('RECAUDACIONES_A_DEPOSITAR', 'Recaudaciones a depositar', 'Recaudaciones pendientes de depósito bancario.', 'TESORERIA', 'Banco/Caja', 1, 1, 0),
('CLIENTES_CC', 'Clientes cuenta corriente', 'Cuenta contable para créditos por ventas con clientes.', 'CUENTA_CORRIENTE', 'Ventas', 1, 0, 0),
('PROVEEDORES_CC', 'Proveedores cuenta corriente', 'Cuenta contable para deudas comerciales con proveedores.', 'CUENTA_CORRIENTE', 'Compras/Pagos', 1, 0, 0),
('ANTICIPOS_PROVEEDORES', 'Anticipos a proveedores', 'Importes adelantados a proveedores.', 'CUENTA_CORRIENTE', 'Compras/Pagos', 1, 0, 0),
('ANTICIPOS_CLIENTES', 'Anticipos de clientes', 'Importes recibidos de clientes antes de facturar o entregar.', 'CUENTA_CORRIENTE', 'Ventas/Cobranzas', 1, 0, 0),
('IVA_CREDITO_FISCAL', 'IVA crédito fiscal', 'Crédito fiscal computable por compras y gastos.', 'FISCAL', 'IVA', 1, 0, 0),
('IVA_DEBITO_FISCAL', 'IVA débito fiscal', 'Débito fiscal generado por ventas gravadas.', 'FISCAL', 'IVA', 1, 0, 0),
('IVA_SALDO_A_FAVOR', 'IVA saldo a favor', 'Saldo de IVA a favor de la empresa.', 'FISCAL', 'IVA', 1, 0, 0),
('IVA_SALDO_A_PAGAR', 'IVA saldo a pagar', 'Saldo de IVA a ingresar.', 'FISCAL', 'IVA', 1, 0, 0),
('IVA_NO_COMPUTABLE_MAYOR_COSTO', 'IVA no computable / mayor costo', 'IVA no computable tratado como mayor costo o gasto.', 'FISCAL', 'Compras/IVA', 1, 0, 0),
('PERCEPCION_IVA', 'Percepción IVA', 'Percepciones de IVA sufridas computables.', 'FISCAL', 'IVA', 1, 0, 0),
('RETENCION_IVA_SUFRIDA', 'Retención IVA sufrida', 'Retenciones de IVA sufridas computables.', 'FISCAL', 'IVA', 1, 0, 0),
('PERCEPCION_IIBB', 'Percepción IIBB', 'Percepciones de Ingresos Brutos sufridas.', 'FISCAL', 'Compras/IVA', 1, 0, 0),
('RETENCION_IIBB_SUFRIDA', 'Retención IIBB sufrida', 'Retenciones de Ingresos Brutos sufridas.', 'FISCAL', 'Compras/IVA', 1, 0, 0),
('PERCEPCION_GANANCIAS', 'Percepción Ganancias', 'Percepciones de Ganancias sufridas.', 'FISCAL', 'Compras', 1, 0, 0),
('RETENCION_GANANCIAS_SUFRIDA', 'Retención Ganancias sufrida', 'Retenciones de Ganancias sufridas.', 'FISCAL', 'Compras', 1, 0, 0),
('PERCEPCION_MUNICIPAL', 'Percepción municipal', 'Percepciones municipales sufridas.', 'FISCAL', 'Compras', 1, 0, 0),
('PERCEPCION_OTROS_NACIONALES', 'Percepción otros impuestos nacionales', 'Percepciones de otros impuestos nacionales.', 'FISCAL', 'Compras', 1, 0, 0),
('IIBB_A_PAGAR', 'IIBB a pagar', 'Deuda fiscal por Ingresos Brutos.', 'FISCAL', 'Impuestos', 1, 0, 0),
('GANANCIAS_A_PAGAR', 'Ganancias a pagar', 'Deuda fiscal por Impuesto a las Ganancias.', 'FISCAL', 'Impuestos', 1, 0, 0),
('SUELDOS_A_PAGAR', 'Sueldos a pagar', 'Deuda por remuneraciones devengadas pendientes de pago.', 'LABORAL', 'Sueldos', 1, 0, 0),
('CARGAS_SOCIALES_A_PAGAR', 'Cargas sociales a pagar', 'Deuda por cargas sociales pendientes de ingreso.', 'LABORAL', 'Sueldos', 1, 0, 0),
('OBRA_SOCIAL_A_PAGAR', 'Obra social a pagar', 'Deuda por obra social pendiente de ingreso.', 'LABORAL', 'Sueldos', 1, 0, 0),
('SINDICATO_A_PAGAR', 'Sindicato a pagar', 'Deuda sindical pendiente de ingreso.', 'LABORAL', 'Sueldos', 1, 0, 0),
('ART_A_PAGAR', 'ART a pagar', 'Deuda por ART pendiente de pago.', 'LABORAL', 'Sueldos', 1, 0, 0),
('VENTAS', 'Ventas', 'Ingresos ordinarios por ventas.', 'RESULTADO_POSITIVO', 'Ventas', 1, 0, 0),
('SERVICIOS_PRESTADOS', 'Servicios prestados', 'Ingresos por servicios prestados.', 'RESULTADO_POSITIVO', 'Ventas', 1, 0, 0),
('VENTAS_EXENTAS_NO_GRAVADAS', 'Ventas exentas / no gravadas', 'Ingresos por ventas exentas o no gravadas.', 'RESULTADO_POSITIVO', 'Ventas', 1, 0, 0),
('COMPRAS_MERCADERIAS', 'Compras / mercaderías', 'Compras imputadas como resultado o cuenta de movimiento.', 'RESULTADO_NEGATIVO', 'Compras', 1, 0, 0),
('MERCADERIAS_REVENTA', 'Mercaderías de reventa', 'Bienes de cambio para reventa.', 'ACTIVO', 'Compras', 1, 0, 0),
('MATERIAS_PRIMAS', 'Materias primas', 'Materias primas destinadas a producción.', 'ACTIVO', 'Compras', 1, 0, 0),
('INSUMOS_PRODUCTIVOS', 'Insumos productivos', 'Insumos vinculados a producción.', 'ACTIVO', 'Compras', 1, 0, 0),
('CMV', 'Costo de mercaderías vendidas', 'Costo de bienes vendidos.', 'RESULTADO_NEGATIVO', 'Ventas/Contabilidad', 1, 0, 0),
('GASTOS_BANCARIOS', 'Gastos bancarios y comisiones', 'Comisiones y gastos bancarios.', 'RESULTADO_NEGATIVO', 'Banco/Caja', 1, 0, 0),
('SERVICIOS_CONTRATADOS', 'Servicios contratados', 'Servicios recibidos de terceros.', 'RESULTADO_NEGATIVO', 'Compras', 1, 0, 0),
('ALQUILERES', 'Alquileres', 'Alquileres devengados o pagados según configuración.', 'RESULTADO_NEGATIVO', 'Compras', 1, 0, 0),
('HONORARIOS_PROFESIONALES', 'Honorarios profesionales', 'Honorarios profesionales devengados.', 'RESULTADO_NEGATIVO', 'Compras', 1, 0, 0),
('COMBUSTIBLES_LUBRICANTES', 'Combustibles y lubricantes', 'Gastos de combustibles y lubricantes.', 'RESULTADO_NEGATIVO', 'Compras', 1, 0, 0),
('SEGUROS', 'Seguros', 'Gastos de seguros.', 'RESULTADO_NEGATIVO', 'Compras', 1, 0, 0),
('REPARACIONES_MANTENIMIENTO', 'Reparaciones y mantenimiento', 'Gastos de reparación y mantenimiento.', 'RESULTADO_NEGATIVO', 'Compras', 1, 0, 0),
('PUBLICIDAD_MARKETING', 'Publicidad y marketing', 'Gastos de publicidad y marketing.', 'RESULTADO_NEGATIVO', 'Compras', 1, 0, 0),
('SERVICIOS_PUBLICOS', 'Servicios públicos', 'Energía, agua, gas y otros servicios públicos.', 'RESULTADO_NEGATIVO', 'Compras', 1, 0, 0),
('LIMPIEZA_SEGURIDAD', 'Limpieza y seguridad', 'Gastos de limpieza y seguridad.', 'RESULTADO_NEGATIVO', 'Compras', 1, 0, 0),
('FLETES_LOGISTICA', 'Fletes y logística', 'Gastos de fletes, acarreo y logística.', 'RESULTADO_NEGATIVO', 'Compras', 1, 0, 0),
('VIATICOS_MOVILIDAD', 'Viáticos y movilidad', 'Gastos de viáticos y movilidad.', 'RESULTADO_NEGATIVO', 'Compras', 1, 0, 0),
('SUELDOS_GASTO', 'Sueldos y jornales', 'Gastos por remuneraciones.', 'RESULTADO_NEGATIVO', 'Sueldos', 1, 0, 0),
('CARGAS_SOCIALES_GASTO', 'Cargas sociales', 'Gastos por cargas sociales.', 'RESULTADO_NEGATIVO', 'Sueldos', 1, 0, 0),
('ART_GASTO', 'ART gasto', 'Gasto por ART.', 'RESULTADO_NEGATIVO', 'Sueldos', 1, 0, 0),
('BIENES_USO_RODADOS', 'Rodados', 'Bienes de uso - Rodados.', 'ACTIVO', 'Compras', 1, 1, 0),
('BIENES_USO_MUEBLES_UTILES', 'Muebles y útiles', 'Bienes de uso - Muebles y útiles.', 'ACTIVO', 'Compras', 1, 1, 0),
('BIENES_USO_EQUIPOS_COMPUTACION', 'Equipos de computación', 'Bienes de uso - Equipos de computación.', 'ACTIVO', 'Compras', 1, 1, 0),
('BIENES_USO_MAQUINARIAS', 'Maquinarias', 'Bienes de uso - Maquinarias.', 'ACTIVO', 'Compras', 1, 1, 0),
('BIENES_USO_INSTALACIONES', 'Instalaciones', 'Bienes de uso - Instalaciones.', 'ACTIVO', 'Compras', 1, 1, 0),
('DIFERENCIA_CAMBIO_POSITIVA', 'Diferencia positiva de cambio', 'Resultado positivo por diferencia de cotización.', 'RESULTADO_FINANCIERO_TENENCIA', 'Contabilidad', 1, 0, 0),
('DIFERENCIA_CAMBIO_NEGATIVA', 'Diferencia negativa de cambio', 'Resultado negativo por diferencia de cotización.', 'RESULTADO_FINANCIERO_TENENCIA', 'Contabilidad', 1, 0, 0),
('RESULTADO_TENENCIA_POSITIVO', 'Resultado por tenencia positivo', 'Resultado positivo por tenencia.', 'RESULTADO_FINANCIERO_TENENCIA', 'Contabilidad', 1, 0, 0),
('RESULTADO_TENENCIA_NEGATIVO', 'Resultado por tenencia negativo', 'Resultado negativo por tenencia.', 'RESULTADO_FINANCIERO_TENENCIA', 'Contabilidad', 1, 0, 0),
('RECPAM', 'RECPAM', 'Resultado por exposición al cambio en el poder adquisitivo de la moneda.', 'RESULTADO_FINANCIERO_TENENCIA', 'Contabilidad', 1, 0, 0),
('FALTANTE_CAJA', 'Faltante de caja', 'Diferencia negativa de arqueo de caja.', 'RESULTADO_NEGATIVO', 'Caja', 1, 0, 0),
('SOBRANTE_CAJA', 'Sobrante de caja', 'Diferencia positiva de arqueo de caja.', 'RESULTADO_POSITIVO', 'Caja', 1, 0, 0),
('REDONDEO', 'Redondeo', 'Ajustes menores por redondeo.', 'RESULTADO', 'Contabilidad', 1, 0, 0),
('AJUSTE_TECNICO', 'Ajuste técnico', 'Ajustes técnicos controlados.', 'RESULTADO', 'Contabilidad', 1, 0, 0);

INSERT OR IGNORE INTO mapeo_comportamiento_uso_operativo (comportamiento_contable, uso_operativo_codigo, observaciones)
VALUES
('CAJA', 'CAJA_GENERAL', 'Migración desde comportamiento contable anterior.'),
('BANCO', 'BANCO_CUENTA_CORRIENTE', 'Migración desde comportamiento contable anterior.'),
('CLIENTES', 'CLIENTES_CC', 'Migración desde comportamiento contable anterior.'),
('PROVEEDORES', 'PROVEEDORES_CC', 'Migración desde comportamiento contable anterior.'),
('IVA_CREDITO', 'IVA_CREDITO_FISCAL', 'Migración desde comportamiento contable anterior.'),
('IVA_DEBITO', 'IVA_DEBITO_FISCAL', 'Migración desde comportamiento contable anterior.'),
('SUELDOS_A_PAGAR', 'SUELDOS_A_PAGAR', 'Migración desde comportamiento contable anterior.'),
('CARGAS_SOCIALES_A_PAGAR', 'CARGAS_SOCIALES_A_PAGAR', 'Migración desde comportamiento contable anterior.'),
('OBRA_SOCIAL_A_PAGAR', 'OBRA_SOCIAL_A_PAGAR', 'Migración desde comportamiento contable anterior.'),
('SINDICATO_A_PAGAR', 'SINDICATO_A_PAGAR', 'Migración desde comportamiento contable anterior.'),
('ART_A_PAGAR', 'ART_A_PAGAR', 'Migración desde comportamiento contable anterior.'),
('SUELDOS_GASTO', 'SUELDOS_GASTO', 'Migración desde comportamiento contable anterior.'),
('CARGAS_SOCIALES_GASTO', 'CARGAS_SOCIALES_GASTO', 'Migración desde comportamiento contable anterior.');

INSERT OR IGNORE INTO eventos_operativos_contables (codigo, nombre, modulo_origen, descripcion, genera_asiento, requiere_revision)
VALUES
('COMPRA_FACTURA_GRAVADA', 'Compra factura gravada', 'Compras', 'Registro de comprobante de compra gravado.', 1, 1),
('COMPRA_BIEN_USO', 'Compra de bien de uso', 'Compras', 'Registro de compra de bien de uso.', 1, 1),
('COMPRA_BIEN_CAMBIO', 'Compra de bien de cambio', 'Compras', 'Registro de compra de mercadería, materia prima o insumo productivo.', 1, 1),
('COMPRA_GASTO_NO_COMPUTABLE', 'Compra gasto no computable', 'Compras', 'Registro de gasto o impuesto no computable como crédito fiscal.', 1, 1),
('VENTA_FACTURA_GRAVADA', 'Venta factura gravada', 'Ventas', 'Registro de comprobante de venta gravado.', 1, 1),
('VENTA_FACTURA_EXENTA', 'Venta factura exenta o no gravada', 'Ventas', 'Registro de comprobante de venta exento o no gravado.', 1, 1),
('COBRANZA_CLIENTE', 'Cobranza a cliente', 'Cobranzas', 'Registro de cobranza a cliente.', 1, 1),
('PAGO_PROVEEDOR', 'Pago a proveedor', 'Pagos', 'Registro de pago a proveedor.', 1, 1),
('COMISION_BANCARIA', 'Comisión bancaria', 'Banco/Caja', 'Registro de gasto o comisión bancaria.', 1, 1),
('IVA_CIERRE_MENSUAL', 'Cierre mensual IVA', 'IVA', 'Asiento propuesto por cierre mensual de IVA.', 1, 1),
('IVA_PAGO', 'Pago de IVA', 'IVA', 'Registro del pago de IVA.', 1, 1),
('SUELDOS_DEVENGAMIENTO', 'Devengamiento de sueldos', 'Sueldos', 'Asiento propuesto de liquidación de sueldos.', 1, 1),
('PAGO_SUELDOS', 'Pago de sueldos', 'Sueldos', 'Pago de sueldos al personal.', 1, 1),
('ARQUEO_CAJA_SOBRANTE', 'Sobrante de caja', 'Caja', 'Diferencia positiva por arqueo de caja.', 1, 1),
('ARQUEO_CAJA_FALTANTE', 'Faltante de caja', 'Caja', 'Diferencia negativa por arqueo de caja.', 1, 1),
('DIFERENCIA_CAMBIO_POSITIVA', 'Diferencia de cambio positiva', 'Contabilidad', 'Resultado positivo por diferencia de cotización.', 1, 1),
('DIFERENCIA_CAMBIO_NEGATIVA', 'Diferencia de cambio negativa', 'Contabilidad', 'Resultado negativo por diferencia de cotización.', 1, 1),
('RECPAM_MENSUAL', 'RECPAM mensual', 'Contabilidad', 'Resultado por exposición al cambio en el poder adquisitivo de la moneda.', 1, 1);

INSERT OR IGNORE INTO reglas_contables (codigo, nombre, descripcion, tipo_regla, severidad, accion_sugerida)
VALUES
('BANCO_SALDO_ACREEDOR', 'Banco con saldo acreedor', 'Una cuenta bancaria de naturaleza deudora puede quedar acreedora por giro en descubierto, sobregiro, error o reclasificación pendiente.', 'SALDO_INVERTIDO', 'ADVERTENCIA', 'Revisar si corresponde reclasificar a pasivo financiero.'),
('PROVEEDORES_SALDO_DEUDOR', 'Proveedores con saldo deudor', 'La cuenta proveedores puede quedar deudora por anticipos, pagos en exceso o notas de crédito pendientes.', 'SALDO_INVERTIDO', 'ADVERTENCIA', 'Revisar si corresponde reclasificar a anticipos a proveedores u otros créditos.'),
('CLIENTES_SALDO_ACREEDOR', 'Clientes con saldo acreedor', 'La cuenta deudores por ventas puede quedar acreedora por anticipos, cobros en exceso o notas de crédito pendientes.', 'SALDO_INVERTIDO', 'ADVERTENCIA', 'Revisar si corresponde reclasificar a anticipos de clientes.'),
('IVA_CREDITO_SALDO_ACREEDOR', 'IVA crédito fiscal con saldo acreedor', 'El IVA crédito fiscal normalmente es deudor. Un saldo acreedor requiere revisión fiscal.', 'SALDO_INVERTIDO', 'ALTA', 'Revisar contra posición IVA, notas de crédito, rectificativas o ajustes.'),
('IVA_DEBITO_SALDO_DEUDOR', 'IVA débito fiscal con saldo deudor', 'El IVA débito fiscal normalmente es acreedor. Un saldo deudor requiere revisión fiscal.', 'SALDO_INVERTIDO', 'ALTA', 'Revisar contra posición IVA, notas de crédito, rectificativas o ajustes.'),
('REGULARIZADORA_SIN_CUENTA_REGULARIZADA', 'Regularizadora sin cuenta regularizada', 'Toda cuenta regularizadora debe informar qué cuenta o rubro regulariza.', 'ESTRUCTURA', 'BLOQUEANTE', 'Completar cuenta regularizada antes de aprobar el plan.'),
('CUENTA_IMPUTABLE_CON_HIJOS', 'Cuenta imputable con cuentas hijas', 'Una cuenta imputable no debería funcionar simultáneamente como cuenta madre.', 'ESTRUCTURA', 'BLOQUEANTE', 'Corregir jerarquía o imputabilidad.'),
('CUENTA_MADRE_USADA_EN_ASIENTOS', 'Cuenta madre usada en asientos', 'Las cuentas agrupadoras no deben utilizarse para registraciones operativas.', 'ESTRUCTURA', 'BLOQUEANTE', 'Reimputar a cuenta imputable.');

INSERT OR IGNORE INTO reglas_fiscales (codigo, impuesto, nombre, descripcion, tratamiento, computable, mayor_costo, informativo, permite_diferir_periodo)
VALUES
('IVA_CREDITO_FISCAL', 'IVA', 'IVA crédito fiscal', 'Crédito fiscal computable en la posición mensual de IVA.', 'CREDITO_FISCAL', 1, 0, 0, 0),
('IVA_NO_COMPUTABLE', 'IVA', 'IVA no computable', 'IVA no computable tratado como mayor costo o gasto.', 'MAYOR_COSTO_GASTO', 0, 1, 0, 0),
('PERCEPCION_IVA', 'IVA', 'Percepción IVA', 'Percepción de IVA sufrida computable según período fiscal.', 'PERCEPCION_COMPUTABLE', 1, 0, 0, 1),
('RETENCION_IVA_SUFRIDA', 'IVA', 'Retención IVA sufrida', 'Retención de IVA sufrida computable según período fiscal.', 'RETENCION_COMPUTABLE', 1, 0, 0, 1),
('PERCEPCION_IIBB', 'IIBB', 'Percepción IIBB', 'Percepción de Ingresos Brutos sufrida.', 'PERCEPCION_COMPUTABLE', 1, 0, 0, 1),
('RETENCION_IIBB_SUFRIDA', 'IIBB', 'Retención IIBB sufrida', 'Retención de Ingresos Brutos sufrida.', 'RETENCION_COMPUTABLE', 1, 0, 0, 1),
('IMPUESTOS_INTERNOS_NO_RECUPERABLES', 'OTROS', 'Impuestos internos no recuperables', 'Impuestos internos no recuperables tratados como mayor costo o gasto.', 'MAYOR_COSTO_GASTO', 0, 1, 0, 0),
('OTROS_TRIBUTOS_NO_RECUPERABLES', 'OTROS', 'Otros tributos no recuperables', 'Tributos no recuperables tratados como mayor costo o gasto.', 'MAYOR_COSTO_GASTO', 0, 1, 0, 0),
('EXENTO', 'IVA', 'Exento', 'Concepto exento que integra la cuenta principal o mayor costo según categoría.', 'MAYOR_COSTO', 0, 1, 0, 0),
('NO_GRAVADO', 'IVA', 'No gravado', 'Concepto no gravado que integra la cuenta principal o mayor costo según categoría.', 'MAYOR_COSTO', 0, 1, 0, 0);

INSERT OR IGNORE INTO reglas_presentacion_contable (codigo, nombre, estado_contable, seccion, orden, criterio_presentacion)
VALUES
('ACTIVO_CORRIENTE', 'Activo corriente', 'ESTADO_SITUACION_PATRIMONIAL', 'ACTIVO', 10, 'Presentar activos realizables o exigibles dentro del ciclo operativo o doce meses.'),
('ACTIVO_NO_CORRIENTE', 'Activo no corriente', 'ESTADO_SITUACION_PATRIMONIAL', 'ACTIVO', 20, 'Presentar activos no clasificados como corrientes.'),
('PASIVO_CORRIENTE', 'Pasivo corriente', 'ESTADO_SITUACION_PATRIMONIAL', 'PASIVO', 30, 'Presentar obligaciones exigibles dentro del ciclo operativo o doce meses.'),
('PASIVO_NO_CORRIENTE', 'Pasivo no corriente', 'ESTADO_SITUACION_PATRIMONIAL', 'PASIVO', 40, 'Presentar obligaciones no clasificadas como corrientes.'),
('PATRIMONIO_NETO', 'Patrimonio neto', 'ESTADO_SITUACION_PATRIMONIAL', 'PATRIMONIO_NETO', 50, 'Presentar aportes, reservas y resultados acumulados.'),
('RESULTADOS_ORDINARIOS', 'Resultados ordinarios', 'ESTADO_RESULTADOS', 'RESULTADOS', 60, 'Presentar resultados propios de la actividad ordinaria.'),
('RESULTADOS_FINANCIEROS_TENENCIA', 'Resultados financieros y por tenencia', 'ESTADO_RESULTADOS', 'RESULTADOS_FINANCIEROS_TENENCIA', 70, 'Presentar resultados financieros, diferencias de cambio y tenencia.'),
('RECPAM', 'RECPAM', 'ESTADO_RESULTADOS', 'RECPAM', 80, 'Presentar resultado por exposición al cambio en el poder adquisitivo de la moneda.');

COMMIT;