import json
import unicodedata
from datetime import datetime

import pandas as pd

from database import (
    ejecutar_query,
    ejecutar_transaccion,
    proximo_asiento,
    archivo_ya_cargado,
    comprobante_ya_procesado,
    tipo_comprobante_existe,
    obtener_tipo_comprobante_config
)

from core.numeros import limpiar_numero
from core.textos import limpiar_texto
from core.fechas import formatear_fecha, obtener_anio_mes
from core.comprobantes import tipo_desde_descripcion

from services.iva_credito_fiscal_service import (
    asegurar_estructura_iva_credito_fiscal,
    calcular_credito_fiscal_compra
)


# ======================================================
# CONSTANTES DE CONTROL
# ======================================================

TOLERANCIA_CENTAVOS_TOTAL = 0.10
TOLERANCIA_MINIMA = 0.005


# ======================================================
# NORMALIZACIÓN
# ======================================================

def quitar_acentos(texto):
    texto = str(texto)
    texto = unicodedata.normalize("NFD", texto)
    texto = texto.encode("ascii", "ignore").decode("utf-8")
    return texto


def normalizar_nombre_columna(nombre):
    nombre = quitar_acentos(nombre)
    nombre = nombre.lower().strip()
    nombre = nombre.replace(".", "")
    nombre = nombre.replace("-", "_")
    nombre = nombre.replace("/", "_")
    nombre = nombre.replace("%", "")
    nombre = nombre.replace(",", "")
    nombre = nombre.replace(" ", "_")

    while "__" in nombre:
        nombre = nombre.replace("__", "_")

    return nombre


def normalizar_df(df):
    df = df.copy()
    df.columns = [normalizar_nombre_columna(c) for c in df.columns]
    return df


def valor(fila, columna, default=""):
    try:
        if columna in fila.index:
            return fila[columna]
        return default
    except Exception:
        return default


def numero(fila, columna):
    return limpiar_numero(valor(fila, columna, 0))


def normalizar_entero_texto(valor_original):
    texto = limpiar_texto(valor_original)

    if texto.lower() in ("nan", "none"):
        return ""

    texto = texto.strip()

    if texto.endswith(".0"):
        texto = texto[:-2]

    texto = texto.replace(" ", "")
    texto = texto.replace(",", "")
    texto = texto.replace(".", "")

    return texto


def normalizar_codigo_comprobante(valor_original):
    texto = normalizar_entero_texto(valor_original)

    if texto == "":
        return ""

    texto = texto.lstrip("0")

    if texto == "":
        return "0"

    return texto


def normalizar_punto_venta(valor_original):
    texto = normalizar_entero_texto(valor_original)

    if texto == "":
        return ""

    return texto.zfill(5)


def normalizar_numero_comprobante(valor_original):
    texto = normalizar_entero_texto(valor_original)

    if texto == "":
        return ""

    return texto.zfill(8)


def normalizar_cuit(valor_original):
    texto = normalizar_entero_texto(valor_original)
    texto = texto.replace("-", "")
    texto = texto.replace("/", "")
    return texto


# ======================================================
# ESTRUCTURA COMPRAS
# ======================================================

def asegurar_columnas_compras_v2():
    ejecutar_query("""
        CREATE TABLE IF NOT EXISTS compras_comprobantes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT,
            anio INTEGER,
            mes INTEGER,
            codigo TEXT,
            tipo TEXT,
            punto_venta TEXT,
            numero TEXT,
            proveedor TEXT,
            cuit TEXT,
            neto REAL,
            iva REAL,
            total REAL,
            archivo TEXT,
            fecha_carga TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    ejecutar_query("""
        CREATE TABLE IF NOT EXISTS advertencias_carga (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            modulo TEXT,
            archivo TEXT,
            fila INTEGER,
            motivo TEXT,
            contenido TEXT,
            fecha_carga TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    columnas = {
        "categoria_compra": "TEXT",
        "cuenta_principal_codigo": "TEXT",
        "cuenta_principal_nombre": "TEXT",
        "cuenta_proveedor_codigo": "TEXT",
        "cuenta_proveedor_nombre": "TEXT",
        "importe_no_gravado": "REAL DEFAULT 0",
        "importe_exento": "REAL DEFAULT 0",
        "iva_total": "REAL DEFAULT 0",
        "credito_fiscal_computable": "REAL DEFAULT 0",
        "metodo_credito_fiscal": "TEXT",
        "coeficiente_iva_aplicado": "REAL DEFAULT 1",
        "iva_computable_sistema": "REAL DEFAULT 0",
        "iva_no_computable_sistema": "REAL DEFAULT 0",
        "iva_computable_csv": "REAL DEFAULT 0",
        "diferencia_iva_csv_sistema": "REAL DEFAULT 0",
        "iva_no_computable": "REAL DEFAULT 0",
        "percepcion_iva": "REAL DEFAULT 0",
        "percepcion_iibb": "REAL DEFAULT 0",
        "percepcion_otros_imp_nac": "REAL DEFAULT 0",
        "impuestos_municipales": "REAL DEFAULT 0",
        "impuestos_internos": "REAL DEFAULT 0",
        "otros_tributos": "REAL DEFAULT 0",
        "moneda": "TEXT",
        "tipo_cambio": "REAL DEFAULT 1",
        "neto_iva_0": "REAL DEFAULT 0",
        "neto_iva_25": "REAL DEFAULT 0",
        "iva_25": "REAL DEFAULT 0",
        "neto_iva_5": "REAL DEFAULT 0",
        "iva_5": "REAL DEFAULT 0",
        "neto_iva_105": "REAL DEFAULT 0",
        "iva_105": "REAL DEFAULT 0",
        "neto_iva_21": "REAL DEFAULT 0",
        "iva_21": "REAL DEFAULT 0",
        "neto_iva_27": "REAL DEFAULT 0",
        "iva_27": "REAL DEFAULT 0",
        "origen_carga": "TEXT"
    }

    for columna, tipo in columnas.items():
        try:
            ejecutar_query(f"ALTER TABLE compras_comprobantes ADD COLUMN {columna} {tipo}")
        except Exception:
            pass


# ======================================================
# CONFIGURACIONES
# ======================================================

def obtener_categoria_compra(categoria):
    df = ejecutar_query("""
        SELECT 
            categoria,
            cuenta_codigo,
            cuenta_nombre,
            cuenta_proveedor_codigo,
            cuenta_proveedor_nombre,
            tipo_categoria
        FROM categorias_compra
        WHERE categoria = ?
          AND activo = 1
    """, (categoria,), fetch=True)

    if df.empty:
        return None

    fila = df.iloc[0]

    return {
        "categoria": str(fila["categoria"]),
        "cuenta_codigo": str(fila["cuenta_codigo"]),
        "cuenta_nombre": str(fila["cuenta_nombre"]),
        "cuenta_proveedor_codigo": str(fila["cuenta_proveedor_codigo"]),
        "cuenta_proveedor_nombre": str(fila["cuenta_proveedor_nombre"]),
        "tipo_categoria": str(fila["tipo_categoria"])
    }


def obtener_conceptos_fiscales():
    df = ejecutar_query("""
        SELECT concepto, cuenta_codigo, cuenta_nombre, tratamiento
        FROM conceptos_fiscales_compra
        WHERE activo = 1
    """, fetch=True)

    conceptos = {}

    for _, fila in df.iterrows():
        clave = str(fila["concepto"]).strip().upper()

        conceptos[clave] = {
            "concepto": clave,
            "cuenta_codigo": str(fila["cuenta_codigo"]).strip(),
            "cuenta_nombre": str(fila["cuenta_nombre"]).strip(),
            "tratamiento": str(fila["tratamiento"]).strip().upper()
        }

    return conceptos


def concepto_config(conceptos, clave):
    clave = str(clave).strip().upper()

    defaults = {
        "IVA_CREDITO_FISCAL": {
            "cuenta_codigo": "1122600000",
            "cuenta_nombre": "IVA CRÉDITO FISCAL",
            "tratamiento": "CREDITO_FISCAL"
        },
        "PERCEPCION_IVA": {
            "cuenta_codigo": "1122400000",
            "cuenta_nombre": "AFIP - RET. Y PER. IVA",
            "tratamiento": "PERCEPCION_COMPUTABLE"
        },
        "PERCEPCION_IIBB": {
            "cuenta_codigo": "1122300000",
            "cuenta_nombre": "DPR - RET. Y PER. IIBB",
            "tratamiento": "PERCEPCION_COMPUTABLE"
        },
        "PERCEPCION_GANANCIAS": {
            "cuenta_codigo": "1122500000",
            "cuenta_nombre": "AFIP - RET. GANANCIAS",
            "tratamiento": "PERCEPCION_COMPUTABLE"
        },
        "PERCEPCION_OTROS_IMP_NAC": {
            "cuenta_codigo": "1122500000",
            "cuenta_nombre": "AFIP - PERCEPCIONES OTROS IMPUESTOS NACIONALES",
            "tratamiento": "PERCEPCION_COMPUTABLE"
        },
        "PERCEPCION_MUNICIPAL": {
            "cuenta_codigo": "1123200000",
            "cuenta_nombre": "PERCEPCIONES IMPUESTOS MUNICIPALES A COMPUTAR",
            "tratamiento": "PERCEPCION_COMPUTABLE"
        },
        "IMPUESTOS_INTERNOS_NO_RECUPERABLES": {
            "cuenta_codigo": "5122100000",
            "cuenta_nombre": "IMPUESTOS INTERNOS NO RECUPERABLES",
            "tratamiento": "MAYOR_COSTO_GASTO"
        },
        "OTROS_TRIBUTOS_NO_RECUPERABLES": {
            "cuenta_codigo": "5122200000",
            "cuenta_nombre": "OTROS TRIBUTOS NO RECUPERABLES",
            "tratamiento": "MAYOR_COSTO_GASTO"
        },
        "IVA_NO_COMPUTABLE": {
            "cuenta_codigo": "5122400000",
            "cuenta_nombre": "IVA NO COMPUTABLE / MAYOR COSTO",
            "tratamiento": "MAYOR_COSTO_GASTO"
        },
        "NO_GRAVADO": {
            "cuenta_codigo": "CUENTA_PRINCIPAL",
            "cuenta_nombre": "CUENTA_PRINCIPAL",
            "tratamiento": "MAYOR_COSTO"
        },
        "EXENTO": {
            "cuenta_codigo": "CUENTA_PRINCIPAL",
            "cuenta_nombre": "CUENTA_PRINCIPAL",
            "tratamiento": "MAYOR_COSTO"
        }
    }

    return conceptos.get(clave, defaults.get(clave))


def usa_cuenta_separada(config):
    if config is None:
        return False

    cuenta = str(config.get("cuenta_codigo", "")).strip().upper()

    if cuenta == "" or cuenta == "CUENTA_PRINCIPAL":
        return False

    return True


# ======================================================
# REGLAS FISCALES
# ======================================================

def descripcion_config(config):
    try:
        return str(config["descripcion"])
    except Exception:
        return ""


def es_comprobante_sin_iva_discriminado(codigo, descripcion=""):
    codigo = normalizar_codigo_comprobante(codigo)

    codigos_sin_iva_discriminado = {
        "6", "7", "8",
        "11", "12", "13", "15", "16",
        "18",
        "19", "20", "21",
        "82", "83",
        "109", "111", "113", "114", "116", "117"
    }

    if codigo in codigos_sin_iva_discriminado:
        return True

    desc = quitar_acentos(descripcion).upper()

    patrones = [
        "FACTURA B",
        "NOTA DE DEBITO B",
        "NOTA DE CREDITO B",
        "FACTURA C",
        "NOTA DE DEBITO C",
        "NOTA DE CREDITO C",
        "FACTURA E",
        "NOTA DE DEBITO E",
        "NOTA DE CREDITO E",
        "TIQUE FACTURA B",
        "TIQUE FACTURA C",
        "TIQUE C"
    ]

    return any(p in desc for p in patrones)


def validar_total_compra(
    total,
    componentes,
    comprobante_sin_iva,
    tolerancia=TOLERANCIA_CENTAVOS_TOTAL
):
    total = round(float(total), 2)

    if comprobante_sin_iva:
        return {
            "aplica": False,
            "valido": True,
            "nivel": "NO_APLICA",
            "requiere_ajuste": False,
            "suma_componentes": 0,
            "diferencia": 0,
            "tolerancia": tolerancia
        }

    suma = round(sum(float(c) for c in componentes), 2)
    diferencia = round(total - suma, 2)
    abs_diferencia = abs(diferencia)

    if abs_diferencia < TOLERANCIA_MINIMA:
        nivel = "OK"
        valido = True
        requiere_ajuste = False
    elif abs_diferencia <= tolerancia:
        nivel = "AJUSTE_CENTAVOS"
        valido = True
        requiere_ajuste = True
    else:
        nivel = "ERROR"
        valido = False
        requiere_ajuste = False

    return {
        "aplica": True,
        "valido": valido,
        "nivel": nivel,
        "requiere_ajuste": requiere_ajuste,
        "suma_componentes": suma,
        "diferencia": diferencia,
        "tolerancia": tolerancia
    }


def validar_reglas_fiscales_compra(
    total,
    iva_total,
    credito_fiscal,
    comprobante_sin_iva,
    codigo,
    tipo,
    numero_full
):
    errores = []
    advertencias = []

    total = round(float(total), 2)
    iva_total = round(float(iva_total), 2)
    credito_fiscal = round(float(credito_fiscal), 2)

    if abs(total) <= TOLERANCIA_MINIMA:
        errores.append(
            f"El comprobante {codigo} {numero_full} tiene importe total cero."
        )

    if comprobante_sin_iva:
        advertencias.append(
            f"Comprobante {codigo} {numero_full} identificado como sin IVA discriminado. "
            "No se bloquea automáticamente; revisar si corresponde cómputo de crédito fiscal."
        )

        if abs(iva_total) > 0.05:
            advertencias.append(
                f"Comprobante {codigo} {numero_full} sin IVA discriminado, pero el CSV informa IVA total {iva_total}. "
                "Se procesa con advertencia para revisión."
            )

        if abs(credito_fiscal) > 0.05:
            advertencias.append(
                f"Comprobante {codigo} {numero_full} sin IVA discriminado, pero el CSV informa crédito fiscal computable {credito_fiscal}. "
                "Se procesa con advertencia para revisión."
            )

    if not comprobante_sin_iva and credito_fiscal - iva_total > 0.05:
        errores.append(
            f"El crédito fiscal computable supera al IVA total. IVA total: {iva_total}. Crédito fiscal: {credito_fiscal}."
        )

    iva_no_computable = round(iva_total - credito_fiscal, 2)

    if iva_no_computable > 0.05:
        advertencias.append(
            f"El comprobante {codigo} {numero_full} tiene IVA no computable según Portal IVA por {iva_no_computable}."
        )

    return errores, advertencias


# ======================================================
# OPERACIONES SQL
# ======================================================

def op_insert_libro_diario(asiento, fecha, cuenta, debe, haber, glosa, origen, archivo):
    return (
        """
        INSERT INTO libro_diario
        (id_asiento, fecha, cuenta, debe, haber, glosa, origen, archivo)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            asiento,
            fecha,
            cuenta,
            round(float(debe), 2),
            round(float(haber), 2),
            glosa,
            origen,
            archivo
        )
    )


def op_insert_comprobante_procesado(modulo, fecha, codigo, numero, proveedor_clave, total, archivo):
    return (
        """
        INSERT INTO comprobantes_procesados
        (modulo, fecha, codigo, numero, cliente_proveedor, total, archivo)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            modulo,
            fecha,
            codigo,
            numero,
            proveedor_clave,
            total,
            archivo
        )
    )


def op_insert_historial(modulo, archivo, registros):
    return (
        """
        INSERT INTO historial_cargas
        (modulo, nombre_archivo, registros)
        VALUES (?, ?, ?)
        """,
        (
            modulo,
            archivo,
            registros
        )
    )


def op_insert_error(modulo, archivo, fila, motivo, contenido):
    try:
        contenido_json = json.dumps(contenido, ensure_ascii=False, default=str)
    except Exception:
        contenido_json = str(contenido)

    return (
        """
        INSERT INTO errores_carga
        (modulo, archivo, fila, motivo, contenido)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            modulo,
            archivo,
            fila,
            motivo,
            contenido_json
        )
    )


def op_insert_advertencia(modulo, archivo, fila, motivo, contenido):
    try:
        contenido_json = json.dumps(contenido, ensure_ascii=False, default=str)
    except Exception:
        contenido_json = str(contenido)

    return (
        """
        INSERT INTO advertencias_carga
        (modulo, archivo, fila, motivo, contenido)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            modulo,
            archivo,
            fila,
            motivo,
            contenido_json
        )
    )


def op_insert_cta_cte_proveedor(fecha, proveedor, cuit, tipo, numero, debe, haber, saldo, origen, archivo):
    return (
        """
        INSERT INTO cuenta_corriente_proveedores
        (fecha, proveedor, cuit, tipo, numero, debe, haber, saldo, origen, archivo)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            fecha,
            proveedor,
            cuit,
            tipo,
            numero,
            debe,
            haber,
            saldo,
            origen,
            archivo
        )
    )


def op_insert_compra(datos):
    columnas = [
        "fecha",
        "anio",
        "mes",
        "codigo",
        "tipo",
        "punto_venta",
        "numero",
        "proveedor",
        "cuit",
        "neto",
        "iva",
        "total",
        "archivo",
        "categoria_compra",
        "cuenta_principal_codigo",
        "cuenta_principal_nombre",
        "cuenta_proveedor_codigo",
        "cuenta_proveedor_nombre",
        "importe_no_gravado",
        "importe_exento",
        "iva_total",
        "credito_fiscal_computable",
        "metodo_credito_fiscal",
        "coeficiente_iva_aplicado",
        "iva_computable_sistema",
        "iva_no_computable_sistema",
        "iva_computable_csv",
        "diferencia_iva_csv_sistema",
        "iva_no_computable",
        "percepcion_iva",
        "percepcion_iibb",
        "percepcion_otros_imp_nac",
        "impuestos_municipales",
        "impuestos_internos",
        "otros_tributos",
        "moneda",
        "tipo_cambio",
        "neto_iva_0",
        "neto_iva_25",
        "iva_25",
        "neto_iva_5",
        "iva_5",
        "neto_iva_105",
        "iva_105",
        "neto_iva_21",
        "iva_21",
        "neto_iva_27",
        "iva_27",
        "origen_carga"
    ]

    placeholders = ", ".join(["?"] * len(columnas))
    columnas_sql = ", ".join(columnas)

    return (
        f"""
        INSERT INTO compras_comprobantes
        ({columnas_sql})
        VALUES ({placeholders})
        """,
        tuple(datos.get(columna, 0) for columna in columnas)
    )


# ======================================================
# ASIENTOS
# ======================================================

def agregar_movimiento(operaciones, asiento, fecha, cuenta, importe_signed, glosa, archivo):
    importe_signed = round(float(importe_signed), 2)

    if abs(importe_signed) < TOLERANCIA_MINIMA:
        return

    debe = importe_signed if importe_signed > 0 else 0
    haber = abs(importe_signed) if importe_signed < 0 else 0

    operaciones.append(
        op_insert_libro_diario(
            asiento,
            fecha,
            cuenta,
            debe,
            haber,
            glosa,
            "COMPRAS",
            archivo
        )
    )


def agregar_concepto_fiscal(lista_componentes, conceptos, clave, importe):
    importe = round(float(importe), 2)

    if importe <= 0:
        return 0

    config = concepto_config(conceptos, clave)

    if usa_cuenta_separada(config):
        lista_componentes.append({
            "clave": clave,
            "cuenta_codigo": config["cuenta_codigo"],
            "cuenta_nombre": config["cuenta_nombre"],
            "importe": importe
        })
        return importe

    return 0


# ======================================================
# DETECCIÓN CSV ARCA
# ======================================================

def es_csv_arca_compras(df):
    columnas = set(normalizar_df(df).columns)

    requeridas = {
        "fecha_de_emision",
        "tipo_de_comprobante",
        "punto_de_venta",
        "numero_de_comprobante",
        "nro_doc_vendedor",
        "denominacion_vendedor",
        "importe_total"
    }

    return requeridas.issubset(columnas)


# ======================================================
# PROCESAMIENTO PRINCIPAL
# ======================================================

def procesar_csv_compras_arca(nombre_archivo, df_original, categoria_compra):
    asegurar_columnas_compras_v2()
    asegurar_estructura_iva_credito_fiscal()

    resultado = {
        "procesados": 0,
        "errores": 0,
        "advertencias": 0,
        "facturas": 0,
        "notas_credito": 0,
        "notas_debito": 0,
        "duplicados": 0,
        "errores_matematicos": 0,
        "errores_codigo": 0,
        "ajustes_centavos": 0,
        "iva_no_computable": 0,
        "diferencias_iva_csv_sistema": 0,
        "comprobantes_sin_iva_discriminado": 0
    }

    operaciones = []
    claves_archivo = set()

    archivo_repetido = archivo_ya_cargado(nombre_archivo)

    if archivo_repetido:
        resultado["advertencias"] += 1
        operaciones.append(
            op_insert_advertencia(
                "COMPRAS",
                nombre_archivo,
                0,
                (
                    "El archivo ya tenía una carga anterior. "
                    "No se bloquea el procesamiento: se procesarán solo comprobantes nuevos "
                    "y se omitirán los comprobantes ya existentes."
                ),
                {}
            )
        )

    categoria = obtener_categoria_compra(categoria_compra)

    if categoria is None:
        resultado["errores"] += 1
        operaciones.append(
            op_insert_error(
                "COMPRAS",
                nombre_archivo,
                0,
                f"No existe la categoría de compra seleccionada: {categoria_compra}",
                {}
            )
        )
        ejecutar_transaccion(operaciones)
        return resultado

    conceptos = obtener_conceptos_fiscales()

    df = normalizar_df(df_original)

    if not es_csv_arca_compras(df_original):
        resultado["errores"] += 1
        operaciones.append(
            op_insert_error(
                "COMPRAS",
                nombre_archivo,
                0,
                "El archivo no parece ser un CSV ARCA/AFIP Compras.",
                {"columnas": list(df_original.columns)}
            )
        )
        ejecutar_transaccion(operaciones)
        return resultado

    asiento = proximo_asiento()

    for numero_fila, (_, fila) in enumerate(df.iterrows(), start=2):

        try:
            fecha_original = valor(fila, "fecha_de_emision")
            fecha = formatear_fecha(fecha_original)
            anio, mes = obtener_anio_mes(fecha_original)

            codigo = normalizar_codigo_comprobante(valor(fila, "tipo_de_comprobante"))
            punto_venta = normalizar_punto_venta(valor(fila, "punto_de_venta"))
            numero_comp = normalizar_numero_comprobante(valor(fila, "numero_de_comprobante"))
            numero_full = f"{punto_venta}-{numero_comp}"

            cuit = normalizar_cuit(valor(fila, "nro_doc_vendedor"))
            proveedor = limpiar_texto(valor(fila, "denominacion_vendedor"))

            if proveedor == "":
                proveedor = "PROVEEDOR SIN NOMBRE"

            proveedor_clave = cuit if cuit else proveedor

            total = numero(fila, "importe_total")
            moneda = limpiar_texto(valor(fila, "moneda_original"))
            tipo_cambio = numero(fila, "tipo_de_cambio") or 1

            importe_no_gravado = numero(fila, "importe_no_gravado")
            importe_exento = numero(fila, "importe_exento")

            credito_fiscal_csv = numero(fila, "credito_fiscal_computable")
            iva_total = numero(fila, "total_iva")

            credito_fiscal = credito_fiscal_csv
            iva_no_computable = max(round(iva_total - credito_fiscal_csv, 2), 0)
            calculo_iva = None

            percepcion_otros_imp_nac = numero(fila, "importe_de_per_o_pagos_a_cta_de_otros_imp_nac")
            percepcion_iibb = numero(fila, "importe_de_percepciones_de_ingresos_brutos")
            impuestos_municipales = numero(fila, "importe_de_impuestos_municipales")
            percepcion_iva = numero(fila, "importe_de_percepciones_o_pagos_a_cuenta_de_iva")
            impuestos_internos = numero(fila, "importe_de_impuestos_internos")
            otros_tributos = numero(fila, "importe_otros_tributos")

            neto_iva_0 = numero(fila, "neto_gravado_iva_0")
            neto_iva_25 = numero(fila, "neto_gravado_iva_25")
            iva_25 = numero(fila, "importe_iva_25")
            neto_iva_5 = numero(fila, "neto_gravado_iva_5")
            iva_5 = numero(fila, "importe_iva_5")
            neto_iva_105 = numero(fila, "neto_gravado_iva_105")
            iva_105 = numero(fila, "importe_iva_105")
            neto_iva_21 = numero(fila, "neto_gravado_iva_21")
            iva_21 = numero(fila, "importe_iva_21")
            neto_iva_27 = numero(fila, "neto_gravado_iva_27")
            iva_27 = numero(fila, "importe_iva_27")

            total_neto_gravado = numero(fila, "total_neto_gravado")

            contenido_fila = fila.to_dict()
            contenido_fila["_normalizado"] = {
                "fecha": fecha,
                "anio": anio,
                "mes": mes,
                "codigo": codigo,
                "punto_venta": punto_venta,
                "numero": numero_full,
                "cuit": cuit,
                "proveedor": proveedor,
                "total": total,
                "categoria_compra": categoria["categoria"]
            }

            if codigo == "":
                resultado["errores"] += 1
                resultado["errores_codigo"] += 1

                operaciones.append(
                    op_insert_error(
                        "COMPRAS",
                        nombre_archivo,
                        numero_fila,
                        "El comprobante no tiene código de tipo de comprobante.",
                        contenido_fila
                    )
                )
                continue

            if punto_venta == "" or numero_comp == "":
                resultado["errores"] += 1

                operaciones.append(
                    op_insert_error(
                        "COMPRAS",
                        nombre_archivo,
                        numero_fila,
                        "El comprobante no tiene punto de venta o número válido.",
                        contenido_fila
                    )
                )
                continue

            if not tipo_comprobante_existe(codigo):
                resultado["errores"] += 1
                resultado["errores_codigo"] += 1

                operaciones.append(
                    op_insert_error(
                        "COMPRAS",
                        nombre_archivo,
                        numero_fila,
                        (
                            f"Código de comprobante inexistente: {codigo}. "
                            "Revisar tabla universal de tipos de comprobantes ARCA/AFIP."
                        ),
                        contenido_fila
                    )
                )
                continue

            config = obtener_tipo_comprobante_config(codigo)

            if config is None:
                resultado["errores"] += 1
                resultado["errores_codigo"] += 1

                operaciones.append(
                    op_insert_error(
                        "COMPRAS",
                        nombre_archivo,
                        numero_fila,
                        f"No se pudo interpretar el comprobante: {codigo}",
                        contenido_fila
                    )
                )
                continue

            descripcion = descripcion_config(config)
            tipo = tipo_desde_descripcion(descripcion)
            signo = int(config["signo"])

            comprobante_sin_iva = es_comprobante_sin_iva_discriminado(codigo, descripcion)

            if comprobante_sin_iva:
                resultado["comprobantes_sin_iva_discriminado"] += 1

            clave = ("COMPRAS", codigo, numero_full, proveedor_clave)

            if clave in claves_archivo or comprobante_ya_procesado("COMPRAS", codigo, numero_full, proveedor_clave):
                resultado["duplicados"] += 1
                resultado["advertencias"] += 1

                operaciones.append(
                    op_insert_advertencia(
                        "COMPRAS",
                        nombre_archivo,
                        numero_fila,
                        (
                            "Comprobante omitido por duplicado. "
                            f"Código {codigo}, número {numero_full}, proveedor/CUIT {proveedor_clave}. "
                            "Ya existe en el sistema o está repetido dentro del mismo archivo."
                        ),
                        contenido_fila
                    )
                )
                continue

            claves_archivo.add(clave)

            errores_fiscales, advertencias_fiscales = validar_reglas_fiscales_compra(
                total=total,
                iva_total=iva_total,
                credito_fiscal=credito_fiscal_csv,
                comprobante_sin_iva=comprobante_sin_iva,
                codigo=codigo,
                tipo=tipo,
                numero_full=numero_full
            )

            if errores_fiscales:
                resultado["errores"] += len(errores_fiscales)

                for motivo in errores_fiscales:
                    operaciones.append(
                        op_insert_error(
                            "COMPRAS",
                            nombre_archivo,
                            numero_fila,
                            motivo,
                            contenido_fila
                        )
                    )

                continue

            if advertencias_fiscales:
                resultado["advertencias"] += len(advertencias_fiscales)

                for motivo in advertencias_fiscales:
                    operaciones.append(
                        op_insert_advertencia(
                            "COMPRAS",
                            nombre_archivo,
                            numero_fila,
                            motivo,
                            contenido_fila
                        )
                    )

            calculo_iva = calcular_credito_fiscal_compra(
                anio=anio,
                mes=mes,
                categoria_compra=categoria["categoria"],
                iva_total=iva_total,
                credito_fiscal_csv=credito_fiscal_csv,
                comprobante_sin_iva=comprobante_sin_iva
            )

            credito_fiscal = calculo_iva["iva_computable_sistema"]
            iva_no_computable = calculo_iva["iva_no_computable_sistema"]

            if iva_no_computable > 0.05:
                resultado["iva_no_computable"] += 1

            if abs(calculo_iva["diferencia_iva_csv_sistema"]) > 0.05:
                resultado["diferencias_iva_csv_sistema"] += 1

            for motivo in calculo_iva["advertencias"]:
                resultado["advertencias"] += 1

                operaciones.append(
                    op_insert_advertencia(
                        "COMPRAS",
                        nombre_archivo,
                        numero_fila,
                        motivo,
                        contenido_fila
                    )
                )

            componentes_para_validar = [
                total_neto_gravado,
                importe_no_gravado,
                importe_exento,
                iva_total,
                percepcion_otros_imp_nac,
                percepcion_iibb,
                impuestos_municipales,
                percepcion_iva,
                impuestos_internos,
                otros_tributos
            ]

            validacion_total = validar_total_compra(
                total=total,
                componentes=componentes_para_validar,
                comprobante_sin_iva=comprobante_sin_iva
            )

            if validacion_total["aplica"] and not validacion_total["valido"]:
                resultado["errores"] += 1
                resultado["errores_matematicos"] += 1

                operaciones.append(
                    op_insert_error(
                        "COMPRAS",
                        nombre_archivo,
                        numero_fila,
                        (
                            "El total del comprobante no coincide con la suma de sus componentes "
                            "y supera la tolerancia permitida. "
                            f"Total informado: {total}. "
                            f"Suma componentes: {validacion_total['suma_componentes']}. "
                            f"Diferencia: {validacion_total['diferencia']}. "
                            f"Tolerancia: {validacion_total['tolerancia']}."
                        ),
                        contenido_fila
                    )
                )
                continue

            if validacion_total["aplica"] and validacion_total["requiere_ajuste"]:
                resultado["ajustes_centavos"] += 1
                resultado["advertencias"] += 1

                operaciones.append(
                    op_insert_advertencia(
                        "COMPRAS",
                        nombre_archivo,
                        numero_fila,
                        (
                            "Diferencia menor tolerada entre total y componentes del Portal IVA. "
                            "El comprobante se procesa y el asiento se cuadra contra el total informado, "
                            "absorbiendo la diferencia en la cuenta principal. "
                            f"Total informado: {total}. "
                            f"Suma componentes: {validacion_total['suma_componentes']}. "
                            f"Diferencia: {validacion_total['diferencia']}. "
                            f"Tolerancia: {validacion_total['tolerancia']}."
                        ),
                        contenido_fila
                    )
                )

            componentes_separados = []

            agregar_concepto_fiscal(componentes_separados, conceptos, "IVA_CREDITO_FISCAL", credito_fiscal)
            agregar_concepto_fiscal(componentes_separados, conceptos, "IVA_NO_COMPUTABLE", iva_no_computable)
            agregar_concepto_fiscal(componentes_separados, conceptos, "PERCEPCION_IVA", percepcion_iva)
            agregar_concepto_fiscal(componentes_separados, conceptos, "PERCEPCION_IIBB", percepcion_iibb)
            agregar_concepto_fiscal(componentes_separados, conceptos, "PERCEPCION_OTROS_IMP_NAC", percepcion_otros_imp_nac)
            agregar_concepto_fiscal(componentes_separados, conceptos, "PERCEPCION_MUNICIPAL", impuestos_municipales)
            agregar_concepto_fiscal(componentes_separados, conceptos, "IMPUESTOS_INTERNOS_NO_RECUPERABLES", impuestos_internos)
            agregar_concepto_fiscal(componentes_separados, conceptos, "OTROS_TRIBUTOS_NO_RECUPERABLES", otros_tributos)

            suma_componentes_separados = round(sum(c["importe"] for c in componentes_separados), 2)

            cuenta_principal_importe = round(total - suma_componentes_separados, 2)

            if cuenta_principal_importe < -0.01:
                resultado["errores"] += 1
                resultado["errores_matematicos"] += 1

                operaciones.append(
                    op_insert_error(
                        "COMPRAS",
                        nombre_archivo,
                        numero_fila,
                        (
                            "La suma de componentes fiscales supera el total del comprobante. "
                            f"Total: {total}, componentes separados: {suma_componentes_separados}"
                        ),
                        contenido_fila
                    )
                )
                continue

            total_s = round(total * signo, 2)
            cuenta_principal_s = round(cuenta_principal_importe * signo, 2)

            glosa = f"{tipo} {numero_full} - {proveedor}"

            agregar_movimiento(
                operaciones,
                asiento,
                fecha,
                categoria["cuenta_nombre"],
                cuenta_principal_s,
                glosa,
                nombre_archivo
            )

            for comp in componentes_separados:
                agregar_movimiento(
                    operaciones,
                    asiento,
                    fecha,
                    comp["cuenta_nombre"],
                    round(comp["importe"] * signo, 2),
                    glosa,
                    nombre_archivo
                )

            agregar_movimiento(
                operaciones,
                asiento,
                fecha,
                categoria["cuenta_proveedor_nombre"],
                -total_s,
                glosa,
                nombre_archivo
            )

            operaciones.append(
                op_insert_comprobante_procesado(
                    "COMPRAS",
                    fecha,
                    codigo,
                    numero_full,
                    proveedor_clave,
                    total_s,
                    nombre_archivo
                )
            )

            datos_compra = {
                "fecha": fecha,
                "anio": anio,
                "mes": mes,
                "codigo": codigo,
                "tipo": tipo,
                "punto_venta": punto_venta,
                "numero": numero_full,
                "proveedor": proveedor,
                "cuit": cuit,
                "neto": round(total_neto_gravado * signo, 2),
                "iva": round(credito_fiscal * signo, 2),
                "total": total_s,
                "archivo": nombre_archivo,
                "categoria_compra": categoria["categoria"],
                "cuenta_principal_codigo": categoria["cuenta_codigo"],
                "cuenta_principal_nombre": categoria["cuenta_nombre"],
                "cuenta_proveedor_codigo": categoria["cuenta_proveedor_codigo"],
                "cuenta_proveedor_nombre": categoria["cuenta_proveedor_nombre"],
                "importe_no_gravado": round(importe_no_gravado * signo, 2),
                "importe_exento": round(importe_exento * signo, 2),
                "iva_total": round(iva_total * signo, 2),
                "credito_fiscal_computable": round(credito_fiscal * signo, 2),
                "metodo_credito_fiscal": calculo_iva["metodo_credito_fiscal"],
                "coeficiente_iva_aplicado": calculo_iva["coeficiente_iva_aplicado"],
                "iva_computable_sistema": round(calculo_iva["iva_computable_sistema"] * signo, 2),
                "iva_no_computable_sistema": round(calculo_iva["iva_no_computable_sistema"] * signo, 2),
                "iva_computable_csv": round(calculo_iva["iva_computable_csv"] * signo, 2),
                "diferencia_iva_csv_sistema": round(calculo_iva["diferencia_iva_csv_sistema"] * signo, 2),
                "iva_no_computable": round(iva_no_computable * signo, 2),
                "percepcion_iva": round(percepcion_iva * signo, 2),
                "percepcion_iibb": round(percepcion_iibb * signo, 2),
                "percepcion_otros_imp_nac": round(percepcion_otros_imp_nac * signo, 2),
                "impuestos_municipales": round(impuestos_municipales * signo, 2),
                "impuestos_internos": round(impuestos_internos * signo, 2),
                "otros_tributos": round(otros_tributos * signo, 2),
                "moneda": moneda,
                "tipo_cambio": tipo_cambio,
                "neto_iva_0": round(neto_iva_0 * signo, 2),
                "neto_iva_25": round(neto_iva_25 * signo, 2),
                "iva_25": round(iva_25 * signo, 2),
                "neto_iva_5": round(neto_iva_5 * signo, 2),
                "iva_5": round(iva_5 * signo, 2),
                "neto_iva_105": round(neto_iva_105 * signo, 2),
                "iva_105": round(iva_105 * signo, 2),
                "neto_iva_21": round(neto_iva_21 * signo, 2),
                "iva_21": round(iva_21 * signo, 2),
                "neto_iva_27": round(neto_iva_27 * signo, 2),
                "iva_27": round(iva_27 * signo, 2),
                "origen_carga": "CSV_ARCA"
            }

            operaciones.append(op_insert_compra(datos_compra))

            operaciones.append(
                op_insert_cta_cte_proveedor(
                    fecha,
                    proveedor,
                    cuit,
                    tipo,
                    numero_full,
                    abs(total_s) if total_s < 0 else 0,
                    total_s if total_s > 0 else 0,
                    0,
                    "COMPRAS",
                    nombre_archivo
                )
            )

            resultado["procesados"] += 1

            if tipo == "FACTURA":
                resultado["facturas"] += 1
            elif tipo == "NC":
                resultado["notas_credito"] += 1
            elif tipo == "ND":
                resultado["notas_debito"] += 1

            asiento += 1

        except Exception as e:
            resultado["errores"] += 1

            operaciones.append(
                op_insert_error(
                    "COMPRAS",
                    nombre_archivo,
                    numero_fila,
                    f"Error inesperado: {str(e)}",
                    fila.to_dict()
                )
            )

    if resultado["procesados"] > 0:
        operaciones.append(
            op_insert_historial(
                "COMPRAS",
                nombre_archivo,
                resultado["procesados"]
            )
        )

    if operaciones:
        ejecutar_transaccion(operaciones)

    return resultado


# ======================================================
# CARGA MANUAL
# ======================================================

def procesar_compra_manual(datos):
    nombre_archivo = (
        f"COMPRA_MANUAL_"
        f"{datos['codigo']}_{datos['punto_venta']}_{datos['numero_comprobante']}_"
        f"{datetime.now().strftime('%Y%m%d%H%M%S')}"
    )

    iva_total_manual = datos.get("iva_total", datos.get("iva_21", 0))
    credito_manual = datos.get("credito_fiscal_computable", iva_total_manual)

    fila = {
        "Fecha de Emisión": datos["fecha"],
        "Tipo de Comprobante": datos["codigo"],
        "Punto de Venta": datos["punto_venta"],
        "Número de Comprobante": datos["numero_comprobante"],
        "Tipo Doc. Vendedor": "80",
        "Nro. Doc. Vendedor": datos["cuit"],
        "Denominación Vendedor": datos["proveedor"],
        "Importe Total": datos["total"],
        "Moneda Original": datos.get("moneda", "PES"),
        "Tipo de Cambio": datos.get("tipo_cambio", 1),
        "Importe No Gravado": datos.get("importe_no_gravado", 0),
        "Importe Exento": datos.get("importe_exento", 0),
        "Crédito Fiscal Computable": credito_manual,
        "Importe de Per. o Pagos a Cta. de Otros Imp. Nac.": datos.get("percepcion_otros_imp_nac", 0),
        "Importe de Percepciones de Ingresos Brutos": datos.get("percepcion_iibb", 0),
        "Importe de Impuestos Municipales": datos.get("impuestos_municipales", 0),
        "Importe de Percepciones o Pagos a Cuenta de IVA": datos.get("percepcion_iva", 0),
        "Importe de Impuestos Internos": datos.get("impuestos_internos", 0),
        "Importe Otros Tributos": datos.get("otros_tributos", 0),
        "Neto Gravado IVA 0%": datos.get("neto_iva_0", 0),
        "Neto Gravado IVA 2,5%": datos.get("neto_iva_25", 0),
        "Importe IVA 2,5%": datos.get("iva_25", 0),
        "Neto Gravado IVA 5%": datos.get("neto_iva_5", 0),
        "Importe IVA 5%": datos.get("iva_5", 0),
        "Neto Gravado IVA 10,5%": datos.get("neto_iva_105", 0),
        "Importe IVA 10,5%": datos.get("iva_105", 0),
        "Neto Gravado IVA 21%": datos.get("neto_iva_21", datos.get("total_neto_gravado", 0)),
        "Importe IVA 21%": datos.get("iva_21", iva_total_manual),
        "Neto Gravado IVA 27%": datos.get("neto_iva_27", 0),
        "Importe IVA 27%": datos.get("iva_27", 0),
        "Total Neto Gravado": datos.get("total_neto_gravado", 0),
        "Total IVA": iva_total_manual
    }

    df = pd.DataFrame([fila])

    return procesar_csv_compras_arca(
        nombre_archivo,
        df,
        datos["categoria_compra"]
    )