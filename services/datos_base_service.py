from database import ejecutar_query


# ======================================================
# DATOS BASE DEL SISTEMA
# ======================================================
# IMPORTANTE:
# Este archivo NO borra datos.
# Solo crea estructuras faltantes e inserta datos base si no existen.
# Se puede ejecutar muchas veces sin perder información.


# ======================================================
# TIPOS DE COMPROBANTES ARCA / AFIP
# ======================================================

TIPOS_COMPROBANTES_BASE = [
    # Clase A
    ("1", "FACTURA A", 1),
    ("2", "NOTA DE DEBITO A", 1),
    ("3", "NOTA DE CREDITO A", -1),
    ("4", "RECIBO A", 1),
    ("5", "NOTA DE VENTA AL CONTADO A", 1),

    # Clase B
    ("6", "FACTURA B", 1),
    ("7", "NOTA DE DEBITO B", 1),
    ("8", "NOTA DE CREDITO B", -1),
    ("9", "RECIBO B", 1),
    ("10", "NOTA DE VENTA AL CONTADO B", 1),

    # Clase C
    ("11", "FACTURA C", 1),
    ("12", "NOTA DE DEBITO C", 1),
    ("13", "NOTA DE CREDITO C", -1),
    ("15", "RECIBO C", 1),

    # Exportación
    ("19", "FACTURA E", 1),
    ("20", "NOTA DE DEBITO E", 1),
    ("21", "NOTA DE CREDITO E", -1),

    # Clase M
    ("51", "FACTURA M", 1),
    ("52", "NOTA DE DEBITO M", 1),
    ("53", "NOTA DE CREDITO M", -1),
    ("54", "RECIBO M", 1),

    # Factura de Crédito Electrónica MiPyME A
    ("201", "FACTURA DE CREDITO ELECTRONICA MIPYMES A", 1),
    ("202", "NOTA DE DEBITO ELECTRONICA MIPYMES A", 1),
    ("203", "NOTA DE CREDITO ELECTRONICA MIPYMES A", -1),

    # Factura de Crédito Electrónica MiPyME B
    ("206", "FACTURA DE CREDITO ELECTRONICA MIPYMES B", 1),
    ("207", "NOTA DE DEBITO ELECTRONICA MIPYMES B", 1),
    ("208", "NOTA DE CREDITO ELECTRONICA MIPYMES B", -1),

    # Factura de Crédito Electrónica MiPyME C
    ("211", "FACTURA DE CREDITO ELECTRONICA MIPYMES C", 1),
    ("212", "NOTA DE DEBITO ELECTRONICA MIPYMES C", 1),
    ("213", "NOTA DE CREDITO ELECTRONICA MIPYMES C", -1),
]


# ======================================================
# PLAN DE CUENTAS BASE
# ======================================================

PLAN_CUENTAS_BASE = [
    # ACTIVO
    ("1", "ACTIVO", "N", "N", "A", "", 1, 10),

    ("1.1", "CAJA Y BANCOS", "N", "N", "A", "1", 2, 20),
    ("1.1.01", "CAJA", "S", "N", "A", "1.1", 3, 30),
    ("1.1.02", "BANCO CUENTA CORRIENTE", "S", "N", "A", "1.1", 3, 40),
    ("1.1.03", "MERCADO PAGO / BILLETERAS VIRTUALES", "S", "N", "A", "1.1", 3, 50),

    ("1.2", "CREDITOS POR VENTAS", "N", "N", "A", "1", 2, 60),
    ("1.2.01", "DEUDORES POR VENTAS", "S", "N", "A", "1.2", 3, 70),

    ("1.3", "CREDITOS FISCALES", "N", "N", "A", "1", 2, 80),
    ("1.3.01", "IVA CREDITO FISCAL", "S", "N", "A", "1.3", 3, 90),
    ("1.3.02", "PERCEPCIONES IVA", "S", "N", "A", "1.3", 3, 100),
    ("1.3.03", "PERCEPCIONES IIBB", "S", "N", "A", "1.3", 3, 110),
    ("1.3.04", "RETENCIONES IVA SUFRIDAS", "S", "N", "A", "1.3", 3, 120),
    ("1.3.05", "RETENCIONES IIBB SUFRIDAS", "S", "N", "A", "1.3", 3, 130),
    ("1.3.06", "PERCEPCIONES OTROS IMPUESTOS NACIONALES", "S", "N", "A", "1.3", 3, 140),
    ("1.3.07", "PERCEPCIONES MUNICIPALES", "S", "N", "A", "1.3", 3, 150),
    ("1.3.08", "RETENCIONES GANANCIAS SUFRIDAS", "S", "N", "A", "1.3", 3, 160),

    ("1.4", "BIENES DE USO", "N", "N", "A", "1", 2, 170),
    ("1.4.01", "RODADOS", "S", "S", "A", "1.4", 3, 180),
    ("1.4.02", "MUEBLES Y UTILES", "S", "S", "A", "1.4", 3, 190),
    ("1.4.03", "EQUIPOS DE COMPUTACION", "S", "S", "A", "1.4", 3, 200),
    ("1.4.04", "MAQUINARIAS", "S", "S", "A", "1.4", 3, 210),
    ("1.4.05", "INSTALACIONES", "S", "S", "A", "1.4", 3, 220),

    ("1.5", "BIENES DE CAMBIO", "N", "N", "A", "1", 2, 230),
    ("1.5.01", "MERCADERIAS", "S", "N", "A", "1.5", 3, 240),
    ("1.5.02", "MATERIAS PRIMAS", "S", "N", "A", "1.5", 3, 250),
    ("1.5.03", "INSUMOS PRODUCTIVOS", "S", "N", "A", "1.5", 3, 260),

    # PASIVO
    ("2", "PASIVO", "N", "N", "P", "", 1, 300),

    ("2.1", "DEUDAS COMERCIALES", "N", "N", "P", "2", 2, 310),
    ("2.1.01", "PROVEEDORES", "S", "N", "P", "2.1", 3, 320),

    ("2.2", "DEUDAS FISCALES", "N", "N", "P", "2", 2, 330),
    ("2.2.01", "IVA DEBITO FISCAL", "S", "N", "P", "2.2", 3, 340),
    ("2.2.02", "IVA A PAGAR", "S", "N", "P", "2.2", 3, 350),
    ("2.2.03", "IMPUESTOS INTERNOS A PAGAR", "S", "N", "P", "2.2", 3, 360),
    ("2.2.04", "OTROS TRIBUTOS A PAGAR", "S", "N", "P", "2.2", 3, 370),
    ("2.2.05", "IIBB A PAGAR", "S", "N", "P", "2.2", 3, 380),
    ("2.2.06", "GANANCIAS A PAGAR", "S", "N", "P", "2.2", 3, 390),

    ("2.3", "DEUDAS LABORALES", "N", "N", "P", "2", 2, 400),
    ("2.3.01", "SUELDOS A PAGAR", "S", "N", "P", "2.3", 3, 410),
    ("2.3.02", "CARGAS SOCIALES A PAGAR", "S", "N", "P", "2.3", 3, 420),
    ("2.3.03", "OBRA SOCIAL A PAGAR", "S", "N", "P", "2.3", 3, 430),
    ("2.3.04", "SINDICATO A PAGAR", "S", "N", "P", "2.3", 3, 440),
    ("2.3.05", "ART A PAGAR", "S", "N", "P", "2.3", 3, 450),

    # PATRIMONIO NETO
    ("3", "PATRIMONIO NETO", "N", "N", "PN", "", 1, 500),
    ("3.1", "CAPITAL Y RESULTADOS", "N", "N", "PN", "3", 2, 510),
    ("3.1.01", "CAPITAL SOCIAL", "S", "N", "PN", "3.1", 3, 520),
    ("3.1.02", "RESULTADOS NO ASIGNADOS", "S", "N", "PN", "3.1", 3, 530),

    # INGRESOS
    ("4", "INGRESOS", "N", "N", "R", "", 1, 600),
    ("4.1", "VENTAS Y SERVICIOS", "N", "N", "R", "4", 2, 610),
    ("4.1.01", "VENTAS", "S", "N", "R", "4.1", 3, 620),
    ("4.1.02", "SERVICIOS PRESTADOS", "S", "N", "R", "4.1", 3, 630),
    ("4.1.03", "VENTAS EXENTAS / NO GRAVADAS", "S", "N", "R", "4.1", 3, 640),

    # COSTOS
    ("5", "COSTOS", "N", "N", "R", "", 1, 700),
    ("5.1", "COSTOS OPERATIVOS", "N", "N", "R", "5", 2, 710),
    ("5.1.01", "COSTO DE MERCADERIAS VENDIDAS", "S", "N", "R", "5.1", 3, 720),

    # GASTOS
    ("6", "GASTOS", "N", "N", "R", "", 1, 800),
    ("6.1", "GASTOS GENERALES", "N", "N", "R", "6", 2, 810),
    ("6.1.01", "COMPRAS / MERCADERIAS", "S", "N", "R", "6.1", 3, 820),
    ("6.1.02", "SERVICIOS CONTRATADOS", "S", "N", "R", "6.1", 3, 830),
    ("6.1.03", "ALQUILERES", "S", "N", "R", "6.1", 3, 840),
    ("6.1.04", "HONORARIOS PROFESIONALES", "S", "N", "R", "6.1", 3, 850),
    ("6.1.05", "COMBUSTIBLES Y LUBRICANTES", "S", "N", "R", "6.1", 3, 860),
    ("6.1.06", "GASTOS BANCARIOS Y COMISIONES", "S", "N", "R", "6.1", 3, 870),
    ("6.1.07", "SEGUROS", "S", "N", "R", "6.1", 3, 880),
    ("6.1.08", "REPARACIONES Y MANTENIMIENTO", "S", "N", "R", "6.1", 3, 890),
    ("6.1.09", "PUBLICIDAD Y MARKETING", "S", "N", "R", "6.1", 3, 900),
    ("6.1.10", "TELEFONIA E INTERNET", "S", "N", "R", "6.1", 3, 910),
    ("6.1.11", "SERVICIOS PUBLICOS", "S", "N", "R", "6.1", 3, 920),
    ("6.1.12", "LIMPIEZA Y SEGURIDAD", "S", "N", "R", "6.1", 3, 930),
    ("6.1.13", "FLETES Y LOGISTICA", "S", "N", "R", "6.1", 3, 940),
    ("6.1.14", "VIATICOS Y MOVILIDAD", "S", "N", "R", "6.1", 3, 950),
    ("6.1.15", "IMPUESTOS, TASAS Y CONTRIBUCIONES", "S", "N", "R", "6.1", 3, 960),
    ("6.1.16", "INSUMOS VARIOS", "S", "N", "R", "6.1", 3, 970),
    ("6.1.17", "SUELDOS Y JORNALES", "S", "N", "R", "6.1", 3, 980),
    ("6.1.18", "CARGAS SOCIALES", "S", "N", "R", "6.1", 3, 990),
    ("6.1.19", "ART", "S", "N", "R", "6.1", 3, 1000),
    ("6.1.20", "IVA NO COMPUTABLE / MAYOR COSTO", "S", "N", "R", "6.1", 3, 1010),
    ("6.1.21", "IMPUESTOS INTERNOS NO RECUPERABLES", "S", "N", "R", "6.1", 3, 1020),
    ("6.1.22", "OTROS TRIBUTOS NO RECUPERABLES", "S", "N", "R", "6.1", 3, 1030),
    ("6.1.23", "GASTOS ACTIVIDAD EXENTA / NO GRAVADA", "S", "N", "R", "6.1", 3, 1040),
    ("6.1.24", "GASTOS COMUNES SUJETOS A PRORRATEO", "S", "N", "R", "6.1", 3, 1050),
    ("6.1.25", "LIBRERIA Y UTILES", "S", "N", "R", "6.1", 3, 1060),
    ("6.1.26", "OTROS GASTOS A REVISAR", "S", "N", "R", "6.1", 3, 1070),
]


# ======================================================
# CATEGORÍAS / DESTINOS DE COMPRA
# ======================================================
# tratamiento_iva:
# GRAVADO_100
# EXENTO_0
# PRORRATEO_GLOBAL
# APROPIACION_DIRECTA
# SEGUN_PORTAL_IVA
# SEGUN_CONFIG_PERIODO

CATEGORIAS_COMPRA_BASE = [
    ("MERCADERIAS PARA REVENTA", "1.5.01", "MERCADERIAS", "2.1.01", "PROVEEDORES", "BIENES_CAMBIO", "GRAVADO_100", None),
    ("MATERIAS PRIMAS", "1.5.02", "MATERIAS PRIMAS", "2.1.01", "PROVEEDORES", "BIENES_CAMBIO", "GRAVADO_100", None),
    ("INSUMOS PRODUCTIVOS", "1.5.03", "INSUMOS PRODUCTIVOS", "2.1.01", "PROVEEDORES", "BIENES_CAMBIO", "GRAVADO_100", None),

    ("SERVICIOS CONTRATADOS", "6.1.02", "SERVICIOS CONTRATADOS", "2.1.01", "PROVEEDORES", "SERVICIOS", "SEGUN_CONFIG_PERIODO", None),
    ("ALQUILERES Y EXPENSAS", "6.1.03", "ALQUILERES", "2.1.01", "PROVEEDORES", "SERVICIOS", "SEGUN_CONFIG_PERIODO", None),
    ("HONORARIOS PROFESIONALES", "6.1.04", "HONORARIOS PROFESIONALES", "2.1.01", "PROVEEDORES", "SERVICIOS", "SEGUN_CONFIG_PERIODO", None),
    ("COMBUSTIBLES Y LUBRICANTES", "6.1.05", "COMBUSTIBLES Y LUBRICANTES", "2.1.01", "PROVEEDORES", "SERVICIOS", "SEGUN_CONFIG_PERIODO", None),
    ("GASTOS BANCARIOS Y COMISIONES", "6.1.06", "GASTOS BANCARIOS Y COMISIONES", "2.1.01", "PROVEEDORES", "SERVICIOS", "SEGUN_CONFIG_PERIODO", None),
    ("SEGUROS", "6.1.07", "SEGUROS", "2.1.01", "PROVEEDORES", "SERVICIOS", "SEGUN_CONFIG_PERIODO", None),
    ("MANTENIMIENTO Y REPARACIONES", "6.1.08", "REPARACIONES Y MANTENIMIENTO", "2.1.01", "PROVEEDORES", "SERVICIOS", "SEGUN_CONFIG_PERIODO", None),
    ("PUBLICIDAD Y MARKETING", "6.1.09", "PUBLICIDAD Y MARKETING", "2.1.01", "PROVEEDORES", "SERVICIOS", "SEGUN_CONFIG_PERIODO", None),
    ("TELEFONIA E INTERNET", "6.1.10", "TELEFONIA E INTERNET", "2.1.01", "PROVEEDORES", "SERVICIOS", "SEGUN_CONFIG_PERIODO", None),
    ("SERVICIOS PUBLICOS", "6.1.11", "SERVICIOS PUBLICOS", "2.1.01", "PROVEEDORES", "SERVICIOS", "SEGUN_CONFIG_PERIODO", None),
    ("LIMPIEZA Y SEGURIDAD", "6.1.12", "LIMPIEZA Y SEGURIDAD", "2.1.01", "PROVEEDORES", "SERVICIOS", "SEGUN_CONFIG_PERIODO", None),
    ("FLETES Y LOGISTICA", "6.1.13", "FLETES Y LOGISTICA", "2.1.01", "PROVEEDORES", "SERVICIOS", "SEGUN_CONFIG_PERIODO", None),
    ("VIATICOS Y MOVILIDAD", "6.1.14", "VIATICOS Y MOVILIDAD", "2.1.01", "PROVEEDORES", "SERVICIOS", "SEGUN_CONFIG_PERIODO", None),
    ("IMPUESTOS, TASAS Y CONTRIBUCIONES", "6.1.15", "IMPUESTOS, TASAS Y CONTRIBUCIONES", "2.1.01", "PROVEEDORES", "TRIBUTOS", "EXENTO_0", None),
    ("INSUMOS VARIOS", "6.1.16", "INSUMOS VARIOS", "2.1.01", "PROVEEDORES", "BIENES", "SEGUN_CONFIG_PERIODO", None),
    ("LIBRERIA Y UTILES", "6.1.25", "LIBRERIA Y UTILES", "2.1.01", "PROVEEDORES", "BIENES", "SEGUN_CONFIG_PERIODO", None),

    ("SUELDOS Y JORNALES", "6.1.17", "SUELDOS Y JORNALES", "2.1.01", "PROVEEDORES", "LABORAL", "EXENTO_0", None),
    ("CARGAS SOCIALES", "6.1.18", "CARGAS SOCIALES", "2.1.01", "PROVEEDORES", "LABORAL", "EXENTO_0", None),
    ("ART", "6.1.19", "ART", "2.1.01", "PROVEEDORES", "LABORAL", "EXENTO_0", None),

    ("BIENES DE USO - RODADOS", "1.4.01", "RODADOS", "2.1.01", "PROVEEDORES", "BIENES_USO", "SEGUN_PORTAL_IVA", None),
    ("BIENES DE USO - MUEBLES Y UTILES", "1.4.02", "MUEBLES Y UTILES", "2.1.01", "PROVEEDORES", "BIENES_USO", "SEGUN_CONFIG_PERIODO", None),
    ("BIENES DE USO - EQUIPOS INFORMATICOS", "1.4.03", "EQUIPOS DE COMPUTACION", "2.1.01", "PROVEEDORES", "BIENES_USO", "SEGUN_CONFIG_PERIODO", None),
    ("BIENES DE USO - MAQUINARIAS", "1.4.04", "MAQUINARIAS", "2.1.01", "PROVEEDORES", "BIENES_USO", "SEGUN_CONFIG_PERIODO", None),
    ("BIENES DE USO - INSTALACIONES", "1.4.05", "INSTALACIONES", "2.1.01", "PROVEEDORES", "BIENES_USO", "SEGUN_CONFIG_PERIODO", None),

    ("COMPRAS ACTIVIDAD EXENTA / NO GRAVADA", "6.1.23", "GASTOS ACTIVIDAD EXENTA / NO GRAVADA", "2.1.01", "PROVEEDORES", "EXENTO_NO_GRAVADO", "EXENTO_0", None),
    ("GASTOS COMUNES SUJETOS A PRORRATEO", "6.1.24", "GASTOS COMUNES SUJETOS A PRORRATEO", "2.1.01", "PROVEEDORES", "PRORRATEO", "PRORRATEO_GLOBAL", None),
    ("GASTO CON APROPIACION DIRECTA 100%", "6.1.02", "SERVICIOS CONTRATADOS", "2.1.01", "PROVEEDORES", "APROPIACION_DIRECTA", "APROPIACION_DIRECTA", 100),
    ("GASTO CON APROPIACION DIRECTA 50%", "6.1.02", "SERVICIOS CONTRATADOS", "2.1.01", "PROVEEDORES", "APROPIACION_DIRECTA", "APROPIACION_DIRECTA", 50),

    ("IMPORTACION DE BIENES", "1.5.01", "MERCADERIAS", "2.1.01", "PROVEEDORES", "IMPORTACION", "SEGUN_PORTAL_IVA", None),
    ("IMPORTACION DE SERVICIOS", "6.1.02", "SERVICIOS CONTRATADOS", "2.1.01", "PROVEEDORES", "IMPORTACION", "SEGUN_PORTAL_IVA", None),
    ("BIENES USADOS / REGIMENES ESPECIALES", "6.1.26", "OTROS GASTOS A REVISAR", "2.1.01", "PROVEEDORES", "ESPECIAL", "SEGUN_PORTAL_IVA", None),
    ("OTROS GASTOS A REVISAR", "6.1.26", "OTROS GASTOS A REVISAR", "2.1.01", "PROVEEDORES", "REVISION", "SEGUN_PORTAL_IVA", None),

    # Compatibilidad con nombres viejos
    ("MERCADERIAS", "6.1.01", "COMPRAS / MERCADERIAS", "2.1.01", "PROVEEDORES", "BIENES", "GRAVADO_100", None),
    ("SERVICIOS", "6.1.02", "SERVICIOS CONTRATADOS", "2.1.01", "PROVEEDORES", "SERVICIOS", "SEGUN_CONFIG_PERIODO", None),
    ("ALQUILERES", "6.1.03", "ALQUILERES", "2.1.01", "PROVEEDORES", "SERVICIOS", "SEGUN_CONFIG_PERIODO", None),
    ("HONORARIOS", "6.1.04", "HONORARIOS PROFESIONALES", "2.1.01", "PROVEEDORES", "SERVICIOS", "SEGUN_CONFIG_PERIODO", None),
    ("COMBUSTIBLES", "6.1.05", "COMBUSTIBLES Y LUBRICANTES", "2.1.01", "PROVEEDORES", "SERVICIOS", "SEGUN_CONFIG_PERIODO", None),
    ("GASTOS BANCARIOS", "6.1.06", "GASTOS BANCARIOS Y COMISIONES", "2.1.01", "PROVEEDORES", "SERVICIOS", "SEGUN_CONFIG_PERIODO", None),
    ("SEGUROS", "6.1.07", "SEGUROS", "2.1.01", "PROVEEDORES", "SERVICIOS", "SEGUN_CONFIG_PERIODO", None),
    ("REPARACIONES", "6.1.08", "REPARACIONES Y MANTENIMIENTO", "2.1.01", "PROVEEDORES", "SERVICIOS", "SEGUN_CONFIG_PERIODO", None),
    ("PUBLICIDAD", "6.1.09", "PUBLICIDAD Y MARKETING", "2.1.01", "PROVEEDORES", "SERVICIOS", "SEGUN_CONFIG_PERIODO", None),
    ("TELEFONIA E INTERNET", "6.1.10", "TELEFONIA E INTERNET", "2.1.01", "PROVEEDORES", "SERVICIOS", "SEGUN_CONFIG_PERIODO", None),
    ("ENERGIA ELECTRICA", "6.1.11", "SERVICIOS PUBLICOS", "2.1.01", "PROVEEDORES", "SERVICIOS", "SEGUN_CONFIG_PERIODO", None),
    ("LIMPIEZA", "6.1.12", "LIMPIEZA Y SEGURIDAD", "2.1.01", "PROVEEDORES", "SERVICIOS", "SEGUN_CONFIG_PERIODO", None),
    ("FLETES", "6.1.13", "FLETES Y LOGISTICA", "2.1.01", "PROVEEDORES", "SERVICIOS", "SEGUN_CONFIG_PERIODO", None),
    ("VIATICOS", "6.1.14", "VIATICOS Y MOVILIDAD", "2.1.01", "PROVEEDORES", "SERVICIOS", "SEGUN_CONFIG_PERIODO", None),
    ("IMPUESTOS Y TASAS", "6.1.15", "IMPUESTOS, TASAS Y CONTRIBUCIONES", "2.1.01", "PROVEEDORES", "TRIBUTOS", "EXENTO_0", None),
    ("INSUMOS VARIOS", "6.1.16", "INSUMOS VARIOS", "2.1.01", "PROVEEDORES", "BIENES", "SEGUN_CONFIG_PERIODO", None),
    ("RODADOS", "1.4.01", "RODADOS", "2.1.01", "PROVEEDORES", "BIENES_USO", "SEGUN_PORTAL_IVA", None),
    ("MUEBLES Y UTILES", "1.4.02", "MUEBLES Y UTILES", "2.1.01", "PROVEEDORES", "BIENES_USO", "SEGUN_CONFIG_PERIODO", None),
    ("EQUIPOS DE COMPUTACION", "1.4.03", "EQUIPOS DE COMPUTACION", "2.1.01", "PROVEEDORES", "BIENES_USO", "SEGUN_CONFIG_PERIODO", None),
    ("MAQUINARIAS", "1.4.04", "MAQUINARIAS", "2.1.01", "PROVEEDORES", "BIENES_USO", "SEGUN_CONFIG_PERIODO", None),
]


# ======================================================
# CONCEPTOS FISCALES DE COMPRA
# ======================================================

CONCEPTOS_FISCALES_COMPRA_BASE = [
    ("IVA_CREDITO_FISCAL", "1.3.01", "IVA CREDITO FISCAL", "CREDITO_FISCAL"),
    ("IVA_NO_COMPUTABLE", "6.1.20", "IVA NO COMPUTABLE / MAYOR COSTO", "MAYOR_COSTO_GASTO"),
    ("PERCEPCION_IVA", "1.3.02", "PERCEPCIONES IVA", "PERCEPCION_COMPUTABLE"),
    ("PERCEPCION_IIBB", "1.3.03", "PERCEPCIONES IIBB", "PERCEPCION_COMPUTABLE"),
    ("PERCEPCION_OTROS_IMP_NAC", "1.3.06", "PERCEPCIONES OTROS IMPUESTOS NACIONALES", "PERCEPCION_COMPUTABLE"),
    ("PERCEPCION_GANANCIAS", "1.3.08", "RETENCIONES GANANCIAS SUFRIDAS", "PERCEPCION_COMPUTABLE"),
    ("PERCEPCION_MUNICIPAL", "1.3.07", "PERCEPCIONES MUNICIPALES", "PERCEPCION_COMPUTABLE"),
    ("IMPUESTOS_INTERNOS_NO_RECUPERABLES", "6.1.21", "IMPUESTOS INTERNOS NO RECUPERABLES", "MAYOR_COSTO_GASTO"),
    ("OTROS_TRIBUTOS_NO_RECUPERABLES", "6.1.22", "OTROS TRIBUTOS NO RECUPERABLES", "MAYOR_COSTO_GASTO"),
    ("NO_GRAVADO", "CUENTA_PRINCIPAL", "CUENTA_PRINCIPAL", "MAYOR_COSTO"),
    ("EXENTO", "CUENTA_PRINCIPAL", "CUENTA_PRINCIPAL", "MAYOR_COSTO"),

    # Compatibilidad con nombres viejos
    ("IVA CREDITO FISCAL", "1.3.01", "IVA CREDITO FISCAL", "CREDITO_FISCAL"),
    ("PERCEPCION IVA", "1.3.02", "PERCEPCIONES IVA", "PERCEPCION_COMPUTABLE"),
    ("PERCEPCION IIBB", "1.3.03", "PERCEPCIONES IIBB", "PERCEPCION_COMPUTABLE"),
    ("RETENCION IVA SUFRIDA", "1.3.04", "RETENCIONES IVA SUFRIDAS", "RETENCION_COMPUTABLE"),
    ("RETENCION IIBB SUFRIDA", "1.3.05", "RETENCIONES IIBB SUFRIDAS", "RETENCION_COMPUTABLE"),
    ("IMPUESTOS INTERNOS", "6.1.21", "IMPUESTOS INTERNOS NO RECUPERABLES", "MAYOR_COSTO_GASTO"),
    ("OTROS TRIBUTOS", "6.1.22", "OTROS TRIBUTOS NO RECUPERABLES", "MAYOR_COSTO_GASTO"),
]


# ======================================================
# ACTIVIDADES ARCA BASE
# ======================================================

ACTIVIDADES_ARCA_BASE = [
    ("COMERCIO_MINORISTA", "Comercio minorista", "Actividad general de venta al por menor."),
    ("COMERCIO_MAYORISTA", "Comercio mayorista", "Actividad general de venta al por mayor."),
    ("SERVICIOS_PROFESIONALES", "Servicios profesionales", "Servicios prestados por profesionales, estudios o consultores."),
    ("SERVICIOS_INFORMATICOS", "Servicios informáticos", "Software, soporte, desarrollo y servicios tecnológicos."),
    ("GASTRONOMIA", "Gastronomía", "Bares, restaurantes y comida preparada."),
    ("CONSTRUCCION", "Construcción", "Obras, instalaciones, reparaciones y mantenimiento."),
    ("TRANSPORTE", "Transporte y logística", "Transporte de cargas, pasajeros o servicios logísticos."),
    ("INDUSTRIA", "Industria / producción", "Fabricación, transformación o producción de bienes."),
    ("AGROPECUARIA", "Agropecuaria", "Actividades agropecuarias generales."),
    ("ALQUILERES", "Alquileres", "Locación de inmuebles, bienes o servicios relacionados."),
    ("SALUD", "Salud", "Servicios vinculados a salud humana."),
    ("EDUCACION", "Educación", "Enseñanza, capacitación o servicios educativos."),
    ("ACTIVIDAD_EXENTA", "Actividad exenta / no gravada", "Actividad con operaciones exentas o no gravadas en IVA."),
    ("MIXTA_GRAVADA_EXENTA", "Actividad mixta gravada y exenta", "Actividad que combina operaciones gravadas y exentas/no gravadas."),
]


# ======================================================
# FUNCIONES AUXILIARES
# ======================================================

def contar(tabla):
    try:
        df = ejecutar_query(f"SELECT COUNT(*) AS cantidad FROM {tabla}", fetch=True)
        return int(df.iloc[0]["cantidad"])
    except Exception:
        return 0


def existe_registro(tabla, columna, valor):
    try:
        df = ejecutar_query(
            f"SELECT COUNT(*) AS cantidad FROM {tabla} WHERE {columna} = ?",
            (valor,),
            fetch=True
        )
        return int(df.iloc[0]["cantidad"]) > 0
    except Exception:
        return False


def columnas_tabla(tabla):
    try:
        df = ejecutar_query(f"PRAGMA table_info({tabla})", fetch=True)
        return df["name"].tolist()
    except Exception:
        return []


def columna_existe(tabla, columna):
    return columna in columnas_tabla(tabla)


def agregar_columna_si_no_existe(tabla, columna, definicion):
    if not columna_existe(tabla, columna):
        try:
            ejecutar_query(f"ALTER TABLE {tabla} ADD COLUMN {columna} {definicion}")
        except Exception:
            pass


def asegurar_estructura_datos_base():
    """
    Asegura tablas y columnas necesarias para datos base.
    No borra datos.
    """

    ejecutar_query("""
        CREATE TABLE IF NOT EXISTS tipos_comprobantes (
            codigo TEXT PRIMARY KEY,
            descripcion TEXT,
            signo INTEGER
        )
    """)

    ejecutar_query("""
        CREATE TABLE IF NOT EXISTS plan_cuentas (
            codigo TEXT,
            nombre TEXT
        )
    """)

    ejecutar_query("""
        CREATE TABLE IF NOT EXISTS plan_cuentas_detallado (
            cuenta TEXT PRIMARY KEY,
            detalle TEXT,
            imputable TEXT,
            ajustable TEXT,
            tipo TEXT,
            madre TEXT,
            nivel INTEGER,
            orden INTEGER
        )
    """)

    ejecutar_query("""
        CREATE TABLE IF NOT EXISTS categorias_compra (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            categoria TEXT UNIQUE,
            cuenta_codigo TEXT,
            cuenta_nombre TEXT,
            cuenta_proveedor_codigo TEXT,
            cuenta_proveedor_nombre TEXT,
            tipo_categoria TEXT,
            activo INTEGER DEFAULT 1
        )
    """)

    agregar_columna_si_no_existe("categorias_compra", "empresa_id", "INTEGER DEFAULT 1")
    agregar_columna_si_no_existe("categorias_compra", "tratamiento_iva", "TEXT DEFAULT 'SEGUN_CONFIG_PERIODO'")
    agregar_columna_si_no_existe("categorias_compra", "porcentaje_iva_computable", "REAL DEFAULT NULL")

    ejecutar_query("""
        CREATE TABLE IF NOT EXISTS conceptos_fiscales_compra (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            concepto TEXT UNIQUE,
            cuenta_codigo TEXT,
            cuenta_nombre TEXT,
            tratamiento TEXT,
            activo INTEGER DEFAULT 1
        )
    """)

    agregar_columna_si_no_existe("conceptos_fiscales_compra", "empresa_id", "INTEGER DEFAULT 1")

    ejecutar_query("""
        CREATE TABLE IF NOT EXISTS actividades_arca (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            codigo TEXT UNIQUE,
            nombre TEXT,
            descripcion TEXT,
            activo INTEGER DEFAULT 1
        )
    """)


def obtener_estado_datos_base():
    asegurar_estructura_datos_base()

    return {
        "tipos_comprobantes": contar("tipos_comprobantes"),
        "plan_cuentas": contar("plan_cuentas"),
        "plan_cuentas_detallado": contar("plan_cuentas_detallado"),
        "categorias_compra": contar("categorias_compra"),
        "conceptos_fiscales_compra": contar("conceptos_fiscales_compra"),
        "actividades_arca": contar("actividades_arca"),
    }


# ======================================================
# CARGAS BASE
# ======================================================

def cargar_tipos_comprobantes_base():
    asegurar_estructura_datos_base()

    antes = contar("tipos_comprobantes")

    for codigo, descripcion, signo in TIPOS_COMPROBANTES_BASE:
        ejecutar_query("""
            INSERT OR IGNORE INTO tipos_comprobantes
            (codigo, descripcion, signo)
            VALUES (?, ?, ?)
        """, (codigo, descripcion, signo))

    despues = contar("tipos_comprobantes")
    return despues - antes


def cargar_plan_cuentas_base():
    asegurar_estructura_datos_base()

    antes = contar("plan_cuentas_detallado")

    for cuenta, detalle, imputable, ajustable, tipo, madre, nivel, orden in PLAN_CUENTAS_BASE:
        ejecutar_query("""
            INSERT OR IGNORE INTO plan_cuentas_detallado
            (cuenta, detalle, imputable, ajustable, tipo, madre, nivel, orden)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (cuenta, detalle, imputable, ajustable, tipo, madre, nivel, orden))

        if not existe_registro("plan_cuentas", "codigo", cuenta):
            ejecutar_query("""
                INSERT INTO plan_cuentas
                (codigo, nombre)
                VALUES (?, ?)
            """, (cuenta, detalle))

    despues = contar("plan_cuentas_detallado")
    return despues - antes


def cargar_categorias_compra_base():
    asegurar_estructura_datos_base()

    antes = contar("categorias_compra")

    for (
        categoria,
        cuenta_codigo,
        cuenta_nombre,
        cuenta_proveedor_codigo,
        cuenta_proveedor_nombre,
        tipo_categoria,
        tratamiento_iva,
        porcentaje_iva_computable
    ) in CATEGORIAS_COMPRA_BASE:

        ejecutar_query("""
            INSERT OR IGNORE INTO categorias_compra
            (
                categoria,
                cuenta_codigo,
                cuenta_nombre,
                cuenta_proveedor_codigo,
                cuenta_proveedor_nombre,
                tipo_categoria,
                tratamiento_iva,
                porcentaje_iva_computable,
                activo
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)
        """, (
            categoria,
            cuenta_codigo,
            cuenta_nombre,
            cuenta_proveedor_codigo,
            cuenta_proveedor_nombre,
            tipo_categoria,
            tratamiento_iva,
            porcentaje_iva_computable
        ))

        try:
            ejecutar_query("""
                UPDATE categorias_compra
                SET tratamiento_iva = ?,
                    porcentaje_iva_computable = COALESCE(porcentaje_iva_computable, ?)
                WHERE categoria = ?
                  AND (
                        tratamiento_iva IS NULL
                        OR TRIM(tratamiento_iva) = ''
                  )
            """, (
                tratamiento_iva,
                porcentaje_iva_computable,
                categoria
            ))
        except Exception:
            pass

    despues = contar("categorias_compra")
    return despues - antes


def cargar_conceptos_fiscales_compra_base():
    asegurar_estructura_datos_base()

    antes = contar("conceptos_fiscales_compra")

    for concepto, cuenta_codigo, cuenta_nombre, tratamiento in CONCEPTOS_FISCALES_COMPRA_BASE:
        ejecutar_query("""
            INSERT OR IGNORE INTO conceptos_fiscales_compra
            (concepto, cuenta_codigo, cuenta_nombre, tratamiento, activo)
            VALUES (?, ?, ?, ?, 1)
        """, (concepto, cuenta_codigo, cuenta_nombre, tratamiento))

    despues = contar("conceptos_fiscales_compra")
    return despues - antes


def cargar_actividades_arca_base():
    asegurar_estructura_datos_base()

    antes = contar("actividades_arca")

    for codigo, nombre, descripcion in ACTIVIDADES_ARCA_BASE:
        ejecutar_query("""
            INSERT OR IGNORE INTO actividades_arca
            (codigo, nombre, descripcion, activo)
            VALUES (?, ?, ?, 1)
        """, (codigo, nombre, descripcion))

    despues = contar("actividades_arca")
    return despues - antes


def inicializar_datos_base():
    """
    Inicialización segura.
    Puede ejecutarse muchas veces.
    Nunca borra datos cargados.
    """

    asegurar_estructura_datos_base()

    resultado = {}

    resultado["tipos_insertados"] = cargar_tipos_comprobantes_base()
    resultado["plan_insertado"] = cargar_plan_cuentas_base()
    resultado["categorias_insertadas"] = cargar_categorias_compra_base()
    resultado["conceptos_insertados"] = cargar_conceptos_fiscales_compra_base()
    resultado["actividades_insertadas"] = cargar_actividades_arca_base()
    resultado["estado_final"] = obtener_estado_datos_base()

    return resultado