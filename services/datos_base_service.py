from database import ejecutar_query


# ======================================================
# DATOS BASE DEL SISTEMA
# ======================================================

TIPOS_COMPROBANTES_BASE = [
    ("1", "FACTURA A", 1),
    ("2", "NOTA DE DEBITO A", 1),
    ("3", "NOTA DE CREDITO A", -1),

    ("6", "FACTURA B", 1),
    ("7", "NOTA DE DEBITO B", 1),
    ("8", "NOTA DE CREDITO B", -1),

    ("11", "FACTURA C", 1),
    ("12", "NOTA DE DEBITO C", 1),
    ("13", "NOTA DE CREDITO C", -1),

    ("51", "FACTURA M", 1),
    ("52", "NOTA DE DEBITO M", 1),
    ("53", "NOTA DE CREDITO M", -1),

    ("201", "FACTURA DE CREDITO ELECTRONICA MIPYMES A", 1),
    ("202", "NOTA DE DEBITO ELECTRONICA MIPYMES A", 1),
    ("203", "NOTA DE CREDITO ELECTRONICA MIPYMES A", -1),

    ("206", "FACTURA DE CREDITO ELECTRONICA MIPYMES B", 1),
    ("207", "NOTA DE DEBITO ELECTRONICA MIPYMES B", 1),
    ("208", "NOTA DE CREDITO ELECTRONICA MIPYMES B", -1),
]


PLAN_CUENTAS_BASE = [
    ("1", "ACTIVO", "N", "N", "A", "", 1, 10),
    ("1.1", "CAJA Y BANCOS", "N", "N", "A", "1", 2, 20),
    ("1.1.01", "CAJA", "S", "N", "A", "1.1", 3, 30),
    ("1.1.02", "BANCO CUENTA CORRIENTE", "S", "N", "A", "1.1", 3, 40),

    ("1.2", "CREDITOS POR VENTAS", "N", "N", "A", "1", 2, 50),
    ("1.2.01", "DEUDORES POR VENTAS", "S", "N", "A", "1.2", 3, 60),

    ("1.3", "CREDITOS FISCALES", "N", "N", "A", "1", 2, 70),
    ("1.3.01", "IVA CREDITO FISCAL", "S", "N", "A", "1.3", 3, 80),
    ("1.3.02", "PERCEPCIONES IVA", "S", "N", "A", "1.3", 3, 90),
    ("1.3.03", "PERCEPCIONES IIBB", "S", "N", "A", "1.3", 3, 100),
    ("1.3.04", "RETENCIONES IVA SUFRIDAS", "S", "N", "A", "1.3", 3, 110),
    ("1.3.05", "RETENCIONES IIBB SUFRIDAS", "S", "N", "A", "1.3", 3, 120),

    ("1.4", "BIENES DE USO", "N", "N", "A", "1", 2, 130),
    ("1.4.01", "RODADOS", "S", "S", "A", "1.4", 3, 140),
    ("1.4.02", "MUEBLES Y UTILES", "S", "S", "A", "1.4", 3, 150),
    ("1.4.03", "EQUIPOS DE COMPUTACION", "S", "S", "A", "1.4", 3, 160),
    ("1.4.04", "MAQUINARIAS", "S", "S", "A", "1.4", 3, 170),

    ("1.5", "BIENES DE CAMBIO", "N", "N", "A", "1", 2, 180),
    ("1.5.01", "MERCADERIAS", "S", "N", "A", "1.5", 3, 190),

    ("2", "PASIVO", "N", "N", "P", "", 1, 200),
    ("2.1", "DEUDAS COMERCIALES", "N", "N", "P", "2", 2, 210),
    ("2.1.01", "PROVEEDORES", "S", "N", "P", "2.1", 3, 220),

    ("2.2", "DEUDAS FISCALES", "N", "N", "P", "2", 2, 230),
    ("2.2.01", "IVA DEBITO FISCAL", "S", "N", "P", "2.2", 3, 240),
    ("2.2.02", "IVA A PAGAR", "S", "N", "P", "2.2", 3, 250),
    ("2.2.03", "IMPUESTOS INTERNOS A PAGAR", "S", "N", "P", "2.2", 3, 260),
    ("2.2.04", "OTROS TRIBUTOS A PAGAR", "S", "N", "P", "2.2", 3, 270),

    ("2.3", "DEUDAS LABORALES", "N", "N", "P", "2", 2, 280),
    ("2.3.01", "SUELDOS A PAGAR", "S", "N", "P", "2.3", 3, 290),
    ("2.3.02", "CARGAS SOCIALES A PAGAR", "S", "N", "P", "2.3", 3, 300),
    ("2.3.03", "OBRA SOCIAL A PAGAR", "S", "N", "P", "2.3", 3, 310),
    ("2.3.04", "SINDICATO A PAGAR", "S", "N", "P", "2.3", 3, 320),

    ("3", "PATRIMONIO NETO", "N", "N", "PN", "", 1, 330),
    ("3.1.01", "CAPITAL SOCIAL", "S", "N", "PN", "3", 2, 340),
    ("3.1.02", "RESULTADOS NO ASIGNADOS", "S", "N", "PN", "3", 2, 350),

    ("4", "INGRESOS", "N", "N", "R", "", 1, 360),
    ("4.1.01", "VENTAS", "S", "N", "R", "4", 2, 370),

    ("5", "COSTOS", "N", "N", "R", "", 1, 380),
    ("5.1.01", "COSTO DE MERCADERIAS VENDIDAS", "S", "N", "R", "5", 2, 390),

    ("6", "GASTOS", "N", "N", "R", "", 1, 400),
    ("6.1.01", "COMPRAS / MERCADERIAS", "S", "N", "R", "6", 2, 410),
    ("6.1.02", "SERVICIOS CONTRATADOS", "S", "N", "R", "6", 2, 420),
    ("6.1.03", "ALQUILERES", "S", "N", "R", "6", 2, 430),
    ("6.1.04", "HONORARIOS PROFESIONALES", "S", "N", "R", "6", 2, 440),
    ("6.1.05", "COMBUSTIBLES", "S", "N", "R", "6", 2, 450),
    ("6.1.06", "GASTOS BANCARIOS", "S", "N", "R", "6", 2, 460),
    ("6.1.07", "SEGUROS", "S", "N", "R", "6", 2, 470),
    ("6.1.08", "REPARACIONES Y MANTENIMIENTO", "S", "N", "R", "6", 2, 480),
    ("6.1.09", "PUBLICIDAD Y PROPAGANDA", "S", "N", "R", "6", 2, 490),
    ("6.1.10", "TELEFONIA E INTERNET", "S", "N", "R", "6", 2, 500),
    ("6.1.11", "ENERGIA ELECTRICA", "S", "N", "R", "6", 2, 510),
    ("6.1.12", "LIMPIEZA", "S", "N", "R", "6", 2, 520),
    ("6.1.13", "FLETES", "S", "N", "R", "6", 2, 530),
    ("6.1.14", "VIATICOS", "S", "N", "R", "6", 2, 540),
    ("6.1.15", "IMPUESTOS Y TASAS", "S", "N", "R", "6", 2, 550),
    ("6.1.16", "INSUMOS VARIOS", "S", "N", "R", "6", 2, 560),
    ("6.1.17", "SUELDOS Y JORNALES", "S", "N", "R", "6", 2, 570),
    ("6.1.18", "CARGAS SOCIALES", "S", "N", "R", "6", 2, 580),
    ("6.1.19", "ART", "S", "N", "R", "6", 2, 590),
]


CATEGORIAS_COMPRA_BASE = [
    ("MERCADERIAS", "6.1.01", "COMPRAS / MERCADERIAS", "2.1.01", "PROVEEDORES", "BIENES"),
    ("SERVICIOS", "6.1.02", "SERVICIOS CONTRATADOS", "2.1.01", "PROVEEDORES", "SERVICIOS"),
    ("ALQUILERES", "6.1.03", "ALQUILERES", "2.1.01", "PROVEEDORES", "SERVICIOS"),
    ("HONORARIOS", "6.1.04", "HONORARIOS PROFESIONALES", "2.1.01", "PROVEEDORES", "SERVICIOS"),
    ("COMBUSTIBLES", "6.1.05", "COMBUSTIBLES", "2.1.01", "PROVEEDORES", "SERVICIOS"),
    ("GASTOS BANCARIOS", "6.1.06", "GASTOS BANCARIOS", "2.1.01", "PROVEEDORES", "SERVICIOS"),
    ("SEGUROS", "6.1.07", "SEGUROS", "2.1.01", "PROVEEDORES", "SERVICIOS"),
    ("REPARACIONES", "6.1.08", "REPARACIONES Y MANTENIMIENTO", "2.1.01", "PROVEEDORES", "SERVICIOS"),
    ("PUBLICIDAD", "6.1.09", "PUBLICIDAD Y PROPAGANDA", "2.1.01", "PROVEEDORES", "SERVICIOS"),
    ("TELEFONIA E INTERNET", "6.1.10", "TELEFONIA E INTERNET", "2.1.01", "PROVEEDORES", "SERVICIOS"),
    ("ENERGIA ELECTRICA", "6.1.11", "ENERGIA ELECTRICA", "2.1.01", "PROVEEDORES", "SERVICIOS"),
    ("LIMPIEZA", "6.1.12", "LIMPIEZA", "2.1.01", "PROVEEDORES", "SERVICIOS"),
    ("FLETES", "6.1.13", "FLETES", "2.1.01", "PROVEEDORES", "SERVICIOS"),
    ("VIATICOS", "6.1.14", "VIATICOS", "2.1.01", "PROVEEDORES", "SERVICIOS"),
    ("IMPUESTOS Y TASAS", "6.1.15", "IMPUESTOS Y TASAS", "2.1.01", "PROVEEDORES", "SERVICIOS"),
    ("INSUMOS VARIOS", "6.1.16", "INSUMOS VARIOS", "2.1.01", "PROVEEDORES", "BIENES"),

    ("RODADOS", "1.4.01", "RODADOS", "2.1.01", "PROVEEDORES", "BIENES_USO"),
    ("MUEBLES Y UTILES", "1.4.02", "MUEBLES Y UTILES", "2.1.01", "PROVEEDORES", "BIENES_USO"),
    ("EQUIPOS DE COMPUTACION", "1.4.03", "EQUIPOS DE COMPUTACION", "2.1.01", "PROVEEDORES", "BIENES_USO"),
    ("MAQUINARIAS", "1.4.04", "MAQUINARIAS", "2.1.01", "PROVEEDORES", "BIENES_USO"),
]


CONCEPTOS_FISCALES_COMPRA_BASE = [
    ("IVA CREDITO FISCAL", "1.3.01", "IVA CREDITO FISCAL", "CREDITO_FISCAL"),
    ("PERCEPCION IVA", "1.3.02", "PERCEPCIONES IVA", "PERCEPCION_IVA"),
    ("PERCEPCION IIBB", "1.3.03", "PERCEPCIONES IIBB", "PERCEPCION_IIBB"),
    ("RETENCION IVA SUFRIDA", "1.3.04", "RETENCIONES IVA SUFRIDAS", "RETENCION_IVA"),
    ("RETENCION IIBB SUFRIDA", "1.3.05", "RETENCIONES IIBB SUFRIDAS", "RETENCION_IIBB"),
    ("IMPUESTOS INTERNOS", "2.2.03", "IMPUESTOS INTERNOS A PAGAR", "OTRO_TRIBUTO"),
    ("OTROS TRIBUTOS", "2.2.04", "OTROS TRIBUTOS A PAGAR", "OTRO_TRIBUTO"),
    ("NO GRAVADO", "6.1.16", "INSUMOS VARIOS", "NO_GRAVADO"),
    ("EXENTO", "6.1.16", "INSUMOS VARIOS", "EXENTO"),
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


def obtener_estado_datos_base():
    return {
        "tipos_comprobantes": contar("tipos_comprobantes"),
        "plan_cuentas": contar("plan_cuentas"),
        "plan_cuentas_detallado": contar("plan_cuentas_detallado"),
        "categorias_compra": contar("categorias_compra"),
        "conceptos_fiscales_compra": contar("conceptos_fiscales_compra"),
    }


# ======================================================
# CARGAS BASE
# ======================================================

def cargar_tipos_comprobantes_base():
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
    antes = contar("categorias_compra")

    for categoria, cuenta_codigo, cuenta_nombre, cuenta_proveedor_codigo, cuenta_proveedor_nombre, tipo_categoria in CATEGORIAS_COMPRA_BASE:
        ejecutar_query("""
            INSERT OR IGNORE INTO categorias_compra
            (categoria, cuenta_codigo, cuenta_nombre, cuenta_proveedor_codigo, cuenta_proveedor_nombre, tipo_categoria, activo)
            VALUES (?, ?, ?, ?, ?, ?, 1)
        """, (
            categoria,
            cuenta_codigo,
            cuenta_nombre,
            cuenta_proveedor_codigo,
            cuenta_proveedor_nombre,
            tipo_categoria
        ))

    despues = contar("categorias_compra")
    return despues - antes


def cargar_conceptos_fiscales_compra_base():
    antes = contar("conceptos_fiscales_compra")

    for concepto, cuenta_codigo, cuenta_nombre, tratamiento in CONCEPTOS_FISCALES_COMPRA_BASE:
        ejecutar_query("""
            INSERT OR IGNORE INTO conceptos_fiscales_compra
            (concepto, cuenta_codigo, cuenta_nombre, tratamiento, activo)
            VALUES (?, ?, ?, ?, 1)
        """, (concepto, cuenta_codigo, cuenta_nombre, tratamiento))

    despues = contar("conceptos_fiscales_compra")
    return despues - antes


def inicializar_datos_base():
    resultado = {}

    resultado["tipos_insertados"] = cargar_tipos_comprobantes_base()
    resultado["plan_insertado"] = cargar_plan_cuentas_base()
    resultado["categorias_insertadas"] = cargar_categorias_compra_base()
    resultado["conceptos_insertados"] = cargar_conceptos_fiscales_compra_base()
    resultado["estado_final"] = obtener_estado_datos_base()

    return resultado