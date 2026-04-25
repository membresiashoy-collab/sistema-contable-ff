from database import ejecutar_query


# ======================================================
# TIPOS DE COMPROBANTES ARCA / AFIP
# ======================================================
# Fuente base:
# AFIP / ARCA - Libro IVA Digital - Tablas del Sistema
#
# Criterio contable:
# - Notas de Crédito: signo -1
# - Facturas, Notas de Débito, Recibos, Liquidaciones, Tiques y otros: signo 1
#
# El código se guarda sin ceros a la izquierda para coincidir con los CSV
# del Portal IVA / Mis Comprobantes, que suelen venir como "1", "6", "81", etc.
# ======================================================

TIPOS_COMPROBANTES_ARCA = [
    ("1", "FACTURAS A", 1),
    ("2", "NOTAS DE DEBITO A", 1),
    ("3", "NOTAS DE CREDITO A", -1),
    ("4", "RECIBOS A", 1),
    ("5", "NOTAS DE VENTA AL CONTADO A", 1),

    ("6", "FACTURAS B", 1),
    ("7", "NOTAS DE DEBITO B", 1),
    ("8", "NOTAS DE CREDITO B", -1),
    ("9", "RECIBOS B", 1),
    ("10", "NOTAS DE VENTA AL CONTADO B", 1),

    ("11", "FACTURAS C", 1),
    ("12", "NOTAS DE DEBITO C", 1),
    ("13", "NOTAS DE CREDITO C", -1),
    ("15", "RECIBOS C", 1),
    ("16", "NOTAS DE VENTA AL CONTADO C", 1),

    ("17", "LIQUIDACION DE SERVICIOS PUBLICOS CLASE A", 1),
    ("18", "LIQUIDACION DE SERVICIOS PUBLICOS CLASE B", 1),

    ("19", "FACTURAS DE EXPORTACION", 1),
    ("20", "NOTAS DE DEBITO POR OPERACIONES CON EL EXTERIOR", 1),
    ("21", "NOTAS DE CREDITO POR OPERACIONES CON EL EXTERIOR", -1),
    ("22", "FACTURAS - PERMISO EXPORTACION SIMPLIFICADO - DTO. 855/97", 1),

    ("23", "COMPROBANTES A DE COMPRA PRIMARIA PARA EL SECTOR PESQUERO MARITIMO", 1),
    ("24", "COMPROBANTES A DE CONSIGNACION PRIMARIA PARA EL SECTOR PESQUERO MARITIMO", 1),
    ("25", "COMPROBANTES B DE COMPRA PRIMARIA PARA EL SECTOR PESQUERO MARITIMO", 1),
    ("26", "COMPROBANTES B DE CONSIGNACION PRIMARIA PARA EL SECTOR PESQUERO MARITIMO", 1),

    ("27", "LIQUIDACION UNICA COMERCIAL IMPOSITIVA CLASE A", 1),
    ("28", "LIQUIDACION UNICA COMERCIAL IMPOSITIVA CLASE B", 1),
    ("29", "LIQUIDACION UNICA COMERCIAL IMPOSITIVA CLASE C", 1),

    ("30", "COMPROBANTES DE COMPRA DE BIENES USADOS", 1),
    ("32", "COMPROBANTES PARA RECICLAR MATERIALES", 1),
    ("33", "LIQUIDACION PRIMARIA DE GRANOS", 1),

    ("34", "COMPROBANTES A DEL APARTADO A INCISO F RG 1415", 1),
    ("35", "COMPROBANTES B DEL ANEXO I APARTADO A INCISO F RG 1415", 1),
    ("36", "COMPROBANTES C DEL ANEXO I APARTADO A INCISO F RG 1415", 1),

    ("37", "NOTAS DE DEBITO O DOCUMENTO EQUIVALENTE QUE CUMPLAN CON RG 1415", 1),
    ("38", "NOTAS DE CREDITO O DOCUMENTO EQUIVALENTE QUE CUMPLAN CON RG 1415", -1),

    ("39", "OTROS COMPROBANTES A QUE CUMPLEN CON RG 1415", 1),
    ("40", "OTROS COMPROBANTES B QUE CUMPLEN CON RG 1415", 1),
    ("41", "OTROS COMPROBANTES C QUE CUMPLEN CON RG 1415", 1),

    ("43", "NOTA DE CREDITO LIQUIDACION UNICA COMERCIAL IMPOSITIVA CLASE B", -1),
    ("44", "NOTA DE CREDITO LIQUIDACION UNICA COMERCIAL IMPOSITIVA CLASE C", -1),
    ("45", "NOTA DE DEBITO LIQUIDACION UNICA COMERCIAL IMPOSITIVA CLASE A", 1),
    ("46", "NOTA DE DEBITO LIQUIDACION UNICA COMERCIAL IMPOSITIVA CLASE B", 1),
    ("47", "NOTA DE DEBITO LIQUIDACION UNICA COMERCIAL IMPOSITIVA CLASE C", 1),
    ("48", "NOTA DE CREDITO LIQUIDACION UNICA COMERCIAL IMPOSITIVA CLASE A", -1),

    ("49", "COMPROBANTES DE COMPRA DE BIENES NO REGISTRABLES A CONSUMIDORES FINALES", 1),
    ("50", "RECIBO FACTURA A REGIMEN DE FACTURA DE CREDITO", 1),

    ("51", "FACTURAS M", 1),
    ("52", "NOTAS DE DEBITO M", 1),
    ("53", "NOTAS DE CREDITO M", -1),
    ("54", "RECIBOS M", 1),
    ("55", "NOTAS DE VENTA AL CONTADO M", 1),
    ("56", "COMPROBANTES M DEL ANEXO I APARTADO A INCISO F RG 1415", 1),
    ("57", "OTROS COMPROBANTES M QUE CUMPLAN CON RG 1415", 1),
    ("58", "CUENTAS DE VENTA Y LIQUIDO PRODUCTO M", 1),
    ("59", "LIQUIDACIONES M", 1),

    ("60", "CUENTAS DE VENTA Y LIQUIDO PRODUCTO A", 1),
    ("61", "CUENTAS DE VENTA Y LIQUIDO PRODUCTO B", 1),
    ("63", "LIQUIDACIONES A", 1),
    ("64", "LIQUIDACIONES B", 1),
    ("66", "DESPACHO DE IMPORTACION", 1),
    ("68", "LIQUIDACION C", 1),
    ("70", "RECIBOS FACTURA DE CREDITO", 1),

    ("81", "TIQUE FACTURA A CONTROLADORES FISCALES", 1),
    ("82", "TIQUE FACTURA B", 1),
    ("83", "TIQUE", 1),

    ("90", "NOTA DE CREDITO OTROS COMPROBANTES QUE NO CUMPLEN CON RG 1415", -1),
    ("99", "OTROS COMPROBANTES QUE NO CUMPLEN CON RG 1415", 1),

    ("109", "TIQUE C", 1),
    ("110", "TIQUE NOTA DE CREDITO", -1),
    ("111", "TIQUE FACTURA C", 1),
    ("112", "TIQUE NOTA DE CREDITO A", -1),
    ("113", "TIQUE NOTA DE CREDITO B", -1),
    ("114", "TIQUE NOTA DE CREDITO C", -1),
    ("115", "TIQUE NOTA DE DEBITO A", 1),
    ("116", "TIQUE NOTA DE DEBITO B", 1),
    ("117", "TIQUE NOTA DE DEBITO C", 1),
    ("118", "TIQUE FACTURA M", 1),
    ("119", "TIQUE NOTA DE CREDITO M", -1),
    ("120", "TIQUE NOTA DE DEBITO M", 1),

    ("150", "LIQUIDACION DE COMPRA PRIMARIA PARA EL SECTOR TABACALERO A", 1),
    ("151", "LIQUIDACION DE COMPRA PRIMARIA PARA EL SECTOR TABACALERO B", 1),

    ("157", "CUENTA DE VENTA Y LIQUIDO PRODUCTO A - SECTOR AVICOLA", 1),
    ("158", "CUENTA DE VENTA Y LIQUIDO PRODUCTO B - SECTOR AVICOLA", 1),
    ("159", "LIQUIDACION DE COMPRA A - SECTOR AVICOLA", 1),
    ("160", "LIQUIDACION DE COMPRA B - SECTOR AVICOLA", 1),
    ("161", "LIQUIDACION DE COMPRA DIRECTA A - SECTOR AVICOLA", 1),
    ("162", "LIQUIDACION DE COMPRA DIRECTA B - SECTOR AVICOLA", 1),
    ("163", "LIQUIDACION DE COMPRA DIRECTA C - SECTOR AVICOLA", 1),
    ("164", "LIQUIDACION DE VENTA DIRECTA A - SECTOR AVICOLA", 1),
    ("165", "LIQUIDACION DE VENTA DIRECTA B - SECTOR AVICOLA", 1),
    ("166", "LIQUIDACION DE CONTRATACION DE CRIANZA POLLOS PARRILLEROS A", 1),
    ("167", "LIQUIDACION DE CONTRATACION DE CRIANZA POLLOS PARRILLEROS B", 1),
    ("168", "LIQUIDACION DE CONTRATACION DE CRIANZA POLLOS PARRILLEROS C", 1),
    ("169", "LIQUIDACION DE CRIANZA POLLOS PARRILLEROS A", 1),
    ("170", "LIQUIDACION DE CRIANZA POLLOS PARRILLEROS B", 1),

    ("171", "LIQUIDACION DE COMPRA DE CAÑA DE AZUCAR A", 1),
    ("172", "LIQUIDACION DE COMPRA DE CAÑA DE AZUCAR B", 1),

    ("180", "CUENTA DE VENTA Y LIQUIDO PRODUCTO A - SECTOR PECUARIO", 1),
    ("182", "CUENTA DE VENTA Y LIQUIDO PRODUCTO B - SECTOR PECUARIO", 1),
    ("183", "LIQUIDACION DE COMPRA A - SECTOR PECUARIO", 1),
    ("185", "LIQUIDACION DE COMPRA B - SECTOR PECUARIO", 1),
    ("186", "LIQUIDACION DE COMPRA DIRECTA A - SECTOR PECUARIO", 1),
    ("188", "LIQUIDACION DE COMPRA DIRECTA B - SECTOR PECUARIO", 1),
    ("189", "LIQUIDACION DE COMPRA DIRECTA C - SECTOR PECUARIO", 1),
    ("190", "LIQUIDACION DE VENTA DIRECTA A - SECTOR PECUARIO", 1),
    ("191", "LIQUIDACION DE VENTA DIRECTA B - SECTOR PECUARIO", 1),

    ("195", "FACTURA CLASE T", 1),
    ("196", "NOTA DE DEBITO CLASE T", 1),
    ("197", "NOTA DE CREDITO CLASE T", -1),

    ("201", "FACTURA DE CREDITO ELECTRONICA MIPYMES FCE A", 1),
    ("202", "NOTA DE DEBITO ELECTRONICA MIPYMES FCE A", 1),
    ("203", "NOTA DE CREDITO ELECTRONICA MIPYMES FCE A", -1),

    ("206", "FACTURA DE CREDITO ELECTRONICA MIPYMES FCE B", 1),
    ("207", "NOTA DE DEBITO ELECTRONICA MIPYMES FCE B", 1),
    ("208", "NOTA DE CREDITO ELECTRONICA MIPYMES FCE B", -1),

    ("211", "FACTURA DE CREDITO ELECTRONICA MIPYMES FCE C", 1),
    ("212", "NOTA DE DEBITO ELECTRONICA MIPYMES FCE C", 1),
    ("213", "NOTA DE CREDITO ELECTRONICA MIPYMES FCE C", -1),

    ("331", "LIQUIDACION SECUNDARIA DE GRANOS", 1),
    ("332", "CERTIFICACION ELECTRONICA GRANOS", 1),
]


def normalizar_codigo_comprobante(codigo):
    codigo = str(codigo).strip()

    if codigo == "":
        return ""

    try:
        codigo = str(int(float(codigo)))
    except Exception:
        codigo = codigo.lstrip("0")

    return codigo


def asegurar_tabla_tipos_comprobantes():
    ejecutar_query("""
        CREATE TABLE IF NOT EXISTS tipos_comprobantes (
            codigo TEXT PRIMARY KEY,
            descripcion TEXT,
            signo INTEGER
        )
    """)


def inicializar_tipos_comprobantes_arca():
    """
    Inserta o actualiza la tabla universal de tipos de comprobantes ARCA/AFIP.
    Es seguro ejecutarlo muchas veces.
    No borra datos.
    """

    asegurar_tabla_tipos_comprobantes()

    insertados = 0
    actualizados = 0

    for codigo, descripcion, signo in TIPOS_COMPROBANTES_ARCA:
        codigo = normalizar_codigo_comprobante(codigo)

        df = ejecutar_query("""
            SELECT codigo, descripcion, signo
            FROM tipos_comprobantes
            WHERE codigo = ?
        """, (codigo,), fetch=True)

        if df.empty:
            ejecutar_query("""
                INSERT INTO tipos_comprobantes
                (codigo, descripcion, signo)
                VALUES (?, ?, ?)
            """, (codigo, descripcion, signo))
            insertados += 1
        else:
            ejecutar_query("""
                UPDATE tipos_comprobantes
                SET descripcion = ?,
                    signo = ?
                WHERE codigo = ?
            """, (descripcion, signo, codigo))
            actualizados += 1

    estado = ejecutar_query("""
        SELECT COUNT(*) AS cantidad
        FROM tipos_comprobantes
    """, fetch=True)

    return {
        "insertados": insertados,
        "actualizados": actualizados,
        "total_tipos_comprobantes": int(estado.iloc[0]["cantidad"])
    }


def obtener_tipos_comprobantes_arca():
    asegurar_tabla_tipos_comprobantes()

    return ejecutar_query("""
        SELECT codigo, descripcion, signo
        FROM tipos_comprobantes
        ORDER BY CAST(codigo AS INTEGER)
    """, fetch=True)